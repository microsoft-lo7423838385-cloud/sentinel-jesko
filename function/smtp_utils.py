import smtplib
import socket
import dns.resolver
import os
import sqlite3
import json
import getpass

# --- Add project root to path to allow imports from the root settings.py ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- "World-Class" Fix: Import socks for proxy support ---
try:
    import socks
except ImportError:
    socks = None

try:
    from dotenv import set_key, find_dotenv
except ImportError:
    set_key = find_dotenv = None

# --- Global state for discovery rotation ---
_discovery_proxy_index = 0

def get_smtp_configs():
    """
    A centralized, "smarter" function to parse SMTP server configurations.
    It now securely loads passwords from the .env file.
    """
    from settings import settings, SmtpConfigModel
    
    # --- "World-Class" SES Mode Bypass ---
    # In SES mode, the endpoint is not an actual SMTP server, so password lookup should be skipped.
    ses_mode = getattr(settings.smtp, 'smtp_ses_mode', False)
    
    smtp_configs = []
    
    # --- Robust Password Loading ---
    # Normalize keys to lowercase for robust lookup
    raw_passwords = settings.dev.smtp_passwords
    
    # Fallback: Check environment variable directly if settings field is empty
    if not raw_passwords:
        env_pass = os.environ.get("SMTP_PASSWORDS")
        if env_pass:
            try:
                raw_passwords = json.loads(env_pass)
                # Update settings object so other parts of the app can see it
                settings.dev.smtp_passwords = raw_passwords
            except Exception:
                raw_passwords = {}

    password_dict = {str(k).lower(): v for k, v in raw_passwords.items()}

    for server_str in settings.smtp.smtp_servers:
        parts = server_str.split('|')
        if len(parts) < 3:
            continue

        email = parts[2]
        
        # --- SES Mode: skip password lookup entirely ---
        if ses_mode:
            password = ''
            sec_val = 'auto'
            limit_val = 0
            trans_val = 'ses'
            # Support extended format even in SES mode
            if len(parts) >= 5:
                sec_val = parts[4] if parts[4] else 'auto'
                limit_val = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0
                trans_val = parts[6] if len(parts) > 6 else 'ses'
            
            # Force a valid sender identity for SES (verified domain already exists)
            sender_email = email if email else 'noreply@departmentallaw.com'
            
            smtp_configs.append(SmtpConfigModel(
                host=parts[0],
                port=int(parts[1]),
                email=sender_email,
                password=password,
                security=sec_val,
                limit=limit_val,
                transport=trans_val
            ))
            continue
        
        # Support "Send As" syntax (auth#sender) for password lookup. Try full string first, then auth part.
        auth_email = email.split('#')[0] if '#' in email else email
        password = password_dict.get(email.strip().lower()) or password_dict.get(auth_email.strip().lower())

        if not password:
            # --- "Smart" Fix: Prompt for password if missing ---
            print(f"\n[Configuration Required] Password for {email} not found in .env file.")
            try:
                password = getpass.getpass(f"Please enter the SMTP password for {email}: ").strip()
            except Exception:
                # Fallback for IDEs/consoles that don't support getpass
                password = input(f"Please enter the SMTP password for {email}: ").strip()
            
            if password:
                # Save to memory for this session
                clean_email = email.strip().lower()
                settings.dev.smtp_passwords[clean_email] = password
                password_dict[email.lower()] = password
                # Attempt to persist to .env for future runs
                if set_key and find_dotenv:
                    try:
                        env_path = find_dotenv() or os.path.join(PROJECT_ROOT, '.env')
                        set_key(env_path, "SMTP_PASSWORDS", json.dumps(settings.dev.smtp_passwords))
                        print(f"[Saved] Password securely saved to .env for future use.")
                    except Exception as e:
                        print(f"[Warning] Could not write to .env file: {e}")
                else:
                    print("[Warning] 'python-dotenv' not installed. Password not saved to disk.")
            else:
                continue

        # Handle both 4-part (standard) and 7-part (extended) formats
        # 4-part: host|port|email|security
        # 7-part: host|port|email|password_placeholder|security|limit|transport
        
        sec_val = 'auto'
        limit_val = 0
        trans_val = 'smtp'
        
        if len(parts) == 4:
            sec_val = parts[3]
        elif len(parts) >= 5:
            sec_val = parts[4] if parts[4] else 'auto'
            limit_val = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0
            trans_val = parts[6] if len(parts) > 6 else 'smtp'

        smtp_configs.append(SmtpConfigModel(
            host=parts[0],
            port=int(parts[1]),
            email=email,
            password=password,
            security=sec_val,
            limit=limit_val,
            transport=trans_val
        ))

    # --- "Jesko" Engine: Enrich configs with state from the database ---
    db_path = os.path.join(PROJECT_ROOT, 'logs', 'state.db')
    if not os.path.exists(db_path):
        return smtp_configs # Return raw configs if DB doesn't exist

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for config in smtp_configs:
            smtp_id = f"{config.host}:{config.port}:{config.email}"
            cursor.execute("SELECT sent_count, fail_count, disabled_until, total_sent, domain_stats, average_latency, reputation_events FROM smtp_state WHERE smtp_id = ?", (smtp_id,))
            row = cursor.fetchone()
            if row:
                config.sent_count = row[0]
                config.fail_count = row[1]
                config.disabled_until = row[2]
                config.total_sent = row[3]
                config.domain_stats = json.loads(row[4]) if row[4] else {}
                config.average_latency = row[5] if row[5] is not None else 0.0
                config.reputation_events = json.loads(row[6]) if row[6] else []
            else:
                # Ensure these attributes exist even for new servers
                config.total_sent = 0
                config.domain_stats = {}
                config.average_latency = 0.0
                config.reputation_events = []
        conn.close()
    except Exception as e:
        # If DB access fails, we can still proceed with raw configs. Log a warning.
        print(f"Warning: Could not load SMTP state from database: {e}")

    return smtp_configs

def test_smtp_connection(smtp_config, logger, timeout=10):
    """
    Tests a single SMTP configuration.
    Tests a single SMTP configuration, with auto-discovery fallback for DNS errors.
    Accepts either a Pydantic model or a dictionary.
    Returns a tuple: (success_boolean, message_string, updated_smtp_config_or_none)
    """
    if isinstance(smtp_config, dict):
        host = smtp_config.get('host')
        port = int(smtp_config.get('port', 0))
        email = smtp_config.get('email')
        password = smtp_config.get('password')
        security = smtp_config.get('security', 'auto')
        is_retry = smtp_config.get('is_retry', False)
    else: # Is Pydantic model
        host = smtp_config.host
        port = smtp_config.port
        email = smtp_config.email
        password = smtp_config.password
        security = smtp_config.security
        is_retry = getattr(smtp_config, 'is_retry', False)
    
    from settings import settings

    try:
        test_helo = settings.smtp.smtp_helo_name
        if security == 'ssl' or (security == 'auto' and port == 465):
            server = smtplib.SMTP_SSL(host, port, timeout=timeout, local_hostname=test_helo)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout, local_hostname=test_helo)
            if security == 'starttls' or (security == 'auto' and port not in [465, 25]):
                server.starttls()

        # Support Send-As Login (auth_user#send_as_user)
        login_user = email.split('#')[0] if '#' in email else email
        server.login(login_user, password)
        server.quit()
        
        if is_retry:
            msg = f"SUCCESS (Auto-Discovered): {host}:{port} with user {email}"
        else:
            msg = f"SUCCESS: {host}:{port} with user {email}"
        return (True, msg, smtp_config)

    except smtplib.SMTPAuthenticationError as e:
        raw_error = str(e)
        if 'BasicAuthBlocked' in raw_error or '535 5.7.139' in raw_error:
            err_msg = f"Microsoft 365 Block: Basic Auth is disabled for {email}. You MUST use an 'App Password' or enable 'Authenticated SMTP' in the Microsoft 365 Admin Center."
            logger.error(f"SMTP Security Block: {host}:{port} - {err_msg}")
        else:
            err_msg = f"Authentication failed for {email}. Check password or use an 'App Password'. (Code: {e.smtp_code})"
            logger.warning(f"SMTP Auth Error: {host}:{port} - {err_msg}")
            
        return (False, err_msg, None)
    except (socket.timeout, ConnectionRefusedError, smtplib.SMTPConnectError, OSError, smtplib.SMTPServerDisconnected) as e:
        # --- "World-Class" Self-Healing for Connection/DNS Errors ---
        # Trigger discovery if we hit a network-level issue on the primary attempt
        if not is_retry and isinstance(e, (socket.gaierror, socket.timeout, ConnectionRefusedError, OSError)):
            logger.info(f"Network error ({e.__class__.__name__}) for '{host}'. Attempting auto-discovery for {email}...")
            from settings import SmtpConfigModel
            new_config_dict, error_msg = discover_smtp_settings(email, password, logger=logger)
            if new_config_dict:
                logger.info(f"Auto-discovery found viable settings: {new_config_dict['host']}:{new_config_dict['port']}. Retesting...")
                new_smtp_config = SmtpConfigModel(**new_config_dict, is_retry=True)
                return test_smtp_connection(new_smtp_config, logger, timeout)

        # If we reach here, it's either already a retry or discovery failed to find a working server
        if isinstance(e, socket.timeout):
            err_msg = f"Connection to {host}:{port} timed out. (Check: Are you on a VPN? Destination server may be blackholing your IP)."
        elif isinstance(e, ConnectionRefusedError):
            err_msg = f"Connection to {host}:{port} was refused. The server is up but the port might be blocked or incorrect."
        else:
            err_msg = f"Connection failed to {host}:{port} ({e.__class__.__name__}). Check server/firewall settings."
        
        # High-priority warning for the log when discovery fails
        logger.debug(f"SMTP Conn Error: {host}:{port} - {err_msg}")
        return (False, err_msg, None)
    except Exception as e:
        err_msg = f"An unexpected error occurred: {e}"
        logger.debug(f"SMTP test failed for {host}:{port} - {err_msg}")
        return (False, err_msg, None)

def discover_smtp_settings(email, password, logger=None):
    """
    A "world-class" discovery engine to find SMTP settings for a given email and password.
    Returns a tuple: (config_dict, error_message). On success, error_message is None. On failure, config_dict is None.
    """
    if '@' not in email:
        return None, "Invalid email format."

    domain = email.split('@')[1].lower()
    
    # --- Build a list of candidate hosts ---
    candidate_hosts = []

    # 1. Known Provider Map (Direct domain match)
    provider_map = {
        'gmail.com': 'smtp.gmail.com',
        'googlemail.com': 'smtp.gmail.com',
        'yahoo.com': 'smtp.mail.yahoo.com',
        'ymail.com': 'smtp.mail.yahoo.com',
        'rocketmail.com': 'smtp.mail.yahoo.com',
        'outlook.com': 'smtp.office365.com',
        'hotmail.com': 'smtp.office365.com',
        'live.com': 'smtp.office365.com',
        'msn.com': 'smtp.office365.com',
        'office365.com': 'smtp.office365.com',
        'aol.com': 'smtp.aol.com',
        'comcast.net': 'smtp.comcast.net',
        'icloud.com': 'smtp.mail.me.com',
        'me.com': 'smtp.mail.me.com',
        'mac.com': 'smtp.mail.me.com',
        'zoho.com': 'smtp.zoho.com',
        'protonmail.com': '127.0.0.1',
        'proton.me': '127.0.0.1',
        'bellsouth.net': 'smtp.mail.att.net',
        'att.net': 'smtp.mail.att.net',
        'sbcglobal.net': 'smtp.mail.att.net',
        'onmicrosoft.com': 'smtp.office365.com',
    }

    if domain in provider_map:
        candidate_hosts.append(provider_map[domain])

    # 2. MX Record Heuristics (The "Smart" part)
    # This detects if a custom domain (e.g. lawyers.com) is hosted by O365/Gmail/etc.
    try:
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = ['8.8.8.8', '1.1.1.1'] # Use reliable DNS
        resolver.timeout = 3
        resolver.lifetime = 3
        mx_records = resolver.resolve(domain, 'MX')
        sorted_mx = sorted(mx_records, key=lambda r: r.preference)
        
        for r in sorted_mx:
            mx_host = str(r.exchange).rstrip('.').lower()
            if 'google.com' in mx_host or 'googlemail.com' in mx_host:
                candidate_hosts.append('smtp.gmail.com')
            elif 'outlook.com' in mx_host or 'protection.outlook.com' in mx_host:
                candidate_hosts.append('smtp.office365.com')
                candidate_hosts.append('outlook.office365.com')
                candidate_hosts.append(mx_host)
            elif 'zoho.com' in mx_host:
                candidate_hosts.append('smtp.zoho.com')
            elif 'secureserver.net' in mx_host: # GoDaddy
                candidate_hosts.append('smtpout.secureserver.net')
            
            # Always include the MX host itself as a candidate - this is critical for corporate domains
            candidate_hosts.append(mx_host)
    except Exception:
        pass # Ignore if MX lookup fails

    # 3. Standard Guesses (Fallback)
    candidate_hosts.extend([
        f"smtp.{domain}",
        f"mail.{domain}",
        domain, # Sometimes the root domain is the mail server
        f"relay.{domain}"
    ])

    # Remove duplicates while preserving order
    unique_hosts = list(dict.fromkeys(candidate_hosts))
    
    # Try a wider range of ports to bypass aggressive ISP/Firewall blocks
    ports_to_try = [587, 465, 2525, 25, 443]
    
    # Use a dummy logger if none is provided
    if logger is None:
        import logging
        logger = logging.getLogger('discover_test')
        logger.setLevel(logging.CRITICAL)

    # --- "World-Class" Proxy Support for Discovery ---
    from settings import settings
    proxy_restorer = None
    global _discovery_proxy_index

    if settings.proxy.proxy_enabled and settings.proxy.proxy_list and socks:
        try:
            # --- "Jesko" Engine: Discovery Proxy Rotation ---
            # Rotate through available proxies so one bad port doesn't kill the whole session.
            idx = _discovery_proxy_index % len(settings.proxy.proxy_list)
            p_conf = settings.proxy.proxy_list[idx].split('|')
            _discovery_proxy_index += 1

            if len(p_conf) >= 3:
                p_type, p_host, p_port = p_conf[0].lower(), p_conf[1], int(p_conf[2])
                p_user = p_conf[3] if len(p_conf) > 3 else None
                p_pass = p_conf[4] if len(p_conf) > 4 else None
                
                # --- "World-Class" Pre-flight Proxy Check ---
                # Verify the machine at p_host is actually reachable on p_port.
                # This prevents "forever hangs" if the Dichvusocks IP has changed.
                try:
                    with socket.create_connection((p_host, p_port), timeout=2):
                        pass
                except Exception:
                    logger.error(f"CRITICAL: Proxy {p_host}:{p_port} is UNREACHABLE (Port Closed/Offline).")
                    logger.error("Please verify the IP address in your config matches your Dichvusocks app.")
                    return None, f"Proxy {p_host}:{p_port} is offline or the IP is incorrect."

                type_map = {'socks5': socks.SOCKS5, 'socks4': socks.SOCKS4, 'http': socks.HTTP}
                if p_type in type_map:
                    original_socket = socket.socket
                    socks.setdefaultproxy(type_map[p_type], p_host, p_port, True, p_user, p_pass)
                    socket.socket = socks.socksocket
                    def restore():
                        socks.setdefaultproxy()
                        socket.socket = original_socket
                    proxy_restorer = restore
                    # Elevate to info so users can see if their proxy is being used during discovery
                    logger.info(f"Using proxy for discovery: {p_host}:{p_port}")
        except Exception as e:
            logger.warning(f"Failed to apply proxy for discovery: {e}")

    try:
        errors = []
        is_using_proxy = proxy_restorer is not None
        
        logger.info(f"  [Discovery] Scanning candidate servers for {email}...")
        for host in unique_hosts:
            host_auth_error = None
            for port in ports_to_try:
                if host_auth_error:
                    break

                # Try both security methods for every port to ensure we find the working one.
                # Usually 465 is SSL, others are STARTTLS, so we prioritize based on port.
                securities = ['ssl', 'starttls'] if port == 465 else ['starttls', 'ssl']
                
                for security in securities:
                    # --- "Smart" Timeout for Discovery ---
                    # Increased discovery timeouts to ensure we don't skip slow-responding pro servers
                    discovery_timeout = 15 if any(x in host.lower() for x in ['outlook', 'protection', 'microsoft']) else 10
                    config = {"host": host, "port": port, "email": email, "password": password, "security": security, "is_retry": True}
                    is_ok, err_msg, _ = test_smtp_connection(config, logger, timeout=discovery_timeout)
                    
                    if is_ok:
                        config['from_email'] = email # Default from_email to the user
                        config['limit'] = 0
                        config['transport'] = 'smtp'
                        return config, None
                    else:
                        # Only collect unique error messages to avoid bloat
                        if err_msg not in errors:
                            if is_using_proxy:
                                errors.append(f"{err_msg} (Tested via proxy port {p_port})")
                            else:
                                errors.append(err_msg)
    finally:
        if proxy_restorer:
            proxy_restorer()

    # --- "AI" Error Analysis ---
    # If we get here, all attempts failed. Analyze the errors to give the best advice.
    if not errors:
        return None, "Could not find any potential SMTP servers to test for this domain."

    error_str_list = [str(e) for e in errors]
    auth_failures = sum(1 for e in error_str_list if "Authentication failed" in e)
    conn_failures = sum(1 for e in error_str_list if "Connection failed" in e or "timeout" in e.lower())
    dns_failures = sum(1 for e in errors if "DNS lookup failed" in str(e))

    # Check if the domain is a known Microsoft/GoDaddy domain
    is_microsoft_domain = any(d in domain for d in ['outlook.com', 'office365.com', 'live.com', 'hotmail.com', 'msn.com', 'onmicrosoft.com', 'secureserver.net'])

    if auth_failures > 0 and auth_failures >= conn_failures:
        # If auth failure is the most common, it's likely the password.
        representative_error = "Authentication failed. 1) Check password. 2) If MFA is on, use an 'App Password'. 3) For Office 365, ensure 'Authenticated SMTP' is enabled in the Microsoft 365 Admin Center for this user."
        if is_microsoft_domain:
            representative_error += " 3) For Office 365/GoDaddy, ensure 'Authenticated SMTP' is enabled for the user in the Microsoft 365 Admin Center."
    elif any("outlook" in host.lower() or "office365" in host.lower() for host in unique_hosts) and conn_failures > 0:
        representative_error = "Connection to Office 365 failed. Microsoft often blocks data center IPs (Proxies) or specific ports. Try: 1) Disable proxies in config. 2) Check if your ISP blocks port 587. 3) Ensure no local firewall is interfering."
        if is_microsoft_domain:
            representative_error += " 4) Consider using the EWS (Exchange Web Services) sending method for Office 365 accounts, as it uses modern authentication and is more reliable."
    elif dns_failures > 0 and dns_failures >= conn_failures:
        representative_error = "DNS lookup failed. The auto-discovered server addresses could not be resolved. Please check your internet connection."
    elif conn_failures > 0:
        if is_using_proxy:
            representative_error = "Connection failed. Your configured proxy may be blocking SMTP traffic or is offline. Try disabling proxies in the config to test discovery."
        else:
            representative_error = "Connection failed. A firewall, antivirus, or ISP is likely blocking the connection to the SMTP server."
    else:
        # Fallback to the first error message for other cases
        representative_error = errors[0]

    return None, representative_error

def initialize_smtp_pool(logger):
    """
    A "world-class" function to test all configured SMTP servers in parallel and return a pool of working ones.
    If SES mode is enabled, returns the single SES endpoint without pool testing.
    """
    from settings import settings
    
    # SES Mode: Single endpoint, no pool testing needed
    if settings.smtp.smtp_ses_mode:
        logger.info("--- SES Mode enabled: Using single Amazon SES endpoint (no pool testing) ---")
        smtp_configs = get_smtp_configs()
        if smtp_configs:
            # Mark as SES mode for downstream logic
            for config in smtp_configs:
                config.transport = 'ses'
            logger.info(f"--- SES endpoint configured: {smtp_configs[0].host}:{smtp_configs[0].port} ---")
        return smtp_configs

    logger.info("--- Initializing and testing SMTP pool... ---")
    
    smtp_configs = get_smtp_configs()

    if not smtp_configs:
        logger.warning("No SMTP servers found in configuration.")
        return []

    working_smtps = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_smtp = {executor.submit(test_smtp_connection, config, logger): config for config in smtp_configs}
        
        for future in as_completed(future_to_smtp):
            config = future_to_smtp[future]
            try:
                is_ok, msg, _ = future.result()
                if is_ok:
                    logger.info(f"--- SMTP OK: {config.host}:{config.port} added to pool. ---")
                    working_smtps.append(config)
                else:
                    logger.warning(f"SMTP check failed for {config.host}:{config.port}. Reason: {msg}")
            except Exception as e:
                logger.error(f"Error checking SMTP {config.host}: {e}")

    return working_smtps
