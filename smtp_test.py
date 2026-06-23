import smtplib
import socket
import threading
import time
import concurrent.futures
import sys
import os
from settings import settings
from dotenv import load_dotenv
from function import smtp_utils

load_dotenv()

# --- Circuit Breaker & Retry Configuration ---
host_failures = {}          # Tracks consecutive failures per host
host_lock = threading.Lock() # Ensures thread safety for the failure counter
MAX_HOST_FAILURES = 5       # If a host fails 5 times, skip remaining checks for it
MAX_RETRIES = 1             # Retry network errors 1 time (Total 2 attempts) for speed

def run_single_test(smtp_config, test_num, total_tests, debug=False):
    """Runs a connection test for a single SMTP configuration."""
    host = smtp_config.host
    port = smtp_config.port
    email = smtp_config.email
    password = smtp_config.password
    security = smtp_config.security
    # Cap timeout at 8 seconds for testing to fail fast on dead servers
    timeout = min(settings.smtp.smtp_timeout, 8)

    # 1. Circuit Breaker Check: Skip if host is known to be down
    with host_lock:
        if host_failures.get(host, 0) >= MAX_HOST_FAILURES:
            # Print minimal output to avoid cluttering logs
            print(f"--- TEST {test_num}/{total_tests} SKIPPED: {host} marked as unresponsive ---")
            return

    if debug:
        print(f"\n--- Running Test {test_num}/{total_tests} for {smtp_config.host} (Direct Connection) ---")

    server = None
    # 2. Retry Loop: Try connection multiple times for network errors
    for attempt in range(MAX_RETRIES + 1):
        try:
            if attempt > 0:
                print(f"  - Retry attempt {attempt} for {host}...")
            elif debug:
                print(f"  - Host: {host}, Port: {port}, User: {email}")

            if security == 'ssl' or (security == 'auto' and port == 465):
                server = smtplib.SMTP_SSL(host, port, timeout=timeout)
            else:
                server = smtplib.SMTP(host, port, timeout=timeout)

            if debug: server.set_debuglevel(1)

            if security == 'starttls' or (security == 'auto' and port not in [465, 25]):
                if debug: print("  - Issuing STARTTLS command...")
                server.starttls()

            if debug: print("  - Logging in...")
            server.login(email, password)
            
            # Clean output for bulk mode
            print(f"  [SUCCESS] {host}:{port} | {email}")
            
            if debug: print(f"\n--- TEST {test_num}/{total_tests} PASSED ---")

            # Success! Reset host failure count because the host is clearly up.
            with host_lock:
                host_failures[host] = 0
            break # Exit retry loop

        except smtplib.SMTPAuthenticationError as e:
            # Decode error if possible, handle bytes
            error_msg = str(e.smtp_error)
            try:
                if isinstance(e.smtp_error, bytes):
                    error_msg = e.smtp_error.decode('utf-8', errors='ignore')
            except Exception:
                pass
            
            print(f"  [AUTH FAIL] {host}:{port} | {email} | Error: {error_msg.strip()}")
            
            if debug:
                print(f"\n--- TEST {test_num}/{total_tests} FAILED: Auth Error (Host is UP) ---")

            # Do not retry bad passwords. Host is working, just the account is bad.
            with host_lock: host_failures[host] = 0 
            break
        except (socket.timeout, OSError, smtplib.SMTPException) as e:
            if attempt < MAX_RETRIES:
                # print(f"  - Warning: Connection failed ({e}). Retrying shortly...")
                time.sleep(1) # Short pause before retry
                continue
            
            print(f"  [NET FAIL] {host}:{port} | {email} | Error: {e}")
            if debug:
                print(f"\n--- TEST {test_num}/{total_tests} FAILED: Network/Connection Error ---")

            # Increment failure count. If this hits limit, subsequent tests for this host are skipped.
            with host_lock:
                host_failures[host] = host_failures.get(host, 0) + 1
        finally:
            if server:
                try: server.quit()
                except Exception: pass


if __name__ == "__main__":
    all_smtp_configs = smtp_utils.get_smtp_configs()

    if not all_smtp_configs:
        print("--- No SMTP_SERVERS configurations found in .env file ---")
    else:
        total_tests = len(all_smtp_configs)
        print(f"--- Found {total_tests} SMTP configuration(s) to test. ---")

        # Use a single thread (sequential) if only one test, which enables detailed debug output.
        # Use multiple threads for bulk testing to significantly speed up the process.
        if total_tests == 1:
            print("--- Running in single-test mode (sequential). ---")
            # Enable debug for a single run to get detailed SMTP conversation logs.
            run_single_test(all_smtp_configs[0], 1, 1, debug=True)
        else:
            # Adjust this number based on your machine's capability and network limits.
            # A good starting point is between 10 and 50. Higher is not always better.
            MAX_CONCURRENT_TESTS = 60
            print(f"--- Running in bulk mode with up to {MAX_CONCURRENT_TESTS} concurrent tests. ---")
            print("--- (Detailed debug output is disabled in bulk mode for clarity) ---")

            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TESTS) as executor:
                # Submit all tests to the thread pool. The 'with' block waits for all to complete.
                futures = []
                for i, smtp_config in enumerate(all_smtp_configs):
                    futures.append(executor.submit(run_single_test, smtp_config, i + 1, total_tests))
                
                # Wait for all futures to complete
                concurrent.futures.wait(futures)

    print("\nAll tests finished. Press Enter to exit.")
    input()