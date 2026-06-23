import imaplib
import email
import json
import os
import configparser
import logging
from datetime import datetime, timedelta
import time

from settings import settings
from function.ai_client import get_ai_client
# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

# Setup a dedicated logger for this module
logger = logging.getLogger('IMAP_Bounce_Scan')
if not logger.handlers:
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    # Use a formatter that matches the main application for consistency
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: (IMAP) %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def _get_plain_text_body(msg):
    """Extracts plain text body from an email.message.Message object."""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))
            if ctype == 'text/plain' and 'attachment' not in cdispo:
                try:
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    return body
                except Exception as e:
                    logger.debug(f"Could not decode part of multipart email: {e}")
                    continue
    else:
        if msg.get_content_type() == 'text/plain':
            try:
                return msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            except Exception as e:
                logger.debug(f"Could not decode non-multipart email body: {e}")
                return ""
    return ""

def _add_to_suppression_list(email_to_suppress, project_root):
    """Adds an email to the suppression list file in a thread-safe way."""
    if not email_to_suppress:
        return
    suppression_list_path = os.path.join(project_root, 'logs', 'suppression_list.txt')
    try:
        with open(suppression_list_path, 'a', encoding='utf-8') as f:
            f.write(f"{email_to_suppress.strip().lower()}\n")
        logger.info(f"Added {GREEN}{email_to_suppress}{RESET} to the suppression list.")
    except Exception as e:
        logger.warning(f"Could not write to suppression list: {e}")
 
def classify_email_content(email_body, client, model_name):
    """Uses an AI client to classify email content into predefined categories."""
    if not client:
        logger.warning("AI client not available. Skipping classification.")
        return "UNKNOWN"
    
    # Truncate body to avoid excessive token usage and costs
    max_length = 8000 # Approx 2k tokens, enough for most bounce messages
    truncated_body = email_body[:max_length]
    system_prompt = """
    You are an email classification expert for an outbound email system. Your task is to analyze the content of an email reply and classify it into one of the following categories. Respond with ONLY the category name.
    The categories are:
    - HARD_BOUNCE: The email address is invalid, does not exist, or the domain is non-existent. Look for phrases like "does not exist", "user unknown", "no such user", "recipient rejected", "address rejected", "permanent failure".
    - SOFT_BOUNCE: The email could not be delivered due to a temporary issue, like a full mailbox or server being down. Look for "mailbox full", "over quota", "delivery temporarily suspended".
    - OUT_OF_OFFICE: An automated reply indicating the person is away. Look for "out of office", "on vacation", "away from my desk", "autoreply".
    - HUMAN_NEGATIVE_UNSUBSCRIBE: A human-written reply asking to be removed from the list. Look for "unsubscribe", "remove me", "stop sending", "do not contact".
    - HUMAN_POSITIVE: A human-written reply showing interest, asking a question, or a simple thank you.
    - UNKNOWN: The email is a system notification, marketing email, or anything else that doesn't fit the above categories.
    """
 
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": truncated_body}
            ],
            max_tokens=20,
            temperature=0.0
        )
        
        classification = response.choices[0].message.content.strip().replace('.', '')
        valid_categories = ["HARD_BOUNCE", "SOFT_BOUNCE", "OUT_OF_OFFICE", "HUMAN_NEGATIVE_UNSUBSCRIBE", "HUMAN_POSITIVE", "UNKNOWN"]
        if classification in valid_categories:
            return classification
        else:
            logger.warning(f"AI returned an invalid category: '{classification}'. Defaulting to UNKNOWN.")
            return "UNKNOWN"
            
    except Exception as e:
        logger.error(f"AI classification failed: {e}")
        return "UNKNOWN"
def scan_bounces(accounts, project_root):
    """
    Connects to IMAP accounts, fetches new emails, classifies them using AI,
    and adds hard bounces or unsubscribe requests to the suppression list.
    """
    logger.info("--- Starting IMAP Bounce Scan ---")

    if not (settings.ai.ai_enabled and settings.ai.ai_classify_replies):
        logger.warning("AI Reply Classifier is not enabled in the config. Aborting scan.")
        return set()

    # Get the centralized AI client
    ai_client = get_ai_client(settings, logger)
    if not ai_client:
        logger.error("AI Reply Classifier is enabled, but the AI client could not be initialized. Aborting scan.")
        return set()

    suppressed_emails = set()
    model_to_use = settings.ai.ai_model

    for account in accounts:
        try:
            user = account['user']
            password = account['password']
            server = account['server']
            port = account.get('port', 993)
            
            logger.info(f"Connecting to {server} for user {user}...")
            mail = imaplib.IMAP4_SSL(server, port)
            mail.login(user, password)
            mail.select('inbox')

            # --- "World-Class" Performance Fix ---
            # Instead of scanning all unread emails, which can be slow on old inboxes,
            # we will only scan for unread emails from the last 7 days.
            # This keeps the scan fast and relevant.
            days_to_scan = 7
            date_since = (datetime.now() - timedelta(days=days_to_scan)).strftime("%d-%b-%Y")
            search_criteria = f'(UNSEEN SINCE "{date_since}")'
            
            logger.info(f"Searching for new emails since {date_since}...")
            status, data = mail.search(None, search_criteria)
            if status != 'OK':
                logger.error(f"Failed to search INBOX for {user}.")
                continue

            email_ids = data[0].split()
            if not email_ids:
                logger.info(f"No new emails found for {user}.")
                continue
            
            logger.info(f"Found {len(email_ids)} new email(s) for {user}. Processing...")

            for e_id in email_ids:
                status, msg_data = mail.fetch(e_id, '(RFC822)')
                if status != 'OK': continue
                
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                from_header = email.utils.parseaddr(msg['From'])[1]
                subject = msg['Subject']
                
                body = _get_plain_text_body(msg)
                if not body:
                    logger.debug(f"Could not extract plain text body from email with subject: '{subject}'. Skipping.")
                    continue
                
                classification = classify_email_content(body, ai_client, model_to_use)
                color_map = {
                    "HARD_BOUNCE": RED, "HUMAN_NEGATIVE_UNSUBSCRIBE": RED,
                    "SOFT_BOUNCE": YELLOW, "OUT_OF_OFFICE": YELLOW,
                    "HUMAN_POSITIVE": GREEN, "UNKNOWN": ""
                }
                color = color_map.get(classification, "")
                
                logger.info(f"Email from '{from_header}' | Subject: '{subject}' | AI Classification: {color}{classification}{RESET}")

                if classification in ["HARD_BOUNCE", "HUMAN_NEGATIVE_UNSUBSCRIBE"]:
                    logger.warning(f"Action: Suppressing '{from_header}' based on classification '{classification}'.")
                    _add_to_suppression_list(from_header, project_root)
                    suppressed_emails.add(from_header)
                
                # Mark email as seen to avoid re-processing
                mail.store(e_id, '+FLAGS', '\\Seen')

            mail.close()
            mail.logout()

        except imaplib.IMAP4.error as e:
            # "Smarter" Error Handling: Detect server mismatches and auth failures
            error_str = str(e)
            server = account.get('server', 'unknown-server')
            
            if 'AUTHENTICATIONFAILED' in error_str:
                user_email = account.get('user')
                logger.error(f"Authentication failed for user '{user_email}' at server '{server}'.")
                
                if 'BasicAuthBlocked' in error_str:
                    logger.error(f"[red]MICROSOFT SECURITY BLOCK:[/] Basic Authentication is disabled for {user_email}.")
                    logger.warning("Microsoft 365 has blocked this connection. To fix:")
                    logger.warning("1. Create and use an 'App Password' (requires MFA to be enabled).")
                    logger.warning("2. Ensure 'IMAP' protocol is enabled for this user in O365 Admin Center.")
                    logger.warning("3. If using the 'Ghost Sending' feature, this account requires Modern Auth or an App Password.")
                elif 'gmail.com' in server:
                    logger.warning(f"{YELLOW}POSSIBLE CONFIG MISMATCH:{RESET} You are connecting to a GMAIL server ({server}).")
                    logger.warning(f"1. If this is NOT a Gmail account (e.g. Elastic Email), please edit 'config/imap_accounts.json' and change the 'server' field.")
                    logger.warning(f"2. If this IS a Gmail account, ensure you are using an '{YELLOW}App Password{RESET}'.")
                else:
                    logger.warning(f"Please verify your username and password in 'config/imap_accounts.json'.")
            else:
                logger.error(f"An IMAP error occurred while processing account {account.get('user')}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing account {account.get('user')}: {e}")
            
    logger.info(f"--- IMAP Bounce Scan Finished. Suppressed {len(suppressed_emails)} new email(s). ---")
    return suppressed_emails
