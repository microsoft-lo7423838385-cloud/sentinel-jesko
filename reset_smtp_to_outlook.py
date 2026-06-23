import os
import configparser
import json
import sys
import logging

# Try to import dotenv
try:
    from dotenv import set_key, find_dotenv, dotenv_values
except ImportError:
    print("python-dotenv not installed. Please run 'pip install python-dotenv'")
    sys.exit(1)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.ini')
ENV_PATH = os.path.join(PROJECT_ROOT, '.env')

def reset_smtp():
    email = "ministerofenjoymentintercontinental@outlook.com"
    host = "smtp.office365.com"
    port = "587"
    security = "starttls"
    
    print(f"--- Resetting SMTP configuration ---")
    print(f"Target Email: {email}")
    print(f"Server: {host}:{port} ({security})")
    
    password = input(f"Enter password for {email}: ").strip()
    if not password:
        print("Password cannot be empty.")
        return

    # 1. Update .env with the password
    if not os.path.exists(ENV_PATH):
        with open(ENV_PATH, 'w') as f: f.write("")
    
    env_file = find_dotenv()
    if not env_file:
        env_file = ENV_PATH

    env_vars = dotenv_values(env_file)
    current_passwords_str = env_vars.get("SMTP_PASSWORDS", "{}")
    try:
        passwords = json.loads(current_passwords_str)
    except json.JSONDecodeError:
        passwords = {}
    
    passwords[email] = password
    set_key(env_file, "SMTP_PASSWORDS", json.dumps(passwords))
    print(f"Password securely saved to .env")

    # 2. Update config.ini
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
    
    if not config.has_section('SMTP'):
        config.add_section('SMTP')
    
    # Format: host|port|email||security (password is empty in config)
    smtp_string = f"{host}|{port}|{email}||{security}"
    
    config.set('SMTP', 'smtp_servers', smtp_string)
    
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    
    print(f"Configuration updated. All other SMTPs removed.")
    
    # 3. Test the connection
    print("\nTesting connection...")
    try:
        sys.path.append(PROJECT_ROOT)
        from function.smtp_utils import test_smtp_connection
        # Create a temporary config dict for testing
        test_config = {"host": host, "port": int(port), "email": email, "password": password, "security": security}
        
        logger = logging.getLogger('reset_test')
        logger.addHandler(logging.StreamHandler())
        
        success, msg, _ = test_smtp_connection(test_config, logger)
        if success:
            print(f"\n[SUCCESS] Connected and authenticated successfully!")
        else:
            print(f"\n[FAILURE] Could not connect: {msg}")
    except Exception as e:
        print(f"Could not run test: {e}")

if __name__ == "__main__":
    reset_smtp()