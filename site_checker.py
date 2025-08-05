import asyncio
import json
import logging
import os
import re
import socket
import ssl
import time
from urllib.parse import urlparse

import requests
from telegram import User
from telegram.helpers import escape_markdown

# --- CẤU HÌNH & HẰNG SỐ (SAO CHÉP TỪ FILE CHÍNH ĐỂ HOẠT ĐỘNG ĐỘC LẬP) ---
# Đây là những cấu hình cần thiết để các lệnh /site, /sitem hoạt động
ADMIN_ID = 5127429005
ADMIN_USERNAME = "@startsuttdow"
USER_FILE = "authorized_users.txt"
BOT_STATUS_FILE = "bot_status.json"
PREFS_FILE = "user_prefs.json"
MESSAGES_VI = {
    "bot_off": "🔴 **THÔNG BÁO BẢO TRÌ** 🔴\n\nBot hiện đang tạm thời ngoại tuyến để bảo trì. Các lệnh check sẽ không hoạt động cho đến khi có thông báo mới. Cảm ơn sự kiên nhẫn của bạn!",
}
MESSAGES_EN = {
    "bot_off": "🔴 **MAINTENANCE NOTICE** 🔴\n\nBot is temporarily offline for maintenance. Checking commands will be disabled until further notice. Thank you for your patience!",
}

# Cấu hình logging riêng cho module này
logger = logging.getLogger(__name__)

# --- CÁC HÀM TIỆN ÍCH (SAO CHÉP TỪ FILE CHÍNH) ---
def load_json_file(filename, default_data={}):
    if not os.path.exists(filename):
        return default_data
    try:
        with open(filename, "r", encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return default_data

def load_users():
    try:
        with open(USER_FILE, "r") as f:
            return {int(line.strip()) for line in f if line.strip().isdigit()}
    except FileNotFoundError:
        return set()

def is_bot_on():
    status = load_json_file(BOT_STATUS_FILE, default_data={'is_on': True})
    return status.get('is_on', True)

def get_user_lang(user_id):
    prefs = load_json_file(PREFS_FILE)
    return prefs.get(str(user_id), 'en') # Mặc định là tiếng Anh

# --- CẤU HÌNH RIÊNG CHO SITE CHECKER ---
# Danh sách Payment Gateways
GATEWAYS_LIST = [
    "PayPal", "Stripe", "Braintree", "Square", "Cybersource", "lemon-squeezy",
    "Authorize.Net", "2Checkout", "Adyen", "Worldpay", "SagePay",
    "Checkout.com", "Bolt", "Eway", "PayFlow", "Payeezy",
    "Paddle", "Mollie", "Viva Wallet", "Rocketgateway", "Rocketgate",
    "Rocket", "Auth.net", "Authnet", "rocketgate.com", "Recurly",
    "Shopify", "WooCommerce", "BigCommerce", "Magento", "Magento Payments",
    "OpenCart", "PrestaShop", "3DCart", "Ecwid", "Shift4Shop",
    "Shopware", "VirtueMart", "CS-Cart", "X-Cart", "LemonStand",
    "AVS", "Convergepay", "PaySimple", "oceanpayments", "eProcessing",
    "hipay", "cybersourse", "payjunction", "usaepay", "creo",
    "SquareUp", "ebizcharge", "cpay", "Moneris", "cardknox",
    "matt sorra", "Chargify", "Paytrace", "hostedpayments", "securepay",
    "blackbaud", "LawPay", "clover", "cardconnect", "bluepay",
    "fluidpay", "Ebiz", "chasepaymentech", "Auruspay", "sagepayments",
    "paycomet", "geomerchant", "realexpayments", "Razorpay",
    "Apple Pay", "Google Pay", "Samsung Pay", "Venmo", "Cash App",
    "Revolut", "Zelle", "Alipay", "WeChat Pay", "PayPay", "Line Pay",
    "Skrill", "Neteller", "WebMoney", "Payoneer", "Paysafe",
    "Payeer", "GrabPay", "PayMaya", "MoMo", "TrueMoney",
    "Touch n Go", "GoPay", "Dana", "JKOPay", "EasyPaisa",
    "Paytm", "UPI", "PayU", "CCAvenue",
    "Mercado Pago", "PagSeguro", "Yandex.Checkout", "PayFort", "MyFatoorah",
    "Kushki", "DLocal", "RuPay", "BharatPe", "Midtrans", "MOLPay",
    "iPay88", "KakaoPay", "Toss Payments", "NaverPay", "OVO", "GCash",
    "Bizum", "Culqi", "Pagar.me", "Rapyd", "PayKun", "Instamojo",
    "PhonePe", "BharatQR", "Freecharge", "Mobikwik", "Atom", "BillDesk",
    "Citrus Pay", "RazorpayX", "Cashfree", "PayUbiz", "EBS",
    "Klarna", "Affirm", "Afterpay", "Zip", "Sezzle",
    "Splitit", "Perpay", "Quadpay", "Laybuy", "Openpay",
    "Atome", "Cashalo", "Hoolah", "Pine Labs", "ChargeAfter",
    "BitPay", "Coinbase Commerce", "CoinGate", "CoinPayments", "Crypto.com Pay",
    "BTCPay Server", "NOWPayments", "OpenNode", "Utrust", "MoonPay",
    "Binance Pay", "CoinsPaid", "BitGo", "Flexa", "Circle",
    "iDEAL", "Giropay", "Sofort", "Bancontact", "Przelewy24",
    "EPS", "Multibanco", "Trustly", "PPRO", "EcoPayz",
    "ACI Worldwide", "Bank of America Merchant Services",
    "JP Morgan Payment Services", "Wells Fargo Payment Solutions",
    "Deutsche Bank Payments", "Barclaycard", "American Express Payment Gateway",
    "Discover Network", "UnionPay", "JCB Payment Gateway",
    "Plaid", "Stripe Terminal", "Square Terminal", "Adyen Terminal",
    "Toast POS", "Lightspeed Payments", "Poynt", "PAX",
    "SumUp", "iZettle", "Tyro", "Vend", "ShopKeep", "Revel",
    "HiPay", "Dotpay", "PayBox", "PayStack", "Flutterwave",
    "Opayo", "MultiSafepay", "PayXpert", "Bambora", "RedSys",
    "NPCI", "JazzCash", "Blik", "PagBank", "VibePay", "Mode",
    "Primer", "TrueLayer", "GoCardless", "Modulr", "Currencycloud",
    "Volt", "Form3", "Banking Circle", "Mangopay", "Checkout Finland",
    "Vipps", "Swish", "MobilePay"
]
# Patterns để phát hiện CMS/Platform
CMS_PATTERNS = {
    'Shopify': r'cdn\.shopify\.com|shopify\.js',
    'BigCommerce': r'cdn\.bigcommerce\.com|bigcommerce\.com',
    'Wix': r'static\.parastorage\.com|wix\.com',
    'Squarespace': r'static1\.squarespace\.com|squarespace-cdn\.com',
    'WooCommerce': r'wp-content/plugins/woocommerce/',
    'Magento': r'static/version\d+/frontend/|magento/',
    'PrestaShop': r'prestashop\.js|prestashop',
    'OpenCart': r'catalog/view/theme|opencart',
    'WordPress': r'wp-content|wp-includes',
    'Joomla': r'media/jui|joomla\.js|media/system/js|joomla\.javascript',
    'Drupal': r'sites/all/modules|drupal\.js|sites/default/files|drupal\.settings\.js',
}
# Patterns để kiểm tra bảo mật
SECURITY_PATTERNS = {
    'GraphQL': r'graphql|__schema|query\s*{',
}

# --- CÁC HÀM CỐT LÕI CỦA SITE CHECKER ---
def normalize_url(url: str) -> str | None:
    """Chuẩn hóa URL, thêm scheme nếu thiếu."""
    if not re.match(r"^(?:f|ht)tps?://", url, re.IGNORECASE):
        url = "http://" + url
    parsed_url = urlparse(url)
    if not all([parsed_url.scheme, parsed_url.netloc]):
        return None
    return f"{parsed_url.scheme}://{parsed_url.netloc}"

def find_payment_gateways(response_text: str) -> list[str]:
    """Tìm các payment gateway trong nội dung response."""
    detected = [gateway for gateway in GATEWAYS_LIST if re.search(r'\b' + re.escape(gateway) + r'\b', response_text, re.IGNORECASE)]
    return list(set(detected)) or ["Unknown"]

def find_captcha_details(response_text: str) -> list[str]:
    """Tìm chi tiết về các loại CAPTCHA."""
    captcha_details = []
    if "recaptcha" in response_text.lower():
        if "recaptcha v1" in response_text.lower():
            captcha_details.append("reCAPTCHA v1")
        if "recaptcha v2" in response_text.lower():
            captcha_details.append("reCAPTCHA v2")
        if "recaptcha v3" in response_text.lower():
            captcha_details.append("reCAPTCHA v3")
        if "recaptcha enterprise" in response_text.lower():
            captcha_details.append("reCAPTCHA Enterprise")
    if "hcaptcha" in response_text.lower():
        captcha_details.append("hCaptcha")
    if "funcaptcha" in response_text.lower():
        captcha_details.append("FunCAPTCHA")
    if "arkoselabs" in response_text.lower():
        captcha_details.append("Arkose Labs")
    
    return captcha_details or ["No CAPTCHA services detected"]

def find_cloudflare_services(response_text: str) -> list[str]:
    """Tìm các dịch vụ bảo mật của Cloudflare."""
    services = []
    if "cloudflare turnstile" in response_text.lower():
        services.append("Cloudflare Turnstile")
    if "ddos protection" in response_text.lower():
        services.append("DDoS Protection")
    if "web application firewall" in response_text.lower():
        services.append("Web Application Firewall (WAF)")
    if "rate limiting" in response_text.lower():
        services.append("Rate Limiting")
    if "bot management" in response_text.lower():
        services.append("Bot Management")
    if "ssl/tls encryption" in response_text.lower():
        services.append("SSL/TLS Encryption")
    if "zero trust security" in response_text.lower():
        services.append("Zero Trust Security")
        
    return services or ["No Cloudflare services detected"]

def find_checkout_details(response_text: str) -> list[str]:
    """Tìm các trang liên quan đến thanh toán."""
    details = []
    if "checkout" in response_text.lower():
        details.append("Checkout Page")
    if "cart" in response_text.lower():
        details.append("Cart Page")
    if "payment" in response_text.lower():
        details.append("Payment Page")
    if "billing" in response_text.lower():
        details.append("Billing Page")
    if "shipping" in response_text.lower():
        details.append("Shipping Page")
        
    return details or ["No checkout details detected"]

def detect_cms_platform(content: str) -> list[str]:
    """Phát hiện CMS/Platform từ nội dung HTML."""
    detected = [cms for cms, pattern in CMS_PATTERNS.items() if re.search(pattern, content, re.IGNORECASE)]
    return list(set(detected))

def check_graphql(content: str) -> bool:
    """Kiểm tra sự tồn tại của GraphQL."""
    for pattern in SECURITY_PATTERNS.values():
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False

def check_ssl_details(domain: str) -> dict | None:
    """Kiểm tra thông tin chứng chỉ SSL."""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((domain, 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                issuer = dict(x[0] for x in cert.get('issuer', []))
                subject = dict(x[0] for x in cert.get('subject', []))
                return {
                    'issuer': issuer.get('organizationName', 'Unknown'),
                    'subject': subject.get('commonName', 'Unknown'),
                }
    except Exception as e:
        logger.error(f"SSL check failed for {domain}: {e}")
        return None

def perform_website_check(url: str, user: User) -> str:
    """Thực hiện một lần kiểm tra site và trả về chuỗi kết quả."""
    normalized_url = normalize_url(url)
    if not normalized_url:
        return f"⚠️ URL không hợp lệ: `{url}`"

    domain = urlparse(normalized_url).netloc
    start_time = time.time()

    try:
        response = requests.get(normalized_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        content = response.text
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {normalized_url}: {e}")
        return f"⚠️ Không thể truy cập website: `{url}`\nLỗi: `{e}`"
    
    time_taken = time.time() - start_time
    
    # Thực hiện tất cả các kiểm tra
    content_lower = content.lower()
    captcha_detected = 'captcha' in content_lower or 'protected by recaptcha' in content_lower or "i'm not a robot" in content_lower
    cloudflare_detected = 'cloudflare' in content_lower or 'cdnjs.cloudflare.com' in content_lower or 'challenges.cloudflare.com' in content_lower

    payment_gateways = find_payment_gateways(content)
    captcha_details = find_captcha_details(content)
    cloudflare_services = find_cloudflare_services(content)
    checkout_details = find_checkout_details(content)
    cms_platforms = detect_cms_platform(content)
    graphql_detected = check_graphql(content)
    ssl_details = check_ssl_details(domain)
    
    # Định dạng kết quả
    gateway_text = escape_markdown(', '.join(payment_gateways))
    captcha_text = escape_markdown(', '.join(captcha_details))
    cloudflare_text = escape_markdown(', '.join(cloudflare_services))
    checkout_text = escape_markdown(', '.join(checkout_details))
    cms_text = escape_markdown(', '.join(cms_platforms) or 'None')
    
    ssl_issuer = "Lỗi/Không hợp lệ"
    ssl_subject = "Lỗi/Không hợp lệ"
    ssl_valid = "⛔"
    if ssl_details:
        ssl_issuer = escape_markdown(ssl_details['issuer'])
        ssl_subject = escape_markdown(ssl_details['subject'])
        ssl_valid = "✅"
        
    checked_by = escape_markdown(user.first_name if not user.username else f"@{user.username}")
    
    # Xây dựng tin nhắn trả về
    result_text = (
        f"**💠 WEBSITE CHECK RESULT 💠**\n\n"
        f"🔍 **Domain**: `{escape_markdown(domain)}`\n"
        f"💳 **Gateways**: `{gateway_text}`\n"
        f"🔒 **CAPTCHA**: `{captcha_text}`\n"
        f"☁️ **Cloudflare**: `{cloudflare_text}`\n"
        f"🛒 **Checkout**: `{checkout_text}`\n\n"
        f"🛡️ **Security**:\n"
        f"   ├─ Captcha: {'✅' if captcha_detected else '⛔'}\n"
        f"   ├─ Cloudflare: {'✅' if cloudflare_detected else '⛔'}\n"
        f"   └─ GraphQL: {'✅' if graphql_detected else '⛔'}\n\n"
        f"🔐 **SSL Details**:\n"
        f"   ├─ Issuer: `{ssl_issuer}`\n"
        f"   ├─ Subject: `{ssl_subject}`\n"
        f"   └─ Valid: {ssl_valid}\n\n"
        f"🛍️ **Platform (CMS)**: `{cms_text}`\n\n"
        f"**⏱️ Took**: `{time_taken:.2f}s`\n"
        f"**👤 Checked by**: {checked_by}"
    )
    return result_text

# --- LỆNH BOT (COMMAND HANDLERS) ---
async def site_command(update, context):
    """Xử lý lệnh /site để check một website."""
    user = update.effective_user
    if user.id != ADMIN_ID and user.id not in load_users():
        await update.message.reply_text(f"Bạn không được phép sử dụng lệnh này. Vui lòng liên hệ Admin: {ADMIN_USERNAME}")
        return

    if user.id != ADMIN_ID and not is_bot_on():
        lang = get_user_lang(user.id)
        message = MESSAGES_VI["bot_off"] if lang == 'vi' else MESSAGES_EN["bot_off"]
        await update.message.reply_text(message)
        return

    if not context.args:
        await update.message.reply_text("Sử dụng: `/site <website.com>`")
        return

    url_input = context.args[0]
    msg = await update.message.reply_text(f"⏳ Đang kiểm tra trang `{url_input}`...")

    try:
        # Chạy hàm blocking trong một thread riêng để không chặn bot
        result_message = await asyncio.to_thread(perform_website_check, url_input, user)
        await msg.edit_text(result_message, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Lỗi trong /site command: {e}", exc_info=True)
        await msg.edit_text(f"⛔️ **Lỗi Hệ Thống khi check site:**\n`{e}`")

async def sitem_command(update, context):
    """Xử lý lệnh /sitem để check nhiều website."""
    user = update.effective_user
    if user.id != ADMIN_ID and user.id not in load_users():
        await update.message.reply_text(f"Bạn không được phép sử dụng lệnh này. Vui lòng liên hệ Admin: {ADMIN_USERNAME}")
        return

    if user.id != ADMIN_ID and not is_bot_on():
        lang = get_user_lang(user.id)
        message = MESSAGES_VI["bot_off"] if lang == 'vi' else MESSAGES_EN["bot_off"]
        await update.message.reply_text(message)
        return

    text_content = update.message.text.split('/sitem', 1)[-1].strip()
    if not text_content:
        await update.message.reply_text("Sử dụng: `/sitem` và dán danh sách website ở dòng dưới."); return

    # Tìm tất cả các URL trong tin nhắn
    url_pattern = r'(https?://)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
    urls_to_check = [match[0] + match[1] for match in re.findall(url_pattern, text_content)]
    
    if not urls_to_check:
        await update.message.reply_text("Không tìm thấy URL hợp lệ nào để check."); return

    max_urls = 10
    if len(urls_to_check) > max_urls:
        await update.message.reply_text(f"⚠️ Quá nhiều URL. Chỉ xử lý {max_urls} URL đầu tiên.")
        urls_to_check = urls_to_check[:max_urls]

    await update.message.reply_text(f"🚀 Bắt đầu kiểm tra `{len(urls_to_check)}` trang web...")

    for url in urls_to_check:
        try:
            result_message = await asyncio.to_thread(perform_website_check, url, user)
            await update.message.reply_text(result_message, disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Lỗi khi check URL {url} trong /sitem: {e}", exc_info=True)
            await update.message.reply_text(f"⛔️ Lỗi khi check `{url}`: `{e}`")
        await asyncio.sleep(1) # Thêm độ trễ để tránh flood
