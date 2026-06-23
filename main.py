import threading
import sys
import time
import types
try:
    from colorama import init as _color_init, Fore, Style
    _color_init(autoreset=True)
    RED = Fore.RED
    GREEN = Fore.GREEN
    YELLOW = Fore.YELLOW
    RESET = Style.RESET_ALL
except ImportError:
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    RESET = '\033[0m'

import os
# --- "World-Class" Fix: GTK3 Path Handling for Windows (Fixes error 0x7e) ---
# This ensures WeasyPrint can find the required DLLs on Windows systems.
_gtk_path_used = None
if os.name == 'nt':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # 1. Identify potential local paths
    candidates = [
        os.path.join(base_dir, 'gtk', 'bin'),
        os.path.join(base_dir, 'gtk'),
    ]
    # Scan for nested (zip extracted) folders
    local_gtk_root = os.path.join(base_dir, 'gtk')
    if os.path.exists(local_gtk_root):
        for item in os.listdir(local_gtk_root):
            sub_bin = os.path.join(local_gtk_root, item, 'bin')
            if os.path.isdir(sub_bin):
                candidates.insert(0, sub_bin)

    # 2. Validate paths contain critical DLL (Strict Validation)
    valid_gtk_path = None
    for path in candidates:
        if os.path.exists(os.path.join(path, 'libpango-1.0-0.dll')):
            valid_gtk_path = path
            break
    
    _dll_handles = [] # Keep handles alive
    if valid_gtk_path:
        print(f"--- GTK3: Using Local Runtime at {valid_gtk_path} ---")
        _gtk_path_used = valid_gtk_path
        os.environ['PATH'] = valid_gtk_path + os.pathsep + os.environ.get('PATH', '')
        if hasattr(os, 'add_dll_directory'):
            try:
                _dll_handles.append(os.add_dll_directory(valid_gtk_path))
            except Exception:
                pass
    else:
        # Fallback: Check for standard system install locations of the *correct* runtime (GTK3-Runtime)
        # and prioritize them over any broken ones (Gtk-Runtime) in the PATH.
        system_candidates = [
            r'C:\Program Files\GTK3-Runtime\bin',
            r'C:\Program Files (x86)\GTK3-Runtime\bin',
        ]
        system_found = False
        for sys_path in system_candidates:
            if os.path.exists(os.path.join(sys_path, 'libpango-1.0-0.dll')):
                print(f"--- GTK3: Found System Runtime at {sys_path}. Prioritizing... ---")
                _gtk_path_used = sys_path
                os.environ['PATH'] = sys_path + os.pathsep + os.environ.get('PATH', '')
                if hasattr(os, 'add_dll_directory'):
                    try:
                        _dll_handles.append(os.add_dll_directory(sys_path))
                    except Exception:
                        pass
                system_found = True
                break
        
        if not system_found:
            print("--- GTK3: Local/System Runtime not found. Relying on PATH (May fail). ---")

import builtins
import sqlite3
import socket
import configparser
import logging
import html2text
import csv
import json
import smtplib
import imaplib
import random
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.utils import make_msgid
from email import encoders
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import warnings

# --- "World-Class" Fix: Pre-silence WeasyPrint logger before import ---
logging.getLogger('weasyprint').setLevel(logging.CRITICAL)
from PIL import Image, ImageDraw, ImageFont
import base64
import re
import dns.resolver
from jinja2 import Environment, FileSystemLoader

import collections
import requests
# --- PySocks Import ---
try:
    import socks
except ImportError:
    socks = None
# --- QR Code Import ---
try:
    import segno
    from io import BytesIO
except ImportError:
    segno = None
# --- EWS and S/MIME Imports ---
try:
    import exchangelib
    from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
except ImportError:
    exchangelib = None

from function import smtp_utils, encryption
from function.message_builder import MessageBuilder
from function.context_builder import ContextBuilder
from function import transports, imap_bounce
from function.keyboard_utils import keyboard_listener

# --- "World-Class" Log Suppression ---
# Silence annoying CSS validation warnings from cssutils (used by premailer/weasyprint)
try:
    import cssutils
    cssutils.log.setLevel(logging.CRITICAL)
    logging.getLogger('weasyprint').setLevel(logging.CRITICAL)
except ImportError:
    pass

print("--- Sentinel Jesko ---", flush=True)

# The real sys.exit is used throughout to allow the script to terminate correctly.
_real_exit = sys.exit

# --- Corrected Import ---
# dynamic_content.py is in the root, not in the 'function' directory
import dynamic_content
# --- New "Smart" Settings Import ---
# This single import brings in our validated, type-safe configuration
from settings import settings, RecipientModel

# --- Non-interactive safety overrides ---
# If the script is run with '--no-listener' or '--no-input', replace interactive
# input/getpass calls with safe defaults so the process cannot block waiting
# for user input.
if any(arg in sys.argv for arg in ('--no-listener', '--no-input')):
    import getpass as _getpass_mod
    _orig_input = builtins.input
    def _safe_input(prompt=''):
        # Log the prompt for debugging, return empty string to accept defaults
        try:
            print(f"[AUTO-INPUT] {prompt}")
        except Exception:
            pass
        return ''
    builtins.input = _safe_input

    _orig_getpass = _getpass_mod.getpass
    def _safe_getpass(prompt='Password: ', stream=None):
        # Try to extract an email from the prompt and return a matching password from settings
        try:
            import re
            m = re.search(r'for\s+(\S+):', prompt)
            if m:
                email = m.group(1)
                pw = settings.dev.smtp_passwords.get(email) or settings.dev.smtp_passwords.get(email.lower())
                if pw:
                    print(f"[AUTO-PASS] Using password from settings for {email}")
                    return pw
        except Exception:
            pass
        return ''
    _getpass_mod.getpass = _safe_getpass

# --- "World-Class" Anti-Freeze: Global Socket Timeout ---
# This prevents any network operation (EWS, SMTP, AI) from hanging indefinitely.
socket.setdefaulttimeout(40.0) # Lowered to 40s to prevent long hangs

# --- "World-Class" Fix: Force IPv4 globally ---
# This prevents IPv6-related hangs on Office 365 and Gmail across the entire app.
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [response for response in responses if response[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo

# --- "World-Class" EWS Timeout & IPv4 Enforcer ---
if exchangelib:
    # 2. Patch HTTP Adapter to enforce strict request timeouts
    class TimeoutAdapter(BaseProtocol.HTTP_ADAPTER_CLS):
        def send(self, *args, **kwargs):
            # Force timeout to 30s always to prevent hangs, overriding library defaults
            kwargs['timeout'] = 30 
            return super().send(*args, **kwargs)
    BaseProtocol.HTTP_ADAPTER_CLS = TimeoutAdapter

DB_PATH = os.path.join(os.path.dirname(__file__), 'logs', 'state.db')

# --- "World-Class" Thread-Safe Proxy SMTP Classes ---
# These classes override the internal socket creation of smtplib to use PySocks
# on a per-instance basis, rather than patching the global socket module.
# This prevents race conditions where one thread changes the proxy for everyone.
class ProxySMTP(smtplib.SMTP):
    def __init__(self, host='', port=0, local_hostname=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, proxy_settings=None):
        self.proxy_settings = proxy_settings
        super().__init__(host, port, local_hostname, timeout, source_address)

    def _get_socket(self, host, port, timeout):
        if self.proxy_settings and socks:
            return socks.create_connection(
                (host, port), timeout=timeout,
                proxy_type=self.proxy_settings['type'],
                proxy_addr=self.proxy_settings['host'],
                proxy_port=self.proxy_settings['port'],
                proxy_rdns=True, # Prevent DNS leaks
                proxy_username=self.proxy_settings['username'],
                proxy_password=self.proxy_settings['password']
            )
        return super()._get_socket(host, port, timeout)

class ProxySMTP_SSL(smtplib.SMTP_SSL):
    def __init__(self, host='', port=0, local_hostname=None, keyfile=None, certfile=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, context=None, proxy_settings=None):
        self.proxy_settings = proxy_settings
        super().__init__(host, port, local_hostname, keyfile, certfile, timeout, source_address, context)

    def _get_socket(self, host, port, timeout):
        if self.proxy_settings and socks:
            sock = socks.create_connection(
                (host, port), timeout=timeout,
                proxy_type=self.proxy_settings['type'],
                proxy_addr=self.proxy_settings['host'],
                proxy_port=self.proxy_settings['port'],
                proxy_rdns=True,
                proxy_username=self.proxy_settings['username'],
                proxy_password=self.proxy_settings['password']
            )
            if self.context:
                return self.context.wrap_socket(sock, server_hostname=host)
            return socket.ssl(sock)
        return super()._get_socket(host, port, timeout)

class Sender:
    def __init__(self):
        """Initializes the sender by loading all settings from the config file."""
        # --- Initialize all attributes first ---
        self.smtp_pool = []
        self._current_smtp_index = 0
        self.sent_recipients_path = None
        self.sends_completed = 0
        self.failures = 0
        self.failure_reasons = {}
        self.proxy_pool = []
        self._current_proxy_index = 0
        self.paused = threading.Event()
        self.shutdown_event = threading.Event()
        self.project_root = os.path.dirname(__file__)
        self.thread_local = threading.local()
        # Lock to protect smtp_pool modifications
        self.proxy_pool_lock = threading.Lock()
        self.smtp_pool_lock = threading.Lock()
        self.throttle_lock = threading.Lock() # For dynamic throttling
        self.suppression_lock = threading.Lock() # For suppression_list.txt
        self.deliverability_lock = threading.Lock() # For hourly send cap
        self.db_lock = threading.Lock() # New lock for all database operations
        self.verification_log_lock = threading.Lock() # For verification_log.csv
        self.ews_token_is_dead = False # New flag to act as a circuit breaker for EWS tokens
        self._logged_imap_blocks = set() # Track IMAP accounts that have logged instructions
        # --- "Sentinel" State ---
        self.sentinel_delivery_methods = ['direct', 'secure_document', 'safe_link']
        self.sentinel_current_delivery_index = self.sentinel_delivery_methods.index(settings.email.link_delivery_method) if settings.email.link_delivery_method in self.sentinel_delivery_methods else 0
        self.sentinel_polymorphic_active = False # Tracks if Sentinel has forced AI rewrite
        # --- New: Performance Tracking ---
        self.hunter_client = None
        self.send_timestamps = collections.deque()
        # --- Deliverability: Hourly send cap and time window enforcement ---
        self._hourly_send_count = 0
        self._last_hourly_reset = time.time()
        # --- "Jesko" Engine: Adaptive Pacing ---
        self.recent_outcomes = collections.deque(maxlen=50) # Track last 50 sends for failure rate
        self.performance_lock = threading.Lock()
        # --- Now, run setup methods ---
        self._setup_logging() # Logging first
        self._load_settings_from_pydantic() # New method to use Pydantic settings
        self.load_recipients() # Load recipients early
        self._setup_templating() # Must be before builders that need it
        self._setup_proxy() # Depends on settings
        self.context_builder = ContextBuilder(self.logger, settings)
        self.message_builder = MessageBuilder(self.logger, settings, self.jinja_env, self.project_root)
    def _setup_logging(self):
        """Sets up logging to logs/sender.log with rotation and console output."""
        log_dir = os.path.join(self.project_root, 'logs')
        os.makedirs(log_dir, exist_ok=True)

        # --- "World-Class" Catastrophic Failure Check ---
        # Before doing anything else, check if we can even write to the disk.
        try:
            test_file_path = os.path.join(log_dir, 'write_test.tmp')
            with open(test_file_path, 'w') as f:
                f.write('test')
            os.remove(test_file_path)
        except OSError as e:
            if e.errno == 28: # No space left on device
                print(f"{RED}FATAL ERROR: No space left on device.{RESET}")
                print(f"{RED}The application cannot write to the log directory: {log_dir}{RESET}")
                print(f"{RED}Please free up disk space and try again.{RESET}")
                _real_exit(1) # Use the real exit to terminate immediately.

        log_file = os.path.join(log_dir, 'sender.log')
        self.logger = logging.getLogger('SenderLogger')
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        # File handler with rotation
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(log_file, maxBytes=2*1024*1024, backupCount=5, encoding='utf-8')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        # --- "Smarter" Database Initialization Check ---
        # Ensure the database exists before we do anything else.
        if not os.path.exists(DB_PATH):
            self.logger.warning(f"Database not found at '{DB_PATH}'.")
            try:
                from database_manager import initialize_database
                self.logger.info("Attempting to initialize the database now...")
                initialize_database()
            except Exception as e:
                self.logger.critical(f"FATAL: Failed to initialize database: {e}")
                self.logger.critical("Please run 'Initialize/Reset Database' from the menu.")
                _real_exit(1)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        self.logger.info("="*50)
        self.logger.info("Initializing New Sender Job")
        if '_gtk_path_used' in globals() and globals()['_gtk_path_used']:
            self.logger.info(f"GTK3 Runtime loaded from: {globals()['_gtk_path_used']}")
        self.logger.info("="*50)

    def _load_settings_from_pydantic(self):
        """
        Assigns validated settings from the global Pydantic `settings` object
        to instance attributes for use throughout the class.
        """
        self.logger.info("Loading validated settings...")

        # General
        self.recipients_file = settings.general.recipients_file
        self.sending_method = settings.general.sending_method.lower()
        self.max_workers = settings.general.max_workers
        self.sleep_time = settings.general.send_sleep_seconds
        self.dynamic_sleep_time = float(self.sleep_time) # Start with the base sleep time

        # Sender

        # Email
        self.subject_list = settings.email.email_subjects
        self.message_file_list = settings.email.message_file
        self.unsubscribe_url = str(settings.email.unsubscribe_url)

        # --- "Jesko" Engine: Parse Link Pool ---
        # Fix: settings.email.link_url is already a list. Convert Url objects to strings.
        if settings.email.link_url:
            self.link_pool = [str(url) for url in settings.email.link_url]
        else:
            self.link_pool = ['#']

        # Dev / API Keys
        self.simulation_mode = settings.dev.simulation_mode
        self.verify_emails = settings.dev.verify_emails_before_send if hasattr(settings.dev, 'verify_emails_before_send') else False
        self.verify_emails_local = getattr(settings.dev, 'verify_emails_local', False)
        self.verify_emails_compulsory = getattr(settings.dev, 'verify_emails_compulsory', False)

        # SMTP
        self.smtp_servers = settings.smtp.smtp_servers
        self.smtp_timeout = settings.smtp.smtp_timeout
        self.smtp_rotation_mode = settings.smtp.smtp_rotate_mode.lower()
        self.failure_threshold = settings.smtp.smtp_failure_threshold
        self.cooldown_minutes = settings.smtp.smtp_cooldown_minutes
        self.smtp_delete_sent = settings.smtp.smtp_delete_sent

        # --- New: DKIM Signing Settings ---
        self.dkim_enabled = settings.dkim.dkim_enabled
        self.dkim_selector = settings.dkim.dkim_selector
        self.dkim_private_key_file = str(settings.dkim.dkim_private_key_file) if settings.dkim.dkim_private_key_file else ''

        # Attachment
        self.attachment_send = settings.attachment.attachment_send
        self.attachment_file = settings.attachment.attachment_file
        self.attachment_display_name = settings.attachment.attachment_display_name
        self.attachment_dynamic_pdf = settings.attachment.attachment_dynamic_pdf
        self.attachment_template_file = settings.attachment.attachment_template_file

        # S/MIME
        self.smime_sign = settings.smime.smime_sign
        self.smime_key_password = settings.smime.smime_key_password

        # Link Shortener
        self.shortener_enabled = settings.link_shortener.shortener_enabled
        self.link_cache = {}
        self.link_cache_lock = threading.Lock()

        # Warmup
        self.warmup_enabled = settings.warmup.warmup_enabled
        self.warmup_sends = settings.warmup.warmup_sends
        self.warmup_initial_workers = settings.warmup.warmup_initial_workers
        self.warmup_ramp_up_sends = settings.warmup.warmup_ramp_up_sends
        self.warmup_plain_text_only = settings.warmup.warmup_plain_text_only
        self.warmup_daily_start = settings.warmup.warmup_daily_start
        self.warmup_daily_increment = settings.warmup.warmup_daily_increment
        self.warmup_target_sends = settings.warmup.warmup_target_sends

        # Proxy
        self.proxy_enabled = settings.proxy.proxy_enabled
        self.proxy_rotate_mode = settings.proxy.proxy_rotate_mode.lower()
        self.proxy_list_str = settings.proxy.proxy_list

        # Misc
        self.retry_attempts = settings.misc.retry_attempts
        self.retry_delay_seconds = settings.misc.retry_delay_seconds

        # HTML Conversion
        self.html_to_pdf = settings.html_conversion.html_to_pdf
        self.letter_image = settings.html_conversion.letter_image
        self.obfuscate_html = settings.html_conversion.obfuscate_html

        # QR
        self.qr_enabled = settings.qr.qr_enabled
        self.qr_scale = settings.qr.qr_scale
        self.qr_border = settings.qr.qr_border
        self.qr_fg_color = settings.qr.qr_fg_color

        # --- "World-Class" Hunter.io Client Initialization ---
        # Securely load the API key and initialize the client for email verification.
        self.hunter_api_key = str(settings.dev.hunter_api_key) if settings.dev.hunter_api_key else None
        if self.verify_emails and self.hunter_api_key:
            try:
                from pyhunter import PyHunter
                self.hunter_client = PyHunter(self.hunter_api_key)
                self.logger.info("Hunter.io client initialized for email verification.")
            except ImportError:
                self.logger.warning("'pyhunter' is not installed. Email verification is disabled.")
                self.hunter_client = None

        if self.sending_method == 'ews':
            if exchangelib is None:
                self.logger.critical("FATAL: 'exchangelib' is not installed. Please run 'pip install exchangelib'.")
                _real_exit(1)
            self.ews_username = settings.ews.ews_username # Used by both auth methods
 
            # --- "World-Class" EWS Auth Validation ---
            # Check for a valid auth configuration for EWS before starting.
            has_oauth = settings.ews.ews_use_oauth
            has_cookies = bool(settings.ews.ews_cookies)
            # Basic auth is the fallback if not oauth and no cookies
            is_basic_auth = not has_oauth and not has_cookies
            has_basic_pass = is_basic_auth and bool(settings.dev.smtp_passwords.get(self.ews_username))
 
            if not (has_oauth or has_cookies or has_basic_pass):
                self.logger.critical("FATAL: EWS sending method is selected, but no valid authentication method is configured.")
                self.logger.critical("Please go to 'Configuration & Setup' -> 'EWS (Office365/GoDaddy) Setup' to configure it.")
                _real_exit(1)

        # Load attachment info
        self.attachment_path = None
        if self.attachment_send and self.attachment_file:
            self.attachment_path = os.path.join(self.project_root, 'files', self.attachment_file)
            if not os.path.exists(self.attachment_path):
                self.logger.warning(f"Attachment file not found at {self.attachment_path}")
                self.attachment_path = None
            else:
                self.logger.info(f"Attachment enabled: {self.attachment_file}")

    def _setup_templating(self):
        """Initializes the Jinja2 templating environment."""
        template_dir = os.path.join(self.project_root, 'files')
        
        # --- New: Spintax Engine ---
        def spintax_filter(text):
            """Parses spintax formatted text and returns a random variation."""
            pattern = re.compile(r'\{([^{}]*?)\}')
            while True:
                match = pattern.search(text)
                if not match:
                    break
                content = match.group(1)
                # Split by pipe | but allow escaped \| for robust handling
                parts = re.split(r'(?<!\\)\|', content)
                # Pick a random part and unescape any pipes within it
                replacement = random.choice(parts).replace(r'\|', '|')
                text = text[:match.start()] + replacement + text[match.end():]
            return text

        # --- "World-Class" Date Formatting Filter ---
        def format_date_filter(date_string, fmt=None):
            """Parses a date string (YYYY-MM-DD) and formats it."""
            if not date_string:
                return ""
            try:
                date_obj = datetime.strptime(date_string, '%Y-%m-%d')
                if fmt:
                    return date_obj.strftime(fmt)
                return date_string
            except (ValueError, TypeError):
                return date_string # Return original on error

        self.jinja_env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
        self.jinja_env.filters['spintax'] = spintax_filter # Register the filter
        self.jinja_env.filters['format_date'] = format_date_filter # Register the new date filter
        self.logger.info(f"Jinja2 templating environment initialized for directory: {template_dir}")

    def _setup_proxy(self):
        """Fetches proxies from a URL and parses local proxy list."""
        if not self.proxy_enabled:
            return

        self.logger.info("Proxy support is enabled. Parsing proxy sources...")
        
        all_proxy_entries = self.proxy_list_str
        self.logger.info(f"Found {len(all_proxy_entries)} proxies in local config.")

        # --- "Jesko" Engine: IP Sanity Check ---
        if all_proxy_entries:
            first_ip = all_proxy_entries[0].split('|')[1]
            if first_ip.startswith('10.') or first_ip.startswith('192.168.') or first_ip == '127.0.0.1':
                self.logger.info(f"{YELLOW}PROX-ALERT: Detected Local/Loopback IP: {first_ip}. Ensure your Dichvusocks client is OPEN and ACTIVE.{RESET}")

        # --- "World-Class" Pre-flight Proxy Validation ---
        try:
            from proxy_connectivity_test import test_proxy
            from concurrent.futures import as_completed

            self.logger.info("Validating proxies... (Checking connectivity to google.com)")
            working_entries = []

            with ThreadPoolExecutor(max_workers=min(20, len(all_proxy_entries) + 1)) as executor:
                future_to_proxy = {executor.submit(test_proxy, p): p for p in all_proxy_entries if p.strip()}
                for future in as_completed(future_to_proxy):
                    p_str = future_to_proxy[future]
                    try:
                        _, success, msg = future.result()
                        if success:
                            working_entries.append(p_str)
                        else:
                            parts = p_str.split('|')
                            host_port = f"{parts[1]}:{parts[2]}" if len(parts) > 2 else "Unknown"
                            self.logger.warning(f"Discarding bad proxy {host_port}: {msg}")
                    except Exception as e:
                        self.logger.warning(f"Proxy check raised exception: {e}")
            self.logger.info(f"Proxy Validation Result: {len(working_entries)} out of {len(all_proxy_entries)} proxies are healthy.")
            all_proxy_entries = working_entries
            settings.proxy.proxy_list = working_entries # Update global settings for AI client
        except Exception as e:
            self.logger.warning(f"Proxy validation failed ({e}). Proceeding with all proxies.")

        for entry in all_proxy_entries:
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split('|')
            if len(parts) < 3:
                self.logger.warning(f"Skipping invalid proxy entry: {entry}. Format: type|host|port|username|password")
                continue
            
            proxy_type_str = parts[0].lower()
            if socks is None:
                self.logger.error("PySocks is not installed. Cannot use proxy feature. Please run 'pip install PySocks'.")
                return
            proxy_map = {'socks5': socks.SOCKS5, 'socks4': socks.SOCKS4, 'http': socks.HTTP}
            if proxy_type_str not in proxy_map:
                self.logger.warning(f"Invalid proxy type '{parts[0]}'. Supported types: socks5, socks4, http.")
                continue

            self.proxy_pool.append({
                'type': proxy_map[proxy_type_str],
                'host': parts[1],
                'port': int(parts[2]),
                'username': parts[3] if len(parts) > 3 else None,
                'password': parts[4] if len(parts) > 4 else None,
                'status': 'ok' # New: Add a status field for health tracking
            })
        
        if self.proxy_pool:
            self.logger.info(f"Successfully loaded {len(self.proxy_pool)} proxies into the pool.")
        else:
            self.logger.warning("Proxy is enabled, but no valid proxies were found from any source.")

    def load_recipients(self):
        """Loads recipients from the CSV file and filters out those already sent."""
        self.logger.info("Loading recipients...")
        recipients_path = os.path.join(self.project_root, self.recipients_file)
        if not os.path.exists(recipients_path):
            self.logger.critical(f"FATAL: Recipients file not found at {recipients_path}")
            _real_exit(1)

        # Load already sent recipients to support resuming campaigns
        sent_recipients = set()  # Default to an empty set
        try:
            with self.db_lock:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT recipient_email FROM sent_log")
                # Use a generator expression for memory efficiency
                sent_recipients = {row[0] for row in cursor.fetchall()}
                conn.close()
                self.logger.info(f"Loaded {len(sent_recipients)} recipients from the sent log to be skipped.")
        except Exception as e:
            self.logger.warning(f"Could not read sent recipients from database: {e}")

        # --- "Smarter" Auto-Warmup ---
        # If the sent log is empty, it's a fresh campaign, so force warmup if it's enabled in config.
        if not sent_recipients and self.warmup_enabled:
            self.logger.info("Fresh campaign detected with warm-up enabled. Activating warm-up mode.")

        # Load all recipients from CSV
        all_recipients = []
        file_ext = os.path.splitext(recipients_path)[1].lower()
        if file_ext == '.txt':
            self.logger.info("Reading recipients from .txt file (one email per line).")
            try:
                with open(recipients_path, 'r', encoding='utf-8') as f:
                    all_recipients = [RecipientModel(email=line.strip()) for line in f if line.strip()]
            except Exception as e:
                self.logger.critical(f"FATAL: Failed to read recipients file {recipients_path}. Error: {e}")
                _real_exit(1)
        elif file_ext == '.csv':
            self.logger.info("Reading recipients from .csv file.")
            try:
                with open(recipients_path, 'r', encoding='utf-8-sig') as f: # utf-8-sig handles BOM
                    # Sniff to see if the CSV has a header
                    has_header = csv.Sniffer().has_header(f.read(1024))
                    f.seek(0) # Rewind file
                    reader = csv.reader(f)
                    if has_header:
                        header = [h.lower().strip() for h in next(reader)]
                        for row in reader:
                            # Create a RecipientModel from the row dictionary
                            all_recipients.append(RecipientModel(**dict(zip(header, row))))
                    else: # No header, assume first column is email
                        for row in reader:
                            if row: all_recipients.append(RecipientModel(email=row[0].lower()))
            except Exception as e:
                self.logger.critical(f"FATAL: Failed to read recipients file {recipients_path}. Error: {e}")
                _real_exit(1)
        else:
            self.logger.critical(f"FATAL: Unsupported recipients file format '{file_ext}'. Please use .txt or .csv.")
            _real_exit(1)

        # --- New: De-duplicate the recipient list ---
        unique_recipients = []
        seen_emails = set()
        invalid_format_count = 0
        for recipient in all_recipients:
            email = recipient.email.strip().lower()
            if email and re.match(r"[^@]+@[^@]+\.[^@]+", email) and email not in seen_emails:
                unique_recipients.append(recipient)
                seen_emails.add(email)
            elif email and email not in seen_emails:
                invalid_format_count += 1
            # Duplicates are handled by the `email not in seen_emails` check
        
        num_duplicates = len(all_recipients) - len(unique_recipients)
        if num_duplicates > 0 or invalid_format_count > 0:
            self.logger.info(f"List cleaning: Removed {num_duplicates} duplicate(s) and {invalid_format_count} invalid format(s).")

        # --- Pre-send Email Verification (Hunter.io or Local Tier-1 DNS) ---
        final_recipients = unique_recipients
        verified_csv = os.path.join(self.project_root, "logs", "verified_recipients.csv")
        use_local   = self.verify_emails_local
        use_hunter  = self.verify_emails and self.hunter_client
        compulsory  = self.verify_emails_compulsory

        # Compulsory mode: if no verified CSV exists, force the user to run the verifier first
        if compulsory and not os.path.exists(verified_csv):
            self.logger.critical(
                "COMPULSORY VERIFICATION: No verified_recipients.csv found. "
                "Run the verifier first from the menu (Option 8) or by executing "
                "function/list_hygiene.py. Send aborted."
            )
            print("\n[bold red]VERIFICATION REQUIRED[/bold red]")
            print("No verified recipient list was found. Before sending, you must verify your list.")
            print("Please run the Scann & Verify List option from the menu first.")
            _real_exit(1)

        # If a verified CSV exists, prefer it (it has verdict + score columns)
        if os.path.exists(verified_csv):
            try:
                with open(verified_csv, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    kept_emails = set()
                    for row in reader:
                        verdict = row.get('verdict', '').lower()
                        # Default keep set: deliverable, risky, catch_all_risky
                        if verdict in ('deliverable', 'risky', 'catch_all_risky'):
                            kept_emails.add(row['email'].strip().lower())
                    if kept_emails:
                        final_recipients = [r for r in unique_recipients if r.email.strip().lower() in kept_emails]
                        self.logger.info(
                            f"Loaded verified_recipients.csv: {len(kept_emails)} kept, "
                            f"{len(unique_recipients) - len(final_recipients)} dropped."
                        )
            except Exception as e:
                self.logger.warning(f"Could not read verified CSV: {e}. Falling back to full list.")

        # Hunter.io fallback (only if no verified CSV and Hunter is enabled)
        if use_hunter and not os.path.exists(verified_csv):
            self.logger.info("--- Starting Hunter.io pre-send verification... ---")
            verified_recipients = []
            invalid_count = 0
            for recipient in final_recipients:
                email = recipient.email.strip()
                if not email:
                    continue
                try:
                    verification_data = self.hunter_client.email_verifier(email)
                    status = verification_data.get('result')
                    action = "kept"
                    if status in ['deliverable', 'risky']:
                        verified_recipients.append(recipient)
                        self.logger.debug(f"Verification PASSED for {email} ({status})")
                    else:
                        self.logger.warning(f"Verification FAILED for {email} ({status}). Removed.")
                        invalid_count += 1
                        action = "removed"
                    self._write_verification_report([datetime.now().isoformat(), email, status, action])
                except Exception as e:
                    self.logger.warning(f"Could not verify {email}: {e}. Keeping in list.")
                    verified_recipients.append(recipient)
                time.sleep(0.2)
            if invalid_count:
                self.logger.info(f"Hunter.io removed {invalid_count} undeliverable email(s).")
            final_recipients = verified_recipients

        # Local Tier-1 fallback (only if no verified CSV and local verifier enabled)
        # This runs synchronously inside load_recipients; for large lists, prefer pre-generating the CSV.
        if use_local and not os.path.exists(verified_csv) and not use_hunter:
            self.logger.info("--- Starting local Tier-1 verification (DNS-only, zero IP risk) ---")
            try:
                from function.list_hygiene import process_batch, VERDICT_KEEP
                emails = [r.email.strip() for r in final_recipients if r.email.strip()]
                results = process_batch(emails, concurrency=min(25, self.max_workers))
                kept_emails = {r.email.lower() for r in results if r.verdict in VERDICT_KEEP}
                pre_count = len(final_recipients)
                final_recipients = [r for r in final_recipients if r.email.strip().lower() in kept_emails]
                dropped = pre_count - len(final_recipients)
                self.logger.info(f"Local verifier removed {dropped} email(s). {len(final_recipients)} remain.")
            except Exception as e:
                self.logger.warning(f"Local verification failed: {e}. Keeping full list.")

        # --- End of Verification Logic ---

        # Filter out already sent and suppressed recipients
        suppressed_recipients = set()
        suppression_list_path = os.path.join(self.project_root, 'logs', 'suppression_list.txt')
        if os.path.exists(suppression_list_path):
            try:
                with open(suppression_list_path, 'r', encoding='utf-8') as f:
                    suppressed_recipients = {line.strip().lower() for line in f if line.strip()}
            except Exception as e:
                self.logger.warning(f"Could not read suppression list: {e}")

        # --- "World-Class" Dry-Run Bypass ---
        # If running a dry-run (simulation), we want to test even if the recipient was already "sent" to.
        is_dry_run = any(arg.startswith('--dry-run') or arg == '--dryrun' for arg in sys.argv)
        if is_dry_run:
            self.logger.info("Dry-run detected: Bypassing 'Sent' log filter to allow re-testing.")
            recipients_to_send = final_recipients
        else:
            recipients_to_send = [r for r in final_recipients if r.email.strip().lower() not in sent_recipients]

        num_suppressed = len(recipients_to_send)
        recipients_to_send = [r for r in recipients_to_send if r.email.strip().lower() not in suppressed_recipients]
        num_suppressed -= len(recipients_to_send)
        self.recipients = recipients_to_send
        self.logger.info(f"Loaded {len(all_recipients)} total recipients. After filtering sent/suppressed, {len(self.recipients)} remain.")

    def _write_verification_report(self, row):
        """Appends a row to the verification_log.csv file."""
        with self.verification_log_lock:
            try:
                report_path = os.path.join(self.project_root, 'logs', 'verification_log.csv')
                header_needed = not os.path.exists(report_path)
                with open(report_path, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    if header_needed:
                        writer.writerow(['timestamp', 'email', 'status', 'action'])
                    writer.writerow(row)
            except Exception as e:
                self.logger.warning(f"Failed to write verification report: {e}")

    def run_bounce_scan(self):
        """Run IMAP bounce scan if IMAP accounts are configured in config/imap_accounts.json."""
        try:
            project_root = self.project_root
            imap_config_path = os.path.join(project_root, 'config', 'imap_accounts.json')
            if os.path.exists(imap_config_path):
                import json
                with open(imap_config_path, 'r', encoding='utf-8') as f:
                    accounts = json.load(f)
                suppressed = imap_bounce.scan_bounces(accounts, project_root=project_root)
                self.logger.info(f"IMAP bounce scan completed. Suppressed recipients: {len(suppressed)}")
        except Exception as e:
            self.logger.warning(f"IMAP bounce scan error: {e}")

    def _convert_html_to_pdf_async(self, html_string):
        """Convert HTML to PDF in background thread, return bytes or None on failure."""
        try:
            # Submit to a thread pool
            with ThreadPoolExecutor(max_workers=2) as ex:
                future = ex.submit(self._convert_html_to_pdf_sync, html_string)
                return future.result()
        except Exception as e:
            self.logger.warning(f"Async PDF conversion failed: {e}")
            return None

    def _convert_html_to_pdf_sync(self, html_string):
        """Synchronous conversion attempt using WeasyPrint, returns bytes or None."""
        try:
            # Lazy import to prevent startup hangs
            from weasyprint import HTML
            pdf_bytes = HTML(string=html_string).write_pdf()
            return pdf_bytes
        except Exception as e:
            self.logger.warning(f"PDF conversion failed (WeasyPrint may be missing/broken): {e}")
            return None

    def set_smtp_pool(self, pool):
        """Sets the SMTP pool (list of working SMTP configs) for the sender."""
        self.smtp_pool = pool or []
        self.logger.info(f"SMTP pool set with {len(self.smtp_pool)} working server(s).")

    def _persist_smtp_usage(self):
        """Persist current smtp_pool sent_count values to the database."""
        try:
            with self.db_lock:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                for s in self.smtp_pool:
                    smtp_id = f"{s.host}:{s.port}:{s.email}"
                    sent_count = s.sent_count
                    cursor.execute("""
                        INSERT INTO smtp_state (smtp_id, sent_count) VALUES (?, ?)
                        ON CONFLICT(smtp_id) DO UPDATE SET sent_count = excluded.sent_count
                    """, (smtp_id, sent_count))
                conn.commit()
                conn.close()
            self.logger.debug("SMTP usage persisted to database.")
        except Exception as e:
            self.logger.warning(f"Failed to persist SMTP state: {e}")

    def _select_smtp_for_send(self, recipient_domain, exclude_ids=None):
        """Selects an SMTP config from the pool respecting rotation and limits.
        Returns the smtp_config dict or None if none available.
        """
        with self.smtp_pool_lock:
            if not self.smtp_pool:
                return None
            exclude_ids = exclude_ids or set()

            # --- SES Mode: bypass warmup/rotation/health scoring ---
            try:
                ses_mode = bool(getattr(settings.smtp, 'smtp_ses_mode', False))
            except Exception:
                ses_mode = False
            if ses_mode:
                first = self.smtp_pool[0]
                try:
                    if first.transport == 'ses':
                        return first
                except Exception:
                    pass
                return next((s for s in self.smtp_pool if getattr(s, 'transport', None) == 'ses'), self.smtp_pool[0])

            today_str = datetime.now().strftime('%Y-%m-%d')
            available_smtps = []
            warmup_limited_smtps = 0
            for s in self.smtp_pool:
                # --- "Brilliant" Failover Logic ---
                # Exclude servers that have already been tried for this specific recipient.
                smtp_id = f"{s.host}:{s.port}:{s.email}"
                if smtp_id in exclude_ids:
                    continue
                # Use attribute access now
                if s.disabled_until or (s.limit and s.sent_count >= s.limit):
                    continue

                if self.warmup_enabled and s.total_sent < self.warmup_target_sends:
                    warmup_state = s.warmup
                    last_sent_day = warmup_state.get('last_day', '')
                    daily_sent = warmup_state.get('daily_sent', 0)

                    if last_sent_day != today_str:
                        daily_sent = 0 # Reset daily counter

                    # Calculate current daily limit for this SMTP
                    days_in_warmup = warmup_state.get('days_in_warmup', 0)
                    daily_limit = self.warmup_daily_start + (days_in_warmup * self.warmup_daily_increment)

                    if daily_sent < daily_limit:
                        available_smtps.append(s)
                    else:
                        warmup_limited_smtps += 1
                else:
                    # This SMTP is fully warmed up or warm-up is disabled
                    available_smtps.append(s)

            if not available_smtps:
                if warmup_limited_smtps > 0:
                    self.logger.warning(f"All {warmup_limited_smtps} active SMTPs have reached their daily warm-up limit ({self.warmup_daily_start} sends). Pausing for this recipient.")
                return None

            if settings.smtp.smtp_prioritize_healthy:
                # Calculate a score for each available SMTP
                scored_smtps = []
                for smtp in available_smtps:
                    sent = smtp.sent_count
                    failed = smtp.fail_count
                    limit = smtp.limit

                    # Base score: higher is better (more successes, fewer failures)
                    # Add 1 to denominator to avoid division by zero if both are 0
                    health_score = (sent - failed) / (sent + failed + 1)
                    
                    # Penalize if nearing limit
                    if limit > 0 and sent / limit >= settings.smtp.smtp_limit_penalty_threshold:
                        health_score *= 0.5 # Halve the score if nearing limit

                    # --- "Jesko" Engine: Domain Affinity Scoring ---
                    domain_stats = smtp.domain_stats.get(recipient_domain, {'success': 0, 'fail': 0})
                    domain_success = domain_stats.get('success', 0)
                    domain_fail = domain_stats.get('fail', 0)
                    # Add 1 to denominator to avoid division by zero
                    domain_affinity_score = domain_success / (domain_success + domain_fail + 1)

                    # --- "Jesko" Engine: Latency Scoring (Pressure Sensors) ---
                    # Lower latency is better. Score 0.0 to 1.0.
                    # Assume < 0.5s is perfect (1.0), > 5.0s is bad (0.0).
                    avg_lat = getattr(smtp, 'average_latency', 0.0)
                    if avg_lat <= 0: avg_lat = 1.0 # Default/Neutral if no data
                    latency_score = 1.0 / (1.0 + avg_lat) # Simple inverse decay

                    # --- "Jesko" Engine: AI Reputation Scoring ---
                    reputation_score = 0.0
                    now = time.time()
                    reputation_events = getattr(smtp, 'reputation_events', [])
                    if reputation_events:
                        total_weight = 0
                        weighted_score = 0
                        for event in reputation_events:
                            # Weight recent events more heavily (e.g., events in the last 24 hours)
                            age_seconds = now - event.get('timestamp', now)
                            weight = max(0, 1 - (age_seconds / (24 * 3600))) # Linear decay over 24 hours
                            
                            event_type = event.get('type')
                            score_modifier = 0
                            if event_type == 'HUMAN_POSITIVE': score_modifier = 1.0
                            elif event_type == 'SOFT_BOUNCE': score_modifier = -0.5
                            elif event_type == 'HUMAN_NEGATIVE_UNSUBSCRIBE': score_modifier = -1.0
                            
                            weighted_score += score_modifier * weight
                            total_weight += weight
                        if total_weight > 0:
                            reputation_score = weighted_score / total_weight

                    # Combine scores: Health (20%), Affinity (40%), Latency (15%), AI Reputation (25%)
                    final_score = (health_score * 0.2) + (domain_affinity_score * 0.4) + (latency_score * 0.15) + (reputation_score * 0.25)
                    self.logger.debug(f"Scoring {smtp.email} for {recipient_domain}: Health={health_score:.2f}, Affinity={domain_affinity_score:.2f}, Latency={avg_lat:.2f}, AI_Rep={reputation_score:.2f} -> Final={final_score:.2f}")

                    scored_smtps.append((final_score, smtp))
                
                # Sort by score (highest first)
                scored_smtps.sort(key=lambda x: x[0], reverse=True)

                # Select from the top N (e.g., top 3) with some randomness to avoid always picking the absolute best
                # This prevents over-reliance on a single "best" server
                top_n = min(3, len(scored_smtps))
                selected_smtp = random.choice([s[1] for s in scored_smtps[:top_n]])
                return selected_smtp

            # Fallback to original rotation modes if prioritization is off
            elif self.smtp_rotation_mode == 'sequential':
                smtp = available_smtps[self._current_smtp_index % len(available_smtps)]
                self._current_smtp_index = (self._current_smtp_index + 1) % len(available_smtps)
                return smtp
            else: # Default to random
                return random.choice(available_smtps)

    def _select_proxy_for_send(self):
        """Selects a proxy config from the pool respecting rotation mode."""
        with self.proxy_pool_lock:
            if not self.proxy_enabled or not self.proxy_pool:
                return None

            # --- "Smarter" Proxy Selection: Only use healthy proxies ---
            healthy_proxies = [p for p in self.proxy_pool if p.get('status') == 'ok']
            if not healthy_proxies:
                if self.proxy_enabled:
                    self.logger.error(f"{RED}CRITICAL: Proxy pool is EXHAUSTED (0/{len(self.proxy_pool)} online). Check your proxy client.{RESET}")
                return None
            
            if self.proxy_rotate_mode == 'sequential':
                # Round-robin selection
                proxy = healthy_proxies[self._current_proxy_index % len(healthy_proxies)]
                self._current_proxy_index = (self._current_proxy_index + 1)
                return proxy
            else: # Default to random
                return random.choice(healthy_proxies)

    def _write_send_report(self, row):
        """Append a row (list) to logs/send_report.csv with thread-safe write."""
        try:
            report_path = os.path.join(self.project_root, 'logs', 'send_report.csv')
            header_needed = not os.path.exists(report_path)
            import csv
            with open(report_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if header_needed:
                    writer.writerow(['timestamp','recipient','smtp_host','smtp_port','smtp_email','result','error', 'subject'])
                writer.writerow(row)
        except Exception as e:
            self.logger.warning(f"Failed to write send report: {e}")

    def _get_thread_local_ews_account(self):
        """Gets or creates a thread-safe EWS account object for the current worker thread."""
        if self.ews_token_is_dead:
            self.logger.debug("EWS token is marked as invalid. Halting account creation for this thread.")
            return None
        if not hasattr(self.thread_local, 'ews_account'):
            self.logger.info("Initializing new EWS account for this thread...")
            self.thread_local.ews_account = self._create_new_ews_account()
        return self.thread_local.ews_account

    def _send_via_ews(self, recipient_data, i):
        """Sends an email using Exchange Web Services (EWS)."""
        # --- "World-Class" Fast Fail: Check for global shutdown signal ---
        if self.shutdown_event.is_set():
            return False

        ews_account = self._get_thread_local_ews_account()
        if not ews_account:
            self.logger.error("EWS account could not be initialized for this thread. Cannot send.")
            return False
        
        try:
            # --- "World-Class" Fix: Create a dummy smtp_config for the message builder ---
            # This provides a consistent identity object for the builder, even when not using SMTP.
            from settings import SmtpConfigModel
            ews_dummy_config = SmtpConfigModel(
                host='outlook.office365.com',
                port=443,
                email=self.ews_username,
                password='', # Not needed for building
                security='ssl'
            )
            context = self.context_builder.build(recipient_data, recipient_index=i, smtp_config=ews_dummy_config)
            
            # --- "Jesko" Engine: Link Mutation (EWS) ---
            # 1. Rotate Base Link
            base_link = random.choice(self.link_pool)
            # 2. Add Unique ID to bypass hash-based spam filters
            unique_id = dynamic_content.generate_random_md5()[:10]
            separator = '&' if '?' in base_link else '?'
            context['link'] = f"{base_link}{separator}v={unique_id}"

            msg, envelope_from, sent_subject = self.message_builder.create(
                context=context, smtp_config=ews_dummy_config, recipient_index=i, sends_completed=self.sends_completed
            )
            
            # --- "World-Class" Fast Fail: Check shutdown again after expensive AI generation ---
            if self.shutdown_event.is_set():
                return False

            # exchangelib can't directly send a pre-built MIMEMultipart object that has been signed.
            # We must send it as a raw MIME content string.
            self.logger.info("Serializing MIME message...")
            mime_content = msg.as_string()
            self.logger.info("MIME serialization complete. Preparing EWS object...")

            # Create and send the message
            # --- "World-Class" Optimization: Skip folder resolution ---
            # Accessing ews_account.sent triggers a network call to find the folder ID which causes hangs.
            # Since we use save_copy=False, we don't need the folder.
            self.logger.info(f"Creating EWS message object for {recipient_data.email} (Skipping folder resolution)...")
            m = exchangelib.Message(
                account=ews_account,
                folder=None, # Skip "Sent Items" lookup to prevent network freeze
                subject=sent_subject,
                body=None, # Body is part of the mime_content
                to_recipients=[recipient_data.email],
                mime_content=mime_content.encode('utf-8')
            )
            self.logger.info(f"Attempting EWS send to {recipient_data.email} (Ghost Sending: No copy will be saved)...")
            m.send(save_copy=settings.ews.ews_save_sent_items) # Set save_copy=True to save in the Sent Items folder
            self.logger.info(f"EWS send successful to {recipient_data.email}")

            # --- "World-Class" Fix: Record success in the database and report for EWS sends ---
            with self.db_lock:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO sent_log (recipient_email) VALUES (?)", (recipient_data.email.lower(),))
                conn.commit()
                conn.close()
            
            timestamp = datetime.now().isoformat()
            self._write_send_report([timestamp, recipient_data.email, 'EWS', '443', self.ews_username, 'success', '', sent_subject])

            return True

        except exchangelib.errors.UnauthorizedError:
            self.logger.critical(f"EWS send failed: Invalid credentials for {self.ews_username}. Please check config or re-authenticate.")
            # This is a fatal error for EWS, so we should stop.
            self.shutdown_event.set()
            self._record_failure('EWSInvalidCredentials')
            return False
        except (exchangelib.errors.TransportError, socket.gaierror) as e:
            if "placeholder.invalid" in str(e):
                # --- "World-Class" Self-Healing ---
                # If cookies expired, instantly switch to Basic Auth and retry.
                if settings.ews.ews_cookies:
                    # Only log the switch once, but allow ALL threads to perform the switch logic
                    if not getattr(self, 'cookie_auth_failed', False):
                        self.logger.warning("EWS Cookies expired during send. Switching to Password/Basic Auth for Long Lasting Session...")
                        self.cookie_auth_failed = True

                    # Clear the broken account from this thread so it gets recreated with password
                    if hasattr(self.thread_local, 'ews_account'):
                        del self.thread_local.ews_account
                    return self._send_via_ews(recipient_data, i) # Recursively retry the send
                
                # If we get here, cookies weren't configured, so it's a real fatal error
                self.logger.critical(f"EWS Token Expired: The configured cookie/token is no longer valid (Auto-refresh blocked). Please update cookies or re-authenticate.")
                self.ews_token_is_dead = True
                self.shutdown_event.set()
                self._record_failure('EWSTokenExpired')
                return False
            self.logger.error(f"EWS send failed for {recipient_data.email}. A network or connection error occurred: {e}")
            self._record_failure('EWSTransportError')
            return False
        except Exception as e:
            # --- "World-Class" Error Handling: Catch OAuth2 refresh failures (AADSTS7000216) ---
            # This occurs when a cookie/token expires and the system tries to refresh it using client creds (which we don't have).
            # Also catch 'placeholder.invalid' which indicates a forced token refresh attempt (token expired).
            if "AADSTS7000216" in str(e) or "placeholder.invalid" in str(e):
                # --- "World-Class" Self-Healing ---
                if settings.ews.ews_cookies:
                    if not getattr(self, 'cookie_auth_failed', False):
                        self.logger.warning("EWS Cookies expired during send. Switching to Password/Basic Auth for Long Lasting Session...")
                        self.cookie_auth_failed = True
                    if hasattr(self.thread_local, 'ews_account'):
                        del self.thread_local.ews_account
                    return self._send_via_ews(recipient_data, i) # Recursively retry the send
                
                self.logger.critical(f"EWS Token Expired: The configured cookie/token is no longer valid. Please update cookies or re-authenticate.")
                self.ews_token_is_dead = True
                self.shutdown_event.set()
                self._record_failure('EWSTokenExpired')
                return False
            self.logger.error(f"EWS send failed for {recipient_data.email} with an unexpected error: {e}")
            self._record_failure(e.__class__.__name__)
            return False

    def _get_imap_host(self, smtp_host):
        """Infers the IMAP host from the SMTP host for Ghost Sending."""
        host = smtp_host.lower()
        if 'gmail.com' in host: return 'imap.gmail.com'
        if 'office365.com' in host or 'outlook.com' in host: return 'outlook.office365.com'
        if 'yahoo.com' in host: return 'imap.mail.yahoo.com'
        if 'zoho.com' in host: return 'imap.zoho.com'
        if 'aol.com' in host: return 'imap.aol.com'
        if 'icloud.com' in host or 'me.com' in host: return 'imap.mail.me.com'
        # Fallback: try replacing smtp with imap
        return host.replace('smtp.', 'imap.')

    def _delete_sent_message(self, smtp_config, message_id):
        """Connects via IMAP and deletes the sent message to achieve 'Ghost Sending'."""
        if not message_id:
            self.logger.debug("Ghost Sending skipped: No Message-ID provided.")
            return
        
        # --- "World-Class" Timing Fix: Wait for the server to save the message ---
        # Decreased initial wait, relying on the robust retry loop below.
        time.sleep(2.0)

        try:
            imap_host = self._get_imap_host(smtp_config.host)
            self.logger.info(f"Ghost Sending: Connecting to {imap_host} to remove trace...")
            
            mail = imaplib.IMAP4_SSL(imap_host)
            mail.login(smtp_config.email, smtp_config.password)
            
            # Try common Sent folder names
            sent_folders = ['"Sent Items"', '"Sent"', 'Sent', '"[Gmail]/Sent Mail"', '"Sent Messages"', 'INBOX.Sent']
            target_folder = None

            for folder in sent_folders:
                try:
                    status, _ = mail.select(folder, readonly=False) # Ensure we can modify flags
                    if status == 'OK':
                        target_folder = folder
                        self.logger.debug(f"Ghost Sending: Found 'Sent' folder: {folder}")
                        break
                except Exception:
                    continue
            
            if not target_folder:
                self.logger.warning(f"Ghost Sending failed: Could not find a 'Sent' folder on the server for {smtp_config.email}.")
                mail.logout()
                return

            # --- "World-Class" Retry Logic: Try up to 5 times to find the message ---
            message_found_and_deleted = False
            for attempt in range(1, 6): # Start from 1 for logging
                found_ids = []
                try:
                    # Strategy 1: Standard Server Search
                    search_id = message_id if message_id.startswith('<') else f'<{message_id}>'
                    typ, data = mail.search(None, f'(HEADER Message-ID "{search_id}")')
                    if data and data[0]:
                        found_ids = data[0].split()
                    
                    # Strategy 2: Manual Fallback (Bypass Indexing Lag)
                    if not found_ids:
                        typ, all_data = mail.search(None, 'ALL')
                        if all_data and all_data[0]:
                            recent_ids = all_data[0].split()[-5:] # Last 5 IDs
                            if not recent_ids: continue
                            id_set = b','.join(recent_ids)
                            typ, header_data = mail.fetch(id_set, '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])')
                            for response_part in header_data:
                                if isinstance(response_part, tuple) and len(response_part) > 1 and response_part[1]:
                                    if message_id.encode() in response_part[1]:
                                        found_ids.append(response_part[0].split()[0])

                    if found_ids:
                        self.logger.debug(f"Ghost Sending: Found message UID(s) {found_ids} to delete.")
                        for num in found_ids:
                            mail.store(num, '+FLAGS', '\\Deleted')
                        mail.expunge()
                        self.logger.info(f"Ghost Sending: Successfully removed trace from {target_folder}.")
                        message_found_and_deleted = True
                        break
                except Exception as e:
                    self.logger.debug(f"Ghost Sending search attempt {attempt}/5 failed: {e}")
                
                if not message_found_and_deleted:
                    self.logger.debug(f"Ghost Sending: Message not found on attempt {attempt}/5. Waiting...")
                    time.sleep(3) # Wait before retry
            
            if not message_found_and_deleted:
                self.logger.warning(f"Ghost Sending failed: Message with ID {message_id} not found in {target_folder} after {attempt} attempts.")

            mail.logout()
        except imaplib.IMAP4.error as e:
            error_str = str(e)
            if 'AuthFailed:LogonDenied-BasicAuthBlocked' in error_str:
                if smtp_config.email not in self._logged_imap_blocks:
                    self.logger.critical(f"{RED}Ghost Sending Failed: Microsoft 365 Basic Auth Blocked for {smtp_config.email}.{RESET}")
                    self.logger.critical(f"{RED}Action: To enable Ghost Sending for Office 365 accounts, you must:{RESET}")
                    self.logger.critical(f"{RED}1. Create and use an 'App Password' if Multi-Factor Authentication (MFA) is enabled on the account.{RESET}")
                    self.logger.critical(f"{RED}2. Ensure 'IMAP' protocol is enabled for this user in the Microsoft 365 Admin Center.{RESET}")
                    self.logger.critical(f"{RED}3. If you are using a custom domain, ensure 'Authenticated SMTP' is enabled for the user.{RESET}")
                    self.logger.critical(f"{RED}Alternatively, disable 'Ghost Sending' in the menu (Configuration & Setup -> Toggle Ghost Sending).{RESET}")
                    self._logged_imap_blocks.add(smtp_config.email)
                else:
                    self.logger.warning(f"Ghost Sending: IMAP access still blocked for {smtp_config.email}. Skipping cleanup for this recipient.")
            elif 'AUTHENTICATIONFAILED' in error_str:
                self.logger.warning(f"Ghost Sending failed: IMAP authentication failed for {smtp_config.email}. Please check the password in your .env file.")
            else:
                self.logger.warning(f"Ghost Sending failed (IMAP error for {smtp_config.email}): {e}")
        except socket.timeout:
            self.logger.warning(f"Ghost Sending failed: IMAP connection to {imap_host} timed out for {smtp_config.email}.")
        except Exception as e:
            self.logger.warning(f"Ghost Sending failed (could not delete from Sent): {e}")

    def _send_via_smtp(self, recipient_data, i):
        """Full SMTP send implementation: selects SMTP, builds message, sends, records results."""
        if self.shutdown_event.is_set():
            return False
        
        # --- Deliverability: Hourly cap + time window enforcement ---
        now = time.time()
        current_hour = datetime.now().hour
        # Reset counter on new hour
        if now - self._last_hourly_reset >= 3600:
            self._hourly_send_count = 0
            self._last_hourly_reset = now
        cap = getattr(settings.deliverability, 'per_hour_cap', 0)
        if cap > 0 and self._hourly_send_count >= cap:
            self.logger.warning(f"Per-hour cap reached ({cap}). Pausing sends.")
            time.sleep(60)
            return False
        window_start = getattr(settings.deliverability, 'send_time_window_start', 0)
        window_end = getattr(settings.deliverability, 'send_time_window_end', 23)
        if not (window_start <= current_hour <= window_end):
            self.logger.warning(f"Outside send window ({window_start}:00-{window_end}:00). Skipping {recipient_data.email}.")
            return False
            
        send_start_time = time.time() # Start timer for the entire send process
        recipient_domain = recipient_data.email.split('@')[-1].lower()

        latency = 0.0 # Initialize to prevent reference errors
        def update_warmup_state(smtp_config):
            if not self.warmup_enabled: return
            today_str = datetime.now().strftime('%Y-%m-%d')
            if isinstance(smtp_config.warmup, dict):
                warmup_state = smtp_config.warmup
            else:
                warmup_state = {}
            last_day = warmup_state.get('last_day', '')
            if last_day != today_str:
                warmup_state['days_in_warmup'] = warmup_state.get('days_in_warmup', 0) + 1
                warmup_state['daily_sent'] = 1
                warmup_state['last_day'] = today_str
            else:
                warmup_state['daily_sent'] = warmup_state.get('daily_sent', 0) + 1
            smtp_config.warmup = warmup_state

        # --- "Brilliant" SMTP Failover Strategy ---
        max_server_attempts = 3
        used_smtp_ids = set()
        last_error = "No available SMTP servers."
        domain_throttles = settings.domain_throttle.throttles

        for server_attempt in range(max_server_attempts):
            if self.shutdown_event.is_set(): return False

            domain_multiplier = domain_throttles.get(recipient_domain, domain_throttles.get('default', 1.0))
            with self.throttle_lock:
                base_delay = self.dynamic_sleep_time
            
            # --- "World-Class" Time-Aware Adaptive Jitter ---
            # Avoid sending during deep-night hours where bulk batches are suspicious.
            # Also use a log-normal distribution for more natural, organic feeling delays.
            current_hour = datetime.now().hour
            night_penalty = 1.0
            if 0 <= current_hour <= 6:
                night_penalty = random.uniform(2.0, 4.0)
            elif 22 <= current_hour <= 23:
                night_penalty = random.uniform(1.5, 2.5)
            elif 7 <= current_hour <= 8:
                night_penalty = random.uniform(0.8, 1.2)  # Morning ramp-up
            elif 17 <= current_hour <= 19:
                night_penalty = random.uniform(0.8, 1.2)  # Evening ramp-down
            
            # Log-normal jitter is more organic than uniform (human send patterns have long-tail delays)
            mu = 0.0
            sigma = 0.4
            jitter_factor = random.lognormvariate(mu, sigma)
            
            final_delay = (base_delay * domain_multiplier * night_penalty) * jitter_factor
            final_delay = max(0.5, final_delay)  # Floor to prevent negative/zero delays
            self.logger.debug(f"Throttling for {recipient_domain}: base={base_delay:.2f}s, multiplier={domain_multiplier}, night={night_penalty:.1f}x, jitter={jitter_factor:.2f}x, final={final_delay:.2f}s")
            time.sleep(final_delay)

            smtp_config = self._select_smtp_for_send(recipient_domain, exclude_ids=used_smtp_ids)
            if not smtp_config:
                self.logger.warning(f"No new SMTP servers available for recipient {recipient_data.email}. Send failed.")
                if self.warmup_enabled:
                    last_error = "No available SMTP servers (Daily warm-up limit reached)."
                break
            used_smtp_ids.add(f"{smtp_config.host}:{smtp_config.port}:{smtp_config.email}")

            attempts = 0
            max_attempts = self.retry_attempts
            retry_delay = self.retry_delay_seconds
            while attempts < max_attempts and not self.shutdown_event.is_set():
                attempts += 1
                proxy_config = None
                is_proxy_failure = False # Track if this failure is the proxy's fault
                last_exception_type = "UnknownConnectionError" # Default for this attempt
                try:
                    context = self.context_builder.build(recipient_data, recipient_index=i, smtp_config=smtp_config)
                    
                    # --- "Jesko" Engine: Link Mutation (SMTP) ---
                    # 1. Rotate Base Link: Selects a random repository from the pool.
                    base_link = random.choice(self.link_pool)
                    # 2. Add Unique ID to bypass hash-based spam filters
                    unique_id = dynamic_content.generate_random_md5()[:10]
                    separator = '&' if '?' in base_link else '?'
                    context['link'] = f"{base_link}{separator}v={unique_id}"

                    build_start_time = time.time()
                    msg, envelope_from, sent_subject = self.message_builder.create(
                        context=context, smtp_config=smtp_config, recipient_index=i, sends_completed=self.sends_completed)
                    build_duration = time.time() - build_start_time
                    self.logger.debug(f"Message built in {build_duration:.2f}s (AI features can increase this time)")

                    # --- "World-Class" Fast Fail: Check shutdown again after expensive AI generation ---
                    if self.shutdown_event.is_set():
                        return False

                    if self.simulation_mode:
                        self.logger.info(f"SIMULATED SEND to {recipient_data.email} via {smtp_config.host}")
                        timestamp = datetime.now().isoformat()
                        self._write_send_report([timestamp, recipient_data.email, smtp_config.host, smtp_config.port, smtp_config.email, 'simulated', 'DEV_MODE', sent_subject])
                        return True

                    transport = smtp_config.transport
                    sent_ok = False
                    is_ses_transport = transport == 'ses'
                    if is_ses_transport:
                        aws_ses_cfg = types.SimpleNamespace(
                            transport='ses',
                            host=getattr(smtp_config, 'aws_region', None) or getattr(settings.aws, 'aws_region', 'eu-north-1'),
                            port=getattr(smtp_config, 'port', 587),
                            email=getattr(smtp_config, 'email', envelope_from),
                            password='',
                            security=getattr(smtp_config, 'security', 'auto'),
                            limit=getattr(smtp_config, 'limit', 0),
                            aws_region=getattr(smtp_config, 'aws_region', None) or getattr(settings.aws, 'aws_region', 'eu-north-1'),
                            aws_access_key_id=getattr(settings.aws, 'aws_access_key_id', None),
                            aws_secret_access_key=getattr(settings.aws, 'aws_secret_access_key', None),
                        )
                        sent_ok = transports.send_via_ses(aws_ses_cfg, msg, envelope_from, recipient_data.email, logger=self.logger)
                        if not sent_ok:
                            raise Exception('SES transport failed to send')
                    elif transport == 'office365':
                        sent_ok = transports.send_via_office365(smtp_config, msg, envelope_from, recipient_data.email, logger=self.logger)
                    else:
                        host = smtp_config.host
                        proxy_config = self._select_proxy_for_send()
                        if proxy_config is None and self.proxy_enabled:
                            raise ConnectionRefusedError("Proxy is enabled, but no working proxy is available in the pool.")

                        if proxy_config:
                            self.logger.info(f"Using proxy {proxy_config['host']}:{proxy_config['port']} for SMTP connection.")

                        port = smtp_config.port
                        security = smtp_config.security
                        server = None
                        helo_domain = settings.smtp.smtp_helo_name

                        try:
                            if str(security).lower() == 'ssl' or port == 465:
                                server = ProxySMTP_SSL(host, port, timeout=self.smtp_timeout, local_hostname=helo_domain, proxy_settings=proxy_config)
                            else:
                                server = ProxySMTP(host, port, timeout=self.smtp_timeout, local_hostname=helo_domain, proxy_settings=proxy_config)
                                if str(security).lower() == 'starttls' or port not in (465, 25):
                                    server.starttls()

                            login_email = smtp_config.email.split('#', 1)[0]
                            server.login(login_email, smtp_config.password)

                            start_time = time.time()
                            server.sendmail(envelope_from, [recipient_data.email], msg.as_string())
                            latency = time.time() - start_time
                            sent_ok = True
                        finally:
                            if server:
                                try:
                                    server.quit()
                                except Exception:
                                    pass

                    if not sent_ok:
                        raise Exception(f"SMTP send failed for {recipient_data.email}")
                    
                    with self.db_lock:
                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()
                        cursor.execute("INSERT OR IGNORE INTO sent_log (recipient_email) VALUES (?)", (recipient_data.email.lower(),))
                        smtp_id = f"{smtp_config.host}:{smtp_config.port}:{smtp_config.email}"
                        cursor.execute("INSERT INTO smtp_state (smtp_id, sent_count) VALUES (?, 1) ON CONFLICT(smtp_id) DO UPDATE SET sent_count = sent_count + 1", (smtp_id,))
                        
                        # --- "Jesko" Engine: Update domain-specific stats on success ---
                        stats = smtp_config.domain_stats
                        domain_stats = stats.get(recipient_domain, {'success': 0, 'fail': 0})
                        domain_stats['success'] += 1
                        stats[recipient_domain] = domain_stats
                        smtp_config.total_sent += 1
                        
                        # Update moving average latency (weight new value by 10%)
                        current_avg = getattr(smtp_config, 'average_latency', 0.0)
                        new_avg = (current_avg * 0.9) + (latency * 0.1) if current_avg > 0 else latency
                        smtp_config.average_latency = new_avg
                        
                        cursor.execute("UPDATE smtp_state SET domain_stats = ?, total_sent = ?, average_latency = ? WHERE smtp_id = ?", (json.dumps(stats), smtp_config.total_sent, new_avg, smtp_id))
                        conn.commit()
                        conn.close()

                    update_warmup_state(smtp_config)
                    timestamp = datetime.now().isoformat()
                    with self.throttle_lock:
                        new_sleep_time = self.dynamic_sleep_time * 0.95
                        self.dynamic_sleep_time = max(self.sleep_time, new_sleep_time)
                        self.logger.debug(f"Throttling down. New sleep base: {self.dynamic_sleep_time:.2f}s")
                    total_send_time = time.time() - send_start_time
                    self.logger.info(f">>> SUCCESS: Sent to {recipient_data.email} via {smtp_config.host} (took {total_send_time:.2f}s)")
                    self._write_send_report([timestamp, recipient_data.email, smtp_config.host, smtp_config.port, smtp_config.email, 'success', '', sent_subject])
                    
                    # --- "Ghost Sending" Logic ---
                    if self.smtp_delete_sent:
                        self._delete_sent_message(smtp_config, msg['Message-ID'])

                    return True

                except smtplib.SMTPAuthenticationError as e:
                    last_error = f"Authentication failed for {smtp_config.email}. Check password. Server response: {e.smtp_error}"
                    last_exception_type = e.__class__.__name__
                    self.logger.error(last_error)
                    self._record_and_disable_smtp(smtp_config, recipient_domain, 'SMTPAuthenticationError', last_error)
                    break
                except smtplib.SMTPRecipientsRefused as e:
                    last_error = f"Recipient {recipient_data.email} was refused by the server. This is often a permanent failure. Details: {e.recipients}"
                    last_exception_type = e.__class__.__name__
                    self.logger.warning(last_error)
                    self._record_failure('SMTPRecipientsRefused')
                    self._add_to_suppression_list(recipient_data.email)
                    self._write_send_report([datetime.now().isoformat(), recipient_data.email, smtp_config.host, smtp_config.port, smtp_config.email, 'failure', last_error, 'N/A'])
                    return False
                except smtplib.SMTPDataError as e:
                    last_error = f"SMTP Data Error: {e.smtp_code} {e.smtp_error}"
                    last_exception_type = e.__class__.__name__
                    self.logger.warning(f"Attempt {attempts}/{max_attempts} failed. {last_error}")

                    # --- "World-Class" Elastic Email Trial Account Detection ---
                    error_str = str(e.smtp_error).lower()
                    if 'elastic email' in error_str and 'for testing purposes' in error_str:
                        self.logger.critical(f"{RED}--- ELASTIC EMAIL TRIAL ACCOUNT DETECTED ---{RESET}")
                        self.logger.critical(f"Your Elastic Email account is in trial mode and can only send to your registration email.")
                        self.logger.critical(f"To send to other recipients, you must upgrade to a paid plan on the Elastic Email website.")
                        # Since all sends will fail, we can stop the campaign to save resources.
                        self.shutdown_event.set()

                    if e.smtp_code == 550 and b'From address is not one of your addresses' in e.smtp_error:
                        self.logger.warning(f"Server {smtp_config.host} rejected 'From' address. Failing over to next server.")
                        break
                except (socket.timeout, ConnectionRefusedError, smtplib.SMTPConnectError, OSError, smtplib.SMTPServerDisconnected, TypeError) as e:
                    last_exception_type = e.__class__.__name__
                    is_rate_limit = hasattr(e, 'smtp_code') and e.smtp_code and isinstance(e, smtplib.SMTPException) and any(code in str(e.smtp_code) for code in ['421', '451'])
                    if is_rate_limit:
                        with self.throttle_lock:
                            new_sleep_time = self.dynamic_sleep_time * 1.5
                            self.dynamic_sleep_time = min(10.0, new_sleep_time)
                            self.logger.warning(f"Rate limit detected. Throttling up. New sleep base: {self.dynamic_sleep_time:.2f}s")
                        last_error = f"Temporary rate-limit or connection issue for {smtp_config.host}:{smtp_config.port}. Error: {e}"
                    elif isinstance(e, TypeError):
                        is_proxy_failure = True
                        # "World-Class" Proxy Diagnosis: Catch PySocks/SSL TypeError
                        last_error = f"Proxy Handshake Error (TypeError). The proxy likely closed the connection unexpectedly during SSL handshake. Error: {e}"
                    else:
                        # --- "World-Class" Fix: Check error message for proxy-related failures ---
                        error_str = str(e).lower()
                        if proxy_config or "proxy" in error_str:
                            is_proxy_failure = True
                        last_error = f"Connection failed for {smtp_config.host}:{smtp_config.port}. Error: {e}"
                    self.logger.warning(f"Attempt {attempts}/{max_attempts} failed. {last_error}")
                    if proxy_config:
                        with self.proxy_pool_lock:
                            for p in self.proxy_pool:
                                if p['host'] == proxy_config['host'] and p['port'] == proxy_config['port'] and p.get('status') == 'ok':
                                    p['status'] = 'bad'
                                    self.logger.warning(f"Proxy {p['host']}:{p['port']} failed. Marking as bad for this session.")
                                    break
                except Exception as e:
                    last_error = f"An unexpected error occurred: {e.__class__.__name__}: {e}"
                    last_exception_type = e.__class__.__name__
                    self.logger.warning(f"Attempt {attempts}/{max_attempts} failed for {recipient_data.email} via {smtp_config.host}:{smtp_config.port}. {last_error}")

                if attempts < max_attempts:
                    time.sleep(retry_delay)
                else:
                    self._record_and_disable_smtp(smtp_config, recipient_domain, last_exception_type, last_error, is_proxy_error=is_proxy_failure)

        # If we exit the server_attempt loop without success
        total_fail_time = time.time() - send_start_time
        if "warm-up limit" in last_error:
            self.logger.warning(f">>> PAUSED: Could not send to {recipient_data.email} (Daily warm-up limit reached).")
        else:
            self.logger.error(f">>> FAILURE: Could not send to {recipient_data.email} after trying {max_server_attempts} servers (took {total_fail_time:.2f}s). Final error: {last_error}")
        self._write_send_report([datetime.now().isoformat(), recipient_data.email, 'N/A', 'N/A', 'N/A', 'failure', last_error, 'N/A'])
        return False

    def _record_failure(self, reason):
        """Records a failure and the reason for it."""
        self.failure_reasons[reason] = self.failure_reasons.get(reason, 0) + 1

    def _add_to_suppression_list(self, email):
        """Adds an email to the suppression list in a thread-safe manner."""
        if not email: return
        with self.suppression_lock:
            try:
                suppression_list_path = os.path.join(self.project_root, 'logs', 'suppression_list.txt')
                with open(suppression_list_path, 'a', encoding='utf-8') as f:
                    f.write(f"{email.strip().lower()}\n")
                self.logger.info(f"Added {email} to the suppression list.")
            except Exception as e:
                self.logger.warning(f"Could not write to suppression list: {e}")

    def _record_and_disable_smtp(self, smtp_config, recipient_domain, reason, error_message, is_proxy_error=False):
        """Records a failure and updates the SMTP state, potentially disabling it."""
        self._record_failure(reason)
        if is_proxy_error:
            self.logger.info(f"Failure for {smtp_config.host} was due to proxy. Not penalizing SMTP server.")
            return
        try:
            with self.db_lock:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                smtp_id = f"{smtp_config.host}:{smtp_config.port}:{smtp_config.email}"

                # Increment fail_count
                cursor.execute("""
                    INSERT INTO smtp_state (smtp_id, fail_count) VALUES (?, 1)
                    ON CONFLICT(smtp_id) DO UPDATE SET fail_count = fail_count + 1, total_sent = total_sent + 1
                """, (smtp_id,))
                smtp_config.fail_count += 1
                smtp_config.total_sent += 1

                # --- "Jesko" Engine: Update domain-specific stats on failure ---
                stats = smtp_config.domain_stats
                domain_stats = stats.get(recipient_domain, {'success': 0, 'fail': 0})
                domain_stats['fail'] += 1
                stats[recipient_domain] = domain_stats
                cursor.execute("UPDATE smtp_state SET domain_stats = ? WHERE smtp_id = ?", (json.dumps(stats), smtp_id))

                # Check if it should be disabled
                if smtp_config.fail_count >= self.failure_threshold:
                    cooldown_seconds = int(self.cooldown_minutes) * 60
                    disabled_until_ts = time.time() + cooldown_seconds
                    smtp_config.disabled_until = disabled_until_ts
                    cursor.execute("""
                        UPDATE smtp_state SET disabled_until = ?, fail_count = 0 WHERE smtp_id = ? 
                    """, (disabled_until_ts, smtp_id))
                    self.logger.info(f"SMTP {smtp_config.host} disabled for {self.cooldown_minutes} minutes due to repeated failures.")
                conn.commit()
                conn.close()
        except Exception as e:
            self.logger.warning(f"Failed to update SMTP state in database: {e}")

    def reset_smtp_state(self):
        """Clears all SMTP state from the database."""
        try:
            with self.db_lock:
                conn = sqlite3.connect(DB_PATH)
                conn.execute("DELETE FROM smtp_state")
                conn.commit()
                conn.close()
            self.logger.info("SMTP state has been reset in the database.")
        except Exception as e:
            self.logger.warning(f"Failed to reset smtp state: {e}")

    def _create_new_ews_account(self):
        """Creates a new EWS account object. This is called once per thread."""
        if self.sending_method != 'ews':
            return None
 
        # --- "World-Class" Auth Strategy ---
        # Determine which auth method to use based on config.
 
        # Helper to find password case-insensitively
        def get_password_smart(target_email):
            pw = settings.dev.smtp_passwords.get(target_email)
            if pw: return pw
            for k, v in settings.dev.smtp_passwords.items():
                if k.lower() == target_email.lower():
                    return v
            return None

        has_cookies = bool(settings.ews.ews_cookies)
        has_password = bool(get_password_smart(self.ews_username))
        use_oauth = settings.ews.ews_use_oauth
        cookie_failed = getattr(self, 'cookie_auth_failed', False)

        # --- Method 0: Hybrid Authentication (Password + Cookies) ---
        # User Requested: "Work together side by side" to bypass MFA while keeping session alive.
        # This initializes with Password but injects Cookies to satisfy the authenticator check.
        if has_cookies and has_password and not use_oauth and not cookie_failed:
            self.logger.info("Attempting EWS Hybrid Authentication (Password + Cookies)...")
            try:
                ews_password = get_password_smart(self.ews_username)
                
                # --- "World-Class" Connection Optimization ---
                # 1. Force BASIC auth to prevent NTLM/Negotiate hangs on GoDaddy servers.
                # 2. Set a strict retry policy to fail fast instead of hanging for 9 minutes.
                from exchangelib.protocol import FaultTolerance
                creds = exchangelib.Credentials(username=self.ews_username, password=ews_password)
                config = exchangelib.Configuration(
                    server='outlook.office365.com', 
                    credentials=creds,
                    auth_type=exchangelib.BASIC, # Prevents auth handshake freezes
                    retry_policy=FaultTolerance(max_wait=15) # Don't wait forever
                )
                
                # --- "World-Class" Stealth: Match Browser User-Agent ---
                # Set this BEFORE creating the Account object so it applies to autodiscover/initial requests.
                config.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

                account = exchangelib.Account(primary_smtp_address=self.ews_username, config=config, autodiscover=False, access_type=exchangelib.DELEGATE)
                
                # Inject Cookies into Session
                import json
                try:
                    cookies_list = json.loads(settings.ews.ews_cookies)

                    # Force protocol instantiation to access the session
                    if not account.protocol:
                        from exchangelib.protocol import Protocol
                        account.protocol = Protocol(config=config)
                    
                    # Inject cookies into the active session adapter
                    # "Smarter" Fix: Use get_session() which ensures the thread-local session exists
                    if hasattr(account.protocol, 'get_session'):
                        session = account.protocol.get_session()
                    
                    if session:
                        # --- "World-Class" Stability: Disable Keep-Alive ---
                        # Microsoft servers can hang on keep-alive connections from scripts.
                        session.headers.update({'Connection': 'close'})
                        
                        for c in cookies_list:
                            session.cookies.set(c['name'], c['value'], domain=c.get('domain'))
                        self.logger.info(f"SUCCESS: EWS Hybrid account initialized (Basic Auth + Cookies + User-Agent).")
                        return account
                except Exception as inj_e:
                    self.logger.warning(f"Hybrid cookie injection warning: {inj_e}. Proceeding with standard fallback.")
            except Exception as e:
                self.logger.warning(f"Hybrid authentication failed: {e}. Will try other methods.")

        # 1. Cookie Authentication (Highest Priority for GoDaddy/Federated accounts)
        # This is used if cookies are present AND OAuth is disabled.
        # We check 'cookie_auth_failed' to skip this if we know it's bad.
        if settings.ews.ews_cookies and not settings.ews.ews_use_oauth and not getattr(self, 'cookie_auth_failed', False):
            try:
                from function.ews_oauth_transport import get_account_from_cookies
                account = get_account_from_cookies(settings, self.logger)
                if account:
                    self.logger.info(f"EWS account initialized using Browser Cookies for {self.ews_username}.")
                    return account
                else:
                    # If cookies fail during init, mark them as bad and let it fall through to Basic Auth
                    self.logger.warning("EWS Cookie initialization failed. Automatically switching to Password/Basic Auth...")
                    self.cookie_auth_failed = True
                    # Do NOT return None; let it proceed to Method 3 (Basic Auth) below
            except Exception as e:
                self.logger.error(f"Failed to initialize EWS from cookies: {e}")
                self.cookie_auth_failed = True
                # Fall through to next method
 
        # 2. OAuth2 (Interactive / Cached Token)
        if settings.ews.ews_use_oauth:
            try:
                from function.ews_oauth_transport import get_oauth_account
                account = get_oauth_account(settings, self.logger)
                if account:
                    self.logger.info(f"EWS OAuth account for {account.primary_smtp_address} successfully initialized.")
                    return account
                else:
                    self.logger.critical("FATAL: Failed to initialize EWS account using OAuth.")
                    self.shutdown_event.set()
                    return None
            except ImportError:
                self.logger.critical("FATAL: 'msal' library is required for EWS OAuth. Please run 'pip install msal'.")
                self.shutdown_event.set()
                return None
        
        # 3. Basic Authentication (Legacy Fallback)
        try:
            ews_password = get_password_smart(self.ews_username)
            if not ews_password:
                self.logger.critical("FATAL: EWS Basic Auth selected, but no password found in .env file.")
                self.shutdown_event.set()
                return None
 
            try:
                creds = exchangelib.Credentials(username=self.ews_username, password=ews_password)
                config = exchangelib.Configuration(server='outlook.office365.com', credentials=creds)
                account = exchangelib.Account(primary_smtp_address=self.ews_username, config=config, autodiscover=False, access_type=exchangelib.DELEGATE)
                self.logger.info(f"EWS account for {self.ews_username} successfully initialized with Basic Auth.")
                return account
            except Exception as e:
                self.logger.critical(f"FATAL: Failed to initialize EWS account with Basic Auth. Error: {e}")
                self.shutdown_event.set()
                return None
        except Exception: # Catch if get() fails for some reason
            return None

    def _send_via_mx(self, recipient_data, i):
        # ... (existing logic)
        # In the except blocks:
        # self._record_failure(e.__class__.__name__)
        pass

    def content(self):
        """The main sending loop that manages the thread pool and processes recipients."""
        if not self.recipients:
            self.logger.warning("Recipient list is empty. Nothing to send.")
            return
            
        self.logger.info(f"Starting sending campaign with {self.max_workers} workers.")

        # --- New: Pre-flight AI Check ---
        if settings.ai.ai_enabled:
            self.logger.info("Performing pre-flight AI health check...")
            
            # --- "World-Class" Robustness: Retry logic for AI check ---
            is_healthy = False
            err_msg = ""
            for attempt in range(1, 4):
                is_healthy, err_msg = self.message_builder.health_check()
                if is_healthy:
                    self.logger.info("AI Health Check PASSED.")
                    break
                self.logger.warning(f"AI Health Check attempt {attempt}/3 failed: {err_msg}")
                if attempt < 3:
                    time.sleep(2)

            if not is_healthy:
                self.logger.error(f"AI Health Check Failed after 3 attempts: {err_msg}")
                # --- "World-Class" User Guidance ---
                # Provide specific, actionable advice based on the error message.
                if any(code in str(err_msg) for code in ['401', '403', 'Access denied', 'authentication']):
                    self.logger.error("This is likely an authentication error. Please verify your Groq API key is correct and active.")
                    self.logger.error("Use 'Diagnostics & Tools' -> 'Test Groq AI Connection' from the menu to confirm.")
                
                # --- "World-Class" User Choice ---
                # Allow the user to override the safety shutdown if they believe it's a false positive.
                print(f"\n{RED}!!! AI HEALTH CHECK FAILED !!!{RESET}")
                print(f"{YELLOW}The AI engine is not responding correctly. Proceeding with AI enabled may cause all emails to fail.{RESET}")
                user_choice = input(f"{YELLOW}Do you want to DISABLE AI for this campaign? (Y/n) [default: Y]: {RESET}").strip().lower()
                
                if user_choice not in ['n', 'no']:
                    self.logger.warning("Disabling AI features for this campaign to prevent errors.")
                    settings.ai.ai_enabled = False
                    self.message_builder.settings.ai.ai_enabled = False
                else:
                    self.logger.warning("User forced AI to remain ENABLED. Proceeding with caution...")

        # --- New: Warm-up Worker Adjustment ---
        if self.warmup_enabled and self.sends_completed < self.warmup_sends:
            # Start with fewer workers during warm-up
            # "Jesko" Fix: Use the configured value, not a hardcoded one.
            current_max_workers = self.warmup_initial_workers
            self.logger.info(f"WARM-UP ACTIVE: Starting with {current_max_workers} workers.")
        else:
            current_max_workers = self.max_workers

        # --- End of Warm-up Logic ---

        # Try to import tqdm for a progress bar, but don't let it stop the sending process.
        try:
            from tqdm import tqdm
            use_tqdm = True
        except ImportError:
            self.logger.error("tqdm is not installed. Progress bar disabled. Please run 'pip install tqdm'.")
            use_tqdm = False
        # Diagnostic: disable tqdm progress bar to avoid console-related freezes
        # (Some Windows terminals can prevent the bar from updating while threads log.)
        use_tqdm = False

        from concurrent.futures import as_completed, wait, FIRST_COMPLETED

        # Conservative defaults to avoid many concurrent EWS cookie-based connections
        if self.sending_method == 'ews' and settings.ews.ews_cookies:
            current_max_workers = min(current_max_workers, 4)

        # Per-send timeout (seconds). Prevents hung worker threads from freezing the whole run.
        per_send_timeout = getattr(settings.ews, 'ews_send_timeout', 60)

        # If using EWS with cookies, run sequentially to avoid thread-based hangs and
        # to make each send easier to monitor and debug. For SMTP we keep the pool.
        if self.sending_method == 'ews':
            for i, recipient in enumerate(self.recipients):
                if self.shutdown_event.is_set():
                    break

                try:
                    send_successful = self._send_via_ews(recipient, i)
                except Exception as e:
                    self.logger.warning(f"Send task for {getattr(recipient,'email',recipient)} raised: {e}")
                    send_successful = False

                if send_successful:
                    self.sends_completed += 1
                    with self.deliverability_lock:
                        self._hourly_send_count += 1
                else:
                    self.failures += 1

                # Update recent outcomes for adaptive pacing (even though sequential)
                self.recent_outcomes.append(send_successful)

                # Small delay between sends to respect throttling
                with self.throttle_lock:
                    time.sleep(self.dynamic_sleep_time)
        else:
            with ThreadPoolExecutor(max_workers=current_max_workers) as executor:
                send_function = self._send_via_smtp
                futures = {executor.submit(send_function, recipient, i): (recipient, time.time()) for i, recipient in enumerate(self.recipients)}
                # Existing threaded SMTP logic (keeps previous behavior)
                pending = set(futures.keys())
                try:
                    while pending and not self.shutdown_event.is_set():
                        done, not_done = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
                        for fut in list(done):
                            pending.discard(fut)
                            recipient, _ = futures.get(fut, (None, None))
                            try:
                                send_successful = fut.result()
                            except Exception as e:
                                send_successful = False
                                self.logger.warning(f"Send task for {getattr(recipient,'email',recipient)} raised: {e}")

                            if send_successful:
                                self.sends_completed += 1
                                with self.deliverability_lock:
                                    self._hourly_send_count += 1
                            else:
                                self.failures += 1

                        time.sleep(0.01)
                finally:
                    try:
                        executor.shutdown(wait=False)
                    except Exception:
                        pass

        self.logger.info("\nFinished sending all messages.")

    def _performance_monitor(self):
        """A background thread to calculate and report real-time performance stats."""
        import json
        perf_file = os.path.join(self.project_root, 'logs', 'performance.json')

        while not self.shutdown_event.is_set():
            with self.performance_lock:
                now = time.time()
                # Remove timestamps older than 60 seconds
                while self.send_timestamps and self.send_timestamps[0] < now - 60:
                    self.send_timestamps.popleft()

                sends_per_minute = len(self.send_timestamps)

            stats = {
                'sends_per_minute': sends_per_minute,
                'dynamic_sleep_time': round(self.dynamic_sleep_time, 2),
                'active_workers': self.max_workers,
                'sends_completed': self.sends_completed,
                'failures': self.failures,
            }

            try:
                os.makedirs(os.path.dirname(perf_file), exist_ok=True)
                with open(perf_file, 'w', encoding='utf-8') as f:
                    json.dump(stats, f)
            except Exception as e:
                self.logger.debug(f"Performance monitor: failed to write stats: {e}")

            time.sleep(2)  # Update stats every 2 seconds

    def _sentinel_engine(self):
        """
        The "Sentinel Mark X" Engine.
        Combines Health Monitoring (Recovery) with Active Defense (Adaptability).
        Replaces the old _smtp_health_monitor.
        """
        monitor_enabled = settings.health_monitor.monitor_enabled
        monitor_interval_minutes = settings.health_monitor.monitor_interval_minutes
        sentinel_enabled = settings.sentinel.sentinel_enabled
        
        if not monitor_enabled and not sentinel_enabled:
            return
            
        self.logger.info("Sentinel Mark X Engine started. Monitoring threats and health.")

        last_recovery_check = time.time()

        while not self.shutdown_event.is_set():
            # --- 1. Sentinel Active Defense (Frequent) ---
            if sentinel_enabled:
                # Analyze recent performance for threats
                with self.performance_lock:
                    if len(self.recent_outcomes) >= 10:
                        failures = self.recent_outcomes.count(False)
                        total = len(self.recent_outcomes)
                        fail_rate = failures / total
                        
                        if fail_rate > settings.sentinel.sentinel_trigger_threshold:
                            self._engage_sentinel_protocols(fail_rate)

            if self.shutdown_event.is_set():
                break

            # --- 2. Health Monitor Recovery (Interval) ---
            # Only run this check every X minutes
            if monitor_enabled and (time.time() - last_recovery_check) > (monitor_interval_minutes * 60):
                self.logger.info("Sentinel: Initiating self-repair protocol (Active Re-evaluation)...")
                try:
                    disabled_smtps_to_test = []
                    with self.smtp_pool_lock:
                        for s in self.smtp_pool:
                            # Check if cooldown has expired or we just want to aggressively recheck
                            if s.disabled_until and time.time() > s.disabled_until:
                                disabled_smtps_to_test.append(s)
                    
                    if not disabled_smtps_to_test:
                        self.logger.info("Sentinel: No disabled units require re-evaluation at this time.")
                    else:
                        self.logger.info(f"Sentinel: Re-evaluating {len(disabled_smtps_to_test)} offline unit(s)...")
                        
                        from concurrent.futures import ThreadPoolExecutor, as_completed
                        with ThreadPoolExecutor(max_workers=5) as executor:
                            future_to_smtp = {executor.submit(smtp_utils.test_smtp_connection, smtp, self.logger): smtp for smtp in disabled_smtps_to_test}
                            
                            for future in as_completed(future_to_smtp):
                                smtp_conf = future_to_smtp[future]
                                smtp_id = f"{smtp_conf.host}:{smtp_conf.port}:{smtp_conf.email}"
                                try:
                                    is_ok, msg, _ = future.result()
                                    with self.smtp_pool_lock, self.db_lock: # Lock both for consistency
                                        conn = sqlite3.connect(DB_PATH)
                                        cursor = conn.cursor()
                                        if is_ok:
                                            self.logger.info(f"{GREEN}Sentinel: Unit {smtp_conf.email} is back online. Re-enabling.{RESET}")
                                            smtp_conf.disabled_until = None
                                            smtp_conf.fail_count = 0 # Reset fail count on recovery
                                            cursor.execute("UPDATE smtp_state SET disabled_until = 0, fail_count = 0 WHERE smtp_id = ?", (smtp_id,))
                                        else:
                                            # "Brutal" Relentless Pursuit: Increase cooldown on repeated failure
                                            new_cooldown = (self.cooldown_minutes * 60) * 2 # Double the cooldown
                                            new_disabled_until = time.time() + new_cooldown
                                            smtp_conf.disabled_until = new_disabled_until
                                            self.logger.warning(f"{YELLOW}Sentinel: Unit {smtp_conf.email} failed re-evaluation. Extending cooldown for {self.cooldown_minutes * 2} mins.{RESET}")
                                            cursor.execute("UPDATE smtp_state SET disabled_until = ? WHERE smtp_id = ?", (new_disabled_until, smtp_id))
                                        conn.commit()
                                        conn.close()
                                except Exception as e:
                                    self.logger.error(f"Sentinel: Error during re-evaluation of {smtp_conf.email}: {e}")
                except Exception as e:
                    self.logger.warning(f"Sentinel: Recovery protocol failure: {e}")
                last_recovery_check = time.time()

            time.sleep(5) # Check Sentinel stats every 5 seconds

    def _engage_sentinel_protocols(self, fail_rate):
        """Analyzes failure reasons and adapts behavior (Polymorphism/Shields)."""
        
        # --- "Brutal" Protocol: Strict Mode Annihilation ---
        if settings.sentinel.sentinel_strict_mode and fail_rate >= settings.sentinel.sentinel_strict_threshold:
            self.logger.critical(f"{RED}SENTINEL: ANNIHILATION PROTOCOL ENGAGED!{RESET}")
            self.logger.critical(f"Failure rate of {int(fail_rate*100)}% has breached the strict threshold of {int(settings.sentinel.sentinel_strict_threshold*100)}%.")
            self.logger.critical("Halting campaign immediately to prevent further reputation damage.")
            self.shutdown_event.set()
            return # Halt all other protocols
        
        # Analyze reason for failure
        content_error_keywords = ['5.7.1', 'spam', 'content', 'rejected', 'policy', 'blocked']
        is_content_related = any(any(k in r.lower() for k in content_error_keywords) for r in self.failure_reasons.keys())
        
        # Protocol 1: Polymorphic Shield (Adapt to Content Blocks)
        if is_content_related:
            # A. AI Body Rewrite
            if settings.sentinel.sentinel_polymorphic_mode and not self.sentinel_polymorphic_active and settings.ai.ai_enabled:
                self.logger.warning(f"{RED}SENTINEL: Threat detected (Content Filter). Engaging Polymorphic Shield (Auto-AI Body Rewrite).{RESET}")
                settings.ai.ai_rewrite_body = True
                self.sentinel_polymorphic_active = True
            
            # B. "Brutal" Adaptive Delivery Method
            if settings.sentinel.sentinel_adaptive_delivery:
                self.sentinel_current_delivery_index = (self.sentinel_current_delivery_index + 1) % len(self.sentinel_delivery_methods)
                new_method = self.sentinel_delivery_methods[self.sentinel_current_delivery_index]
                
                if settings.email.link_delivery_method != new_method:
                    self.logger.warning(f"{RED}SENTINEL: Adapting attack vector. Switching Link Delivery Method to '{new_method.upper()}'.{RESET}")
                    settings.email.link_delivery_method = new_method
                    # Also update the message_builder's copy of settings
                    self.message_builder.settings.email.link_delivery_method = new_method
        
        # Protocol 2: Adaptive Armor (Throttling)
        # If we are failing fast, slow down to prevent total IP burn
        with self.throttle_lock:
            if self.dynamic_sleep_time < 5.0:
                self.logger.warning(f"{YELLOW}SENTINEL: Taking heavy fire ({int(fail_rate*100)}% fail). Reinforcing armor (Increasing delays).{RESET}")
                self.dynamic_sleep_time = min(15.0, self.dynamic_sleep_time * 2.0)

    def run_deliverability_test(self):
        """Sends a single, fully-rendered test email to a seed list for inbox placement testing."""
        seed_list_file = str(settings.deliverability_test.seed_list_file)
        
        seed_list_path = os.path.join(self.project_root, seed_list_file)

        with open(seed_list_path, 'r', encoding='utf-8') as f:
            seed_emails = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        self.logger.info(f"--- Starting Deliverability Test for {len(seed_emails)} seed address(es) ---")

        # Use the first recipient from the main list as a template for personalization
        if not self.recipients:
            self.logger.error("No recipients loaded. Cannot generate a test email.")
            return
        test_recipient_data = self.recipients[0]

        # Send the same email to all seed addresses
        for email in seed_emails:
            self.logger.info(f"Sending test to: {email}")
            # Create a temporary RecipientModel for the send function
            temp_recipient = RecipientModel(email=email, **test_recipient_data.model_dump())
            self._send_via_smtp(temp_recipient, 0)
        
        self.logger.info("--- Deliverability Test Complete ---")
        self.logger.info("Check your deliverability testing service (e.g., mail-tester.com) for results.")

if __name__ == "__main__":
    # --- "World-Class" Argument Parsing ---
    import argparse
    parser = argparse.ArgumentParser(description="Sentinel Jesko - High-performance email sending tool.")
    parser.add_argument('--fresh-start', action='store_true', help="Clear all state for a fresh campaign. Includes a pre-flight bounce scan.")
    parser.add_argument('--reset-smtp-state', action='store_true', help="Clear all SMTP usage and failure state from the database.")
    parser.add_argument('--reenable-smtps', action='store_true', help="Manually re-enable all temporarily disabled SMTP servers.")
    parser.add_argument('--deliverability-test', action='store_true', help="Send a test email to the seed list for inbox placement analysis.")
    parser.add_argument('--dry-run', type=int, metavar='N', help="Simulate sending to the first N recipients without actually sending emails.")
    parser.add_argument('--imap-scan', action='store_true', help="Run the IMAP bounce/reply scanner and then exit.")
    parser.add_argument('--no-listener', action='store_true', help=argparse.SUPPRESS) # Hidden argument for menu integration

    # Manually check for 'imap-scan' to run it before the main Sender initialization
    if 'imap-scan' in sys.argv or '--imap-scan' in sys.argv:
        sender = Sender()
        sender.run_bounce_scan()
        _real_exit(0)

    args = parser.parse_args()

    sender = Sender()

    if args.fresh_start:
        sender.run_bounce_scan()

    if args.reset_smtp_state:
        sender.reset_smtp_state() 
        _real_exit(0)

    if args.reenable_smtps:
        try:
            with sender.db_lock:
                conn = sqlite3.connect(DB_PATH)
                conn.execute("UPDATE smtp_state SET disabled_until = 0")
                conn.commit()
                conn.close()
            sender.logger.info("All SMTP servers have been manually re-enabled.")
        except Exception as e:
            sender.logger.error(f"Failed to re-enable SMTPs: {e}")
        _real_exit(0)

    if args.deliverability_test:
        sender.run_deliverability_test()
        _real_exit(0)

    if args.dry_run is not None:
        n = args.dry_run
        sender.logger.info(f"--- Starting DRY-RUN for {n} recipients. ---")
        sender.simulation_mode = True
        sender.recipients = sender.recipients[:n]

    if sender.sending_method == 'smtp':
        if not sender.simulation_mode:
            # The smtp_utils function now handles reading the config itself.
            working_smtp_pool = smtp_utils.initialize_smtp_pool(sender.logger) # It will read the config itself
            if not working_smtp_pool:
                sender.logger.error("--- FATAL: No working SMTP servers found after testing. ---")
                sender.logger.error("Please check your SMTP credentials and network connection in the config.ini file.")
                _real_exit(1)
            sender.set_smtp_pool(working_smtp_pool)
        else:
            # --- "World-Class" Simulation Support ---
            # In dry-run, we load the configs but skip the network connectivity test.
            sender.logger.info("Dry-run: Loading SMTP configurations without connectivity test.")
            raw_configs = smtp_utils.get_smtp_configs()
            if not raw_configs:
                from settings import SmtpConfigModel
                sender.logger.warning("No SMTP configs found. Using dummy for simulation.")
                dummy = SmtpConfigModel(host='simulated.smtp', port=587, email='simulation@local', password='sim', security='starttls')
                raw_configs = [dummy]
            sender.set_smtp_pool(raw_configs)
    elif sender.sending_method == 'ews':
        sender.logger.info("--- Sending method set to EWS. SMTP pool will not be initialized. ---")

    # --- "World-Class" Fix: Only start the keyboard listener if the script is run directly, not from the menu. ---
    # The menu will pass '--no-listener' to prevent console conflicts.
    if not args.no_listener:
        listener_thread = threading.Thread(target=keyboard_listener, args=(sender,), daemon=True)
        listener_thread.start()

    # --- New: Start the performance monitor thread ---
    perf_monitor_thread = threading.Thread(target=sender._performance_monitor, daemon=True)
    perf_monitor_thread.start()

    # --- New: Start the Sentinel Engine thread ---
    sentinel_thread = threading.Thread(target=sender._sentinel_engine, daemon=True)
    sentinel_thread.start()

    sender.content()
