import dns.resolver
import sys
import argparse
import os
import configparser
from socket import gethostbyname, gaierror, gethostbyaddr
from settings import settings
# ANSI color codes for better output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def check_dns(domain, record_type):
    """Queries DNS for a specific record type and prints the result."""
    print(f"\n{YELLOW}Querying for {record_type.upper()} records for '{domain}'...{RESET}")
    try:
        answers = dns.resolver.resolve(domain, record_type)
        print(f"{GREEN}SUCCESS: Found {len(answers)} {record_type.upper()} record(s):{RESET}")
        for rdata in answers:
            print(f"  -> {rdata.to_text()}")
        return answers
    except dns.resolver.NoAnswer:
        print(f"{RED}FAILED: The DNS query was successful, but no {record_type.upper()} records were found for '{domain}'.{RESET}")
    except dns.resolver.NXDOMAIN:
        print(f"{RED}FAILED: The domain '{domain}' does not exist (NXDOMAIN).{RESET}")
    except dns.resolver.Timeout:
        print(f"{RED}FAILED: The query timed out. The DNS server may be slow or unreachable.{RESET}")
    except Exception as e:
        print(f"{RED}FAILED: An unexpected error occurred: {e}{RESET}")
    return None

def suggest_records(main_domain):
    """Suggests recommended SPF and DMARC records for the user to add."""
    print(f"\n{YELLOW}--- Recommended DNS Records for {main_domain} ---{RESET}")

    # --- "World-Class" Freemail Detection ---
    free_domains = {'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'icloud.com', 'aol.com'}
    if main_domain.lower() in free_domains:
        print(f"{RED}NOTICE: You are testing a public freemail domain ({main_domain}).{RESET}")
        print(f"You cannot edit DNS records for this domain. Your deliverability is restricted by")
        print(f"the provider's global reputation. For professional results,")
        print(f"{YELLOW}it is HIGHLY recommended to use a custom domain (e.g., yourcompany.com).{RESET}")
        return

    print("To improve deliverability, please add the following TXT records to your domain's DNS settings (e.g., in Hostinger).")

    # --- "Smarter" SPF Record Generation ---
    # Read SMTP servers from the centralized settings
    from function.smtp_utils import get_smtp_configs
    smtp_configs = get_smtp_configs()
    smtp_hosts = {s.host for s in smtp_configs}

    ip_mechanisms = ""
    if smtp_hosts:
        print("\nResolving IPs for your configured SMTP servers to include in SPF...")
        for host in smtp_hosts:
            try:
                ip = gethostbyname(host)
                ip_mechanisms += f" ip4:{ip}"
                print(f"  -> Found {host} -> {ip}")
            except gaierror:
                print(f"  -> Could not resolve IP for {host}. It might be covered by 'a' or 'mx' records.")

    print(f"\n{YELLOW}1. SPF Record:{RESET}")
    print("   This record tells servers which mail servers are allowed to send email for your domain.")
    print(f"   - Type:    TXT")
    print(f"   - Name:    @ (or {main_domain})")
    spf_value = f"v=spf1 mx a{ip_mechanisms} ~all"
    print(f"   - Value:   {GREEN}\"{spf_value}\"{RESET}")
    print(f"   - TTL:     14400 (or default)")

    # Suggest a basic DMARC record
    report_email = f"dmarc-reports@{main_domain}"
    print(f"\n{YELLOW}2. DMARC Record:{RESET}")
    print("   This record tells servers what to do with unauthenticated emails. MailGenius recommends 'p=quarantine' or 'p=reject'.")
    print(f"\n   {YELLOW}Starting/Monitoring Policy (Safe for beginners):{RESET}")
    print(f"   - Name:    {GREEN}_dmarc{RESET}")
    print(f"   - Value:   {GREEN}\"v=DMARC1; p=none; rua=mailto:{report_email};\""+RESET)
    print(f"\n   {YELLOW}Enforcement Policies (Required for BIMI & full protection):{RESET}")
    print(f"   - Quarantine: {GREEN}\"v=DMARC1; p=quarantine; pct=100; rua=mailto:{report_email};\""+RESET)
    print(f"   - Reject:     {GREEN}\"v=DMARC1; p=reject; pct=100; rua=mailto:{report_email};\""+RESET)
    
    print(f"\n   {YELLOW}PRO TIP:{RESET} Start with 'p=none' to monitor reports. Once you are confident that all your")
    print(f"   legitimate emails are passing SPF and DKIM, you MUST upgrade to 'p=quarantine' or")
    print(f"   'p=reject' to protect your domain and enable advanced features like BIMI.")

    print(f"\n{YELLOW}3. DKIM Record:{RESET}")
    print("   DKIM adds a digital signature to your emails. You can generate a key using the 'DKIM Key Manager' from the main menu.")
    print("   Once generated, you will be given the exact record to add.")
    dkim_selector = settings.dkim.dkim_selector
    if dkim_selector:
        print(f"   Based on your config, the DKIM record name should be: {GREEN}{dkim_selector}._domainkey{RESET}")

    # --- "World-Class" BIMI Record Suggestion ---
    print(f"\n{YELLOW}4. BIMI Record (Brand Indicators for Message Identification):{RESET}")
    print(f"   BIMI allows you to display your logo in the inbox. It requires DMARC policy of 'quarantine' or 'reject'.")
    print(f"   - Type:    {GREEN}TXT{RESET}")
    print(f"   - Name:    {GREEN}default._bimi{RESET}")
    # MailGenius highlighted missing BIMI. Suggesting a basic self-assertion record.
    print(f"   - Value:   {GREEN}\"v=BIMI1; l=https://{main_domain}/logo.svg; a=;\""+RESET)
    print("   (You must replace the URLs with the actual paths to your SVG logo and VMC file.)")

def check_reverse_dns(logger=None):
    """A 'smart' function to check for PTR/HELO mismatches for configured SMTPs."""
    print(f"\n{YELLOW}[7] Checking Reverse DNS (PTR) Records for Configured SMTPs...{RESET}")
    try:
        from function.smtp_utils import get_smtp_configs
        smtp_configs = get_smtp_configs()
        if not smtp_configs:
            print(f"{YELLOW}  No SMTP servers configured. Skipping check.{RESET}")
            return

        for config in smtp_configs:
            try:
                ip_address = gethostbyname(config.host)
                hostname, _, _ = gethostbyaddr(ip_address)
                print(f"  -> SMTP Host: {config.host} ({ip_address})")
                print(f"     - Reverse DNS (PTR): {hostname}")
                if config.host.lower() != hostname.lower():
                    print(f"{RED}     [✗] MISMATCH! Your server's hostname ({config.host}) does not match its Reverse DNS record ({hostname}).{RESET}")
                    print(f"{YELLOW}         Action: Contact your hosting provider and ask them to align the PTR record for {ip_address} to point to '{config.host}'.{RESET}")
                else:
                    print(f"{GREEN}     [✓] OK! Hostname and Reverse DNS match.{RESET}")
            except gaierror:
                print(f"{YELLOW}  -> Could not resolve IP for SMTP host '{config.host}'. Skipping.{RESET}")
            except Exception as e:
                print(f"{RED}  -> An error occurred checking {config.host}: {e}{RESET}")
    except ImportError:
        print(f"{RED}  Could not import SMTP utilities. Skipping check.{RESET}")

def main():
    parser = argparse.ArgumentParser(description="A 'smart' DNS health checker for the Advanced Sender.")
    parser.add_argument("domain", nargs='?', help="The domain or subdomain to check (e.g., track.circlesrenergy.com).")
    parser.add_argument("record_type", nargs='?', default="A", help="The DNS record type to query (e.g., A, MX, CNAME, TXT).")
    
    args = parser.parse_args()

    if args.domain:
        check_dns(args.domain, args.record_type.upper())
    else:
        # --- Interactive Mode ---
        print("--- DNS & Domain Health Check ---")
        print("This tool helps you verify that your domain settings are correct.")

        # 1. Check the tracking subdomain
        print("\n[1] Checking Custom Tracking Subdomain (e.g., track.circlesrenergy.com)...")
        tracking_domain = input("Enter your tracking subdomain (e.g., track.circlesrenergy.com): ").strip()
        if tracking_domain:
            answers = check_dns(tracking_domain, "A")
            if answers:
                # --- "Smarter" IP Check ---
                # Instead of hardcoding one IP, we make it interactive.
                expected_ip = input("  Enter the IP address your web host provided for this subdomain (or press Enter to skip): ").strip()
                if expected_ip:
                    if any(str(r) == expected_ip for r in answers):
                        print(f"{GREEN}  [✓] Correctly pointing to the expected IP address ({expected_ip}). Good job!{RESET}")
                    else:
                        print(f"{YELLOW}  [!] WARNING: The A record does not point to the expected IP address ({expected_ip}).{RESET}")
                        print(f"{YELLOW}      Please ensure your A record in your DNS settings (e.g., Hostinger) points to the 'Website IP' from your web hosting account.{RESET}")

        # 2. Check the main domain's MX records for email receiving
        print("\n[2] Checking Main Domain MX Records (for receiving replies/bounces)...")
        
        # --- "Smarter" Domain Inference ---
        main_domain = ""
        if tracking_domain:
            parts = tracking_domain.split('.')
            if len(parts) > 2:
                # Assumes something like 'track.txtarv.com', infers 'txtarv.com'
                inferred_domain = ".".join(parts[-2:])
                main_domain = input(f"Enter your main domain (inferred: {inferred_domain}): ").strip() or inferred_domain
            else:
                # Assumes the tracking domain is the main domain
                main_domain = tracking_domain
        else:
            main_domain = input("Enter your main domain (e.g., txtarv.com): ").strip()

        if main_domain:
            answers = check_dns(main_domain, "MX")
            if answers:
                print(f"{GREEN}  [✓] Found MX records. Your domain is configured to receive email.{RESET}")

        # 3. Check SPF record
        print("\n[3] Checking Main Domain SPF Record (for deliverability)...")
        if main_domain:
            answers = check_dns(main_domain, "TXT")
            if answers:
                spf_found = False
                for r in answers:
                    if "v=spf1" in r.to_text().lower():
                        print(f"{GREEN}  [✓] Found SPF record: {r.to_text()}{RESET}")
                        spf_found = True
                if not spf_found:
                    print(f"{YELLOW}  [!] No SPF record found. This can hurt deliverability. Consider adding one.{RESET}")

        # --- New: Suggest records if SPF or DMARC is missing ---
        suggest_now = False
        if main_domain and not 'spf_found' in locals() or not spf_found:
            suggest_now = True
        
        if main_domain:
            # Check DMARC record
            dmarc_domain = f"_dmarc.{main_domain}"
            # Check if DMARC is missing to trigger suggestion
            try:
                dns.resolver.resolve(dmarc_domain, "TXT")
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                suggest_now = True
        
        if suggest_now:
            if input("\nWould you like me to suggest the correct DNS records to add? [y/n]: ").strip().lower() == 'y':
                suggest_records(main_domain)
        
        # Run the DMARC check after the suggestion prompt for a better user experience
        if main_domain:
            print("\n[4] Checking Main Domain DMARC Record (for deliverability & reporting)...")
            check_dns(f"_dmarc.{main_domain}", "TXT")
            
            # --- "Smarter" HELO Check ---
            print(f"\n[4.5] HELO/EHLO SPF Check...")
            helo_name = settings.smtp.smtp_helo_name
            print(f"   Your sender uses HELO: '{helo_name}'")
            if helo_name == "localhost.localdomain":
                print(f"{YELLOW}   [!] Using 'localhost.localdomain' triggers 'SPF_HELO_NONE' in some tests.{RESET}")
                print(f"       If you use a custom domain, set 'smtp_helo_name' in config.ini to match your domain.")
        
        # --- New: Check for BIMI record ---
        if main_domain:
            print("\n[5] Checking for BIMI Record (for displaying brand logo)...")
            check_dns(f"default._bimi.{main_domain}", "TXT")

        # 5. Check for DKIM record
        if main_domain:
            print("\n[6] Checking for a common DKIM Record...")
            dkim_selector = settings.dkim.dkim_selector
            print(f"   Your configured DKIM selector is: '{dkim_selector}'" if dkim_selector else "   No DKIM selector is configured.")
            selector = input("   Enter a DKIM selector to check (e.g., 'google', 'default') (or press Enter to skip): ").strip()
            if selector:
                check_dns(f"{selector}._domainkey.{main_domain}", "TXT")

        # --- New: Add the Reverse DNS check to the interactive flow ---
        check_reverse_dns()

        print("\n--- DNS Check Complete ---")


if __name__ == "__main__":
    main()