import sqlite3
import json
from datetime import datetime

DB_NAME = "logs.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            category TEXT,
            raw_text TEXT,
            structured_data TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_log(user_id, category, raw_text, structured_data):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO logs (user_id, category, raw_text, structured_data)
        VALUES (?, ?, ?, ?)
    """, (user_id, category, raw_text, json.dumps(structured_data, ensure_ascii=False)))
    conn.commit()
    conn.close()

def get_recent_logs(user_id, limit=10):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM logs WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_stats(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category, COUNT(*) FROM logs WHERE user_id = ? GROUP BY category
    """, (user_id,))
    stats = cursor.fetchall()
    conn.close()
    return stats

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
