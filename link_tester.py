import os
import requests
from settings import settings
# Removed base64, hmac, hashlib as they were for the old tracking system

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def test_link_system():
    """A "smart" test to validate the email's destination links."""
    print("\n--- Email Link Validation Test ---")

    try:
        # Get all configured link_urls
        destination_urls = [str(url) for url in settings.email.link_url]

        if not destination_urls:
            print(f"{RED}ERROR: No 'link_url' values found in config.ini under the [EMAIL] section.{RESET}")
            print(f"{YELLOW}Action: Please add at least one valid URL to 'link_url' in your config.ini.{RESET}")
            return

        print(f"Found {len(destination_urls)} destination URL(s) to test.")

        all_links_ok = True
        # --- Step 1: Test Main Destination Links ---
        for i, dest_url in enumerate(destination_urls):
            print(f"\n[1] Validating destination URL #{i+1}: {dest_url}...")
            try:
                # --- "World-Class" Base URL Validation ---
                # Use requests.get to follow redirects and get the final status.
                # Add a standard User-Agent to mimic a real browser.
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                response = requests.get(dest_url, headers=headers, allow_redirects=True, timeout=15)
                
                if response.status_code >= 400:
                    print(f"{RED}  [✗] CRITICAL: This 'link_url' is broken! (Status: {response.status_code}){RESET}")
                    print(f"{YELLOW}      Action: Update this 'link_url' in the [EMAIL] section of your config.ini to a valid, working URL.{RESET}")
                    all_links_ok = False
                else:
                    print(f"{GREEN}  [✓] This destination URL is valid (Status: {response.status_code}).{RESET}")
                    print(f"      Final URL after redirects: {response.url}")
            except requests.exceptions.MissingSchema:
                print(f"{RED}  [✗] CRITICAL: Invalid URL format. Missing schema (e.g., 'http://' or 'https://').{RESET}")
                print(f"{YELLOW}      Action: Ensure this 'link_url' in your config.ini starts with 'http://' or 'https://'.{RESET}")
                all_links_ok = False
            except requests.exceptions.InvalidSchema:
                print(f"{RED}  [✗] CRITICAL: Invalid URL schema. Only 'http' and 'https' are supported.{RESET}")
                print(f"{YELLOW}      Action: Ensure this 'link_url' in your config.ini uses 'http://' or 'https://'.{RESET}")
                all_links_ok = False
            except requests.exceptions.ConnectionError as e:
                print(f"{RED}  [✗] CRITICAL: Could not connect to this 'link_url'.{RESET}")
                print(f"      Error: {e}")
                print(f"{YELLOW}      Action: Check your internet connection, the URL for typos, and ensure the website is online.{RESET}")
                all_links_ok = False
            except requests.exceptions.SSLError as e:
                print(f"\n{RED}CRITICAL FAILURE: SSL Certificate is INVALID.{RESET}")
                print(f"  Error: {e}")
                print(f"\n{YELLOW}Action Required:{RESET}")
                print(f"  1. Log in to your hosting provider for '{dest_url.split('/')[2]}'.")
                print(f"  2. Find the SSL/TLS settings for the subdomain.")
                print(f"  3. Issue or install a valid SSL certificate (e.g., from Let's Encrypt). This is often a free, one-click process.")
                print(f"  This is severely hurting your deliverability.")
                all_links_ok = False
            except requests.RequestException as e: # Catch all other requests-related errors
                print(f"{RED}  [✗] CRITICAL: An HTTP request error occurred for this 'link_url'.{RESET}")
                print(f"      Error: {e}")
                print(f"{YELLOW}      Action: Check the URL for typos and ensure the website is online.{RESET}")
                all_links_ok = False

        # --- Step 2: Test Unsubscribe Link ---
        unsubscribe_url = str(settings.email.unsubscribe_url)
        if unsubscribe_url:
            print(f"\n[2] Validating Unsubscribe URL: {unsubscribe_url}...")
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                response = requests.get(unsubscribe_url, headers=headers, allow_redirects=True, timeout=15)
                
                if response.status_code >= 400:
                    print(f"{RED}  [✗] CRITICAL: Your unsubscribe link is broken! (Status: {response.status_code}){RESET}")
                    print(f"{YELLOW}      Action: You MUST create a working web page at this URL to avoid spam complaints.{RESET}")
                    all_links_ok = False
                else:
                    print(f"{GREEN}  [✓] Unsubscribe URL is valid (Status: {response.status_code}).{RESET}")
            except requests.RequestException as e:
                print(f"{RED}  [✗] CRITICAL: Could not connect to your unsubscribe URL.{RESET}")
                print(f"      Error: {e}")
                print(f"{YELLOW}      Action: Check the URL and ensure your web server is running and accessible.{RESET}")
                all_links_ok = False
        else:
            print(f"\n{YELLOW}[!] WARNING: No 'unsubscribe_url' is configured in your config.ini. This is required for compliance.{RESET}")
            all_links_ok = False

        if all_links_ok:
            print(f"\n{GREEN}SUCCESS: All configured 'link_url's are working correctly!{RESET}")
        else:
            print(f"\n{RED}FAILURE: One or more 'link_url's are broken or inaccessible. Please fix them.{RESET}")

    except Exception as e:
        print(f"\n{RED}An error occurred during the test: {e}{RESET}")

if __name__ == "__main__":
    test_link_system()
    input("\nPress Enter to return to the menu...")