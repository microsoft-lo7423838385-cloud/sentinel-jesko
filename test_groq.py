import os
import sys
import logging
import configparser
from settings import settings
from function.ai_client import get_ai_client
import openai # Import for specific exception handling
import function.ai_client as ai_client_module # Access to singleton

# Configure logging to capture details from the AI client factory
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GroqTest")

def test_groq_connection():
    print("\n--- Testing Groq AI Connection (with Proxy Support) ---")
    
    # 1. Check API Key
    api_key = settings.dev.groq_api_key
    if not api_key:
        print(f"  [FAILURE] Groq API Key is not set in your .env file.")
        print(f"  [ACTION] Please go to 'Configuration & Setup' -> 'AI Content Engine' -> 'Manage API Keys' to set it.")
        return

    print(f"API Key: Found")
    print(f"AI Model: {settings.ai.ai_model}")

    if settings.proxy.proxy_enabled and settings.proxy.proxy_ai_connections:
        print(f"Proxy Enabled: Yes")
        print(f"Proxy for AI: {settings.proxy.proxy_ai_connections}")
    else:
        print(f"Proxy Enabled: No")

    proxies_to_try = []
    if settings.proxy.proxy_enabled and settings.proxy.proxy_ai_connections and settings.proxy.proxy_list:
        proxies_to_try.extend(settings.proxy.proxy_list)
        print(f"\n[INFO] Proxy for AI is ENABLED. Testing {len(settings.proxy.proxy_list)} configured proxies.")
    else:
        # If proxies are disabled, test only the direct connection.
        proxies_to_try.append(None)
        print("\n[INFO] Proxy for AI is DISABLED. Testing direct connection only.")

    successful_connections = []
    # Loop through proxies
    for i, proxy_candidate in enumerate(proxies_to_try):
        # Temporarily modify settings for this specific test run
        original_proxy_list = settings.proxy.proxy_list
        original_proxy_enabled = settings.proxy.proxy_enabled

        if proxy_candidate:
            print(f"\n--- Attempt {i+1}/{len(proxies_to_try)} using proxy: {proxy_candidate.split('|')[1]} ---")
            
            # FORCE RESET the singleton client so it picks up the new proxy setting
            ai_client_module._ai_client_instance = None
            
            # Temporarily inject this proxy as the first one in settings
            settings.proxy.proxy_list = [proxy_candidate]
            settings.proxy.proxy_enabled = True
        else:
            print(f"\n--- Attempt {i+1}/{len(proxies_to_try)}: Direct Connection (No Proxy) ---")
            settings.proxy.proxy_enabled = False

        # Initialize Client
        try:
            client = get_ai_client(settings, logger)
        except Exception as e:
            print(f"  [SKIP] Client init failed: {e}")
            continue

        if not client:
            print("  [SKIP] Client returned None.")
            continue

        # Send Request
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Reply with 'Groq is operational!'"}
                ],
                model=settings.ai.ai_model,
                max_tokens=10
            )
            response_text = chat_completion.choices[0].message.content.strip()
            print(f"  [SUCCESS] Connection established! Response: \"{response_text}\"")
            successful_connections.append("Direct" if not proxy_candidate else proxy_candidate)

        except openai.APIConnectionError as e:
            # This is the most common error for network issues. Let's provide "world-class" diagnosis.
            root_cause = e.__cause__
            err_str = str(root_cause or e).lower() # Check the root cause first for more specific details.

            if '403' in err_str:
                print(f"  [FAILURE] 403 Forbidden (IP Blocked by Groq).")
                print(f"  [ACTION] To fix this, use a VPN to change your IP address, as Groq is blocking your current IP.")
            elif 'timed out' in err_str:
                print(f"  [FAILURE] Connection Timed Out. The proxy is likely offline, very slow, or a firewall is blocking the connection.")
            elif 'connection refused' in err_str:
                print(f"  [FAILURE] Connection Refused. The proxy server at this address/port is not running or is actively refusing the connection.")
            elif 'proxy authentication' in err_str or 'authenticate' in err_str:
                print(f"  [FAILURE] Proxy Authentication Failed. Please check the username/password for this proxy in config.ini.")
            elif 'name or service not known' in err_str or 'getaddrinfo failed' in err_str:
                print(f"  [FAILURE] DNS Error. The proxy hostname could not be resolved. Check for typos in the proxy IP/hostname.")
            else:
                print(f"  [FAILURE] API Connection Error. The proxy is likely offline or misconfigured.")
                print(f"      Details: {str(e)}") # Print the full original error for debugging
        except Exception as e:
            err_str = str(e).lower()
            if "model_decommissioned" in err_str:
                print(f"  [FAILURE] Critical Error: The model '{settings.ai.ai_model}' is decommissioned.")
                print(f"  [ACTION] Please go to 'Configuration & Setup' -> 'AI Content Engine' and select a new, valid model.")
                return # Stop the test immediately, as all subsequent calls will fail.
            else:
                # Catch-all for other errors
                print(f"  [FAILURE] An unexpected error occurred: {str(e)}")
        finally:
            # Restore original settings
            settings.proxy.proxy_list = original_proxy_list
            settings.proxy.proxy_enabled = original_proxy_enabled

    print("\n--- Test Complete ---")
    if successful_connections:
        print(f"[SUCCESS] {len(successful_connections)} connection method(s) worked:")
        for conn in successful_connections:
            print(f"  - {conn}")
    else:
        print("[FAILURE] All connection methods failed. Please check your API key and proxy configurations.")
        print("[INFO] If you are using the Dichvusocks Desktop App, ensure it is running and the IP/Ports match your config.")

if __name__ == "__main__":
    test_groq_connection()
    input("\nPress Enter to return to the menu...")