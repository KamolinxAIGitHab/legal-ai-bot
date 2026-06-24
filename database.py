import sqlite3
from datetime import datetime

DB_NAME = "assistant.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            entry_type TEXT,
            raw_text TEXT,
            amount REAL,
            currency TEXT,
            category TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_entry(user_id, entry_type, raw_text, amount=None, currency=None, category=None, content=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO entries (user_id, entry_type, raw_text, amount, currency, category, content)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, entry_type, raw_text, amount, currency, category, content))
    conn.commit()
    conn.close()

def get_entries(user_id, limit=10):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT entry_type, amount, currency, content, created_at
        FROM entries WHERE user_id = ?
        ORDER BY created_at DESC LIMIT ?
    ''', (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_stats(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT entry_type, COUNT(*), SUM(amount), currency
        FROM entries WHERE user_id = ?
        GROUP BY entry_type, currency
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
