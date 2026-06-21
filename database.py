import sqlite3
import threading
from datetime import datetime


class Database:
    def __init__(self, db_path="foundation_accounts.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    foundation_url TEXT,
                    wallet_address TEXT NOT NULL,
                    balance_eth REAL,
                    twitter TEXT,
                    instagram TEXT,
                    website TEXT,
                    discovered_at TEXT,
                    UNIQUE(wallet_address)
                )
            """)
            conn.commit()

    def add_account(self, username, foundation_url, wallet_address,
                    balance_eth, twitter="", instagram="", website=""):
        with self._lock:
            try:
                with self._get_conn() as conn:
                    conn.execute("""
                        INSERT INTO accounts
                            (username, foundation_url, wallet_address, balance_eth,
                             twitter, instagram, website, discovered_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (username, foundation_url, wallet_address.lower(),
                          balance_eth, twitter, instagram, website,
                          datetime.utcnow().isoformat()))
                    conn.commit()
                    return True
            except sqlite3.IntegrityError:
                with self._get_conn() as conn:
                    conn.execute("""
                        UPDATE accounts SET balance_eth=?, twitter=?, instagram=?, website=?
                        WHERE wallet_address=?
                    """, (balance_eth, twitter, instagram, website, wallet_address.lower()))
                    conn.commit()
                return False

    def get_accounts(self, limit=50):
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM accounts ORDER BY discovered_at DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_top_by_balance(self, limit=20):
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM accounts
                WHERE balance_eth IS NOT NULL
                ORDER BY balance_eth DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self):
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(DISTINCT wallet_address) AS unique_accounts,
                    COUNT(DISTINCT wallet_address) AS unique_wallets,
                    COALESCE(SUM(balance_eth), 0) AS total_balance,
                    COUNT(CASE WHEN twitter != '' THEN 1 END) AS with_twitter,
                    COUNT(CASE WHEN instagram != '' THEN 1 END) AS with_instagram
                FROM accounts
            """).fetchone()
        return dict(row)
