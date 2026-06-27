import sqlite3
from datetime import datetime

DB_NAME = "records.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            content TEXT,
            amount REAL,
            timestamp DATETIME
        )
    """)
    conn.commit()
    conn.close()

def save_record(user_id, category, content, amount=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO records (user_id, category, content, amount, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, category, content, amount, datetime.now()))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
