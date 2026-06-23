import smtplib
import socket
import sys
import os
from function import smtp_utils
from settings import settings


def setup_proxy():
    """Configures the global socket proxy if enabled in the config."""
    try:
        import socks

        if settings.proxy.proxy_enabled:
            print("--- Proxy is enabled. Reading proxy settings... ---")
            # For this test, we'll just use the first configured proxy
            if not settings.proxy.proxy_list:
                print("Proxy is enabled, but proxy_list is empty in config.ini.")
                return False
            
            first_proxy = settings.proxy.proxy_list[0]
            parts = first_proxy.split('|')
            proxy_type_str, proxy_host, proxy_port = parts[0], parts[1], int(parts[2])
            proxy_user = parts[3] if len(parts) > 3 else None
            proxy_pass = parts[4] if len(parts) > 4 else None
            
            proxy_type_map = {'socks5': socks.SOCKS5, 'socks4': socks.SOCKS4, 'http': socks.HTTP}
            proxy_type = proxy_type_map.get(proxy_type_str.lower())
            socks.set_default_proxy(proxy_type, proxy_host, proxy_port, rdns=True, username=proxy_user, password=proxy_pass)
            socket.socket = socks.socksocket
            print("[SUCCESS] Sockets patched for proxy.")
            return True
        else:
            print("--- Proxy is disabled in config.ini. Attempting a direct connection. ---")
            return True

    except (ImportError, ValueError) as e:
        print(f"--- FATAL: Could not configure proxy. Error: {e} ---")
        return False

def run_single_test(smtp_config, test_num, total_tests):
    """Runs a connection test for a single SMTP configuration."""
    print(f"\n--- Running Test {test_num}/{total_tests} for {smtp_config.host} (Through Proxy) ---")
    host = smtp_config.host
    port = smtp_config.port
    email = smtp_config.email
    password = smtp_config.password
    security = smtp_config.security

    server = None
    try:
        print(f"  - Host: {host}, Port: {port}, Email: {email}, Security: {security}")
        print("  - Timeout is set to 30 seconds.")

        # Determine connection type based on security setting
        if security == 'ssl' or (security == 'auto' and port == 465):
            print(f"  - Attempting to connect using SMTP_SSL...")
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            print(f"  - Attempting to connect using standard SMTP...")
            server = smtplib.SMTP(host, port, timeout=30)

        print("  - [SUCCESS] TCP connection established.")
        server.set_debuglevel(1)

        # Issue STARTTLS if required
        if security == 'starttls' or (security == 'auto' and port not in [465, 25]):
            print("\n  - Issuing STARTTLS command...")
            server.starttls()
            print("  - [SUCCESS] Secure connection established via STARTTLS.")

        print("\n  - Logging in...")
        server.login(email, password)
        print(f"  - [SUCCESS] Login successful for {email}.")
        print(f"\n--- TEST {test_num}/{total_tests} PASSED ---")

    except smtplib.SMTPAuthenticationError as e:
        print(f"\n--- TEST {test_num}/{total_tests} FAILED: SMTP Authentication Error ---")
        print(f"The connection to the SMTP server was successful, but authentication failed: {e}")
        print("Please double-check the SMTP password in your .env file.")
    except socket.timeout:
        print(f"\n--- TEST {test_num}/{total_tests} FAILED: Connection Timed Out ---")
        print(f"The script could not connect to {host} on port {port} within 30 seconds.")
        print("\nPOSSIBLE CAUSES:")
        print("1. Your proxy/VPN is not connected or is not working correctly.")
        print("2. A firewall (Windows Firewall, Antivirus) is blocking the connection.")
        print(f"3. The SMTP server ({host}) is blocking your proxy/VPN's IP address.")
        print("4. The SMTP server details (host, port, security) in .env are incorrect.")
    except (smtplib.SMTPException, OSError) as e:
        print(f"\n--- TEST FAILED: A connection or protocol error occurred ---")
        print(f"Error details: {e}")
        print("\nThis could be a network issue, a problem with the VPN, or a firewall block.")
        print("If the error is 'getaddrinfo failed', it means the SMTP hostname is wrong or can't be reached.")
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass # Ignore errors on quit

if __name__ == "__main__":
    # Setup proxy first
    if not setup_proxy():
        print("\n--- Proxy setup failed. Aborting test. ---")
        input("Press Enter to exit.")
        sys.exit(1)

    all_smtp_configs = smtp_utils.get_smtp_configs()

    if not all_smtp_configs:
        print("--- No SMTP_SERVERS configurations found in config.ini ---")
    else:
        print(f"--- Found {len(all_smtp_configs)} SMTP configuration(s) to test through the proxy. ---")
        for i, smtp_config in enumerate(all_smtp_configs):
            run_single_test(smtp_config, i + 1, len(all_smtp_configs))

    print("\nTest finished. Press Enter to exit.")
    input()