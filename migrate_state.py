import os
import json
import sqlite3

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

PROJECT_ROOT = os.path.dirname(__file__)
LOGS_DIR = os.path.join(PROJECT_ROOT, 'logs')
DB_PATH = os.path.join(LOGS_DIR, 'state.db')

OLD_SENT_FILE = os.path.join(LOGS_DIR, 'sent_recipients.txt')
OLD_STATE_FILE = os.path.join(LOGS_DIR, 'smtp_state.json')
OLD_USAGE_FILE = os.path.join(LOGS_DIR, 'smtp_usage.json')

def migrate_state_to_db():
    """
    A "smart" utility to migrate data from old flat files (sent_recipients.txt, smtp_state.json)
    into the new SQLite database (state.db).
    """
    print("\n--- Old State to Database Migration Utility ---")

    if not os.path.exists(DB_PATH):
        print(f"{RED}ERROR: Database file 'state.db' not found.{RESET}")
        print("Please run 'Initialize/Reset Database' from the menu first.")
        input("Press Enter to return to the menu...")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    migrated_count = 0

    # 1. Migrate sent_recipients.txt
    if os.path.exists(OLD_SENT_FILE):
        print(f"\nFound '{os.path.basename(OLD_SENT_FILE)}'. Migrating sent recipients...")
        try:
            with open(OLD_SENT_FILE, 'r', encoding='utf-8') as f:
                recipients = [line.strip().lower() for line in f if line.strip()]
            
            if recipients:
                # Use INSERT OR IGNORE to prevent errors on duplicates
                cursor.executemany("INSERT OR IGNORE INTO sent_log (recipient_email) VALUES (?)", [(r,) for r in recipients])
                conn.commit()
                print(f"{GREEN}Successfully migrated {cursor.rowcount} new sent recipients.{RESET}")
                migrated_count += cursor.rowcount
            else:
                print(f"{YELLOW}File is empty. Nothing to migrate.{RESET}")
        except Exception as e:
            print(f"{RED}Error migrating sent recipients: {e}{RESET}")
    
    # 2. Migrate smtp_state.json and smtp_usage.json
    state_data = {}
    if os.path.exists(OLD_STATE_FILE):
        print(f"\nFound '{os.path.basename(OLD_STATE_FILE)}'. Migrating SMTP failure states...")
        try:
            with open(OLD_STATE_FILE, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
        except Exception as e:
            print(f"{RED}Error reading SMTP state file: {e}{RESET}")

    if os.path.exists(OLD_USAGE_FILE):
        print(f"\nFound '{os.path.basename(OLD_USAGE_FILE)}'. Migrating SMTP usage counts...")
        try:
            with open(OLD_USAGE_FILE, 'r', encoding='utf-8') as f:
                usage_data = json.load(f)
                # Merge usage counts into state data
                for key, count in usage_data.items():
                    if key in state_data:
                        state_data[key]['sent_count'] = count
                    else:
                        state_data[key] = {'sent_count': count}
        except Exception as e:
            print(f"{RED}Error reading SMTP usage file: {e}{RESET}")

    if state_data:
        print("\nUpdating database with combined SMTP state...")
        for smtp_id, data in state_data.items():
            sent = data.get('sent_count', 0)
            failed = data.get('fail_count', 0)
            disabled = data.get('disabled_until', 0)
            cursor.execute("""
                INSERT INTO smtp_state (smtp_id, sent_count, fail_count, disabled_until) VALUES (?, ?, ?, ?)
                ON CONFLICT(smtp_id) DO UPDATE SET
                    sent_count = excluded.sent_count,
                    fail_count = excluded.fail_count,
                    disabled_until = excluded.disabled_until
            """, (smtp_id, sent, failed, disabled))
            migrated_count += 1
        conn.commit()
        print(f"{GREEN}Successfully migrated state for {len(state_data)} SMTP servers.{RESET}")

    conn.close()

    if migrated_count == 0:
        print(f"\n{YELLOW}No old state files found or files were empty. Nothing to migrate.{RESET}")
    else:
        print(f"\n{GREEN}Migration complete!{RESET}")

    input("\nPress Enter to return to the menu...")

if __name__ == "__main__":
    migrate_state_to_db()