==================================================
Jesseg============================================
Welcome to Sentinel Jesko! This guide will help yo

---------------------
--- 1. Main Menu ---
---------------------
This is the main screen you see when you start the application. It provides a high-level status dashboard.

[1] Campaign Management: Start, resume, and test your email campaigns.
[2] Diagnostics & Tools: Test your setup, validate configuration, and monitor performance.
[3] Configuration & Setup: Edit settings, manage security (S/MIME, DKIM), and configure AI.
[4] Data & State Management: Manage your database, scan for bounced emails, and view suppression lists.
[5] Toggle Warm-up Mode: Cycle between sending modes (DISABLED, SEMI, FULL) to manage sender reputation.
[0] Exit: Closes the application.

---------------------------------
--- 1. Campaign Management ---
---------------------------------
Actions for running your email campaigns.

[1] Start Fresh Campaign: Deletes all previous logs and state. Starts a new campaign from scratch. **Recommended for new mailings.**
[2] Resume Campaign: Continues a previous campaign, skipping recipients that have already been sent an email.
[3] Test SMTPs & Send Fresh Campaign: Tests all SMTP servers, then starts a fresh campaign.
[4] Dry-run N recipients (preview): Simulates sending to 'N' recipients without actually sending emails. Perfect for checking templates and personalization.
[5] Run Deliverability/Inbox Test: Sends your email to a "seed list" (e.g., from mail-tester.com) to check your inbox placement score.
[6] Generate HTML Click Report: (Future Feature) Will generate a report of clicked links.

---------------------------------
--- 2. Configuration & Setup ---
---------------------------------
Manage your application's settings.

[1] Guided Setup: A wizard for first-time users to configure the most important settings. **Start here!**
[2] Advanced Configuration: Manually edit any setting in the `config.ini` file, section by section.
[3] S/MIME: Auto-Generate Certs: Automatically creates a unique S/MIME certificate for each of your configured SMTP accounts, which can add a "verified" checkmark in some email clients.
[4] DKIM Key Manager: Generates a DKIM key pair and shows you the DNS record you need to add to your domain for email authentication.
[5] Select Link Delivery Strategy: Easily switch between how links are delivered: directly in the email body, inside a PDF attachment, or in a secure HTML attachment.
[6] EML Forwarding Settings: Configure the advanced strategy of sending your email as a `.eml` attachment inside a wrapper email.
[7] AI Content Engine: Enable/disable AI features, manage API keys, and toggle specific AI actions like subject rewriting and reply classification.

---------------------------------
--- EWS (Exchange) Sending ---
---------------------------------
This application supports sending via Microsoft Exchange for high deliverability.

**Authentication Methods:**
1.  **Basic Auth (Legacy):** Uses the username and password configured for the EWS account. This will fail if the account has Multi-Factor Authentication (MFA) enabled.
2.  **OAuth2 (Modern):** The recommended method. It is secure and works with MFA-enabled accounts. The first time you use it, a browser window will open for you to log in and grant consent. The application will then handle token refreshes automatically.

**If you have MFA, you MUST either use the OAuth2 method OR create an "App Password" in your Microsoft account security settings and use that with the Basic Auth method.**


---------------------------------
--- 3. Diagnostics & Tools ---
---------------------------------
Test and validate your setup.

[1] Validate Configuration: Checks your `config.ini` file for common errors and missing files.
[2] Test SMTPs Only: Runs a connection test on all configured SMTP servers without sending campaign emails.
[3] Live SMTP Dashboard: A live, auto-refreshing screen showing sends per minute, throttle delay, and the status of all SMTP servers.
[4] View SMTP State (Static): A one-time snapshot of the status, sent counts, and failure counts for all SMTP servers.
[5] DNS & Domain Health Check: Checks your domain's SPF, DKIM, and DMARC records for correct setup.
[6] Test Custom Tracking Link: (Not Implemented)
[7] Test Zapier Webhook: (Not Implemented)
[8] View Logs Folder: Opens the 'logs' folder where all log files and reports are stored.
[9] Test Groq AI Connection: Performs a quick test to ensure your AI API key is working correctly. **Run this if you have AI issues!**

-----------------------------------
--- 4. Data & State Management ---
-----------------------------------
Manage your campaign data.

[1] IMAP Bounce Scan: Connects to the email accounts you define in `config/imap_accounts.json`. It uses AI to read new emails, classify them (e.g., bounce, unsubscribe request, out-of-office), and automatically add hard bounces to the suppression list.
[2] View Suppression List: Opens the `suppression_list.txt` file so you can see which emails are being blocked from sending.
[3] Initialize/Reset Database: Creates or completely wipes the application's database (`state.db`), which stores all sending history and SMTP states.
[4] Migrate Old State to Database: A utility to move legacy log files into the new database structure.


==================================================
Quick Start Guide for Sending & Monitoring
==================================================

You've set up your Gmail accounts with App Passwords. Here's how to send a campaign and monitor the replies.

**Step 1: Verify Your AI Setup (Crucial for Monitoring)**
The reply monitoring feature depends on AI. Let's make sure it's working.
1. Go to `3) Diagnostics & Tools`.
2. **For maximum speed**, ensure your AI provider is set to Groq. Go to `3) Configuration & Setup` -> `7) AI Content Engine` -> `2) Select Provider & Model` and choose Groq. Using a local provider like Ollama will be significantly slower.
3. If using Groq, ensure your API key is set. Go to `3) Configuration & Setup` -> `7) AI Content Engine` -> `3) Manage API Keys` to enter your key.
**Step 2: Configure IMAP Accounts for Monitoring**
1. Open the `config/imap_accounts.json` file in a text editor.
2. Fill in the `user`, `password` (use your App Password here), and `server` (`imap.gmail.com` for Gmail) for each account you want to monitor.

**Step 3: Start Your Campaign**
1. Go to `1) Campaign Management`.
2. Select `1) Start Fresh Campaign`. This will clear old logs and start sending to the recipients in your list.

**Step 4: Run the Reply/Bounce Scan**
After your campaign has been running for a while and you expect replies have come in:
1. Go to `4) Data & State Management`.
2. Select `1) IMAP Bounce Scan`.
3. The system will log into your configured IMAP accounts, read new emails, and use AI to classify them.

**Step 5: Check the Results**
1. The console will show you the classification for each email it processes.
2. Emails classified as `HARD_BOUNCE` or `HUMAN_NEGATIVE_UNSUBSCRIBE` will be automatically added to the suppression list.
3. You can view this list by going to `4) Data & State Management` -> `2) View Suppression List`.
4. For detailed logs, go to `3) Diagnostics & Tools` -> `8) View Logs Folder`.


==================================================
AI Troubleshooting (Groq Connection Issues)
==================================================

Groq is extremely fast, but sometimes blocks connections from data centers or certain regions. If you are having trouble connecting, proxies are the solution.

**The Problem:** Your IP address might be blocked by Groq's firewall.

**The Solution: Use Proxies**
This application has a built-in tool to find and manage free proxies for you.

1.  **Fetch New Proxies:** Go to `2) Diagnostics & Tools` -> `10) Fetch & Validate Free Proxies`. This will download a list of public proxies and test them to find working ones.
2.  **Test Again:** After fetching, immediately run `2) Diagnostics &tools` -> `9) Test Groq AI Connection`. This test will now try connecting through the new proxies it just fetched.

**Important Note:** Free proxies are not always reliable and can go offline. If you experience AI errors again in the future, simply repeat the two steps above to refresh your proxy list. The system is designed to automatically try all configured proxies until it finds one that works.