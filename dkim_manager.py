import os
import sys
import subprocess
import shutil
import configparser

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

PROJECT_ROOT = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.ini')

def find_openssl():
    """Finds the path to the OpenSSL executable."""
    path = shutil.which('openssl')
    if path:
        return path
    if sys.platform == 'win32':
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        git_path = os.path.join(program_files, "Git", "usr", "bin", "openssl.exe")
        if os.path.exists(git_path):
            return git_path
    return None

def generate_dkim_keys():
    """
    Generates a DKIM private/public key pair and displays the required DNS record.
    """
    print("\n--- DKIM Key & DNS Record Generator ---")

    openssl_path = find_openssl()
    if not openssl_path:
        print(f"\n{RED}ERROR: OpenSSL command not found.{RESET}")
        print("Please install OpenSSL or ensure it's in your system's PATH (Git for Windows includes it).")
        input("Press Enter to return to the menu...")
        return

    print(f"Found OpenSSL at: {openssl_path}")

    # "Smarter" Fix: Prompt for the domain directly instead of relying on obsolete config settings.
    domain = input("\nEnter the domain to generate a DKIM key for (e.g., txtarv.com): ").strip()
    if not domain:
        print(f"{RED}Domain cannot be empty. Operation cancelled.{RESET}")
        return
        
    selector = input(f"\nEnter a DKIM selector (a simple name, e.g., 'dkim' or 'mail'): ").strip()
    if not selector:
        print(f"{RED}Selector cannot be empty. Operation cancelled.{RESET}")
        return

    print(f"\nGenerating a new 2048-bit DKIM key for domain '{domain}' with selector '{selector}'...")

    certs_dir = os.path.join(PROJECT_ROOT, 'certs')
    os.makedirs(certs_dir, exist_ok=True)
    private_key_path = os.path.join(certs_dir, f'dkim_{selector}.private.pem')
    public_key_path = os.path.join(certs_dir, f'dkim_{selector}.public.pem')

    try:
        # 1. Generate private key
        priv_command = [openssl_path, 'genrsa', '-out', private_key_path, '2048']
        subprocess.run(priv_command, check=True, capture_output=True)

        # 2. Extract public key from private key
        pub_command = [openssl_path, 'rsa', '-in', private_key_path, '-pubout', '-out', public_key_path]
        subprocess.run(pub_command, check=True, capture_output=True)

        print(f"\n{GREEN}Successfully generated DKIM keys:{RESET}")
        print(f"  - Private Key: {private_key_path}")
        print(f"  - Public Key:  {public_key_path}")

        # 3. Read the public key and format it for DNS
        with open(public_key_path, 'r') as f:
            public_key_lines = f.read().splitlines()
        # Remove the header and footer lines ('-----BEGIN PUBLIC KEY-----')
        public_key_base64 = "".join(public_key_lines[1:-1])

        # Format the DNS record value
        dns_value = f"v=DKIM1; k=rsa; p={public_key_base64}"

        print(f"\n{YELLOW}--- DNS Record to Add ---{RESET}")
        print("Add the following TXT record to your DNS provider (e.g., Hostinger):")
        print(f"\n  - Type:    {GREEN}TXT{RESET}")
        print(f"  - Name:    {GREEN}{selector}._domainkey{RESET}  (or {selector}._domainkey.{domain})")
        print(f"  - Value:   {GREEN}\"{dns_value}\"{RESET}")
        print(f"  - TTL:     14400 (or default)")

        # --- "World-Class" Auto-Configuration ---
        # Automatically update config.ini with the new settings
        try:
            cfg = configparser.ConfigParser()
            cfg.read(CONFIG_PATH)
            if not cfg.has_section('DKIM'):
                cfg.add_section('DKIM')
            
            relative_private_key_path = os.path.join('certs', f'dkim_{selector}.private.pem')
            
            cfg.set('DKIM', 'dkim_enabled', 'true')
            cfg.set('DKIM', 'dkim_selector', selector)
            cfg.set('DKIM', 'dkim_private_key_file', relative_private_key_path)
            
            with open(CONFIG_PATH, 'w') as f:
                cfg.write(f)
            
            print(f"\n{GREEN}Configuration Updated!{RESET}")
            print(f"  - Enabled DKIM and set the private key path in 'config.ini'.")
        except Exception as e:
            print(f"\n{RED}Could not automatically update 'config.ini': {e}{RESET}")
            print(f"{YELLOW}Please manually set 'dkim_private_key_file = {relative_private_key_path}' in your config.{RESET}")

    except subprocess.CalledProcessError as e:
        print(f"\n{RED}ERROR: OpenSSL command failed.{RESET}")
        print(f"Stderr: {e.stderr.decode('utf-8', errors='ignore')}")
    except Exception as e:
        print(f"\n{RED}An unexpected error occurred: {e}{RESET}")

    input("\nPress Enter to return to the menu...")

if __name__ == "__main__":
    generate_dkim_keys()