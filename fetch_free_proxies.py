import requests
import configparser
import os
import sys
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import httpx
    from httpx_socks import SyncProxyTransport
except ImportError:
    httpx = None
    SyncProxyTransport = None

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def _is_proxy_working(proxy_str, timeout=30):
    """Tests if a single proxy is alive by connecting to a test site."""
    if not httpx or not SyncProxyTransport:
        return False
    
    parts = proxy_str.split('|')
    proxy_type, host, port = parts[0], parts[1], parts[2]
    user = parts[3] if len(parts) > 3 else None
    pwd = parts[4] if len(parts) > 4 else None
    auth = f"{user}:{pwd}@" if user and pwd else ""
    proxy_url = f"{proxy_type}://{auth}{host}:{port}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        if proxy_type.lower() == "socks5":
            transport = SyncProxyTransport.from_url(proxy_url)
            with httpx.Client(transport=transport, timeout=timeout) as client:
                response = client.get("http://httpbin.org/ip", headers=headers)
                return response.status_code == 200
        elif proxy_type.lower() == "http":
            proxies = {
                "http://": proxy_url,
                "https://": proxy_url,
            }
            with httpx.Client(proxies=proxies, timeout=timeout) as client:
                response = client.get("https://api.ipify.org", headers=headers) # Use a more reliable target
                return response.status_code == 200
        else:
            return False
    except Exception as e:
        # print(f"Proxy {host}:{port} failed validation: {e}") # Uncomment for debugging
        return False

def fetch_and_update():
    try:
        print(f"\n{YELLOW}--- Auto-Fetch Free Proxies ---{RESET}")
        
        # Define config path at the start
        project_root = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(project_root, 'config', 'config.ini')
        
        # --- "World-Class" Resiliency: Try multiple reliable sources ---
        urls = [
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
            "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
        ]
        
        # if credentials are provided in config, try to log in to the site first
        parser = configparser.ConfigParser(inline_comment_prefixes=('#',))
        parser.read(config_path)
        site_user = parser.get('PROXY', 'proxy_site_username', fallback=None)
        site_pass = parser.get('PROXY', 'proxy_site_password', fallback=None)
        site_login_url = parser.get('PROXY', 'proxy_site_login_url', fallback=None)
        site_list_url = parser.get('PROXY', 'proxy_site_list_url', fallback=None)

        def _scrape_site(username, password, login_url, list_url):
            """Attempt to authenticate to a given site and parse any proxies found.
            This is intentionally generic; if the site's login or layout changes you
            can update the URLs or parsing logic accordingly.
            """
            if not all([username, password, login_url, list_url]):
                print(f"{YELLOW}Skipping site scrape: username, password, login_url, and list_url must be set in config.{RESET}")
                return []

            session = requests.Session()
            try:
                print(f"Attempting to log in to {login_url} as '{username}'...")
                resp = session.post(str(login_url), data={
                    'username': username,
                    'password': password
                }, timeout=15)
                if resp.status_code != 200:
                    print(f"Login failed (status {resp.status_code})")
                    return []
                # load the page that lists proxies
                resp2 = session.get(str(list_url), timeout=15)
                text = resp2.text
                # crude regex to capture ip:port pairs
                matches = re.findall(r"(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})", text)
                proxies = []
                for ip, port in matches:
                    proxies.append(f"socks5|{ip}|{port}")
                return list(dict.fromkeys(proxies))  # deduplicate
            except requests.RequestException as e:
                print(f"Site fetch error: {e}")
                return []

        raw_proxies = []
        if site_user and site_pass:
            site_proxies = _scrape_site(site_user, site_pass, site_login_url, site_list_url)
            if site_proxies:
                print(f"{GREEN}Fetched {len(site_proxies)} proxies from site using login credentials.{RESET}")
                raw_proxies = site_proxies
            else:
                print(f"{YELLOW}Failed to retrieve proxies from site. Falling back to public sources.{RESET}")

        if not raw_proxies:
            # no credentials or site fetch failed; fall back to public sources
            response = None
            for url in urls:
                print(f"Fetching free HTTP proxies from: {url}...")
                try:
                    response = requests.get(url, timeout=15)
                    response.raise_for_status()
                    if response.text.strip():
                        print(f"{GREEN}Successfully fetched proxy list.{RESET}")
                        break # Stop on the first successful fetch
                except requests.RequestException as e:
                    print(f"{YELLOW}Could not fetch from {url}: {e}. Trying next source...{RESET}")

            if not response or not response.text.strip():
                raise Exception("All proxy sources failed.")
            
            lines = response.text.strip().splitlines()
            
            # "Smarter" Selection: Take a random sample instead of just the top.
            sample_size = min(50, len(lines))
            print(f"Found {len(lines)} potential proxies. Selecting and validating a random sample of {sample_size}...")
            
            import random
            for line in random.sample(lines, sample_size):
                if ':' in line:
                    ip, port = line.strip().split(':', 1)
                    # Format for config.ini: type|host|port
                    raw_proxies.append(f"http|{ip}|{port}")
            
            if not raw_proxies:
                print(f"{RED}No valid proxy formats found in the response.{RESET}")
                return

        print(f"Validating {len(raw_proxies)} proxies... This may take a moment.")
        
        # --- "World-Class" Proxy Pre-validation ---
        working_proxies = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_proxy = {executor.submit(_is_proxy_working, p): p for p in raw_proxies}
            for future in as_completed(future_to_proxy):
                if future.result():
                    working_proxies.append(future_to_proxy[future])

        if not working_proxies:
            print(f"{RED}\nValidation failed. No working proxies found from the source. Please try again later.{RESET}")
            return

        # Update config.ini
        cfg = configparser.ConfigParser(inline_comment_prefixes=('#',))
        cfg.read(config_path)
        
        if not cfg.has_section('PROXY'):
            cfg.add_section('PROXY')
            
        proxy_list_str = "::".join(working_proxies)
        cfg.set('PROXY', 'proxy_list', proxy_list_str)
        cfg.set('PROXY', 'proxy_ai_connections', '1')
        
        with open(config_path, 'w') as f:
            cfg.write(f)
            
        print(f"\n{GREEN}[SUCCESS] Added {len(working_proxies)} VALIDATED free HTTP proxies to configuration.{RESET}")
        print(f"{GREEN}[SUCCESS] Proxies have been ENABLED for AI connections.{RESET}")
        print(f"\n{YELLOW}Next Step:{RESET} Go back and run 'Test Groq AI Connection' again.")
        
    except Exception as e:
        print(f"{RED}[ERROR] Failed to fetch or update proxies: {e}{RESET}")

if __name__ == "__main__":
    fetch_and_update()