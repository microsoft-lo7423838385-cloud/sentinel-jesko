import os
import logging
from msal import PublicClientApplication, SerializableTokenCache
import json
import atexit

_import_error = None
try:
    import exchangelib
    from exchangelib.credentials import OAuth2Credentials
except ImportError as e:
    exchangelib = None
    OAuth2Credentials = None
    _import_error = str(e)

# --- "World-Class" Fix: Import OAuth2Token to satisfy exchangelib type checking ---
try:
    from oauthlib.oauth2 import OAuth2Token
except ImportError:
    OAuth2Token = None

if exchangelib and OAuth2Credentials:
    class BearerCredentials(OAuth2Credentials):
        """
        Custom credentials class to use an existing OAuth2 access token
        with exchangelib, bypassing internal token fetching.
        """
        def __init__(self, access_token):
            # --- "World-Class" Fix: Wrap token string in OAuth2Token object ---
            # exchangelib strictly validates that access_token is an instance of OAuth2Token.
            if OAuth2Token and not isinstance(access_token, OAuth2Token):
                self.access_token = OAuth2Token({
                    'access_token': access_token,
                    'token_type': 'Bearer',
                    'expires_in': 315360000  # 10 years to prevent local expiry checks
                })
            else:
                self.access_token = access_token
            # Initialize with dummy values as we don't use the library's fetch logic
            # --- "World-Class" Fix: Use valid public client/tenant IDs to pass exchangelib validation ---
            # Using "custom" causes AADSTS900023 errors during autodiscovery/version guessing.
            # d3590ed6... is the standard Microsoft Outlook public client ID.
            super().__init__(client_id="d3590ed6-52b3-4102-aeff-aad2292ab01c", client_secret=None, tenant_id="common")
            # --- "World-Class" Fix: Force remove any instance-level token_url attribute ---
            # This ensures that our property override below is respected, preventing auto-refresh attempts.
            self.__dict__.pop('token_url', None)

        @property
        def token_url(self):
            # Return a placeholder URL to prevent 'NoneType' errors if exchangelib checks attributes.
            # If auto-refresh is attempted, it will fail connection to this invalid domain,
            # allowing us to catch it as a token expiration.
            return "https://placeholder.invalid/token"

        def refresh(self, session=None):
            # Token refresh is handled externally by MSAL or cookies
            # Raising an error here prevents exchangelib from trying to auto-refresh 
            # using default flows (like client_credentials) which cause AADSTS errors.
            raise exchangelib.errors.UnauthorizedError("Access token expired or invalid. Cannot refresh cookie-based token.")

def get_oauth_account(settings, logger: logging.Logger):
    """
    Acquires an OAuth2 token for EWS, interactively if needed, and returns
    a configured exchangelib.Account object.
    """
    if not exchangelib:
        logger.critical(f"EWS OAuth requires 'exchangelib'. Import error: {_import_error}")
        return None

    project_root = os.path.dirname(os.path.dirname(__file__))
    token_cache_path = os.path.join(project_root, 'logs', 'ews_token_cache.bin')
    cache = SerializableTokenCache()

    if os.path.exists(token_cache_path):
        logger.info("Loading EWS token cache...")
        cache.deserialize(open(token_cache_path, "r").read())

    atexit.register(lambda:
        open(token_cache_path, "w").write(cache.serialize())
        if cache.has_state_changed else None
    )

    app = PublicClientApplication(
        client_id=str(settings.ews.ews_client_id),
        authority=f"https://login.microsoftonline.com/{settings.ews.ews_tenant_id}",
        token_cache=cache
    )

    accounts = app.get_accounts(username=settings.ews.ews_username)
    scopes = ['https://outlook.office365.com/.default']

    if accounts:
        logger.info("Found cached account. Attempting to acquire token silently...")
        result = app.acquire_token_silent(scopes, account=accounts[0])
    else:
        result = None

    if not result: # This can happen if silent auth fails
        logger.warning("No cached token found or token expired. Starting interactive login flow...")
        print("\nA browser window will now open for you to log in and grant consent for EWS access.")
        print("Please complete the login to continue...")
        # --- "World-Class" Fix: Remove explicit redirect_uri to prevent MSAL TypeError ---
        # Passing it explicitly causes a conflict with msal's internal handler in newer versions.
        result = app.acquire_token_interactive(
            scopes=scopes, login_hint=settings.ews.ews_username)

    # --- "World-Class" Fix: Handle user cancelling the interactive flow ---
    if not result:
        logger.error("Failed to acquire OAuth token: The interactive login flow was cancelled or did not return a result.")
        return None

    if "access_token" not in result:
        logger.error(f"Failed to acquire OAuth token: {result.get('error_description')}")
        return None

    logger.info("OAuth token acquired successfully.")
    # OAuth2Credentials is for when exchangelib manages the flow. Since we are using
    # MSAL to get the token, BearerCredentials is the correct class to use.
    access_token = result['access_token']
    creds = BearerCredentials(access_token=access_token)
    config = exchangelib.Configuration(server='outlook.office365.com', credentials=creds)
    return exchangelib.Account(primary_smtp_address=settings.ews.ews_username, config=config, autodiscover=False, access_type=exchangelib.DELEGATE)

def get_account_from_cookies(settings, logger: logging.Logger):
    """
    Parses the browser cookies provided in settings to extract the ESTSAUTH token
    and uses it as an OAuth2 Bearer token for EWS.
    """
    if not exchangelib:
        logger.critical(f"EWS requires 'exchangelib'. Import error: {_import_error}")
        return None
    
    raw_cookies = settings.ews.ews_cookies
    if not raw_cookies:
        return None
        
    token = None
    try:
        # Try parsing as JSON list of cookies (EditThisCookie format)
        cookies_list = json.loads(raw_cookies)
        for cookie in cookies_list:
            if cookie.get('name') == 'ESTSAUTH':
                token = cookie.get('value')
                break
    except json.JSONDecodeError:
        logger.error("Failed to parse ews_cookies JSON. Ensure it is a valid JSON array.")
        return None

    if not token:
        logger.error("Could not find 'ESTSAUTH' cookie in the provided configuration.")
        return None

    logger.info("Successfully extracted 'ESTSAUTH' token from cookies.")
    # --- "World-Class" Fix: Use BearerCredentials for pre-existing tokens ---
    # This is the correct and simplest way to use a raw bearer token with exchangelib,
    # avoiding the "'Protocol' object has no attribute 'session'" error.
    try:
        creds = BearerCredentials(access_token=token)
        # Use a stricter retry policy and user-agent to improve stability and avoid long hangs
        try:
            from exchangelib.protocol import FaultTolerance
            retry_policy = FaultTolerance(max_wait=30)
        except Exception:
            retry_policy = None

        config = exchangelib.Configuration(server='outlook.office365.com', credentials=creds)
        if retry_policy:
            config.retry_policy = retry_policy
        # Set a browser-like user-agent to improve server compatibility
        try:
            config.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        except Exception:
            pass

        # Create account and ensure the underlying HTTP session enforces timeouts
        account = exchangelib.Account(primary_smtp_address=settings.ews.ews_username, config=config, autodiscover=False, access_type=exchangelib.DELEGATE)

        # Try to patch the protocol session to enforce a default timeout so sends don't hang indefinitely
        try:
            protocol = getattr(account, 'protocol', None)
            if protocol:
                session = None
                # Prefer protocol.get_session() if available
                if hasattr(protocol, 'get_session'):
                    session = protocol.get_session()
                elif hasattr(protocol, 'session'):
                    session = protocol.session

                if session:
                    orig_request = session.request
                    def request_with_timeout(method, url, **kwargs):
                        kwargs.setdefault('timeout', 30)
                        return orig_request(method, url, **kwargs)
                    session.request = request_with_timeout
                    # Also ensure get_session returns this patched session
                    try:
                        protocol.get_session = lambda: session
                    except Exception:
                        pass
        except Exception:
            # Non-fatal: proceed without patched session if we cannot modify it
            pass

        return account
    except Exception as e:
        logger.error(f"Failed to initialize EWS with BearerCredentials: {e}")
        return None