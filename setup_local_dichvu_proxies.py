import os
import configparser
import sys

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.ini')

def main():
    """
    A "world-class" interactive setup script to configure the sender
    to use the local Dichvusocks desktop application.
    """
    print(f"\n{YELLOW}--- Setup for Local Dichvusocks Desktop App ---{RESET}")
    print("This will configure the sender to use the proxies provided by your running Dichvusocks app.")
    print("Please ensure the Dichvusocks app is running and check its display for your current IP.")

    # 1. Get IP address
    default_ip = '127.0.0.1'
    print(f"\n{CYAN}Note: If the app is on THIS machine, use 127.0.0.1.{RESET}")
    ip_address = input(f"Enter the IP address shown in your Dichvusocks App (Current: {default_ip}): ").strip() or default_ip

    # 2. Get Port Range
    start_port_str = input("Enter the starting port number (e.g., 6001): ").strip()
    end_port_str = input("Enter the ending port number (e.g., 6010): ").strip()

    try:
        start_port = int(start_port_str)
        end_port = int(end_port_str)
        if start_port > end_port:
            print(f"{RED}Error: Starting port cannot be greater than ending port.{RESET}")
            return
    except ValueError:
        print(f"{RED}Error: Invalid port number. Please enter integers only.{RESET}")
        return

    # 3. Get Credentials
    username = input("Enter your Dichvusocks username (e.g., Bot_001): ").strip()
    password = input("Enter your Dichvusocks password: ").strip()

    if not all([ip_address, username, password]):
        print(f"{RED}Error: IP Address, Username, and Password are required.{RESET}")
        return

    # 4. Construct proxy strings
    proxies = []
    for port in range(start_port, end_port + 1):
        # The app provides HTTP/SOCKS5, but we should use SOCKS5 for better compatibility
        proxy_str = f"socks5|{ip_address}|{port}|{username}|{password}"
        proxies.append(proxy_str)

    if not proxies:
        print(f"{RED}No proxies were generated. Please check your input.{RESET}")
        return

    print(f"\nGenerated {len(proxies)} proxy entries.")

    # 5. Update config.ini
    try:
        cfg = configparser.ConfigParser(inline_comment_prefixes=('#',))
        cfg.read(CONFIG_PATH)

        if not cfg.has_section('PROXY'):
            cfg.add_section('PROXY')

        proxy_list_str = "::".join(proxies)
        cfg.set('PROXY', 'proxy_list', proxy_list_str)
        cfg.set('PROXY', 'proxy_enabled', '1')
        cfg.set('PROXY', 'proxy_rotate_mode', 'sequential')
        cfg.set('PROXY', 'proxy_ai_connections', '1') # Also enable for AI

        with open(CONFIG_PATH, 'w') as f:
            cfg.write(f)

        print(f"\n{GREEN}[SUCCESS] Configuration updated!{RESET}")
        print(f"  - Added {len(proxies)} local Dichvusocks proxies to your config.")
        print("  - Enabled proxies for both SMTP and AI connections.")
        print(f"\n{YELLOW}Next Step:{RESET} You can now run a test (e.g., 'Test SMTPs Only' or 'Test Groq AI Connection') to verify.")

    except Exception as e:
        print(f"{RED}An error occurred while updating the configuration file: {e}{RESET}")

if __name__ == "__main__":
    main()