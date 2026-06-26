import sqlite3
from datetime import datetime

DB_NAME = "records.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            category TEXT,
            content TEXT,
            amount REAL
        )
    ''')
    conn.commit()
    conn.close()

def add_record(user_id, category, content, amount=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO records (user_id, category, content, amount)
        VALUES (?, ?, ?, ?)
    ''', (user_id, category, content, amount))
    conn.commit()
    conn.close()

def get_recent_records(user_id, limit=10):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT category, content, amount, timestamp
        FROM records
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
