import dns.resolver
import socket
import smtplib

def verify_email_address(email, logger):
    """
    Performs a basic, self-hosted email verification.
    1. Checks for MX records on the domain.
    2. Attempts a connection to the mail server to see if the user is rejected.
    Returns True if the email seems deliverable, False otherwise.
    """
    domain = email.split('@')[1]

    # 1. Check for MX records
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        if not mx_records:
            logger.warning(f"Verification FAILED for {email}: No MX records found for domain.")
            return False
        mail_server = str(mx_records[0].exchange)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        logger.warning(f"Verification FAILED for {email}: Domain does not exist or has no MX records.")
        return False
    except Exception as e:
        logger.warning(f"Verification SKIPPED for {email}: DNS lookup failed ({e}). Assuming valid.")
        return True # Assume valid if DNS fails, to avoid false negatives

    # 2. Attempt SMTP connection test
    try:
        with smtplib.SMTP(mail_server, 25, timeout=10) as server:
            server.set_debuglevel(0)
            server.helo('example.com') # Identify ourselves
            server.mail('verifier@example.com') # A dummy from address
            code, message = server.rcpt(email)

            # 250 or 251 means the user is accepted
            if code == 250 or code == 251:
                logger.debug(f"Verification PASSED for {email}: Server accepted recipient.")
                return True
            # 5xx codes are permanent failures
            elif code >= 500:
                logger.warning(f"Verification FAILED for {email}: Server rejected recipient (Code: {code}).")
                return False
            # 4xx codes are temporary failures, we'll treat them as valid to avoid false negatives
            else:
                logger.debug(f"Verification SKIPPED for {email}: Server returned a temporary failure (Code: {code}). Assuming valid.")
                return True
    except (socket.timeout, smtplib.SMTPServerDisconnected, ConnectionRefusedError, OSError) as e:
        logger.warning(f"Verification SKIPPED for {email}: Could not connect to mail server ({e}). Assuming valid.")
        return True # Assume valid if we can't connect
    except Exception as e:
        logger.error(f"An unexpected error occurred during SMTP verification for {email}: {e}")
        return True # Assume valid on unexpected errors