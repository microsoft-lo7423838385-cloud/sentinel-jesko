import requests
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to path to import settings
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from settings import settings

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
CYAN = '\033[96m'

def check_proxy_ip(proxy_str):
    """
    Connects to an IP echo service via the proxy to reveal the actual public IP.
    """
    try:
        parts = proxy_str.split('|')
        if len(parts) < 3:
            return proxy_str, False, "Invalid Format"

        proxy_type_str, host, port = parts[0], parts[1], parts[2]
        proxy_user = parts[3] if len(parts) > 3 else None
        proxy_pass = parts[4] if len(parts) > 4 else None

        # Construct the proxy URL for requests.
        # We use 'socks5h' to ensure DNS resolution happens on the proxy side (preventing leaks).
        scheme = "socks5h" if "socks" in proxy_type_str.lower() else "http"
        
        if proxy_user and proxy_pass:
            proxy_url = f"{scheme}://{proxy_user}:{proxy_pass}@{host}:{port}"
        else:
            proxy_url = f"{scheme}://{host}:{port}"

        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }

        # Timeout set to 15s to filter out slow proxies
        # Using api.ipify.org as a reliable IP echo service
        response = requests.get('https://api.ipify.org?format=json', proxies=proxies, timeout=15)
        
        if response.status_code == 200:
            remote_ip = response.json().get('ip')
            return proxy_str, True, remote_ip
        else:
            return proxy_str, False, f"Status Code: {response.status_code}"

    except Exception as e:
        return proxy_str, False, str(e)

def main():
    print(f"\n{YELLOW}--- Proxy IP Verification Tool ---{RESET}")
    print("This tool will connect to the internet through each of your proxies")
    print("and verify the Public IP address being used.")
    print("-" * 60)

    if not settings.proxy.proxy_enabled:
        print(f"{RED}Proxies are currently DISABLED in config.ini.{RESET}")
        return

    proxy_list = settings.proxy.proxy_list
    if not proxy_list:
        print(f"{RED}No proxies found in configuration.{RESET}")
        return

    print(f"Testing {len(proxy_list)} proxies...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_proxy = {executor.submit(check_proxy_ip, p): p for p in proxy_list}
        
        for future in as_completed(future_to_proxy):
            original_proxy, success, result = future.result()
            parts = original_proxy.split('|')
            host_port = f"{parts[1]}:{parts[2]}"
            
            if success:
                # result is the Remote IP
                print(f"Proxy: {CYAN}{host_port:<21}{RESET} -> Public IP: {GREEN}{result}{RESET}")
            else:
                # result is the error message
                print(f"Proxy: {CYAN}{host_port:<21}{RESET} -> {RED}FAILED ({result}){RESET}")

    print("-" * 60)
    print("If the 'Public IP' matches the Proxy IP, your setup is working correctly.")
    print("If you are using a local proxy client, ensure the 'Public IP' is NOT your home IP.")
    input("\nPress Enter to return...")

if __name__ == "__main__":
    main()