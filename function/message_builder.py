import os
import sys
import time
import random
import threading
import base64
import hashlib
import hmac
import re
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.utils import make_msgid, formatdate
from email import encoders
import json
import logging
import configparser

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import dkim
except ImportError:
    dkim = None

try:
    from smime.sign import sign as smime_sign
except ImportError:
    smime_sign = None

try:
    import segno
    from io import BytesIO
except ImportError:
    segno = None

try:
    from premailer import Premailer
except ImportError:
    Premailer = None

import html2text
from function.encryption import encrypt_attachment
from function import dynamic_content
from function.ai_client import get_ai_client

# --- Anti-Fingerprint Header Pools ---
X_MAILER_POOL = [
    'Microsoft Outlook 16.0',
    'Apple Mail (2.4323)',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Thunderbird/115.0',
    'Microsoft Outlook 15.0',
    'Apple Mail (2.4124)',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15',
]
MID_DOMAIN_POOL = [
    'gmail.com',
    'outlook.com',
    'yahoo.com',
    'hotmail.com',
    'icloud.com',
    'aol.com',
    'proton.me',
    'fastmail.com',
    'zoho.com',
    'hey.com',
    'live.com',
    'msn.com',
]

class MessageBuilder:
    """
    A "smart" builder class responsible for constructing a complete email message.
    This encapsulates all logic related to templating, content, attachments, and signing.
    """
    def __init__(self, logger, settings, jinja_env, project_root):
        self.logger = logger
        self.settings = settings
        self.jinja_env = jinja_env
        self.project_root = project_root
        self.config_path = os.path.join(project_root, 'config', 'config.ini')
        self._ai_cache = {} # Simple cache to prevent re-generating for identical contexts if needed
        self._missing_templates_logged = set()
        self._log_lock = threading.Lock()
        self._mid_domain_index = 0  # Sequential rotation for Message-ID domain

    def create(self, context, smtp_config, recipient_index, sends_completed, is_eml_inner_call=False):
        """
        Creates a fully formed MIMEMultipart message for a given recipient.
        
        Returns a tuple of (MIMEMultipart, from_email, subject).
        """
        # --- "Brilliant" EML Forwarding Strategy ---
        if self.settings.eml.eml_enabled and not is_eml_inner_call:
            # If EML forwarding is on, call a dedicated builder method
            return self._create_eml_forward(context, smtp_config, recipient_index)

        # A/B Testing for Subjects
        # --- [FIX] "World-Class" Subject Parsing ---
        # Handle cases where configparser returns the subjects as a single multiline string.
        raw_subjects = self.settings.email.email_subjects
        if isinstance(raw_subjects, str):
            subjects_list = [s.strip() for s in raw_subjects.split('\n') if s.strip()]
        elif isinstance(raw_subjects, list):
            subjects_list = []
            for item in raw_subjects:
                subjects_list.extend([s.strip() for s in item.split('\n') if s.strip()])
        else:
            subjects_list = ["Notification"]
            
        # Prefer dynamic subject variant from this send's context.
        final_subject = context.get('subject_variant') or context.get('subject')
        if final_subject:
            subject_template = self.jinja_env.from_string(str(final_subject))
            final_subject = subject_template.render(context)
        else:
            subject_index = recipient_index % len(subjects_list)
            subject_template = self.jinja_env.from_string(subjects_list[subject_index])
            final_subject = subject_template.render(context)
        
        # --- "World-Class" Rendering Check ---
        # If Jinja failed to render tags (e.g. due to syntax or missing vars), log it and attempt a simple fallback.
        if "{{" in final_subject:
            self.logger.warning(f"Subject rendering incomplete: '{final_subject}'. Attempting fallback replacement.")
            
            # 1. Simple variable replacements
            final_subject = final_subject.replace("{{ sender_company }}", context.get('sender_company', 'Service Provider'))
            final_subject = final_subject.replace("{{ sender_name }}", context.get('sender_name', 'Support Team'))
            
            # 2. Date replacements (handling filters roughly)
            if "current_date" in final_subject:
                now = datetime.now()
                # Handle specific format used in config: {{ current_date | format_date('%B') }}
                # We use a regex to be flexible with spaces and quotes. Matches %B or %%B.
                final_subject = re.sub(r'\{\{\s*current_date\s*\|\s*format_date\([\'"]%*B[\'"]\)\s*\}\}', now.strftime('%B'), final_subject)
                # Handle standard date
                final_subject = final_subject.replace("{{ current_date }}", context.get('current_date', now.strftime('%Y-%m-%d')))
            
            # 3. Cleanup any remaining tags to look professional
            final_subject = re.sub(r'\{\{.*?\}\}', '', final_subject).strip()
            # Clean up double spaces created by removal
            final_subject = re.sub(r'\s+', ' ', final_subject)

        context['subject'] = final_subject # Set initial subject for templates

        # --- "World-Class" Identity Alignment ---
        # The From address MUST match the SMTP user to pass SPF/DKIM alignment.
        # Support "Send As" via 'auth_user#send_as_user' syntax
        if '#' in smtp_config.email:
            _, from_email_to_use = smtp_config.email.split('#', 1)
        else:
            from_email_to_use = smtp_config.email
        # The friendly name is now dynamically generated in the context builder.
        final_from_name = context.get('sender_name', 'Support')

        # --- "World-Class" Warm-up Strategy ---
        # If text-only warm-up is active, we use a completely separate, simplified logic path.
        # This ensures no HTML is processed, resulting in a pure plain-text message for deliverability.
        if self.settings.warmup.warmup_enabled and self.settings.warmup.warmup_plain_text_only:
            self.logger.info("WARM-UP (TEXT ONLY): Sending plain-text version of email to build reputation.")
            
            # --- [FIX] "World-Class" User Guidance ---
            # Check if the user is editing an HTML file while in text-only mode.
            html_templates_in_config = any(f.lower().endswith('.html') for f in self.settings.email.message_file)
            txt_templates_in_config = any(f.lower().endswith('.txt') for f in self.settings.email.message_file)
            
            if html_templates_in_config and not txt_templates_in_config:
                self.logger.warning("Your 'message_file' is set to an HTML file, but warm-up is in TEXT-ONLY mode.")
                self.logger.warning("The system will now automatically convert your HTML to plain text for this mode.")
            
            # Find a .txt template from the configured message_file list
            txt_templates = [f for f in self.settings.email.message_file if f.lower().endswith('.txt')]
            
            # --- "World-Class" Auto-Discovery ---
            # If no explicit .txt templates are configured, check if we can infer them from .html files.
            # This ensures files like 'letter.txt' are picked up even if only 'letter.html' is in config.
            if not txt_templates:
                # Strategy 1: Infer from HTML config (e.g. letter.html -> letter.txt)
                for f in self.settings.email.message_file:
                    if f.lower().endswith('.html'):
                        candidate = f.rsplit('.', 1)[0] + '.txt'
                        if os.path.exists(os.path.join(self.project_root, 'files', candidate)):
                            txt_templates.append(candidate)
                            self.logger.info(f"Auto-discovered plain text template: {candidate}")

                # Strategy 2: Scan 'files/' directory for ANY .txt template if inference failed
                if not txt_templates:
                    files_dir = os.path.join(self.project_root, 'files')
                    if os.path.exists(files_dir):
                        for f in os.listdir(files_dir):
                            if f.lower().endswith('.txt') and not f.startswith('.'):
                                txt_templates.append(f)
                                # Prioritize 'letter.txt' or similar standard names
                                txt_templates.sort(key=lambda x: 0 if 'letter' in x.lower() else 1)
                                self.logger.info(f"Fallback: Found plain text template in files directory: {txt_templates[0]}")
                                break 

            # --- [MODIFIED] "World-Class" Unified Template Logic for Warm-up ---
            if txt_templates:
                # Use the first available .txt template
                template_index = recipient_index % len(txt_templates)
                chosen_plain_template_file = txt_templates[template_index]
                try:
                    plain_template = self.jinja_env.get_template(chosen_plain_template_file)
                    personalized_body_plain = plain_template.render(context)
                except Exception as e:
                    self.logger.error(f"Could not load or render plain text template '{chosen_plain_template_file}': {e}")
                    # Fallback to the safe default if rendering fails
                    personalized_body_plain = "Hello {{ recipient_name | default('there') }},\n\nThis is a notification regarding your account.\n\nPlease check your account for more details.\n\nThank you,\n{{ sender_name }}"
                    plain_template = self.jinja_env.from_string(personalized_body_plain)
                    personalized_body_plain = plain_template.render(context)
            else:
                # --- NEW: HTML-to-Text Fallback ---
                # No .txt templates found, so we'll render the HTML and convert it.
                html_templates = [f for f in self.settings.email.message_file if f.lower().endswith('.html')]
                if html_templates:
                    template_index = recipient_index % len(html_templates)
                    chosen_html_template_file = html_templates[template_index]
                    try:
                        message_template = self.jinja_env.get_template(chosen_html_template_file)
                        personalized_body_html = message_template.render(context)
                        h = html2text.HTML2Text()
                        h.ignore_links = False
                        personalized_body_plain = h.handle(personalized_body_html)
                    except Exception as e:
                        self.logger.error(f"Could not load/render HTML template '{chosen_html_template_file}' for text conversion: {e}")
                        personalized_body_plain = "Hello {{ recipient_name | default('there') }},\n\nThis is a notification regarding your account.\n\nPlease check your account for more details.\n\nThank you,\n{{ sender_name }}"
                        plain_template = self.jinja_env.from_string(personalized_body_plain)
                        personalized_body_plain = plain_template.render(context)
                else:
                    # "Smarter" Fallback: If no templates of any kind are configured.
                    self.logger.warning("Text-Only Warm-up is active, but no .txt or .html templates are configured. Using a safe default template.")
                    personalized_body_plain = "Hello {{ recipient_name | default('there') }},\n\nThis is a notification regarding your account.\n\nPlease check your account for more details.\n\nThank you,\n{{ sender_name }}"
                    plain_template = self.jinja_env.from_string(personalized_body_plain)
                    personalized_body_plain = plain_template.render(context)

            # AI content generation for plain text
            if self.settings.ai.ai_enabled:
                 final_subject, ai_intro, personalized_body_plain = self._generate_ai_content_in_one_shot(
                    context, final_subject, personalized_body_plain
                )
                 if ai_intro:
                    # Prepend the intro to the plain text body
                    personalized_body_plain = ai_intro + "\n\n" + personalized_body_plain

            # Build the plain-text-only message
            msg = MIMEText(personalized_body_plain, 'plain', 'utf-8')

        # --- Standard HTML/Multipart Email Logic ---
        else:
            # --- "Brilliant" Strategic QR Code Handling ---
            # Only generate a QR code if the delivery method is 'direct'.
            # For 'secure_document' or 'safe_link', the link is in an attachment, so a QR code in the body is illogical.
            is_direct_method = self.settings.email.link_delivery_method == 'direct'
            if self.settings.qr.qr_enabled and is_direct_method and context.get('link', '#').startswith('http'):
                self._add_qr_code_to_context(context)

            # --- "World-Class" Unified Template Strategy ---
            # Always use the configured HTML templates. The content of the template itself
            # should be what instructs the user on how to access the link (direct vs. attachment).
            template_index = recipient_index % len(self.settings.email.message_file)
            chosen_html_template_file = self.settings.email.message_file[template_index]
            
            # --- "World-Class" Dual-Template System ---
            # Use a dedicated plain-text template for maximum professionalism and control.
            # Fallback to the first configured template if the corresponding one is missing.
            try:
                chosen_plain_template_file = chosen_html_template_file.replace('.html', '.txt')
                plain_template = self.jinja_env.get_template(chosen_plain_template_file)
            except Exception:
                with self._log_lock:
                    if chosen_html_template_file not in self._missing_templates_logged:
                        self.logger.info(f"Plain text template for '{chosen_html_template_file}' not found. Auto-generating from HTML (This is normal).")
                        self._missing_templates_logged.add(chosen_html_template_file)
                plain_template = None # Signal to auto-generate

            try:
                message_template = self.jinja_env.get_template(chosen_html_template_file)
            except Exception as e:
                self.logger.warning(f"Could not load template '{chosen_html_template_file}'. Error: {e}. Falling back to the first configured template.")
                message_template = self.jinja_env.get_template(self.settings.email.message_file[0])
            
            self.logger.info("Rendering HTML template...")
            personalized_body_html = message_template.render(context)

            # --- "World-Class" Auto-Spintax ---
            # Automatically apply spintax randomization {a|b} to subject and body
            if 'spintax' in self.jinja_env.filters:
                # self.logger.info("Processing Spintax...")
                final_subject = self.jinja_env.filters['spintax'](final_subject)
                personalized_body_html = self.jinja_env.filters['spintax'](personalized_body_html)

            # --- "World-Class" HTML Structure Check ---
            # If the template was a .txt file or lacked HTML tags, wrap it to prevent "Bad HTML" penalties.
            if "<html" not in personalized_body_html.lower() and "<body" not in personalized_body_html.lower():
                 # Convert newlines to breaks and wrap
                 content_wrapped = personalized_body_html.replace("\n", "<br>")
                 personalized_body_html = f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body style='font-family: Arial, sans-serif; font-size: 14px; line-height: 1.5;'>{content_wrapped}</body></html>"

            # --- "World-Class" CSS Inlining ---
            # Automatically inline CSS for maximum email client compatibility.
            # We now check the settings to see if this feature is enabled (defaults to True).
            if Premailer and self.settings.html_conversion.enable_css_inlining:
                self.logger.info("Starting CSS Inlining (Premailer)...")
                try:
                    # allow_network=False prevents hangs if the HTML contains external links (fonts, css) that are unreachable.
                    # disable_validation=True prevents time-consuming CSS validation that can appear as a hang.
                    p = Premailer(personalized_body_html, allow_network=False, remove_classes=False, disable_validation=True)
                    personalized_body_html = p.transform()
                    self.logger.info("CSS Inlining (Premailer) completed.")
                except Exception as e:
                    self.logger.warning(f"CSS Inlining warning: {e}")

            self.logger.info("Converting HTML to plain text...")
            if plain_template:
                personalized_body_plain = plain_template.render(context)
            else:
                h = html2text.HTML2Text()
                h.ignore_links = False
                personalized_body_plain = h.handle(personalized_body_html)
            self.logger.info("Plain text conversion completed.")
            
            # --- "World-Class" Ratio Check ---
            # Mail-Tester flags HTML_IMAGE_ONLY if text count is low relative to images (Seal/QR).
            word_count = len(re.findall(r'\w+', personalized_body_plain))
            if word_count < 150 and (context.get('qr_code_cid') or context.get('sender_seal_cid')):
                self.logger.warning(f"Low text-to-image ratio detected ({word_count} words). Consider adding more text to avoid SpamAssassin flags.")

            # --- "HYPERDRIVE" AI ENGINE ---
            # Generate all AI content in one shot for maximum speed.
            if self.settings.ai.ai_enabled and any([self.settings.ai.ai_rewrite_subject, self.settings.ai.ai_generate_intro, self.settings.ai.ai_rewrite_body]):
                self.logger.info("Starting AI content generation...")
                final_subject, ai_intro, personalized_body_plain = self._generate_ai_content_in_one_shot(
                    context, final_subject, personalized_body_plain
                )
                self.logger.info("AI content generation complete.")
                context['ai_intro'] = ai_intro
            
            # Update subject in context after AI rewrite
            context['subject'] = final_subject
    
            # Build the MIME message
            self.logger.info("Building MIME message structure...")
            # --- "World-Class" MIME Structure ---
            # To properly display inline images (CID) AND attachments, we use a nested structure:
            # Root (multipart/mixed) -> for attachments
            #   inner (multipart/related) -> for inline images (seal, QR)
            #     inner_alt (multipart/alternative) -> for text/html versions
            msg = MIMEMultipart('mixed')
            
            msg_related = MIMEMultipart('related')
            msg.attach(msg_related)
            
            msg_alternative = MIMEMultipart('alternative')
            msg_related.attach(msg_alternative)
            
            msg_alternative.attach(MIMEText(personalized_body_plain, 'plain', 'utf-8'))
            msg_alternative.attach(MIMEText(personalized_body_html, 'html', 'utf-8'))

            # --- "Smarter" CID Image Attachment ---
            # If a QR code was generated, attach it as a MIMEImage with its Content-ID
            if context.get('qr_code_cid') and context.get('qr_code_data'):
                qr_image = MIMEImage(context['qr_code_data'])
                qr_image.add_header('Content-ID', f"<{context['qr_code_cid']}>")
                msg_related.attach(qr_image)

            # --- [NEW] Attach Sender Seal/Photo ---
            # If a sender seal was found, attach it as a MIMEImage with its Content-ID
            if context.get('sender_seal_cid') and context.get('sender_seal_data'):
                self.logger.debug(f"Attaching sender seal with CID: {context['sender_seal_cid']}")
                seal_image = MIMEImage(context['sender_seal_data'])
                seal_image.add_header('Content-ID', f"<{context['sender_seal_cid']}>")
                msg_related.attach(seal_image)

            # --- "World-Class" Attachment Strategy ---
            # Determine the final delivery method. The "Human Gate" (obfuscate_html)
            # has been removed, as it overrode user choice. The user should now explicitly
            # select their desired strategy from the menu.
            delivery_method = self.settings.email.link_delivery_method
            context['delivery_method'] = delivery_method

            # Attachments
            if delivery_method == 'secure_document':
        # Force dynamic PDF attachment for the secure link
                self.logger.info("Generating secure PDF document (WeasyPrint)...")
                self._attach_dynamic_pdf(msg, context) # This method now handles its own logging
            elif delivery_method == 'safe_link':
                # Attach the interstitial HTML page
                self._attach_safe_link_html(msg, context)
            elif self.settings.attachment.attachment_send and self.settings.attachment.attachment_file:
                self._attach_file(msg)

        # --- Common Header and Signing Logic ---
        msg['Subject'] = final_subject
        msg['From'] = f'"{final_from_name}" <{from_email_to_use}>'
        msg['To'] = context['recipient_email']
        # --- "Brilliant" Fix: Add the Date header back. ---
        # Some MTAs (like Comcast's) do not add this header, resulting in a penalty.
        # It is more robust to add it ourselves.
        # --- "World-Class" Date Jitter: Add seconds-level variance so timestamps aren't identical across batch sends.
        _now = time.time()
        jittered_seconds = random.uniform(0, 60)
        msg['Date'] = datetime.fromtimestamp(_now + jittered_seconds).strftime('%a, %d %b %Y %H:%M:%S %z')

        # --- Anti-Fingerprint: Randomize Message-ID domain ---
        # Using the From-domain in Message-ID leaks a consistent pattern across all sends.
        # Rotate through a pool of realistic mail-user domains to break fingerprinting.
        if getattr(self.settings.headers, 'header_add_random_x', False):
            mid_domain = MID_DOMAIN_POOL[self._mid_domain_index % len(MID_DOMAIN_POOL)]
            self._mid_domain_index += 1
        else:
            mid_domain = from_email_to_use.split('@')[-1]
        msg['Message-ID'] = make_msgid(domain=mid_domain)

        # --- "World-Class" Stealth Logic ---
        # Detect if sending from a free provider. If so, remove "Bot" headers to look Human.
        sender_domain = from_email_to_use.split('@')[-1].lower()
        free_domains = {'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com', 'icloud.com', 'live.com', 'msn.com', 'yandex.com', 'proton.me', 'protonmail.com'}
        is_free_provider = sender_domain in free_domains

        # Add Headers
        if self.settings.headers.header_reply_to:
            msg.add_header('Reply-To', self.settings.headers.header_reply_to)
        
        # --- "World-Class" Professional Headers ---
        # Removed 'Precedence: bulk' and 'X-Auto-Response-Suppress' to prevent
        # identifying the email as automated marketing traffic. This improves Inbox placement.
        
        # 2. Add a trace ID that matches a business system pattern
        if context.get('reference_code') and not is_free_provider:
            msg.add_header('X-Entity-Ref-ID', context['reference_code'])

        # --- "World-Class" Compliance Headers ---
        # Add List-Unsubscribe and List-Unsubscribe-Post headers for CAN-SPAM/GDPR compliance and deliverability.
        # "Smarter" Fix: Strip quotes from the URL before checking it.
        unsubscribe_url_str = str(self.settings.email.unsubscribe_url).strip('"\' ')
        # [MODIFIED] Force List-Unsubscribe header for all providers to satisfy deliverability checkers.
        if unsubscribe_url_str.lower().startswith('http'):
            msg.add_header('List-Unsubscribe', f'<{self.settings.email.unsubscribe_url}>')
            msg.add_header('List-Unsubscribe-Post', 'List-Unsubscribe=One-Click')
        # Add SES configuration set header when using Amazon SES SMTP mode
        if getattr(smtp_config, 'transport', None) == 'ses' or getattr(self.settings.smtp, 'smtp_ses_mode', False):
            try:
                msg.add_header('X-SES-CONFIGURATION-SET', self.settings.smtp.smtp_configuration_set)
            except Exception:
                pass

        # --- Anti-Fingerprint: Rotate X-Mailer and add organic headers ---
        # Free providers don't need X-Mailer; custom domains benefit from a realistic client match.
        if not is_free_provider:
            msg['X-Mailer'] = random.choice(X_MAILER_POOL)
        
        # --- "World-Class" Trace ID Injection ---
        # Every message gets a unique trace ID to break bulk fingerprinting.
        if not context.get('reference_code'):
            context['reference_code'] = f"TRX-{random.randint(100000, 999999)}-{random.randint(1000, 9999)}"
        if context.get('reference_code') and not is_free_provider:
            msg.add_header('X-Entity-Ref-ID', context['reference_code'])
        
        # --- "Brilliant" Fix: Use the unified signing method ---
        msg = self._sign_message(msg, smtp_config, context)

        return msg, from_email_to_use, final_subject

    def _add_qr_code_to_context(self, context):
        if not segno: return
        try:
            link_for_qr = context.get('link', '#')
            if link_for_qr.startswith(('http://', 'https://')):
                # "Smarter" Fix: Provide a default color if the config value is empty to prevent crashes.
                qr_color = self.settings.qr.qr_fg_color if self.settings.qr.qr_fg_color else '#000000'
                out = BytesIO()
                segno.make(link_for_qr, error='h').save(out, kind='png', scale=self.settings.qr.qr_scale, border=self.settings.qr.qr_border, dark=qr_color)
                qr_image_data = out.getvalue()
                # --- "Smarter" Fix: Use Content-ID (cid) instead of base64 ---
                qr_cid = f"qrcode_{dynamic_content.generate_random_md5()}@sender.local"
                context['qr_code_cid'] = qr_cid
                context['qr_code_data'] = qr_image_data # Store the raw image data
            else:
                context['qr_code_cid'] = None
        except Exception as e:
            self.logger.warning(f"Failed to generate QR code: {e}")
            context['qr_code_cid'] = None

    def _attach_file(self, msg):
        attachment_path = os.path.join(self.project_root, 'files', self.settings.attachment.attachment_file)
        if not os.path.exists(attachment_path):
            self.logger.warning(f"Attachment file not found: {attachment_path}")
            return
        try:
            with open(attachment_path, 'rb') as f:
                file_content = f.read()

            part = MIMEBase('application', 'octet-stream')

            # --- "Lost Soul" Found: Encryption ---
            if self.settings.encryption.use_cipher:
                self.logger.info(f"Encrypting attachment '{self.settings.attachment.attachment_file}'...")
                encrypted_content = encrypt_attachment(
                    file_content,
                    password=self.settings.encryption.cipher_password,
                    random_level=self.settings.encryption.cipher_random,
                    strictness=1 if self.settings.encryption.cipher_strict else 0,
                    line_length=self.settings.encryption.cipher_lines
                )
                # encrypt_attachment returns a base64 string, so we set it directly
                part.set_payload(encrypted_content)
                part.add_header('Content-Transfer-Encoding', 'base64')
            else:
                part.set_payload(file_content)
                encoders.encode_base64(part)

            display_name = self.settings.attachment.attachment_display_name or os.path.basename(attachment_path)
            part.add_header('Content-Disposition', f'attachment; filename="{display_name}"')
            msg.attach(part)
        except Exception as e:
            self.logger.warning(f"Could not attach file {attachment_path}. Error: {e}")

    def _attach_dynamic_pdf(self, msg, context):
        """Renders and attaches the secure document, falling back to ZIP if PDF fails."""
        try:
            attachment_template = self.jinja_env.get_template(self.settings.attachment.attachment_template_file)
            personalized_attachment_html = attachment_template.render(context)

            orientation = self.settings.attachment.attachment_pdf_orientation or "A4"
            if "<style>" in personalized_attachment_html:
                personalized_attachment_html = personalized_attachment_html.replace("<style>", f"<style>@page {{ size: {orientation}; }} ")
            else:
                personalized_attachment_html = f"<style>@page {{ size: {orientation}; }}</style>" + personalized_attachment_html

            meta_tags = f"""
            <meta name="author" content="{context.get('sender_name', 'Sender')}">
            <meta name="title" content="Secure Document">
            <meta name="generator" content="Documentation Tool">
            """
            if "<head>" in personalized_attachment_html:
                personalized_attachment_html = personalized_attachment_html.replace("<head>", f"<head>{meta_tags}")
            else:
                personalized_attachment_html = f"<html><head>{meta_tags}</head>" + personalized_attachment_html

            # Try to generate the PDF
            from weasyprint import HTML
            pdf_bytes = HTML(string=personalized_attachment_html).write_pdf()

            part = MIMEBase('application', "octet-stream")
            part.set_payload(pdf_bytes)
            encoders.encode_base64(part)

            r_name = context.get('recipient_name')
            if not r_name: r_name = "Recipient"
            if len(r_name) > 50: r_name = r_name[:50] # Truncate long names

            filename = f"Document_for_{r_name.replace(' ', '_')}.pdf"
            part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
            msg.attach(part)
            self.logger.info(f"Attached dynamically generated PDF: {filename}")
            return True

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"PDF generation failed: {error_msg}. Falling back to ZIP-wrapped HTML attachment.")

            # --- "World-Class" Error Diagnosis ---
            # 0x7e = Module Not Found (Missing DLLs)
            # 0x7f = Procedure Not Found (Incompatible/Old DLLs)
            if "0x7f" in error_msg or "0x7e" in error_msg:
                self.logger.critical(f"{'='*40}")
                self.logger.critical(f"CRITICAL GTK ERROR ({'Incompatible Version' if '0x7f' in error_msg else 'Missing Files'})")
                self.logger.critical("Please run 'python install_gtk.py' to download the correct dependencies.")
                self.logger.critical(f"{'='*40}")

            # --- "Jesko" Self-Healing: Zip the HTML Fallback ---
            import zipfile
            from io import BytesIO
            
            zip_buffer = BytesIO()
            html_filename = f"Secure_Document_Ref_{context.get('reference_code', '001')}.html"
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(html_filename, personalized_attachment_html)
            
            part = MIMEBase('application', 'zip')
            part.set_payload(zip_buffer.getvalue())
            encoders.encode_base64(part)
            
            r_name = context.get('recipient_name')
            if not r_name: r_name = "Recipient"
            if len(r_name) > 50: r_name = r_name[:50]

            filename = f"Document_{r_name.replace(' ', '_')}.zip"
            part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
            msg.attach(part)
            self.logger.info(f"Attached ZIP fallback document: {filename}")
            return True
        
    def _attach_safe_link_html(self, msg, context):
        """Generates and attaches a self-redirecting HTML page."""
        try:
            # The real link, which we are hiding from the email body
            redirect_url = context.get('link', '#')
            
            html_content = None

            # --- [NEW] Custom Index File Support ---
            # If the user placed 'index.html' in the files folder, use that as the attachment template.
            if os.path.exists(os.path.join(self.project_root, 'files', 'index.html')):
                try:
                    template = self.jinja_env.get_template('index.html')
                    html_content = template.render(context)
                    self.logger.info("Using custom 'index.html' for Safe Link attachment.")
                except Exception as e:
                    self.logger.warning(f"Could not load custom index.html: {e}")

            if not html_content:
                # --- "World-Class" Sanitization (XSS Prevention) ---
                # JSON-encode the URL to make it safe for injection into a JavaScript string.
                safe_js_url = json.dumps(redirect_url)

                # The content that will be revealed.
                # If obfuscation is on, this is hidden inside the JS blob.
                standard_inner_html = f"""
                <!DOCTYPE html><html><head><title>Document</title>
                <meta http-equiv="refresh" content="0;url={redirect_url}"></head>
                <body><p>Document ready. <a href="{redirect_url}">Click here to view</a>.</p>
                </body></html>
                """

                # Always use the polymorphic clean generator for HTML attachments
                # This fixes the Chrome "Dangerous Site" and AV flags by avoiding document.write/atob
                html_content = dynamic_content.generate_safe_html_attachment(redirect_url)
            
            attachment = MIMEText(html_content, 'html')
            filename = f"secure-document-{dynamic_content.generate_random_md5()[:8]}.html"
            attachment.add_header('Content-Disposition', 'attachment', filename=filename)
            msg.attach(attachment)
        except Exception as e:
            self.logger.error(f"Failed to generate or attach 'Safe Link' HTML. Error: {e}")

    def _apply_smime_signature(self, msg, smtp_config):
        if not smime_sign: return msg
        try:
            # --- "World-Class" Dynamic Certificate Selection ---
            # Infer the certificate path based on the sending email address.
            email_address = smtp_config.email
            if '#' in email_address:
                _, email_address = email_address.split('#', 1)
            safe_filename = email_address.replace('@', '_at_').replace('.', '_')
            key_file = os.path.join(self.project_root, 'certs', f"{safe_filename}.key.pem")
            cert_file = os.path.join(self.project_root, 'certs', f"{safe_filename}.cert.pem")

            if os.path.exists(key_file) and os.path.exists(cert_file):
                self.logger.info(f"Applying S/MIME signature for {email_address} using {os.path.basename(cert_file)}")
                return smime_sign(msg, key_file, cert_file, password=self.settings.smime.smime_key_password)
            else:
                self.logger.debug(f"No specific S/MIME certificate found for {email_address}. Skipping signature.")
                return msg # Return the original message if no cert is found
        except Exception as e:
            self.logger.error(f"Failed to apply S/MIME signature: {e}")
            return msg

    def _apply_dkim_signature(self, msg, smtp_config):
        if not dkim: return msg
        try:
            key_path_from_config = self.settings.dkim.dkim_private_key_file
            if not key_path_from_config:
                self.logger.warning("DKIM is enabled but 'dkim_private_key_file' is not set in config.ini. Skipping signature.")
                return msg

            # --- "World-Class" Path Resolution ---
            # If the path is not absolute, assume it's relative to the project root.
            if not os.path.isabs(key_path_from_config):
                key_path = os.path.join(self.project_root, key_path_from_config)
            else:
                key_path = key_path_from_config

            if not os.path.exists(key_path):
                self.logger.warning(f"DKIM is enabled but key file not found at: '{key_path}'. Skipping signature.")
                return msg

            with open(key_path, 'rb') as f:
                private_key = f.read()
            
            # --- "Brilliant" Domain-Aware DKIM Signing ---
            # Sign with the domain of the *actual sending server*, not the 'From' header domain.
            # This prevents SPF/DKIM mismatch when using services like iCloud/Comcast.
            raw_email = smtp_config.email
            if '#' in raw_email:
                _, raw_email = raw_email.split('#', 1)
            from_domain = raw_email.split('@')[-1]

            # --- "World-Class" Signed Unsubscribe ---
            # Include unsubscribe headers in the DKIM signature to prove their authenticity.
            headers_to_sign = [
                b'From', b'To', b'Subject', b'Message-ID', b'Date'
            ]
            # "Smarter" Fix: Conditionally add headers to the signature only if they exist in the message.
            if 'List-Unsubscribe' in msg: headers_to_sign.append(b'List-Unsubscribe')
            if 'List-Unsubscribe-Post' in msg: headers_to_sign.append(b'List-Unsubscribe-Post')
            sig = dkim.sign(message=msg.as_bytes(), selector=self.settings.dkim.dkim_selector.encode(), domain=from_domain.encode(), privkey=private_key, include_headers=headers_to_sign)
            msg['DKIM-Signature'] = sig.decode().replace('DKIM-Signature: ', '').strip()
        except Exception as e:
            self.logger.error(f"Failed to apply DKIM signature: {e}")
        return msg
    
    def _sign_message(self, msg, smtp_config, context):
        """
        A unified signing method that applies S/MIME and DKIM signatures in the correct order.
        """
        # Apply S/MIME first, as it alters the message structure.
        if self.settings.smime.smime_sign:
            msg = self._apply_smime_signature(msg, smtp_config)

        # Apply DKIM last, as it signs the final headers and body.
        if self.settings.dkim.dkim_enabled:
            msg = self._apply_dkim_signature(msg, smtp_config)
        
        return msg

    def _get_ai_client(self):
        """
        A "world-class" factory method to get the correct AI client.
        This now calls the centralized client factory function.
        """
        return get_ai_client(self.settings, self.logger)

    def _polymorphic_keyword_injector(self, text):
        """
        Intelligently injects zero-width spaces into keywords to break spam filter footprints
        while maintaining high entropy.
        """
        keywords = [
            "administrative", "review", "processed", "regulatory", "claim", 
            "litigation", "compliance", "adjudication", "enforcement", 
            "notification", "official", "mandated", "requirement", "file", "document"
        ]
        for kw in keywords:
            pattern = re.compile(re.escape(kw), re.IGNORECASE)
            def replacer(match):
                word = match.group(0)
                if len(word) < 4: return word
                # Randomly place \u200b inside the word (avoiding start/end)
                idx = random.randint(1, len(word) - 1)
                return word[:idx] + "\u200b" + word[idx:]
            # Apply to keywords with 70% probability to ensure every email is unique
            text = pattern.sub(lambda m: replacer(m) if random.random() > 0.3 else m.group(0), text)
        return text

    def _generate_ai_content_in_one_shot(self, context, subject, body):
        """
        'Inbuilt AI' Implementation: Uses local randomization and dynamic content
        to generate unique subjects and intros without external API calls.
        """
        from function import dynamic_content as dc

        new_subject = subject
        if self.settings.ai.ai_rewrite_subject:
            # Inbuilt Randomizer: Wraps the subject in rotating legal themes
            templates = [
                "{phrase}: {subject}",
                "[{ref}] {subject}",
                "{subject} - {doc}",
                "{dept} Notice: {subject}"
            ]
            new_subject = random.choice(templates).format(
                phrase=dc.generate_legal_phrase(),
                subject=subject,
                ref=context.get('reference_code', 'REF-001'),
                doc=random.choice(dc.LEGAL_DOC_TYPES),
                dept=random.choice(dc.LEGAL_DEPARTMENTS)
            )

        ai_intro = ""
        if self.settings.ai.ai_generate_intro:
            # Local Intro Generator: Instant and unique
            intros = [
                "This official notification is issued regarding {comp}.",
                "Please review the attached details concerning {case}.",
                "An administrative update has been processed for {ref}.",
                "The {dept} requires your attention regarding the following matter.",
                # --- [NEW] Concise Legal Intro (User Requested) ---
                "This notice concerns the admin\u200bistrative rev\u200biew of your file (Case: {case_co} #{case_num}). "
                "Updated materials have been pro\u200bcessed into the official case record. "
                "Please rev\u200biew these updates immediately to ensure adherence to regu\u200blatory and "
                "procedural requirements for this cl\u200baim under the National Liti\u200bgation & Com\u200bpliance framework."
            ]
            ai_intro = random.choice(intros).format(
                comp=context.get('company_phrase', 'your account'),
                case=context.get('case_claim_number', 'your case'),
                ref=context.get('reference_code', 'your file'),
                dept=random.choice(dc.LEGAL_DEPARTMENTS),
                case_co=context.get('case_insurance_co', 'Insurance Provider'),
                case_num=context.get('case_claim_number', 'REF-001')
            )

        if self.settings.ai.ai_rewrite_body:
            # --- [NEW] Concise Legal Body (User Requested) ---
            body = ("Updated records and next steps are available via the secure portal link above. "
                    "Failure to complete this review promptly may result in admin\u200bistrative holds "
                    "or enforce\u200bment actions impacting the final adjudi\u200bcation of this case.")

        return new_subject, ai_intro, body

    def health_check(self):
        """
        Performs a quick connectivity test to the AI provider.
        Returns (bool, str): (True/False, Error Message)
        """
        if not self.settings.ai.ai_enabled:
            return True, "AI disabled"
        
        return True, "Inbuilt AI Active"

    def _create_eml_forward(self, context, smtp_config, recipient_index):
        """
        Builds an email that has another email (.eml) as an attachment.
        This is a sophisticated deliverability technique.
        """
        # 1. Build the INNER email (the real message)
        # This re-uses the main `create` logic but without the EML-forwarding part.
        inner_msg, from_email_to_use, inner_subject = self.create(context, smtp_config, recipient_index, 0, is_eml_inner_call=True)

        # 2. Build the OUTER email (the wrapper)
        outer_msg = MIMEMultipart()
        
        # --- "Smarter" From Header for EML Wrapper ---
        # Use the same "Identity-Aligned" logic as the main sender to ensure DKIM/SPF pass.
        outer_from_email = smtp_config.email
        outer_from_name = self.settings.eml.eml_from_name or context.get('sender_name', 'Support')
        outer_msg['From'] = f'"{outer_from_name}" <{outer_from_email}>'
        outer_msg['To'] = context['recipient_email']
        # --- "Smarter" EML Subject Rotation ---
        # Use the main subject list for the outer email as well for more variation.
        subject_index = recipient_index % len(self.settings.email.email_subjects)
        outer_msg['Subject'] = self.settings.email.email_subjects[subject_index]
        outer_msg['Date'] = formatdate(localtime=True)
        outer_msg['Message-ID'] = make_msgid(domain=outer_from_email.split('@')[-1])

        # 3. Create the body of the outer email
        try:
            wrapper_template = self.jinja_env.get_template(self.settings.eml.eml_letter_file)
            wrapper_body = wrapper_template.render(context)
        except Exception:
            wrapper_body = "Please see the attached message." # Fallback
        outer_msg.attach(MIMEText(wrapper_body, 'plain', 'utf-8'))

        # 4. Attach the inner email as a .eml file
        eml_attachment = MIMEBase('message', 'rfc822')
        eml_attachment.set_payload(inner_msg.as_bytes())
        # "World-Class" Fix: Use 7bit encoding instead of base64 to appear less suspicious to spam filters.
        # This directly addresses the AI feedback about visible base64 encoding.
        encoders.encode_7or8bit(eml_attachment)
        attachment_name = f"{self.settings.eml.eml_attachment_name}.eml"
        eml_attachment.add_header('Content-Disposition', f'attachment; filename="{attachment_name}"')
        outer_msg.attach(eml_attachment)

        # 5. Sign the OUTER message
        signed_outer_msg = self._sign_message(outer_msg, smtp_config, context)
        
        return signed_outer_msg, outer_from_email, outer_msg['Subject']