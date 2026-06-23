import os
import sys

# --- Add project root to the Python path to allow imports ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
# -------------------------------------------------------------

from settings import settings

def list_models():
    print("\n--- Listing Available Gemini Models ---")
    print("Connecting to Google's API to retrieve the list of valid model names...")
    
    api_key = settings.dev.gemini_api_key
    if not api_key:
        print("\n[ERROR] GEMINI_API_KEY is not set in your .env file.")
        print("Please configure it in 'Configuration & Setup' -> 'AI Content Engine' -> 'Manage API Keys'.")
        return

    try:
        from google.genai import Client
    except ImportError:
        print("\n[ERROR] 'google-genai' library is not installed.")
        print("Please run: pip install -r requirements.txt")
        return

    try:
        client = Client(api_key=api_key)
        
        print(f"\n{'Model ID (Use this in config)':<40} | {'Display Name'}")
        print("-" * 75)
        
        count = 0
        # List models with robust attribute checking
        try:
            for model in client.models.list():
                count += 1
                # Handle attributes that might be missing or different
                raw_name = getattr(model, 'name', 'unknown')
                clean_id = raw_name.replace('models/', '')
                display_name = getattr(model, 'display_name', clean_id)
                methods = getattr(model, 'supported_generation_methods', [])

                # If methods are specified, check for generateContent. If empty/None, print anyway to be safe.
                if not methods or 'generateContent' in methods:
                    print(f"{clean_id:<40} | {display_name}")
        except Exception as iter_err:
            print(f"[WARNING] Error during iteration: {iter_err}")

        if count == 0:
            print("\n[WARNING] No models found. This implies your API Key may lack permissions")
            print("or your region does not have access to the public model list.")

    except Exception as e:
        print(f"\n[ERROR] Failed to list models: {e}")

if __name__ == "__main__":
    list_models()
    input("\nPress Enter to return...")