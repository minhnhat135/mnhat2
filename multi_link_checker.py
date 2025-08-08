import json
import os
import random
import re
import time
import asyncio
import logging
from urllib.parse import urlparse

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# --- CONFIGURATION ---
LINK_FILE = "dynamic_links.json"
TEST_CARD = "5168155124645796|9|2028|462" # Test card for link validation
ADMIN_ID = 5127429005 # Ensure this matches your main file's ADMIN_ID

# --- HELPER FUNCTIONS ---
# These functions are imported from main.py, so we recreate simplified versions or placeholders
# In a real integrated scenario, you'd likely share these from a common 'utils.py'
logger = logging.getLogger(__name__)

def generate_random_string(length=8):
    """Generates a random string of characters."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    return ''.join(random.choice(letters) for _ in range(length))

def random_email():
    """Generates a random email address."""
    prefix = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz" + "0123456789", k=random.randint(8, 15)))
    domain = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz", k=random.randint(5, 10)))
    return f"{prefix}@{domain}.com"

def random_user_agent():
    """Generates a random realistic User-Agent string."""
    chrome_major = random.randint(100, 125)
    chrome_build = random.randint(0, 6500)
    chrome_patch = random.randint(0, 250)
    safari_version = f"{random.randint(537, 605)}.{random.randint(36, 99)}"
    chrome_version = f"{chrome_major}.0.{chrome_build}.{chrome_patch}"
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/{safari_version} (KHTML, like Gecko) "
        f"Chrome/{chrome_version} Safari/{safari_version}"
    )

def make_request_with_retry(session, method, url, max_retries=5, **kwargs):
    """Simplified request function for this module."""
    last_exception = None
    for attempt in range(max_retries):
        try:
            response = session.request(method, url, timeout=20, **kwargs)
            return response, None
        except requests.exceptions.RequestException as e:
            last_exception = e
            logger.warning(f"Request attempt {attempt + 1}/{max_retries} failed: {e}. Retrying...")
            time.sleep(attempt + 1)
    error_message = f"All {max_retries} retry attempts failed. Last error: {last_exception}"
    logger.error(error_message)
    return None, error_message

# --- LINK MANAGEMENT ---
def load_links():
    """Loads the list of dynamic links from a JSON file."""
    if not os.path.exists(LINK_FILE):
        return []
    try:
        with open(LINK_FILE, "r", encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_links(links):
    """Saves the list of dynamic links to a JSON file."""
    with open(LINK_FILE, "w", encoding='utf-8') as f:
        json.dump(links, f, indent=4)

def _format_proxy_for_requests(proxy_str):
    """Converts a proxy string to a dict format for the requests library."""
    if not proxy_str: return None
    parts = proxy_str.strip().split(':')
    if len(parts) == 2:
        proxy_url = f"http://{parts[0]}:{parts[1]}"
        return {"http": proxy_url, "https": proxy_url}
    elif len(parts) == 4:
        proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        return {"http": proxy_url, "https": proxy_url}
    return None

def _get_session_with_proxy(main_bot_proxy_config):
    """Creates a requests session, adding a proxy if enabled."""
    session = requests.Session()
    if main_bot_proxy_config.get("enabled") and main_bot_proxy_config.get("proxies"):
        try:
            proxy_str = random.choice(main_bot_proxy_config["proxies"])
            proxy_dict = _format_proxy_for_requests(proxy_str)
            if proxy_dict:
                session.proxies = proxy_dict
                logger.info("Link validation will use a proxy.")
        except IndexError:
            logger.warning("Proxy is enabled, but the proxy list is empty.")
    return session

async def _validate_and_add_link(link_url, context, chat_id, main_bot_proxy_config):
    """The core validation logic for a single link."""
    try:
        short_code = urlparse(link_url).path.strip('/')
        if not short_code:
            await context.bot.send_message(chat_id, f"❌ Invalid URL format: `{link_url}`. Could not extract code.")
            return

        session = _get_session_with_proxy(main_bot_proxy_config)

        # Step 1: Get identifiers from RaiseNow
        identifier_url = f"https://api.raisenow.io/short-identifiers/{short_code}"
        headers = {"User-Agent": random_user_agent()}
        
        response, error = await asyncio.to_thread(make_request_with_retry, session, 'get', identifier_url, headers=headers)

        if error or not response:
            await context.bot.send_message(chat_id, f"❌ Failed to fetch data for `{short_code}`. Error: `{error}`")
            return

        if response.status_code != 200:
            await context.bot.send_message(chat_id, f"❌ Error for `{short_code}`. Status: `{response.status_code}`\nResponse:\n`{response.text[:500]}`")
            return
        
        try:
            data = response.json()
        except json.JSONDecodeError:
            await context.bot.send_message(chat_id, f"❌ Failed to parse JSON response for `{short_code}`.")
            return
        
        payload = data.get("payload", {})
        payment_methods = payload.get("payment_methods", [])
        card_method = next((m for m in payment_methods if m.get("method_name") == "card"), None)

        if not card_method:
            await context.bot.send_message(chat_id, f"ℹ️ Link for `{short_code}` does not support card payments. Skipping.")
            return

        account_uuid = payload.get("account_uuid")
        profile = card_method.get("profile")

        if not all([account_uuid, profile]):
            await context.bot.send_message(chat_id, f"❌ Missing crucial info for `{short_code}` (account_uuid or profile). Skipping.")
            return
            
        # Step 2: Perform a test charge to validate the payload
        test_cc, test_mes, test_ano, test_cvv = TEST_CARD.split('|')
        
        status, _, response_text, _ = await asyncio.to_thread(
            check_card_dalink,
            session, TEST_CARD, test_cc, test_mes, test_ano, test_cvv, {}, None,
            'charge', # Force charge mode for validation
            { # Manually provide the link data for this test
                "code": short_code,
                "account_uuid": account_uuid,
                "profile": profile
            }
        )
        
        if status in ['success', 'decline']:
            links = load_links()
            if any(l['code'] == short_code for l in links):
                await context.bot.send_message(chat_id, f"ℹ️ Link for `{short_code}` is already in the database.")
            else:
                new_link_data = {
                    "code": short_code,
                    "account_uuid": account_uuid,
                    "profile": profile,
                    "url": link_url
                }
                links.append(new_link_data)
                save_links(links)
                await context.bot.send_message(chat_id, f"✅ **Link OK!** Successfully added `{short_code}`.")
        
        elif status == 'error' and "400 Client Error" in response_text:
             await context.bot.send_message(chat_id, f"❌ **Link Payload Error!**\nLink `{short_code}` returned a 400 Bad Request. This usually means the payload structure is not supported.\n\nFailing URL: `{link_url}`")
        
        elif status == 'error' and any(code in response_text for code in ["405 Client Error", "503 Server Error"]):
            await context.bot.send_message(chat_id, f"🟠 **Link Retry Failure!**\nLink `{short_code}` failed after multiple retries (Status 405/503). It might be temporarily unavailable. Not added.")
        
        else: # Other errors
            await context.bot.send_message(chat_id, f"❓ **Unknown Validation Error!**\nLink `{short_code}` could not be validated.\nStatus: `{status}`\nResponse: `{response_text[:500]}`")

    except Exception as e:
        logger.error(f"Critical error in _validate_and_add_link for {link_url}: {e}", exc_info=True)
        await context.bot.send_message(chat_id, f"⛔️ A system error occurred while processing `{link_url}`.")


async def addlink_command_worker(update, context, load_proxies_func):
    """Worker for the /addlink command."""
    if update.effective_user.id != ADMIN_ID: return

    # Extract links from arguments or message text
    if context.args:
        text_content = " ".join(context.args)
    else:
        text_content = update.message.text.split('/addlink', 1)[-1].strip()

    if not text_content:
        await update.message.reply_text("Usage: `/addlink <url1> <url2>...`\nOr reply with `/addlink` to a message containing URLs.")
        return

    # Regex to find all URLs in the provided text
    urls = re.findall(r'https?://[^\s]+', text_content)
    if not urls:
        await update.message.reply_text("No valid URLs found.")
        return
        
    await update.message.reply_text(f"Found `{len(urls)}` link(s). Starting validation... (This may take a moment)")
    
    proxy_config = load_proxies_func()

    for url in urls:
        await _validate_and_add_link(url.strip(), context, update.effective_chat.id, proxy_config)
        await asyncio.sleep(1) # Small delay to prevent rate-limiting

    await update.message.reply_text("✅ Link validation process complete.")


async def deletelink_command_worker(update, context):
    """Worker for the /deletelink command."""
    if update.effective_user.id != ADMIN_ID: return
    
    links = load_links()
    if not links:
        await update.message.reply_text("📭 The dynamic link list is empty.")
        return
        
    keyboard = []
    for i, link_data in enumerate(links):
        # Displaying the last 15 chars of the URL for brevity
        url_display = link_data.get('url', '...'+link_data['code'])
        button_text = f"🗑️ {url_display}"
        keyboard.append([InlineKeyboardButton(button_text[:50], callback_data=f"dellink_{i}")])
    
    keyboard.append([InlineKeyboardButton("❌ DELETE ALL LINKS ❌", callback_data="dellink_all")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select a link to delete:", reply_markup=reply_markup)


def check_card_dalink(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, mode, forced_link_data=None):
    """
    Main checking logic for the dynamic link mode.
    Inspired by _check_card_gate1.
    `forced_link_data` is used only for validation.
    """
    try:
        links = load_links()
        if not links and not forced_link_data:
            return 'error', line, "Dynamic link list is empty. Add links with /addlink.", bin_info

        if forced_link_data:
            link_to_use = forced_link_data
        else:
            link_to_use = random.choice(links)

        account_uuid = link_to_use['account_uuid']
        profile_id = link_to_use['profile']
        short_code = link_to_use['code']

        user_agent = random_user_agent()
        
        # Random personal info
        first_name = generate_random_string(random.randint(12, 20))
        last_name = generate_random_string(random.randint(10, 20))
        cardholder = f"{first_name} {last_name}"
        email = random_email()

        # Step 1: Tokenize card (This part is fairly standard)
        tokenize_url = "https://pay.datatrans.com/upp/payment/SecureFields/paymentField"
        tokenize_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://pay.datatrans.com",
            "Referer": "https://pay.datatrans.com/upp/payment/SecureFields/paymentField",
            "User-Agent": user_agent,
            "X-Requested-With": "XMLHttpRequest"
        }
        # Using a randomly generated formId as it seems less critical
        form_id = f"250808{''.join(random.choices('0123456789', k=12))}"

        tokenize_payload = {
            "mode": "TOKENIZE",
            "formId": form_id,
            "cardNumber": cc,
            "cvv": cvv,
            "paymentMethod": "ECA",
            "merchantId": "3000022877", # This seems to be a constant merchant ID
            "browserUserAgent": user_agent,
            "browserJavaEnabled": "false",
            "browserLanguage": "en-US",
            "browserColorDepth": "24",
            "browserScreenHeight": "1152",
            "browserScreenWidth": "2048",
            "browserTZ": "-420"
        }

        token_response, error = make_request_with_retry(session, 'post', tokenize_url, data=tokenize_payload, headers=tokenize_headers, max_retries=3)
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
                return 'error', line, f"HTTP Error {token_response.status_code} during Tokenization. Response: {token_response.text}", bin_info
            return 'error', line, "Tokenize response was not JSON", bin_info

        # Step 2: Make request based on mode
        payment_headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://donate.raisenow.io",
            "Referer": "https://donate.raisenow.io/",
            "User-Agent": user_agent
        }
        
        # This payload is a generic structure. We will fill in the dynamic parts.
        base_payload = {
            "account_uuid": account_uuid,
            "test_mode": False,
            "create_supporter": False,
            "supporter": {
                "locale": "en",
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
            },
            "payment_information": {
                "brand_code": "eca",
                "cardholder": cardholder,
                "expiry_month": mes.zfill(2),
                "expiry_year": ano,
                "transaction_id": transaction_id
            },
            "profile": profile_id,
            "return_url": f"https://donate.raisenow.io/{short_code}?lng=en&rnw-view=payment_result",
        }

        # --- CHARGE MODE ---
        if mode == 'charge':
            payment_url = "https://api.raisenow.io/payments"
            payment_payload = base_payload.copy()
            payment_payload["amount"] = {"currency": "EUR", "value": 50} # Standard 0.5 EUR charge

            # Use a higher retry count for charge validation, as per request
            retries = 6 if forced_link_data else 3
            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, max_retries=retries)
            
            if error: return 'error', line, f"Payment Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment", bin_info
            
            response_text = payment_response.text
            
            if payment_response.status_code == 400:
                 return 'error', line, f"400 Client Error: Bad Request. The payload might be incompatible. Response: {response_text}", bin_info
            if payment_response.status_code == 405:
                 return 'error', line, f"405 Client Error: Method Not Allowed. Link may be unavailable. Response: {response_text}", bin_info

            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, f'GATE_DIED: Forbidden on link {short_code}', bin_info
            
            if '"payment_status":"succeeded"' in response_text: return 'success', line, f'CHARGED_50', bin_info
            elif '"payment_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            elif '"action":{"action_type":"redirect"' in response_text: return 'custom', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info
        
        # --- LIVE CHECK MODE ---
        else: # 'live'
            payment_url = "https://api.raisenow.io/payment-sources"
            payment_payload = base_payload.copy()
            # Live mode requires an amount, even if not charged
            payment_payload["amount"] = {"currency": "EUR", "value": 50}

            payment_response, error = make_request_with_retry(session, 'post', payment_url, json=payment_payload, headers=payment_headers, max_retries=3)
            
            if error: return 'error', line, f"Payment Source Error: {error}", bin_info
            if not payment_response: return 'error', line, "HTTP Error with no response during Payment Source", bin_info

            response_text = payment_response.text
            if '{"message":"Forbidden"}' in response_text: return 'gate_dead', line, f'GATE_DIED: Forbidden on link {short_code}', bin_info
            
            if '"payment_source_status":"pending"' in response_text: return 'live_success', line, response_text, bin_info
            elif '"payment_source_status":"failed"' in response_text: return 'decline', line, response_text, bin_info
            else: return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Dynamic Link Checker for line '{line}': {e}", exc_info=True)
        return 'error', line, f"DaLink System Error: {e}", bin_info
