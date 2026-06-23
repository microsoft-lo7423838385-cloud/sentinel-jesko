import os
import sys
import time
import subprocess
import configparser
import shutil
import sqlite3
import json
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.table import Table

try:
    from dotenv import set_key, find_dotenv, dotenv_values
except ImportError:
    set_key = find_dotenv = dotenv_values = None

# --- "World-Class" Fix: Correctly define the project root as the parent of the 'function' directory ---
# This ensures that scripts like 'main.py' are found in the correct location.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.ini')
CHOICE_FILE = os.path.join(PROJECT_ROOT, '.menuchoice')
DB_PATH = os.path.join(PROJECT_ROOT, 'logs', 'state.db')


def get_venv_python():
    venv_python = os.path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe')
    if os.path.exists(venv_python):
        return venv_python
    return sys.executable


def run_script(script_name, args=None):
    """
    A "world-class" script runner that executes a Python script as a subprocess,
    waits for it to complete, and handles potential console conflicts on Windows.
    """
    py = get_venv_python()
    cmd_parts = script_name.split(':')
    script_to_run = cmd_parts[0]
    script_path = os.path.join(PROJECT_ROOT, script_to_run)
    
    cmd = [py, script_path]
    
    # Add arguments from the script_name string (e.g., 'main.py:--fresh-start')
    if len(cmd_parts) > 1:
        cmd.extend(cmd_parts[1:])
    
    # Add arguments from the optional args list
    if args: cmd.extend(args)

    # "World-Class" Fix: Prevent console input conflicts with the main sender script.
    if 'main.py' in script_to_run:
        cmd.append('--no-listener')

    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"--- Running [bold cyan]{script_to_run}[/bold cyan]... ---")
    subprocess.run(cmd, cwd=PROJECT_ROOT)
    input("\n--- Script finished. Press Enter to return to the menu. ---")


def _update_env_passwords(email, password):
    """
    A "smarter" helper to securely add or update an SMTP password in the .env file.
    """
    if not all([set_key, find_dotenv, dotenv_values]):
        print("  -> [red]ERROR: 'python-dotenv' is not installed. Cannot securely save password.[/red]")
        return

    env_path = find_dotenv()
    if not env_path:
        env_path = os.path.join(PROJECT_ROOT, '.env')

    current_passwords_str = dotenv_values(env_path).get("SMTP_PASSWORDS", "{}")
    passwords = json.loads(current_passwords_str)
    passwords[email] = password
    set_key(env_path, "SMTP_PASSWORDS", json.dumps(passwords))
    print(f"  -> Securely updated password for {email} in .env file.")

def _edit_section(cfg, section_name):
    """Generic helper to edit a section in the config."""
    print(f'\nCurrent {section_name.upper()} settings:')
    for k, v in cfg[section_name].items():
        print(f"{k} = {v}")
    key = input('Enter key to change (or blank to cancel): ').strip()
    if key:
        val = input(f'New value for {key}: ')
        cfg[section_name][key] = val
        with open(CONFIG_PATH, 'w') as f:
            cfg.write(f)
        print('Saved.')


def auto_generate_smime_certs():
    """
    A "world-class" function to automatically scan all configured SMTPs
    and generate a unique S/MIME certificate for each one.
    """
    console = Console()
    console.print("\n--- [bold]Auto-Generate S/MIME Certificates[/bold] ---")

    # --- Find OpenSSL ---
    def find_openssl():
        path = shutil.which('openssl')
        if path: return path
        if sys.platform == 'win32':
            program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
            git_path = os.path.join(program_files, "Git", "usr", "bin", "openssl.exe")
            if os.path.exists(git_path): return git_path
        return None

    openssl_path = find_openssl()
    if not openssl_path:
        console.print("[red]ERROR: OpenSSL command not found. This feature cannot run.[/red]")
        input("Press Enter to return to the menu...")
        return

    console.print(f"Found OpenSSL at: [cyan]{openssl_path}[/cyan]")
    
    try:
        from function.smtp_utils import get_smtp_configs
        smtp_configs = get_smtp_configs()
    except ImportError:
        console.print("[red]ERROR: Could not load SMTP configurations.[/red]")
        return

    if not smtp_configs:
        console.print("[yellow]No SMTP servers are configured. Nothing to do.[/yellow]")
        return

    certs_dir = os.path.join(PROJECT_ROOT, 'certs')
    os.makedirs(certs_dir, exist_ok=True)
    
    console.print(f"\nScanning [bold]{len(smtp_configs)}[/bold] SMTP servers...")

    for smtp in smtp_configs:
        email_address = smtp.email
        # Sanitize email for use as a filename
        safe_filename = email_address.replace('@', '_at_').replace('.', '_')
        key_file = os.path.join(certs_dir, f"{safe_filename}.key.pem")
        cert_file = os.path.join(certs_dir, f"{safe_filename}.cert.pem")

        if os.path.exists(cert_file):
            console.print(f"  -> [green]SKIP:[/] Certificate for [cyan]{email_address}[/cyan] already exists.")
            continue

        console.print(f"  -> [yellow]CREATE:[/] Generating certificate for [cyan]{email_address}[/cyan]...")
        domain = email_address.split('@')[1]
        subj = f"/C=US/ST=State/L=City/O=MyOrg/OU=MyUnit/CN={domain}/emailAddress={email_address}"
        command = [
            openssl_path, 'req', '-x509', '-newkey', 'rsa:2048',
            '-keyout', key_file, '-out', cert_file,
            '-sha256', '-days', '365', '-nodes', '-subj', subj
        ]
        subprocess.run(command, capture_output=True) # Run silently

    console.print("\n[bold green]Certificate generation complete![/bold green]")
    console.print("The system will now automatically use the correct certificate when sending.")
    input("Press Enter to return to the menu...")

def guided_setup():
    """A wizard to configure the most important settings interactively."""
    print("\n--- Guided Setup Wizard ---")
    print("This will walk you through the most important settings.")

    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)

    # --- "World-Class" Auto-Repair: Ensure sections exist ---
    for sec in ['GENERAL', 'EMAIL', 'SMIME', 'AI']:
        if not cfg.has_section(sec):
            cfg.add_section(sec)

    # 1. Sending Method
    current_method = cfg.get('GENERAL', 'sending_method', fallback='smtp')
    print(f"\n[1] Sending Method (Current: {current_method.upper()})")
    print("  'smtp' - Standard email sending. (Recommended for most users)")
    print("  'ews'  - Microsoft Exchange Web Services. (Advanced, for high deliverability with Exchange accounts)")
    method = input(f"Choose sending method [smtp/ews] (press Enter to keep '{current_method}'): ").strip().lower()
    if method in ['smtp', 'ews']:
        # Section existence guaranteed above
        cfg.set('GENERAL', 'sending_method', method) 
        print(f"-> Sending method set to: {method.upper()}")

    # 2. File Paths
    print("\n[2] File Paths")
    current_recipients = cfg.get('GENERAL', 'recipients_file', fallback='recipients.txt')
    recipients_file = input(f"  Enter recipients file name (e.g., recipients.txt) (current: {current_recipients}): ").strip()
    if recipients_file:
        cfg.set('GENERAL', 'recipients_file', recipients_file)
        print(f"-> Recipients file set to: {recipients_file}")

    current_message = cfg.get('EMAIL', 'message_file', fallback='letter.html')
    message_file = input(f"  Enter message template file name (e.g., letter.html) (current: {current_message}): ").strip()
    if message_file:
        cfg.set('EMAIL', 'message_file', message_file)
        print(f"-> Message file set to: {message_file}")

    # 3. S/MIME Digital Signature
    print("\n[3] S/MIME Digital Signature (adds a 'verified' checkmark in some clients)")
    current_smime = cfg.getboolean('SMIME', 'smime_sign', fallback=False)
    enable_smime = input(f"Enable S/MIME signing? [y/n] (current: {'Yes' if current_smime else 'No'}): ").strip().lower()

    if enable_smime == 'y':
        if not cfg.has_section('SMIME'):
            cfg.add_section('SMIME')
        cfg.set('SMIME', 'smime_sign', 'true')
        print("-> S/MIME signing ENABLED.")
        print("   (Ensure you have generated certificates using the 'Auto-Generate S/MIME Certs' option.)")
    elif enable_smime == 'n':
        if not cfg.has_section('SMIME'):
            cfg.add_section('SMIME')
        cfg.set('SMIME', 'smime_sign', 'false')
        print("-> S/MIME signing DISABLED.")

    # Save all changes
    with open(CONFIG_PATH, 'w') as f:
        cfg.write(f)
    print("\nConfiguration saved successfully!")
    input("Press Enter to return to the menu...")

def select_delivery_strategy():
    """A new menu to allow the user to easily switch link delivery methods."""
    console = Console()
    cfg = configparser.ConfigParser(inline_comment_prefixes=('#',))
    cfg.read(CONFIG_PATH)

    strategies = {
        '1': 'direct',
        '2': 'secure_document',
        '3': 'safe_link'
    }
    
    while True:
        current_strategy = cfg.get('EMAIL', 'link_delivery_method', fallback='direct')
        console.print("\n--- [bold]Select Link Delivery Strategy[/bold] ---")
        console.print(f"Current Strategy: [bold yellow]{current_strategy.upper()}[/bold yellow]\n")
        console.print("1) [bold]Direct[/bold] - Standard link in email body. (Highest compatibility)")
        console.print("2) [bold]Secure Document[/bold] - Link embedded in a dynamically generated PDF attachment.")
        console.print("3) [bold]Safe Link[/bold] - Link embedded in an attached HTML redirect page (no external links in body).")
        console.print("0) Back to Configuration Menu")

        choice = input("Enter choice: ").strip()

        if choice in strategies:
            new_strategy = strategies[choice]
            cfg.set('EMAIL', 'link_delivery_method', new_strategy)
            with open(CONFIG_PATH, 'w') as f:
                cfg.write(f)
            console.print(f"\n[green]Success![/green] Delivery strategy set to [bold yellow]{new_strategy.upper()}[/bold yellow].")
            break 
        elif choice == '0':
            break
        else:
            console.print("[red]Invalid choice. Please try again.[/red]")

def ai_config_menu():
    """Menu to configure AI settings."""
    console = Console()
    cfg = configparser.ConfigParser(inline_comment_prefixes=('#',))
    cfg.read(CONFIG_PATH)
    
    if not cfg.has_section('AI'):
        cfg.add_section('AI')

    while True:
        # "Smarter" Fix: Load API key status securely from .env
        # Use dotenv_values to read the .env file without printing warnings for missing keys.
        env_path = find_dotenv()
        api_key_set = False
        if env_path and dotenv_values:
            env_vars = dotenv_values(env_path)
            # Check if the key exists and has a non-empty value
            api_key_set = "OPENAI_API_KEY" in env_vars and env_vars["OPENAI_API_KEY"]

        console.print("\n--- [bold purple]AI Content Engine[/bold purple] ---")
        ai_enabled = cfg.getboolean('AI', 'ai_enabled', fallback=False)
        rewrite_subject = cfg.getboolean('AI', 'ai_rewrite_subject', fallback=False)
        classify_replies = cfg.getboolean('AI', 'ai_classify_replies', fallback=False)
        generate_intro = cfg.getboolean('AI', 'ai_generate_intro', fallback=False)
        
        status_color = "green" if ai_enabled else "red"
        console.print(f"1) Toggle AI Engine (Currently: [{status_color}]{'ENABLED' if ai_enabled else 'DISABLED'}[/{status_color}])")
        console.print(f"2) Manage API Keys (OpenAI Key Status: {'[green]SET[/green]' if api_key_set else '[red]NOT SET[/red]'})")
        console.print(f"3) Toggle Subject Rewriting (Currently: {'[green]ON[/green]' if rewrite_subject else '[yellow]OFF[/yellow]'})")
        console.print(f"4) Toggle IMAP Reply Classifier (Currently: {'[green]ON[/green]' if classify_replies else '[yellow]OFF[/yellow]'})")
        console.print(f"5) Toggle Intro Sentence Generation (Currently: {'[green]ON[/green]' if generate_intro else '[yellow]OFF[/yellow]'})")
        console.print("0) Back")
        
        choice = input("Enter choice: ").strip()
        
        if choice == '1':
            cfg.set('AI', 'ai_enabled', str(int(not ai_enabled)))
        elif choice == '2':
            api_key_menu()
        elif choice == '3':
            cfg.set('AI', 'ai_rewrite_subject', str(int(not rewrite_subject)))
        elif choice == '4':
            cfg.set('AI', 'ai_classify_replies', str(int(not classify_replies)))
        elif choice == '5':
            cfg.set('AI', 'ai_generate_intro', str(int(not generate_intro)))
        elif choice == '0':
            break
            
        with open(CONFIG_PATH, 'w') as f:
            cfg.write(f)
        console.print("[green]AI settings updated.[/green]")

def api_key_menu():
    """A dedicated and secure menu for managing API keys in the .env file."""
    console = Console()
    if not all([set_key, find_dotenv, dotenv_values]):
        console.print("[red]ERROR: 'python-dotenv' is not installed. This feature is unavailable.[/red]")
        console.print("Please run 'pip install python-dotenv'.")
        return

    env_path = find_dotenv()
    if not env_path: # If .env doesn't exist, create it.
        with open(os.path.join(PROJECT_ROOT, '.env'), 'w') as f:
            f.write('')
        env_path = find_dotenv()

    while True:
        openai_key_set = False
        hunter_key_set = False
        if env_path and dotenv_values:
            env_vars = dotenv_values(env_path)
            openai_key_set = "OPENAI_API_KEY" in env_vars and env_vars["OPENAI_API_KEY"]
            hunter_key_set = "HUNTER_API_KEY" in env_vars and env_vars["HUNTER_API_KEY"]

        console.print("\n--- [bold]API Key Management[/bold] ---")
        console.print(f"1) Set OpenAI API Key (Status: {'[green]SET[/green]' if openai_key_set else '[red]NOT SET[/red]'})")
        console.print(f"2) Set Hunter.io API Key (Status: {'[green]SET[/green]' if hunter_key_set else '[red]NOT SET[/red]'})")
        console.print("0) Back")
        choice = input("Enter choice: ").strip()

        if choice == '1':
            key = input("Enter your OpenAI API Key: ").strip()
            if key: set_key(env_path, "OPENAI_API_KEY", key)
        elif choice == '2':
            key = input("Enter your Hunter.io API Key: ").strip()
            if key: set_key(env_path, "HUNTER_API_KEY", key)
        elif choice == '0':
            break

def eml_settings_menu():
    """A new menu to manage the EML forwarding strategy."""
    console = Console()
    cfg = configparser.ConfigParser(inline_comment_prefixes=('#',))
    cfg.read(CONFIG_PATH)

    if not cfg.has_section('EML'):
        cfg.add_section('EML')

    while True:
        console.print("\n--- [bold]EML Forwarding Settings[/bold] ---")
        eml_enabled = cfg.getboolean('EML', 'eml_enabled', fallback=False)
        attachment_name = cfg.get('EML', 'eml_attachment_name', fallback='Forwarded Message')
        from_name = cfg.get('EML', 'eml_from_name', fallback='Support')
        
        console.print(f"1) Toggle EML Forwarding (Currently: {'[green]ENABLED[/green]' if eml_enabled else '[yellow]DISABLED[/yellow]'})")
        console.print(f"2) Edit Attachment Name (Currently: '{attachment_name}')")
        console.print(f"3) Edit Wrapper 'From' Name (Currently: '{from_name}')")
        console.print("0) Back")
        choice_eml = input("Enter choice: ").strip()
        if choice_eml == '1':
            cfg.set('EML', 'eml_enabled', '0' if eml_enabled else '1')
        elif choice_eml == '2':
            nn = input(f"Enter new attachment name: ").strip()
            if nn: cfg.set('EML', 'eml_attachment_name', nn)
        elif choice_eml == '3':
            nfn = input(f"Enter new 'From' name: ").strip()
            if nfn: cfg.set('EML', 'eml_from_name', nfn)
        elif choice_eml == '0':
            break
        with open(CONFIG_PATH, 'w') as f:
            cfg.write(f)
        console.print("[green]Settings updated.[/green]")

def edit_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    while True:
        print('\n--- Edit Configuration ---')
        print('1) General settings')
        print('2) Sender settings')
        print('3) Email settings')
        print('4) Attachment settings')
        print('5) SMTP servers (list/add/remove)')
        print('6) Proxy settings')
        print('7) Dev and misc')
        print('0) Back')
        choice = input('Choice: ').strip()
        if choice == '1':
            _edit_section(cfg, 'GENERAL')
        elif choice == '2':
            _edit_section(cfg, 'SENDER')
        elif choice == '3':
            _edit_section(cfg, 'EMAIL')
        elif choice == '4':
            _edit_section(cfg, 'ATTACHMENT')
        elif choice == '5':
            sep = cfg.get('MISC', 'CONFIG_SEPARATOR', fallback='::')
            smtp_str = cfg.get('SMTP', 'SMTP_SERVERS', fallback='')
            entries = [e for e in smtp_str.split(sep) if e.strip()]
            print('\nCurrent SMTP entries:')
            for i,e in enumerate(entries,1):
                print(f"{i}) {e}")
            print('\na) Add entry')
            print('s) Smart Add (bulk, auto-detects settings)')
            print('r) Remove entry')
            sub = input('Choice: ').strip().lower()
            if sub == 'a':
                print('\n--- Manual Add SMTP ---')
                host = input('Host: ').strip()
                port = input('Port: ').strip()
                email = input('Email: ').strip()
                password = input('Password: ').strip()
                security = input('Security (ssl, starttls, none) [auto]: ').strip().lower() or 'auto'
                
                if all([host, port, email, password]):
                    # Add the password to the .env file
                    _update_env_passwords(email, password)
                    # --- "World-Class" Security Fix: Do NOT write the password to config.ini ---
                    # The empty field between email and security is where the password used to be.
                    new_entry = f"{host}|{port}|{email}||{security}"
                    entries.append(new_entry)
                    cfg['SMTP']['SMTP_SERVERS'] = sep.join(entries)
                    with open(CONFIG_PATH, 'w') as f:
                        cfg.write(f)
                    print('Added SMTP entry to config.ini.')
                else:
                    print("Cancelled. All fields are required.")
            elif sub == 'r':
                idx = input('Index to remove: ').strip()
                try:
                    i = int(idx)-1
                    entries.pop(i)
                    cfg['SMTP']['SMTP_SERVERS'] = sep.join(entries)
                    with open(CONFIG_PATH, 'w') as f:
                        cfg.write(f)
                    print('Removed.')
                except Exception:
                    print('Invalid index')
            elif sub == 's':
                print('\n--- Smart Add SMTP ---')
                print('Enter one or more SMTP credentials. Format: email:password')
                print('Enter a blank line when you are finished.')
                
                new_creds = []
                while True:
                    line = input('Enter credential (or blank to finish): ').strip()
                    if not line:
                        break
                    new_creds.append(line)

                if not new_creds:
                    continue

                try:
                    from smtp_utils import discover_smtp_settings, test_smtp_connection
                    import logging
                    
                    # Create a temporary logger for the test
                    test_logger = logging.getLogger('smart_add_test')
                    test_logger.setLevel(logging.INFO) # Show discovery progress
                    if not test_logger.handlers:
                        test_logger.addHandler(logging.StreamHandler())
                    
                    added_count = 0
                    deferred_creds = []

                    def attempt_smart_add(cred_str, is_deferred_pass=False):
                        nonlocal added_count
                        if ':' not in cred_str:
                            print(f"  -> [red]Invalid format for '{cred_str}'. Skipping.[/red]")
                            return
                        
                        email, password = cred_str.split(':', 1)
                        email, password = email.strip(), password.strip()
                        
                        # Call discovery which returns (config_dict, error_msg)
                        config_dict, error_msg = discover_smtp_settings(email, password, logger=test_logger)
                        
                        if config_dict:
                            print(f"  -> [green]Success![/green] Discovered and verified settings for {email}.")
                            _update_env_passwords(email, password)
                            new_entry = f"{config_dict['host']}|{config_dict['port']}|{config_dict['email']}|{config_dict['security']}"
                            entries.append(new_entry)
                            added_count += 1
                        else:
                            # If it requires an App Password, defer it if we haven't already
                            if not is_deferred_pass and error_msg and "App Password" in error_msg:
                                print(f"  -> [yellow]Deferred:[/] {email} requires an App Password. Moving to end of list.")
                                deferred_creds.append(cred_str)
                                return
                            print(f"  -> [red]Failed for {email}:[/red] {error_msg}")

                    # Pass 1: Attempt to add all credentials, deferring those needing App Passwords
                    for cred in new_creds:
                        attempt_smart_add(cred)

                    # Pass 2: Re-process deferred accounts at the very end
                    if deferred_creds:
                        print(f"\n--- [bold yellow]Processing {len(deferred_creds)} Deferred Account(s)[/bold yellow] ---")
                        print("These require an 'App Password'. Enter it now, or leave blank to skip.")
                        for deferred_cred in deferred_creds:
                            email = deferred_cred.split(':')[0].strip()
                            new_pass = input(f"Enter App Password for {email} (or blank to skip): ").strip()
                            if new_pass:
                                attempt_smart_add(f"{email}:{new_pass}", is_deferred_pass=True)
                    
                    if added_count > 0:
                        cfg['SMTP']['SMTP_SERVERS'] = sep.join(entries)
                        with open(CONFIG_PATH, 'w') as f:
                            cfg.write(f)
                        print(f"\nSuccessfully added {added_count} new SMTP server(s).")
                    else:
                        print("\nNo new SMTP servers were added.")
                except ImportError:
                    print("ERROR: Could not import 'discover_smtp_settings'. Feature unavailable.")
        elif choice == '6':
            # This is the proxy settings menu
            while True:
                print('\n--- Proxy Settings ---')
                proxy_enabled = cfg.getboolean('PROXY', 'proxy_enabled', fallback=False)
                status = "ENABLED" if proxy_enabled else "DISABLED"
                print(f"1) Toggle Proxies (Currently: {status})")
                print("2) Edit Proxy List (manual)")
                print("3) Edit Proxy URL (for auto-fetching)")
                print("4) Set proxy site credentials")
                print("0) Back to main config menu")
                
                proxy_choice = input("Choice: ").strip()

                if proxy_choice == '1':
                    new_status = not proxy_enabled
                    cfg.set('PROXY', 'proxy_enabled', '1' if new_status else '0')
                    with open(CONFIG_PATH, 'w') as f:
                        cfg.write(f)
                    print(f"-> Proxies are now {'ENABLED' if new_status else 'DISABLED'}.")
                elif proxy_choice == '2':
                    print("\nCurrent Proxy List:", cfg.get('PROXY', 'proxy_list', fallback=''))
                    new_list = input("Enter new proxy list (or blank to keep current): ").strip()
                    if new_list:
                        cfg.set('PROXY', 'proxy_list', new_list)
                        with open(CONFIG_PATH, 'w') as f:
                            cfg.write(f)
                        print("-> Proxy list updated.")
                elif proxy_choice == '3':
                    print("\nCurrent Proxy URL:", cfg.get('PROXY', 'proxy_url', fallback=''))
                    new_url = input("Enter new proxy URL (or blank to clear): ").strip()
                    cfg.set('PROXY', 'proxy_url', new_url)
                    with open(CONFIG_PATH, 'w') as f:
                        cfg.write(f)
                    print("-> Proxy URL updated.")
                elif proxy_choice == '4':
                    print("\nCurrent Site Username:", cfg.get('PROXY', 'proxy_site_username', fallback=''))
                    new_user = input("Enter new proxy site username (or blank to clear): ").strip()
                    if new_user != '':
                        cfg.set('PROXY', 'proxy_site_username', new_user)
                    print("\nCurrent Site Password:", "(hidden)" if cfg.get('PROXY', 'proxy_site_password', fallback='') else "(none)")
                    new_pass = input("Enter new proxy site password (or blank to clear): ").strip()
                    if new_pass != '':
                        cfg.set('PROXY', 'proxy_site_password', new_pass)
                    with open(CONFIG_PATH, 'w') as f:
                        cfg.write(f)
                    print("-> Proxy site credentials updated.")
                elif proxy_choice == '0':
                    break
                else:
                    print("Invalid choice.")
        elif choice == '7':
            _edit_section(cfg, 'DEV')
            _edit_section(cfg, 'MISC')
        elif choice == '0':
            break
        else:
            print('Unknown')


def imap_scan():
    # run the imap-scan command
    run_script('main.py', ['--imap-scan'])


def reset_smtp_state():
    run_script('main.py', ['--reset-smtp-state'])


def reenable_smtps():
    run_script('main.py', ['--reenable-smtps'])


def view_logs():
    logs = os.path.join(PROJECT_ROOT, 'logs')
    if os.path.exists(logs):
        if sys.platform == 'win32':
            os.startfile(logs)
        else:
            subprocess.run(['xdg-open', logs])
    else:
        print('No logs directory yet.')


def view_smtp_state():
    # Show a table of SMTP entries, usage and state. Color rows: red=disabled, yellow=near/at limit or failing, green=ok
    from rich.table import Table
    import datetime as _dt
    import sqlite3

    # Import the centralized SMTP parsing function
    try:
        from function.smtp_utils import get_smtp_configs
    except ImportError:
        print("\nERROR: Could not import 'get_smtp_configs' from 'function/smtp_utils.py'.")
        return

    # --- "World-Class" Fix: Read state directly from the database ---
    db_state = {}
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT smtp_id, sent_count, fail_count, disabled_until FROM smtp_state")
            for row in cursor.fetchall():
                db_state[row[0]] = {'sent_count': row[1], 'fail_count': row[2], 'disabled_until': row[3]}
            conn.close()
        except Exception as e:
            print(f"[red]Could not read from database: {e}[/red]")

    # Use the centralized function to get all configured SMTPs
    configured_smtps = get_smtp_configs()

    rows = []
    for config in configured_smtps:
        key = f"{config.host}:{config.port}:{config.email}"
        smtp_db_state = db_state.get(key, {})
        sent_count = smtp_db_state.get('sent_count', 0)
        fail_count = smtp_db_state.get('fail_count', 0)
        disabled_until = smtp_db_state.get('disabled_until')
        disabled = False
        time_left = ""
        if disabled_until:
            disabled_ts = float(disabled_until)
            if _dt.datetime.now().timestamp() < disabled_ts:
                disabled = True
                time_left_seconds = max(0, disabled_ts - _dt.datetime.now().timestamp())
                time_left = f"{int(time_left_seconds // 60)}m {int(time_left_seconds % 60)}s"

        rows.append({
            'host': config.host,
            'port': config.port,
            'email': config.email,
            'limit': config.limit,
            'sent': sent_count,
            'fail_count': fail_count,
            'disabled': disabled,
            'disabled_until': disabled_until,
            'time_left': time_left,
        })

    # --- "Smarter" Rich Table ---
    console = Console()
    table = Table(title="[bold]SMTP Server State[/bold]", show_header=True, header_style="bold magenta")
    table.add_column("Host", style="cyan", no_wrap=True)
    table.add_column("Port", justify="right")
    table.add_column("Email", style="green")
    table.add_column("Limit", justify="right")
    table.add_column("Sent", justify="right")
    table.add_column("Fails", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Time Left", justify="center")

    for r in rows:
        status_text = "[green]OK[/green]"
        if r['disabled']:
            status_text = "[bold red]DISABLED[/bold red]"
        elif r['limit'] and r['sent'] >= r['limit']:
            status_text = "[yellow]AT LIMIT[/yellow]"
        elif r['fail_count'] > 0:
            status_text = f"[yellow]FAILING ({r['fail_count']})[/yellow]"
        
        table.add_row(r['host'], str(r['port']), r['email'], str(r['limit']), str(r['sent']), str(r['fail_count']), status_text, r['time_left'])

    if not configured_smtps:
        print('No SMTP entries found in config.')
    else:
        console.print(table)


def check_isp_port_blocking():
    """Checks if common SMTP ports are blocked by the ISP or Firewall."""
    import socket
    console = Console()
    console.print("\n--- [bold]ISP Port Connectivity Test[/bold] ---")
    console.print("Testing outbound connections to common mail relay points...\n")

    # Test targets: A mix of Google and Microsoft as they are standard
    targets = [
        ("smtp.gmail.com", 587, "STARTTLS"),
        ("smtp.gmail.com", 465, "SSL"),
        ("smtp.office365.com", 587, "Office 365"),
        ("outlook.office365.com", 993, "O365 IMAP"),
        ("mail.protection.outlook.com", 25, "O365 Direct"),
        ("smtp.mail.yahoo.com", 465, "Yahoo SSL"),
        ("relay.jangosmtp.net", 2525, "Alt Port 2525")
    ]

    for host, port, label in targets:
        try:
            with socket.create_connection((host, port), timeout=5):
                status = "[green]OPEN (Success)[/green]"
        except (socket.timeout, ConnectionRefusedError, OSError):
            status = "[red]BLOCKED (Failed)[/red]"
        
        console.print(f"  {label.ljust(15)} ({host}:{port}): {status}")

    console.print("\n[yellow]Advice:[/yellow]")
    console.print(" - You are connected via [bold cyan]VPN[/bold cyan]. If Gmail works but Office 365 fails, the VPN IP is likely blacklisted.")
    console.print(" - Try switching your VPN region to a [bold]Residential[/bold] or [bold]dedicated IP[/bold] if possible.")
    console.print(" - If 587/465 are [red]BLOCKED[/red], try using port [bold]2525[/bold] if your provider supports it.")
    console.print(" - Blocked ports will prevent the 'Smart Add' and 'Discovery' features from working.")
    input("\nPress Enter to return to diagnostics...")


def live_smtp_dashboard():
    """Shows a live, auto-refreshing dashboard of SMTP state."""
    import time
    
    # Helper to clear the console screen
    def clear_screen():
        os.system('cls' if os.name == 'nt' else 'clear')

    try:
        while True:
            clear_screen()
            print("--- Live Performance Dashboard (Press Ctrl+C to exit) ---")
            print(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}")

            # --- New: Read and display performance stats ---
            perf_file = os.path.join(PROJECT_ROOT, 'logs', 'performance.json')
            if os.path.exists(perf_file):
                try:
                    with open(perf_file, 'r') as f:
                        stats = json.load(f)
                    spm = stats.get('sends_per_minute', 0)
                    sleep = stats.get('dynamic_sleep_time', 'N/A')
                    sent = stats.get('sends_completed', 0)
                    failed = stats.get('failures', 0)
                    print("\n[ Performance Metrics ]")
                    print(f"  Throughput: {spm} sends/min")
                    print(f"  Throttle Delay: {sleep}s")
                    print(f"  Sent: {sent} | Failed: {failed}")
                except (json.JSONDecodeError, KeyError):
                    print("\nWaiting for performance data...")
            
            # Reuse the existing view_smtp_state logic
            view_smtp_state()
            
            print("\nRefreshing in 5 seconds...")
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nExiting dashboard.")
        return
    except ImportError as e:
        print(f"\nERROR: A required library is missing: {e}")
        print("Dashboard cannot run.")
        return
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        return


def view_smtp_pool():
    """Initialize the SMTP pool using function/smtp_utils and display the currently usable SMTPs."""
    print('\n--- Live SMTP pool (initializing and testing) ---')
    try:
        import logging
        from function.smtp_utils import initialize_smtp_pool
    except Exception as e:
        print('Error importing smtp_utils:', e)
        print('Ensure function/smtp_utils.py exists and is importable.')
        return

    # create a small temporary logger that prints to console
    logger = logging.getLogger('menu_smtp_pool')
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        logger.addHandler(ch)

    try:
        pool = initialize_smtp_pool(logger)
    except Exception as e:
        print('Error while initializing SMTP pool:', e)
        return

    if not pool:
        print('No usable SMTP servers found (pool is empty).')
        return

    # Print the pool in a readable format
    print('\nUsable SMTP servers:')
    for i, s in enumerate(pool, start=1):
        host = s.host
        port = s.port
        email = s.email
        sent = s.sent_count
        limit = s.limit
        transport = s.transport
        fail_count = s.fail_count
        print(f"{i}) {host}:{port}  user={email}  sent={sent} limit={limit} transport={transport} fails={fail_count}")


def dry_run_n():
    print('\n--- Dry-run (preview) ---')
    n = input('How many recipients to dry-run (enter 0 to cancel): ').strip()
    try:
        n_val = int(n)
        if n_val <= 0:
            print('Cancelled or zero specified')
            return
    except Exception:
        print('Invalid number')
        return

    # Pass dry-run argument to main.py. main.py should support '--dry-run N' or fall back to DEV_MODE
    run_script('main.py', [f'--dry-run={n_val}'])


def clear_sent_history():
    """Deletes the sent_recipients.txt log file to allow resending to all recipients."""
    print("\n--- Clear Sent History ---")
    sent_log_path = os.path.join(PROJECT_ROOT, 'logs', 'sent_recipients.txt')
    
    if not os.path.exists(sent_log_path):
        print("Sent history log (sent_recipients.txt) does not exist. Nothing to clear.")
        input("Press Enter to continue...")
        return

    confirm = input(f"This will delete the sent history log, allowing you to resend to all recipients in your list.\nAre you sure? [y/n]: ").strip().lower()
    if confirm == 'y':
        try:
            os.remove(sent_log_path)
            print("Successfully cleared sent history.")
        except Exception as e:
            print(f"ERROR: Could not delete file. Reason: {e}")
    else:
        print("Operation cancelled.")
    input("Press Enter to continue...")


def view_suppression_list():
    """Opens the suppression list file for viewing/editing."""
    print("\n--- View/Edit Suppression List ---")
    suppression_list_path = os.path.join(PROJECT_ROOT, 'logs', 'suppression_list.txt')
    
    if not os.path.exists(suppression_list_path):
        print("Suppression list (suppression_list.txt) does not exist yet. It will be created when an email hard-bounces.")
    else:
        print(f"Opening {suppression_list_path}...")
        if sys.platform == 'win32':
            os.startfile(suppression_list_path)
        else:
            # For macOS/Linux, try to open with the default text editor
            subprocess.run(['open', suppression_list_path] if sys.platform == 'darwin' else ['xdg-open', suppression_list_path])
    input("Press Enter to continue...")


def clear_campaign_state():
    """
    A "world-class" function to safely clear all campaign state without deleting the DB file itself.
    This avoids file lock errors on Windows. It clears the relevant tables and other log files.
    """
    logs_dir = os.path.join(PROJECT_ROOT, 'logs')
    cleanup_ok = True

    # 1. Clear database tables
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            print("[yellow]Clearing database tables (sent_log, smtp_state)...[/yellow]")
            cursor.execute("DELETE FROM sent_log")
            cursor.execute("DELETE FROM smtp_state")
            conn.commit()
            # Vacuum shrinks the database file after deletion
            print("[yellow]Compacting database...[/yellow]")
            cursor.execute("VACUUM")
            conn.commit()
            conn.close()
            print("[green]Database tables cleared successfully.[/green]")
        except Exception as e:
            print(f"[red]Could not clear database tables: {e}[/red]")
            cleanup_ok = False

    # 2. Clear other log files, but keep the DB and the directory
    if os.path.exists(logs_dir):
        print("[yellow]Clearing other log files (sender.log, performance.json, etc.)...[/yellow]")
        for filename in os.listdir(logs_dir):
            # Don't delete the database file itself or subdirectories
            file_path = os.path.join(logs_dir, filename)
            if filename != os.path.basename(DB_PATH) and os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    print(f"  - Deleted {filename}")
                except Exception as e:
                    print(f"[red]Could not delete log file {filename}: {e}[/red]")
    return cleanup_ok

def campaign_menu():
    """Sub-menu for campaign-related actions."""
    while True:
        console = Console()
        menu_table = Table.grid(padding=(0, 2))
        menu_table.add_column(style="green")
        menu_table.add_row('1)', 'Start Fresh Campaign (clears logs, recommended)')
        menu_table.add_row('2)', 'Resume Campaign (skips already sent)')
        menu_table.add_row('3)', 'Test SMTPs & Send Fresh Campaign')
        menu_table.add_row('4)', 'Dry-run N recipients (preview)')
        menu_table.add_row('5)', 'Run Deliverability/Inbox Test (e.g., mail-tester.com)')
        menu_table.add_row('6)', 'Generate HTML Click Report')
        menu_table.add_row('0)', 'Back to Main Menu')
        console.print(Panel(menu_table, title="[bold cyan]Campaign Management[/bold cyan]", border_style="cyan"))
        choice = input('Enter choice: ').strip()

        if choice == '1':
            # --- "World-Class" Intelligent Warm-up Prompt ---
            # Check if warm-up is configured but disabled, and offer to enable it.
            # This directly addresses high spam confidence scores.
            cfg = configparser.ConfigParser()
            cfg.read(CONFIG_PATH)
            warmup_enabled = cfg.getboolean('WARMUP', 'warmup_enabled', fallback=False)
            if not warmup_enabled:
                prompt = (
                    "\n[yellow]Your emails may be landing in spam due to a high 'Spam Confidence Level'.[/yellow]\n"
                    "Enabling [bold]Warm-up Mode[/bold] sends plain-text emails initially to build trust and lower your spam score.\n\n"
                    "Would you like to enable Warm-up Mode for this campaign? [y/n]: "
                )
                if input(prompt).strip().lower() == 'y':
                    cfg.set('WARMUP', 'warmup_enabled', '1')
                    with open(CONFIG_PATH, 'w') as f:
                        cfg.write(f)
                    print("[green]Warm-up Mode has been ENABLED for this campaign.[/green]")

            # "Smarter" Fresh Start: Use a safe cleanup function to avoid file locks.
            print("[yellow]Clearing state for a fresh campaign...[/yellow]")
            cleanup_ok = clear_campaign_state()

            if cleanup_ok:
                run_script('main.py:--fresh-start')
        elif choice == '2':
            run_script('main.py')
        elif choice == '3':
            # "Smarter" Fix: This option should also be a "fresh start" as described.
            print("[yellow]Clearing state for a fresh campaign...[/yellow]")
            cleanup_ok = clear_campaign_state()
            if not cleanup_ok:
                print("[red]State clearing failed. Aborting campaign start.[/red]")
                continue # Abort this choice if cleanup fails

            # "World-Class" Multi-Step Execution
            run_script('bulk_smtp_tester.py')
            run_script('main.py:--fresh-start')
        elif choice == '4':
            dry_run_n()
        elif choice == '5':
            run_script('main.py:deliverability-test')
        elif choice == '6':
            # This script doesn't exist yet, but the framework is here.
            print("[yellow]Report generator is not yet implemented.[/yellow]")
        elif choice == '0':
            break
        else:
            print('Unknown choice')

def config_menu():
    """Sub-menu for configuration and setup."""
    while True:
        console = Console()
        menu_table = Table.grid(padding=(0, 2))
        menu_table.add_column(style="yellow")
        menu_table.add_row('1)', 'Guided Setup [green](Recommended for first-time use)[/green]')
        menu_table.add_row('2)', 'Advanced Configuration (Edit all settings)')
        menu_table.add_row('3)', '[bold cyan]S/MIME: Auto-Generate Certs (for all SMTPs)[/bold cyan]')
        menu_table.add_row('4)', '[bold]DKIM Key Manager[/bold]')
        menu_table.add_row('5)', '[bold cyan]Select Link Delivery Strategy[/bold cyan]')
        menu_table.add_row('6)', '[bold]EML Forwarding Settings[/bold]')
        menu_table.add_row('7)', '[bold purple]AI Content Engine[/bold purple]')
        menu_table.add_row('0)', 'Back to Main Menu')
        console.print(Panel(menu_table, title="[bold yellow]Configuration & Setup[/bold yellow]", border_style="yellow"))
        choice = input('Enter choice: ').strip()

        if choice == '1':
            guided_setup()
        elif choice == '2':
            edit_config()
        elif choice == '3':
            auto_generate_smime_certs()
        elif choice == '4':
            run_script('dkim_manager.py')
        elif choice == '5':
            select_delivery_strategy()
        elif choice == '6':
            eml_settings_menu()
        elif choice == '7':
            ai_config_menu()
        elif choice == '0':
            break
        else:
            print('Unknown choice')

def diagnostics_menu():
    """Sub-menu for diagnostics and testing tools."""
    while True:
        console = Console()
        menu_table = Table.grid(padding=(0, 2))
        menu_table.add_column(style="cyan")
        menu_table.add_row('1)', 'Validate Configuration')
        menu_table.add_row('2)', 'Test SMTPs Only')
        menu_table.add_row('3)', 'Live SMTP Dashboard (Auto-refreshing)')
        menu_table.add_row('4)', 'View SMTP State (Static)')
        menu_table.add_row('5)', 'DNS & Domain Health Check')
        menu_table.add_row('6)', 'Test Custom Tracking Link')
        menu_table.add_row('7)', '[bold yellow]Check ISP Port Blocking[/bold yellow]')
        menu_table.add_row('8)', 'Test Zapier Webhook')
        menu_table.add_row('9)', 'View Logs Folder')
        menu_table.add_row('9)', '[bold green]Final Integration Test (AI + Email)[/bold green]')
        menu_table.add_row('0)', 'Back to Main Menu')
        console.print(Panel(menu_table, title="[bold cyan]Diagnostics & Tools[/bold cyan]", border_style="cyan"))
        choice = input('Enter choice: ').strip()

        if choice == '1':
            run_script('config_validator.py')
        elif choice == '2':
            run_script('bulk_smtp_tester.py')
        elif choice == '3':
            live_smtp_dashboard()
        elif choice == '4':
            view_smtp_state()
        elif choice == '5':
            run_script('dns_checker.py')
        elif choice == '6':
            run_script('link_tester.py')
        elif choice == '7':
            check_isp_port_blocking()
        elif choice == '8':
            run_script('test_zapier.py')
        elif choice == '9':
            view_logs()
        elif choice == '10':
            run_script('final_test.py')
        elif choice == '0':
            break
        else:
            print('Unknown choice')

def data_menu():
    """Sub-menu for data and state management."""
    while True:
        console = Console()
        menu_table = Table.grid(padding=(0, 2))
        menu_table.add_column(style="blue")
        menu_table.add_row('1)', 'IMAP Bounce Scan')
        menu_table.add_row('2)', 'View Suppression List')
        menu_table.add_row('3)', 'Initialize/Reset Database [yellow](Warning: Deletes all state)[/yellow]')
        menu_table.add_row('4)', 'Migrate Old State to Database')
        menu_table.add_row('12)', '[dim]Reset SMTP State (Legacy)[/dim]')
        menu_table.add_row('13)', '[dim]Re-enable SMTPs (Legacy)[/dim]')
        menu_table.add_row('14)', '[dim]Clear Sent History (Legacy)[/dim]')
        menu_table.add_row('0)', 'Back to Main Menu')
        console.print(Panel(menu_table, title="[bold blue]Data & State Management[/bold blue]", border_style="blue"))
        choice = input('Enter choice: ').strip()

        if choice == '1':
            imap_scan()
        elif choice == '2':
            view_suppression_list()
        elif choice == '3':
            run_script('database_manager.py')
        elif choice == '4':
            run_script('migrate_state.py')
        elif choice == '12':
            reset_smtp_state()
        elif choice == '13':
            reenable_smtps()
        elif choice == '14':
            clear_sent_history()
        elif choice == '0':
            break
        else:
            print('Unknown choice')

def toggle_warmup_mode():
    """Cycles through warmup modes: DISABLED, SEMI (HTML+Text), FULL (Text Only)."""
    console = Console()
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)

    if not cfg.has_section('WARMUP'):
        cfg.add_section('WARMUP')

    enabled = cfg.getboolean('WARMUP', 'warmup_enabled', fallback=False)
    plain_text_only = cfg.getboolean('WARMUP', 'warmup_plain_text_only', fallback=False)

    # Determine current mode
    if not enabled:
        current_mode = 'DISABLED'
        # Next mode is SEMI
        new_enabled, new_plain_text_only = True, False
        new_mode_text = "[bold yellow]SEMI (HTML + Text)[/bold yellow]"
        new_mode_desc = "The next campaign will send standard multipart emails (HTML and plain text) with normal warm-up limits."
        # Ensure limits are reset if coming from a high-volume text campaign
        cfg.set('WARMUP', 'warmup_daily_start', '50')
        cfg.set('WARMUP', 'warmup_target_sends', '500')
    elif enabled and not plain_text_only:
        current_mode = 'SEMI'
        # Next mode is FULL
        new_enabled, new_plain_text_only = True, True
        new_mode_text = "[bold red]FULL (Text Only)[/bold red]"
        new_mode_desc = "The next campaign will send ONLY plain-text emails. This is ideal for large campaigns or building reputation."
        # --- "World-Class" High-Volume Text Mode ---
        # To support large text-only campaigns, we dramatically increase the daily limits.
        cfg.set('WARMUP', 'warmup_daily_start', '5000')
        cfg.set('WARMUP', 'warmup_target_sends', '5000')
        new_mode_desc += "\n[bold cyan]Daily sending limits have been temporarily increased to 5000 for this mode.[/bold cyan]"
    else: # enabled and plain_text_only
        current_mode = 'FULL'
        # Next mode is DISABLED
        new_enabled, new_plain_text_only = False, False
        new_mode_text = "[bold green]DISABLED[/bold green]"
        new_mode_desc = "The next campaign will send full HTML emails immediately."
        # Reset limits back to default when disabling warm-up
        cfg.set('WARMUP', 'warmup_daily_start', '50')
        cfg.set('WARMUP', 'warmup_target_sends', '500')
    
    cfg.set('WARMUP', 'warmup_enabled', '1' if new_enabled else '0')
    cfg.set('WARMUP', 'warmup_plain_text_only', '1' if new_plain_text_only else '0')
    
    with open(CONFIG_PATH, 'w') as f:
        cfg.write(f)
        
    console.print(f"\n[green]Warm-up strategy changed to {new_mode_text}.[/green]")
    console.print(new_mode_desc)
    
    import time
    time.sleep(3)

def display_status_dashboard():
    """A 'smart' function to read config and state to display a live dashboard."""
    from rich.columns import Columns
    console = Console()

    cfg = configparser.ConfigParser(inline_comment_prefixes=('#',))
    cfg.read(CONFIG_PATH)

    # Helper to format status
    def get_status(enabled):
        return "[green]ENABLED[/green]" if enabled else "[yellow]DISABLED[/yellow]"

    # 1. Recipients Status
    recipients_file = cfg.get('GENERAL', 'recipients_file', fallback='recipients.txt')
    recipients_path = os.path.join(PROJECT_ROOT, recipients_file)
    rec_count = 0
    if os.path.exists(recipients_path):
        with open(recipients_path, 'r', encoding='utf-8') as f:
            rec_count = sum(1 for line in f if line.strip())
    
    sent_count = 0
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sent_log")
            sent_count = cursor.fetchone()[0]
            conn.close()
        except Exception:
            sent_count = 'N/A'

    recipients_panel_content = f"[cyan]Recipients File:[/] [white]{recipients_file}[/]\n[cyan]Recipients Loaded:[/] [white]{rec_count}[/]\n[cyan]Total Sent (DB):[/] [white]{sent_count}[/]"

    # 2. SMTP Status
    smtp_str = cfg.get('SMTP', 'smtp_servers', fallback='')
    sep = cfg.get('MISC', 'config_separator', fallback='::')
    smtp_count = len([s for s in smtp_str.split(sep) if s.strip()])

    # 3. Key Feature Status
    dkim_status = get_status(cfg.getboolean('DKIM', 'dkim_enabled', fallback=False))
    smime_status = get_status(cfg.getboolean('SMIME', 'smime_sign', fallback=False))
    verify_status = get_status(cfg.getboolean('DEV', 'verify_emails_before_send', fallback=False))
    proxy_status = get_status(cfg.getboolean('PROXY', 'proxy_enabled', fallback=False))
    
    # "Smarter" Warmup Status Display
    warmup_enabled = cfg.getboolean('WARMUP', 'warmup_enabled', fallback=False)
    plain_text_only = cfg.getboolean('WARMUP', 'warmup_plain_text_only', fallback=False)
    if not warmup_enabled:
        warmup_status = "[green]DISABLED[/green]"
    elif warmup_enabled and not plain_text_only:
        warmup_status = "[yellow]SEMI (HTML+Text)[/yellow]"
    else:
        warmup_status = "[red]FULL (Text Only)[/red]"

    features_panel_content = (
        f"[cyan]SMTP Servers:[/] [white]{smtp_count}[/]\n"
        f"[cyan]DKIM Signing:[/] {dkim_status}\n"
        f"[cyan]S/MIME Signing:[/] {smime_status}\n"
        f"[cyan]Email Verification:[/] {verify_status}\n"
        f"[cyan]Proxy Enabled:[/] {proxy_status}"
    )
    
    warmup_panel_content = f"[cyan]Current Mode:[/] {warmup_status}"

    # Create panels
    panel1 = Panel(recipients_panel_content, title="[bold blue]System Status[/]", border_style="blue", expand=True)
    panel2 = Panel(features_panel_content, title="[bold blue]Feature Status[/]", border_style="blue", expand=True)
    panel3 = Panel(warmup_panel_content, title="[bold blue]Warm-up Strategy[/]", border_style="blue", expand=True)

    console.print(Columns([panel1, panel2, panel3]))

def main_menu():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        display_status_dashboard()
        
        menu_table = Table.grid(padding=(0, 3))
        menu_table.add_column(style="bold", no_wrap=True)
        menu_table.add_row("1) [green]Campaign Management[/green]", "2) [cyan]Diagnostics & Tools[/cyan]", "3) [yellow]Configuration & Setup[/yellow]")
        menu_table.add_row("4) [blue]Data & State Management[/blue]", "5) [bold]Toggle Warm-up Mode[/bold]", "0) [red]Exit[/red]")
        
        print(Panel(menu_table, title="[bold]Main Menu[/bold]", border_style="white", expand=False))
        choice = input('Enter choice: ').strip()
        if choice == '1':
            campaign_menu()
        elif choice == '2':
            diagnostics_menu()
        elif choice == '3':
            config_menu()
        elif choice == '4':
            data_menu()
        elif choice == '5':
            toggle_warmup_mode()
        elif choice == '0':
            sys.exit(1) # Exit with a non-zero code to signal the launcher to terminate.
        # "Smarter" Fix: Add a small delay for unknown choices to prevent rapid looping on accidental key presses.
        time.sleep(1)


if __name__ == '__main__':
    # Simple CLI flags to allow run.bat to call specific actions non-interactively
    args = sys.argv[1:]
    if args:
        flag = args[0].lower()
        if flag in ('--view-smtp-state', '--view-smtpstate', '--view-state'):
            view_smtp_state()
            sys.exit(0)
        if flag in ('--dry-run', '--dryrun'):
            # if a number was provided like --dry-run=10 handle it
            if '=' in flag:
                try:
                    n = int(flag.split('=', 1)[1])
                    run_script('main.py', [f'--dry-run={n}'])
                except Exception:
                    dry_run_n()
            else:
                dry_run_n()
            sys.exit(0)
        if flag in ('--imap-scan', '--imap'):
            imap_scan()
            sys.exit(0)
        if flag in ('--reset-smtp-state', '--reset-smtp'):
            reset_smtp_state()
            sys.exit(0)
        if flag in ('--reenable-smtps', '--reenable'):
            reenable_smtps()
            sys.exit(0)
        # unknown flag -> fall back to interactive
    main_menu()
