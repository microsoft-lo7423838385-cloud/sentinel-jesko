import sqlite3
import os

PROJECT_ROOT = os.path.dirname(__file__)
DB_PATH = os.path.join(PROJECT_ROOT, 'logs', 'state.db')

def initialize_database():
    """
    Initializes the SQLite database and creates the necessary tables if they don't exist.
    This is the new "brain" for storing the application's state.
    """
    print("\n--- Initializing State Database ---")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Table for SMTP state (replaces smtp_state.json and smtp_usage.json)
        # smtp_id is a unique key like 'host:port:email'
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS smtp_state (
            smtp_id TEXT PRIMARY KEY,
            sent_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            disabled_until REAL DEFAULT 0,
            total_sent INTEGER DEFAULT 0,
            domain_stats TEXT,
            average_latency REAL DEFAULT 0.0,
            reputation_events TEXT
        )
        ''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS sent_log (
    recipient_email TEXT PRIMARY KEY
)''')

        # --- "Jesko" Upgrade: Add columns for advanced stats to existing DBs ---
        # We try to add each column; if it exists, SQLite throws an OperationalError which we ignore.
        columns_to_ensure = [
            ("total_sent", "INTEGER DEFAULT 0"),
            ("domain_stats", "TEXT"),
            ("average_latency", "REAL DEFAULT 0.0"),
            ("reputation_events", "TEXT")
        ]
        
        for col_name, col_def in columns_to_ensure:
            try:
                cursor.execute(f"ALTER TABLE smtp_state ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass # Column already exists
        conn.commit()
        conn.close()
        print("Database initialized successfully at 'logs/state.db'.")
    except Exception as e:
        print(f"ERROR: Could not initialize database: {e}")

if __name__ == "__main__":
    initialize_database()