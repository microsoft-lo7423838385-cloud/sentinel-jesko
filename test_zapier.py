import configparser
import os
import requests

PROJECT_ROOT = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.ini')

def test_zapier_webhook():
    """
    Sends a single test request to the Zapier webhook URL defined in the config.
    """
    print("--- Zapier Webhook Tester ---")

    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    webhook_url = config.get('LINK_SHORTENER', 'zapier_webhook_url', fallback=None)

    if not webhook_url or 'hooks.zapier.com' not in webhook_url:
        print("\nERROR: 'zapier_webhook_url' not found or invalid in config/config.ini.")
        return

    test_payload = {
        "long_url": "https://www.google.com/search?q=test"
    }

    print(f"\nSending test payload to: {webhook_url}")
    print(f"Payload: {test_payload}")

    try:
        response = requests.post(webhook_url, json=test_payload)
        response.raise_for_status()
        print("\nSUCCESS: Test request sent successfully!")
        print("Now, go back to Zapier and click the 'Test trigger' button.")
        print(f"Response from Zapier: {response.json()}")
    except Exception as e:
        print(f"\nERROR: Failed to send test request. Reason: {e}")
    
    input("\nPress Enter to return to the menu...")

if __name__ == "__main__":
    test_zapier_webhook()