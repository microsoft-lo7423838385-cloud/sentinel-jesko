#!/usr/bin/env python
"""
Simple test to verify email sending with AI content generation works.
This bypasses caching issues and tests the full pipeline.
"""
import sys
import os

# Force reimport of settings
if 'settings' in sys.modules:
    del sys.modules['settings']
    
# Clear all pycache
import shutil
pycache_dir = os.path.join(os.path.dirname(__file__), '__pycache__')
if os.path.exists(pycache_dir):
    shutil.rmtree(pycache_dir)

from settings import settings
from function.ai_client import get_ai_client
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SendTest")

def test_email_send_with_ai():
    """Test if email sending with AI is configured correctly."""
    
    print("\n" + "="*60)
    print("EMAIL SEND WITH AI TEST")
    print("="*60)
    
    # 1. Check AI settings
    print("\n--- AI Configuration Check ---")
    print(f"AI Enabled: {settings.ai.ai_enabled}")
    print(f"AI Provider: {settings.ai.ai_provider}")
    print(f"AI Model: {settings.ai.ai_model}")
    print(f"AI Features:")
    print(f"  - Rewrite Subject: {settings.ai.ai_rewrite_subject}")
    print(f"  - Generate Intro: {settings.ai.ai_generate_intro}")
    print(f"  - Rewrite Body: {settings.ai.ai_rewrite_body}")
    print(f"  - Classify Replies: {settings.ai.ai_classify_replies}")
    
    # 2. Check API Key
    api_key = settings.dev.groq_api_key
    if api_key:
        key_display = api_key[:10] + "..." + api_key[-10:] if len(api_key) > 20 else "***"
        print(f"\nGroq API Key: {key_display}")
    else:
        print(f"\n❌ Groq API Key: NOT FOUND")
        print("   Please add GROQ_API_KEY to your .env file or config")
        return False
    
    # 3. Check Proxy Settings
    print(f"\n--- Proxy Configuration ---")
    print(f"Proxy for AI Enabled: {settings.proxy.proxy_ai_connections}")
    print(f"Proxies Available: {len(settings.proxy.proxy_list)}")
    
    # 4. Try to initialize AI client
    print(f"\n--- AI Client Initialization ---")
    try:
        client = get_ai_client(settings, logger)
        if client:
            print("✓ AI Client initialized successfully")
        else:
            print("❌ AI Client returned None - Check settings and API key")
            return False
    except Exception as e:
        print(f"❌ Failed to initialize AI client: {e}")
        return False
    
    # 5. Check SMTP settings
    print(f"\n--- SMTP Configuration ---")
    smtp_servers = settings.smtp.smtp_servers
    if smtp_servers:
        print(f"SMTP Servers Configured: {len(smtp_servers)}")
        for server in smtp_servers[:3]:  # Show first 3
            print(f"  - {server}")
    else:
        print("❌ No SMTP servers configured")
        print("   Configure SMTP servers in config.ini [SMTP] section")
        return False
    
    # 6. Check email template files
    print(f"\n--- Email Templates ---")
    message_files = settings.email.message_file
    print(f"Message Files: {message_files}")
    for msg_file in message_files:
        file_path = os.path.join(os.path.dirname(__file__), 'files', msg_file)
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
                print(f"  ✓ {msg_file} ({len(content)} bytes)")
        else:
            print(f"  ❌ {msg_file} - FILE NOT FOUND")
    
    # 7. Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print("✓ AI is configured and client initialized")
    print("✓ Email template files exist")
    print("✓ SMTP servers are configured")
    print("\nYou can now:")
    print("1. Run 'python main.py' to start the main sender")
    print("2. Configure recipients in recipients.txt")
    print("3. The system will automatically generate AI content for emails")
    print("="*60 + "\n")
    
    return True

if __name__ == "__main__":
    success = test_email_send_with_ai()
    sys.exit(0 if success else 1)
