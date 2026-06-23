import os
import sys
import logging
from datetime import datetime

# Add project root to path to allow imports
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from settings import settings

try:
    import exchangelib
except ImportError:
    print("Error: exchangelib is not installed. Run 'pip install exchangelib'.")
    sys.exit(1)

# Set up logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EWSTest")

def get_ews_account():
    username = settings.ews.ews_username
    if not username:
        logger.error("EWS username is not set in 'config.ini' under [EWS].")
        return None

    # 1. Try Cookie Auth
    if settings.ews.ews_cookies:
        try:
            from function.ews_oauth_transport import get_account_from_cookies
            account = get_account_from_cookies(settings, logger)
            if account:
                logger.info("Initialized EWS account via Browser Cookies.")
                return account
        except Exception as e:
            logger.error(f"Cookie auth failed: {e}")

    # 2. Try OAuth
    if settings.ews.ews_use_oauth:
        try:
            from function.ews_oauth_transport import get_oauth_account
            account = get_oauth_account(settings, logger)
            if account:
                logger.info("Initialized EWS account via OAuth.")
                return account
        except Exception as e:
            logger.error(f"OAuth failed: {e}")
    
    # 3. Try Basic Auth
    try:
        password = settings.dev.smtp_passwords.get(username)
        if not password:
            logger.error(f"No password found for {username} in .env file (SMTP_PASSWORDS).")
            return None
        
        creds = exchangelib.Credentials(username=username, password=password)
        config = exchangelib.Configuration(server='outlook.office365.com', credentials=creds)
        account = exchangelib.Account(primary_smtp_address=username, config=config, autodiscover=False, access_type=exchangelib.DELEGATE)
        logger.info("Initialized EWS account via Basic Auth.")
        return account
    except Exception as e:
        logger.error(f"Basic Auth failed: {e}")
    
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_ews_single.py <recipient_email>")
        sys.exit(1)

    recipient = sys.argv[1]
    account = get_ews_account()

    if account:
        subject = f"EWS Test {datetime.now().strftime('%H:%M:%S')}"
        body = "This is a test email sent via the EWS single test script."
        print(f"Sending test email to: {recipient}...")
        m = exchangelib.Message(
            account=account,
            subject=subject,
            body=body,
            to_recipients=[recipient]
        )
        # save_copy=True will automatically find the default Sent Items folder and save a copy there.
        m.send(save_copy=True)
        print("Success! Email sent.")

if __name__ == "__main__":
    main()