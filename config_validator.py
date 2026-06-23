import configparser
import os
import shutil

# ANSI color codes for better output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

PROJECT_ROOT = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.ini')

def print_status(status, message):
    """Prints a formatted status message."""
    if status == 'OK':
        print(f"  {GREEN}[✓] {message}{RESET}")
    elif status == 'WARN':
        print(f"  {YELLOW}[!] {message}{RESET}")
    elif status == 'FAIL':
        print(f"  {RED}[✗] {message}{RESET}")

def check_config():
    """Reads and validates the config.ini file."""
    print("\n--- Running Configuration Validator ---")

    if not os.path.exists(CONFIG_PATH):
        print_status('FAIL', f"Config file not found at '{CONFIG_PATH}'")
        return

    # Use the same "smart" parser as main.py to handle inline comments
    config = configparser.ConfigParser(inline_comment_prefixes=('#',))
    config.read(CONFIG_PATH)

    # --- [GENERAL] Section ---
    print("\n[GENERAL]")
    recipients_file = config.get('GENERAL', 'recipients_file', fallback='recipients.txt')
    recipients_path = os.path.join(PROJECT_ROOT, recipients_file)
    if os.path.exists(recipients_path):
        print_status('OK', f"Recipients file '{recipients_file}' found.")
    else:
        print_status('FAIL', f"Recipients file '{recipients_file}' not found at '{recipients_path}'.")

    # --- [EMAIL] Section ---
    print("\n[EMAIL]")
    message_files_str = config.get('EMAIL', 'message_file', fallback='letter.html')
    separator = config.get('MISC', 'config_separator', fallback='::')
    message_files = [f.strip() for f in message_files_str.split(separator)]
    
    missing_templates = []
    found_templates = []

    for tpl in message_files:
        message_path = os.path.join(PROJECT_ROOT, 'files', tpl)
        if not os.path.exists(message_path):
            print_status('FAIL', f"Message template '{tpl}' not found in 'files/' directory.")
            missing_templates.append(tpl)
        else:
            found_templates.append(tpl)

    if not missing_templates:
        print_status('OK', "All configured message templates were found.")
    
    # --- "Smarter" Interactive Fix ---
    if missing_templates and found_templates:
        first_valid_template = found_templates[0]
        if input(f"\n{YELLOW}Missing template(s) detected. Would you like to create them now by copying '{first_valid_template}'? [y/n]: {RESET}").strip().lower() == 'y':
            source_path = os.path.join(PROJECT_ROOT, 'files', first_valid_template)
            for missing_tpl in missing_templates:
                dest_path = os.path.join(PROJECT_ROOT, 'files', missing_tpl)
                try:
                    shutil.copy(source_path, dest_path)
                    print_status('OK', f"Successfully created '{missing_tpl}'.")
                except Exception as e:
                    print_status('FAIL', f"Could not create '{missing_tpl}'. Error: {e}")

    # --- [SMTP] Section ---
    print("\n[SMTP]")
    smtp_servers = config.get('SMTP', 'smtp_servers', fallback='')
    if smtp_servers:
        print_status('OK', "SMTP servers are configured.")
    else:
        print_status('WARN', "No SMTP servers configured. Sender will not be able to send emails.")

    # --- [LINK_SHORTENER] Section ---
    print("\n[LINK_SHORTENER]")
    shortener_enabled = config.getboolean('LINK_SHORTENER', 'shortener_enabled', fallback=False)
    if shortener_enabled:
        provider = config.get('LINK_SHORTENER', 'shortener_provider', fallback='').lower()
        if provider == 'rebrandly':
            api_key = config.get('LINK_SHORTENER', 'shortener_api_key', fallback='')
            if api_key:
                print_status('OK', "Rebrandly link shortener is enabled with an API key.")
            else:
                print_status('FAIL', "Rebrandly is enabled, but 'shortener_api_key' is missing.")
        elif provider == 'zapier':
            webhook_url = config.get('LINK_SHORTENER', 'zapier_webhook_url', fallback='')
            if webhook_url and 'hooks.zapier.com' in webhook_url:
                print_status('OK', "Zapier link shortener is enabled with a webhook URL.")
            else:
                print_status('FAIL', "Zapier is enabled, but 'zapier_webhook_url' is missing or invalid.")
        else:
            print_status('FAIL', f"Link shortener is enabled, but the provider '{provider}' is unknown.")
    else:
        print_status('OK', "Link shortener is disabled.")

    # --- [TRACKING] Section (Self-hosted) ---
    print("\n[TRACKING]")
    tracking_url = config.get('EMAIL', 'tracking_url', fallback='')
    if tracking_url and not shortener_enabled:
        if 'your-tracking-domain.com' in tracking_url:
            print_status('WARN', "Self-hosted tracking is enabled, but the URL is the default placeholder.")
        elif 'redirect.php' in tracking_url:
            print_status('OK', "Self-hosted tracking is enabled with a custom URL.")
        else:
            print_status('WARN', "Tracking URL is set, but does not seem to point to 'redirect.php'.")
    elif not tracking_url and not shortener_enabled:
        print_status('OK', "No link tracking is configured.")

    # --- [SMIME] Section ---
    print("\n[S/MIME]")
    smime_enabled = config.getboolean('SMIME', 'smime_sign', fallback=False)
    if smime_enabled:
        cert_file = config.get('SMIME', 'smime_cert_file', fallback='')
        key_file = config.get('SMIME', 'smime_key_file', fallback='')
        if cert_file and os.path.exists(cert_file) and key_file and os.path.exists(key_file):
            print_status('OK', "S/MIME is enabled and certificate/key files were found.")
        else:
            print_status('FAIL', "S/MIME is enabled, but the 'smime_cert_file' or 'smime_key_file' is missing or path is incorrect.")
    else:
        print_status('OK', "S/MIME signing is disabled.")

    # --- [DEV] Section ---
    print("\n[DEV]")
    verify_enabled = config.getboolean('DEV', 'verify_emails_before_send', fallback=False)
    hunter_key = config.get('DEV', 'hunter_api_key', fallback='')
    if verify_enabled and not hunter_key:
        print_status('FAIL', "Email verification is enabled, but 'hunter_api_key' is not set.")
    elif verify_enabled and hunter_key:
        print_status('OK', "Email verification is enabled with an API key.")
    else:
        print_status('OK', "Email verification is disabled.")

    # --- [AI] Section ---
    print("\n[AI]")
    ai_enabled = config.getboolean('AI', 'ai_enabled', fallback=False)
    if ai_enabled:
        print_status('OK', "AI Content Engine is enabled.")
        # Check for API key in .env file
        try:
            from dotenv import find_dotenv, dotenv_values
            env_path = find_dotenv()
            env_vars = dotenv_values(env_path) if env_path else {}
            if "GROQ_API_KEY" not in env_vars or not env_vars["GROQ_API_KEY"]:
                print_status('FAIL', "AI is enabled, but 'GROQ_API_KEY' is not set in your .env file. Reply classification will fail.")
        except ImportError:
            print_status('WARN', "'python-dotenv' is not installed. Cannot check for AI API key in .env file.")

    print("\n--- Validation Complete ---")

if __name__ == "__main__":
    check_config()