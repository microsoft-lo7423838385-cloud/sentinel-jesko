import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import configparser
import socks
import socket
import ssl

# Add project root to path to import settings
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from settings import settings

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def test_proxy(proxy_str, timeout=5):
    """Tests a single proxy's connectivity using a low-level socket connection."""
    try:
        parts = proxy_str.split('|')
        proxy_type_str, host, port = parts[0], parts[1], int(parts[2])
        proxy_user = parts[3] if len(parts) > 3 else None
        proxy_pass = parts[4] if len(parts) > 4 else None

        # Map string type to socks constant
        proxy_type_map = {
            'socks5': socks.SOCKS5, 
            'socks4': socks.SOCKS4, 
            'http': socks.HTTP
        }
        proxy_type = proxy_type_map.get(proxy_type_str.lower(), socks.SOCKS5)
        
        # Create a socket that uses the proxy without global patching
        s = socks.socksocket()
        s.set_proxy(proxy_type, host, port, True, proxy_user, proxy_pass)
        s.settimeout(timeout)
        
        # Attempt a TCP connection to a reliable target (Google DNS 8.8.8.8 on port 53)
        s.connect(("8.8.8.8", 53))
        s.close()
        
        return proxy_str, True, "OK (Socket Handshake Success)"
    except TypeError as e:
        return proxy_str, False, f"Handshake Failed (Likely bad proxy): {e}"
    except Exception as e:
        return proxy_str, False, f"Connection Failed: {e}"

def run_proxy_test():
    print(f"\n{YELLOW}--- Advanced Proxy Connectivity Test ---{RESET}")

    if not settings.proxy.proxy_enabled:
        print("Proxy is not enabled in config.ini. Nothing to test.")
        return

    proxies_to_test = settings.proxy.proxy_list
    if not proxies_to_test or not proxies_to_test[0]:
        print("Proxy is enabled, but the proxy_list is empty.")
        return

    print(f"Found {len(proxies_to_test)} proxies in your configuration. Testing all with a max of 10 workers...")

    working_proxies = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_proxy = {executor.submit(test_proxy, p): p for p in proxies_to_test}
        for future in as_completed(future_to_proxy):
            proxy_str, success, message = future.result()
            if success:
                print(f"  - {GREEN}[PASS]{RESET} {proxy_str.split('|')[1]}:{proxy_str.split('|')[2]} -> {message}")
                working_proxies.append(proxy_str)
            else:
                print(f"  - {RED}[FAIL]{RESET} {proxy_str.split('|')[1]}:{proxy_str.split('|')[2]} -> {message}")

    print("\n--- Test Summary Complete ---")
    
    if working_proxies and len(working_proxies) < len(proxies_to_test):
        print(f"\n{YELLOW}Result: {len(working_proxies)} out of {len(proxies_to_test)} proxies are working.{RESET}")
        update = input(f"Do you want to automatically update 'config.ini' to keep ONLY the {len(working_proxies)} working proxies? [y/N]: ").strip().lower()
        if update == 'y':
            config_path = os.path.join(PROJECT_ROOT, 'config', 'config.ini')
            config = configparser.ConfigParser(inline_comment_prefixes=('#',))
            config.read(config_path)
            if not config.has_section('PROXY'):
                config.add_section('PROXY')
            
            # Reconstruct the list string
            new_list_str = "::".join(working_proxies)
            config.set('PROXY', 'proxy_list', new_list_str)
            
            with open(config_path, 'w') as f:
                config.write(f)
            print(f"{GREEN}Configuration updated! Bad proxies have been removed.{RESET}")
    elif not working_proxies:
        print(f"\n{RED}All proxies failed. Please check your proxy source or credentials.{RESET}")

if __name__ == "__main__":
    run_proxy_test()
    input("\nPress Enter to return to the menu...")