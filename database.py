import sqlite3
import os

DB_FILE = os.path.join(os.path.dirname(__file__), "transactions.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (user_id TEXT, product TEXT, txid TEXT PRIMARY KEY, currency TEXT, status TEXT)''')
    conn.commit()
    conn.close()

def save_transaction(user_id, product, txid, currency, status="pending"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO transactions (user_id, product, txid, currency, status) VALUES (?, ?, ?, ?, ?)",
              (user_id, product, txid, currency, status))
    conn.commit()
    conn.close()

def update_transaction_status(txid, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE transactions SET status = ? WHERE txid = ?", (status, txid))
    conn.commit()
    conn.close()

def get_transaction(txid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id, product, txid, currency, status FROM transactions WHERE txid = ?", (txid,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"user_id": row[0], "product": row[1], "txid": row[2], "currency": row[3], "status": row[4]}
    return None

init_db()