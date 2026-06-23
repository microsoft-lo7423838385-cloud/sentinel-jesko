import requests
try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: 'beautifulsoup4' is not installed. Please run: pip install beautifulsoup4")
    sys.exit(1)
import configparser
import os
import sys
import re
# --- "World-Class" Fix: Import settings to use configured credentials ---
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from settings import settings
# URLs (may need to be updated based on actual site)
LOGIN_URL = 'https://dichvusocks.net/login'
PROXY_URL = 'https://dichvusocks.net/user'  # Assuming the proxy list is on the user dashboard

def login_and_fetch_proxies():
    print("Logging in to dichvusocks.net...")

    # --- "World-Class" Fix: Use credentials from config, not hardcoded values ---
    USERNAME = settings.proxy.proxy_site_username
    PASSWORD = settings.proxy.proxy_site_password
    SITE_PORT = settings.proxy.proxy_site_port

    # --- "World-Class" Safety Net: Prevent accidental overwrite of Local App config ---
    # This check runs *before* attempting to log in, to avoid user confusion.
    project_root = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(project_root, 'config', 'config.ini')
    cfg = configparser.ConfigParser(inline_comment_prefixes=('#',))
    cfg.read(config_path)
    current_list = cfg.get('PROXY', 'proxy_list', fallback='')

    is_local_app_config = False
    if '10.' in current_list or '192.168.' in current_list or '127.0.0.1' in current_list:
        is_local_app_config = True

    if is_local_app_config:
        print(f"\n{YELLOW}WARNING: Your config is set to use the Local Dichvusocks Desktop App.{RESET}")
        print(f"{CYAN}This script ('Fetch Dichvusocks Proxies') is for scraping the WEBSITE, not the app.{RESET}")
        print(f"{YELLOW}Running this will overwrite your local app settings with proxies from the website.{RESET}")
        print(f"\nIf you want to use the Desktop App, you don't need to run this script. Your setup is already correct.")
        if input("\nDo you still want to proceed and fetch from the website anyway? [y/N]: ").strip().lower() != 'y':
            print("\nOperation cancelled. Your local app configuration is safe.")
            return []

    if not all([USERNAME, PASSWORD, SITE_PORT]):
        print(f"{RED}ERROR: 'proxy_site_username', 'proxy_site_password', and 'proxy_site_port' must be set in config.ini.{RESET}")
        print(f"{YELLOW}Action: Go to 'Configuration & Setup' -> 'Advanced Configuration' -> 'Proxy settings' -> 'Set Premium Proxy Site Credentials' to configure them.{RESET}")
        
        # --- "World-Class" Guidance for Local App Users ---
        print(f"\n{CYAN}NOTE: This script scrapes the Dichvusocks WEBSITE. If you are using the Dichvusocks DESKTOP APP,")
        print(f"      please use the '[bold]Setup Local Dichvusocks App[/bold]' option in the proxy menu instead.{RESET}")

        
        # --- "World-Class" Fallback Suggestion ---
        print(f"\n{YELLOW}Don't have a Dichvusocks account?{RESET}")
        return []

    EMAIL = USERNAME # The login field might be 'email', so we use the username for both.

    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    # Get the login page to get any CSRF tokens if needed
    try:
        response = session.get(LOGIN_URL, headers=headers, timeout=15)
        response.raise_for_status()
    except (requests.RequestException, NameError) as e:
        print(f"Failed to access login page: {e}")
        return []

    # Parse the login page for form fields (if CSRF token is needed)
    soup = BeautifulSoup(response.text, 'html.parser')
    csrf_token = None
    csrf_input = soup.find('input', {'name': 'csrf_token'}) or soup.find('input', {'name': '_token'}) or soup.find('input', {'name': 'token'})
    if csrf_input:
        csrf_token = csrf_input.get('value')

    # --- "Smart" Form Detection ---
    # Auto-detect login fields to handle 'email' vs 'username'
    login_data = {}
    
    user_input = soup.find('input', attrs={'name': re.compile(r'(user|email|login)', re.I)})
    if user_input:
        field_name = user_input.get('name')
        if 'email' in field_name.lower():
            print(f"Detected login field '{field_name}'. Using EMAIL credential.")
            login_data[field_name] = EMAIL
        else:
            print(f"Detected login field '{field_name}'. Using USERNAME credential.")
            login_data[field_name] = USERNAME
    else:
        login_data['username'] = USERNAME # Fallback

    # --- "World-Class" Enhancement: Dynamically find password field ---
    pass_input = soup.find('input', attrs={'type': 'password'})
    if pass_input and pass_input.get('name'):
        login_data[pass_input.get('name')] = PASSWORD
    else:
        login_data['password'] = PASSWORD # Fallback
    
    if csrf_token:
        token_name = csrf_input.get('name') if csrf_input else '_token'
        login_data[token_name] = csrf_token

    # Post login
    try:
        # --- "World-Class" Enhancement: Add Referer header to mimic browser behavior ---
        post_headers = headers.copy()
        post_headers['Referer'] = LOGIN_URL
        
        response = session.post(LOGIN_URL, data=login_data, headers=post_headers, timeout=15)
        if response.status_code != 200:
            print(f"Login failed with status {response.status_code}: {response.text[:500]}")
            return []
        response.raise_for_status()
        if 'login' in response.url.lower() or 'auth' in response.url.lower():
            print("Login failed: Redirected back to login page.")
            # --- "World-Class" Debugging: Show the error message from the page ---
            soup = BeautifulSoup(response.text, 'html.parser')
            error_div = soup.find('div', class_=re.compile(r'(error|alert|danger|invalid)', re.I))
            if error_div:
                print(f"{RED}Server Error Message: {error_div.get_text(strip=True)}{RESET}")
            return _get_fallback_proxies()
    except requests.RequestException as e:
        print(f"Login failed: {e}")
        return _get_fallback_proxies()

    print("Login successful. Fetching proxy list...")

    # Get the proxy page
    try:
        response = session.get(PROXY_URL, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Failed to fetch proxy page: {e}")
        return _get_fallback_proxies()

    # Parse the proxy list
    proxies = parse_proxies(response.text, SITE_PORT, USERNAME, PASSWORD)
    if not proxies:
        print("No proxies found on page. Using fallback.")
        return _get_fallback_proxies()
    print(f"Found {len(proxies)} proxies.")
    return proxies

def parse_proxies(html, port, username, password):
    """
    A "smarter" parser that finds all public IPv4 addresses in the page content.
    This is robust against HTML structure changes.
    """
    proxies = []
    # This regex is a reliable way to find all IPv4 addresses in a block of text.
    ip_pattern = r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
    found_ips = re.findall(ip_pattern, html)
    
    # Filter out common private/local IPs that might be on the page
    potential_ips = [
        ip for ip in found_ips 
        if not (
            ip.startswith(('10.', '192.168.', '127.')) or 
            ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31
        )
    ]
    
    if not potential_ips:
        print("Could not find any public IP addresses on the proxy page.")
        return []
        
    for host in potential_ips:
        # Format as socks5|host|port|user|pass
        proxy_str = f"socks5|{host}|{port}|{USERNAME}|{PASSWORD}"
        proxies.append(proxy_str)
        
    return list(dict.fromkeys(proxies)) # Deduplicate and return

def update_config(proxies):
    if not proxies:
        print("No proxies to update.")
        return

    project_root = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(project_root, 'config', 'config.ini')

    cfg = configparser.ConfigParser(inline_comment_prefixes=('#',))
    cfg.read(config_path)

    if not cfg.has_section('PROXY'):
        cfg.add_section('PROXY')

    proxy_list_str = "::".join(proxies)
    cfg.set('PROXY', 'proxy_list', proxy_list_str)
    cfg.set('PROXY', 'proxy_enabled', '1')
    cfg.set('PROXY', 'proxy_ai_connections', '1')

    with open(config_path, 'w') as f:
        cfg.write(f)

    print("Config updated with new proxies.")

def _get_fallback_proxies():
    """Returns proxies based on the last known working IP if login fails."""
    print(f"{RED}[FAIL] Login failed. Could not retrieve premium proxies.{RESET}")
    print(f"{YELLOW}Recommendation: Use option '10) Fetch & Validate Free Proxies' in the Diagnostics menu instead.{RESET}")
    return []

# Define ANSI colors for the standalone run
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

if __name__ == "__main__":
    proxies = login_and_fetch_proxies()
    if proxies:
        update_config(proxies)
        print("Proxy list updated successfully.")
    else:
        print("Failed to fetch proxies.")