# Tên file: site_checker.py
import requests
import re
import ssl
import socket
import time
import logging
from urllib.parse import urlparse
from flask import Flask, request, jsonify

# --- CẤU HÌNH ---
# Tắt bớt log của Flask để console sạch hơn
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

# --- CẤU HÌNH CHO SITE CHECKER ---
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

# --- CÁC HÀM CHO SITE CHECKER ---
def escape_markdown(text: str) -> str:
    """Hàm helper để escape các ký tự Markdown V2."""
    if not text:
        return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

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
        if "recaptcha v1" in response_text.lower(): captcha_details.append("reCAPTCHA v1")
        if "recaptcha v2" in response_text.lower(): captcha_details.append("reCAPTCHA v2")
        if "recaptcha v3" in response_text.lower(): captcha_details.append("reCAPTCHA v3")
        if "recaptcha enterprise" in response_text.lower(): captcha_details.append("reCAPTCHA Enterprise")
    if "hcaptcha" in response_text.lower(): captcha_details.append("hCaptcha")
    if "funcaptcha" in response_text.lower(): captcha_details.append("FunCAPTCHA")
    if "arkoselabs" in response_text.lower(): captcha_details.append("Arkose Labs")
    return captcha_details or ["No CAPTCHA services detected"]

def find_cloudflare_services(response_text: str) -> list[str]:
    """Tìm các dịch vụ bảo mật của Cloudflare."""
    services = []
    if "cloudflare turnstile" in response_text.lower(): services.append("Cloudflare Turnstile")
    if "ddos protection" in response_text.lower(): services.append("DDoS Protection")
    if "web application firewall" in response_text.lower(): services.append("Web Application Firewall (WAF)")
    if "rate limiting" in response_text.lower(): services.append("Rate Limiting")
    if "bot management" in response_text.lower(): services.append("Bot Management")
    if "ssl/tls encryption" in response_text.lower(): services.append("SSL/TLS Encryption")
    if "zero trust security" in response_text.lower(): services.append("Zero Trust Security")
    return services or ["No Cloudflare services detected"]

def find_checkout_details(response_text: str) -> list[str]:
    """Tìm các trang liên quan đến thanh toán."""
    details = []
    if "checkout" in response_text.lower(): details.append("Checkout Page")
    if "cart" in response_text.lower(): details.append("Cart Page")
    if "payment" in response_text.lower(): details.append("Payment Page")
    if "billing" in response_text.lower(): details.append("Billing Page")
    if "shipping" in response_text.lower(): details.append("Shipping Page")
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
        # Ghi log lỗi thay vì print để không làm nhiễu output
        logging.error(f"SSL check failed for {domain}: {e}")
        return None

def perform_website_check(url: str, username: str, first_name: str) -> str:
    """
    Thực hiện một lần kiểm tra site và trả về chuỗi kết quả.
    Đã được sửa đổi để nhận username và first_name thay vì object User.
    """
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
        logging.error(f"Failed to fetch {normalized_url}: {e}")
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
        
    checked_by = escape_markdown(first_name if not username else f"@{username}")
    
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


@app.route('/check', methods=['POST'])
def handle_check_request():
    """Endpoint API để nhận yêu cầu kiểm tra website."""
    data = request.json
    url = data.get('url')
    # Lấy thông tin người dùng từ request để hiển thị "Checked by"
    username = data.get('username')
    first_name = data.get('first_name')

    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        # Gọi hàm xử lý chính
        result = perform_website_check(url, username, first_name)
        return jsonify({"result": result})
    except Exception as e:
        logging.error(f"Error in perform_website_check for URL {url}: {e}", exc_info=True)
        return jsonify({"error": f"An internal error occurred: {e}"}), 500


if __name__ == '__main__':
    # Chạy Flask server trên cổng 5001
    # Host 0.0.0.0 để có thể truy cập từ bot (nếu chạy trong container)
    print("Site Checker service is starting on http://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001)
