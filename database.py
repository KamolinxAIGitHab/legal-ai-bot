import sqlite3
from datetime import datetime

DB_NAME = "records.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            category TEXT,
            content TEXT,
            amount REAL
        )
    """)
    conn.commit()
    conn.close()

def add_record(user_id, category, content, amount=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO records (user_id, category, content, amount)
        VALUES (?, ?, ?, ?)
    """, (user_id, category, content, amount))
    conn.commit()
    conn.close()

def get_recent_records(user_id, days=1):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category, content, amount, timestamp
        FROM records
        WHERE user_id = ? AND timestamp >= datetime('now', '-' || ? || ' day')
        ORDER BY timestamp DESC
    """, (user_id, days))
    records = cursor.fetchall()
    conn.close()
    return records

def get_expenses_total(user_id, days=1):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT SUM(amount)
        FROM records
        WHERE user_id = ? AND category = 'expense' AND timestamp >= datetime('now', '-' || ? || ' day')
    """, (user_id, days))
    total = cursor.fetchone()[0]
    conn.close()
    return total or 0.0

def get_tasks(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT content, timestamp
        FROM records
        WHERE user_id = ? AND category = 'task'
        ORDER BY timestamp ASC
    """, (user_id,))
    tasks = cursor.fetchall()
    conn.close()
    return tasks
