import smtplib
import socket
import os
import sys
import json
import configparser
from concurrent.futures import ThreadPoolExecutor, as_completed

# Try to enable color output with colorama on Windows, fallback to ANSI or no color
try:
    from colorama import init as _color_init, Fore, Style
    _color_init(autoreset=True)
    RED = Fore.RED
    YELLOW = Fore.YELLOW
    GREEN = Fore.GREEN
    RESET = Style.RESET_ALL
except ImportError:
    # Basic ANSI escape codes for non-Windows or if colorama is not installed
    RED = '\033[31m'
    YELLOW = '\033[33m'
    GREEN = '\033[32m'
    RESET = '\033[0m'

# --- Add project root to path to allow imports from 'function' ---
PROJECT_ROOT = os.path.dirname(__file__)
sys.path.append(PROJECT_ROOT)

try:
    from function.smtp_utils import get_smtp_configs, test_smtp_connection
    from settings import settings, SmtpConfigModel
except ImportError:
    print(f"{RED}FATAL: Could not import 'get_smtp_configs' from 'function.smtp_utils.py'.{RESET}")
    print("Please ensure the file exists and the project structure is correct.")
    sys.exit(1)

# --- EWS / Cookie Handler ---
def handle_ews_cookies(email, cookies_json):
    """Verifies cookies and updates config to use EWS."""
    try:
        from function.ews_oauth_transport import BearerCredentials
        import exchangelib
    except ImportError:
        print(f"{RED}Error: 'exchangelib' is not installed. Cannot verify EWS cookies.{RESET}")
        return False

    print(f"Verifying cookies for {email}...")
    try:
        cookies_list = json.loads(cookies_json)
        token = next((c['value'] for c in cookies_list if c['name'] == 'ESTSAUTH'), None)
        if not token:
            print(f"{RED}Error: 'ESTSAUTH' cookie not found in the provided JSON.{RESET}")
            return False

        # Verify connectivity
        creds = BearerCredentials(access_token=token)
        config = exchangelib.Configuration(server='outlook.office365.com', credentials=creds)
        account = exchangelib.Account(primary_smtp_address=email, config=config, autodiscover=False, access_type=exchangelib.DELEGATE)
        # Test access (will raise error if invalid)
        account.root.refresh()

        print(f"{GREEN}✓ EWS Access Verified via Cookies!{RESET}")

        # Update config.ini
        config_path = os.path.join(PROJECT_ROOT, 'config', 'config.ini')
        cfg = configparser.ConfigParser(inline_comment_prefixes=('#',))
        cfg.read(config_path)
        if not cfg.has_section('EWS'): cfg.add_section('EWS')
        if not cfg.has_section('GENERAL'): cfg.add_section('GENERAL')
        
        cfg.set('EWS', 'ews_cookies', cookies_json)
        cfg.set('EWS', 'ews_username', email)
        cfg.set('EWS', 'ews_use_oauth', 'false')
        cfg.set('GENERAL', 'sending_method', 'ews')
        
        with open(config_path, 'w') as f:
            cfg.write(f)
        
        print(f"{GREEN}Configuration updated: Switched sending method to 'EWS' and saved cookies.{RESET}")
        return True
    except Exception as e:
        print(f"{RED}Cookie verification failed: {e}{RESET}")
        return False

# --- Helper to update .env directly ---
try:
    from dotenv import set_key, find_dotenv, dotenv_values
except ImportError:
    set_key = None

def update_password_in_env(email, new_password):
    if not set_key: return False
    env_path = find_dotenv()
    if not env_path:
        env_path = os.path.join(PROJECT_ROOT, '.env')
    
    env_vals = dotenv_values(env_path)
    try:
        passwords = json.loads(env_vals.get("SMTP_PASSWORDS", "{}"))
    except json.JSONDecodeError:
        passwords = {}
    passwords[email] = new_password
    set_key(env_path, "SMTP_PASSWORDS", json.dumps(passwords))
    return True


def main():
    """
    Main function to read SMTP configs and test them in parallel.
    """
    print(f"{YELLOW}--- Starting Bulk SMTP Tester ---{RESET}")
    
    # Get all SMTP configurations from config/config.ini
    smtp_configs = get_smtp_configs()

    if not smtp_configs:
        print(f"{RED}No SMTP servers found in 'config/config.ini' under the [SMTP] -> SMTP_SERVERS key.{RESET}")
        print("Please add your servers there to use the tester.")
        return

    print(f"Found {len(smtp_configs)} SMTP configurations to test. Starting tests...\n")

    # Get the timeout from the central settings
    smtp_timeout = settings.smtp.smtp_timeout
    print(f"Using connection timeout of {smtp_timeout} seconds for each test.")

    working_smtps = []
    failed_smtps = []
    auth_failures = []
    
    # Create a logger for the test function to use
    import logging
    test_logger = logging.getLogger('bulk_test')
    test_logger.setLevel(logging.INFO)
    if not test_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(f"{YELLOW}%(message)s{RESET}"))
        test_logger.addHandler(handler)

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_smtp = {executor.submit(test_smtp_connection, config, test_logger, smtp_timeout): config for config in smtp_configs}
        
        for future in as_completed(future_to_smtp):
            original_config = future_to_smtp[future]
            try:
                success, message, updated_config = future.result()
                if success:
                    print(f"{GREEN}{message}{RESET}")
                    if updated_config and original_config.host != updated_config.host:
                        print(f"{YELLOW}  -> Suggestion: Update config.ini for {original_config.email} to use host '{updated_config.host}' and port '{updated_config.port}'.{RESET}")
                    working_smtps.append(updated_config or original_config)
                else:
                    print(f"{RED}FAILED: {original_config.host}:{original_config.port} - {message}{RESET}")
                    
                    # Capture auth failures for the interactive fixer
                    if "Authentication failed" in message:
                        auth_failures.append(original_config)
            except Exception as e:
                print(f"{RED}An exception occurred while testing {original_config.email}: {e}{RESET}")

    print(f"\n--- Test Complete ---")
    print(f"Total working SMTPs: {GREEN}{len(working_smtps)}{RESET} out of {len(smtp_configs)}")

    if not working_smtps:
        print(f"{YELLOW}Warning: No working SMTPs were found. The sender will not be able to send emails.{RESET}")

    # --- Interactive Authentication Fixer ---
    if auth_failures:
        print(f"\n{YELLOW}--- Authentication Fixer ---{RESET}")
        print(f"Detected {len(auth_failures)} authentication failure(s).")
        if input("Would you like to update the passwords for these accounts now? [y/N]: ").strip().lower() == 'y':
            if not set_key:
                print(f"{RED}Error: python-dotenv is not installed. Cannot update .env file.{RESET}")
                return
            for config in auth_failures:
                print(f"\nUpdating password for: {GREEN}{config.email}{RESET} (Host: {config.host})")
                is_office365 = "office365" in config.host or "outlook" in config.host or "secureserver.net" in config.host
                if is_office365:
                    print(f"{YELLOW}Note: For Office 365/GoDaddy accounts, ensure 'Authenticated SMTP' is enabled for this user in the Microsoft 365 Admin Center.{RESET}")
                    print(f"{YELLOW}      If MFA is on, you may need an 'App Password'.{RESET}")
                    print(f"{YELLOW}      Alternatively, for a more robust connection, consider switching to the EWS sending method in the main menu.{RESET}")
                    print(f"{YELLOW}      You can paste browser cookies (JSON) below to automatically configure EWS.{RESET}")
                
                new_input = input(f"Enter new password or paste cookies for {config.email} (leave blank to skip): ").strip()
                if new_input:
                    # Check for cookies (must start with [ and contain ESTSAUTH)
                    if is_office365 and new_input.startswith('[') and 'ESTSAUTH' in new_input:
                        if handle_ews_cookies(config.email, new_input):
                            continue # Config updated, skip env password update

                    if update_password_in_env(config.email, new_input):
                        print(f"{GREEN}Password updated in .env file! Please re-run the test to verify.{RESET}")
                    else:
                        print(f"{RED}Failed to write to .env file.{RESET}")

if __name__ == "__main__":
    main()