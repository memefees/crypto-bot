import sqlite3
import threading
from datetime import datetime


class Database:
    def __init__(self, db_path: str = "crypto_accounts.db"):
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
                    twitter_username TEXT NOT NULL,
                    twitter_url TEXT NOT NULL,
                    wallet_address TEXT NOT NULL,
                    balance_eth REAL,
                    discovered_at TEXT NOT NULL,
                    UNIQUE(twitter_username, wallet_address)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wallet ON accounts(wallet_address)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_username ON accounts(twitter_username)")
            conn.commit()

    def add_account(self, twitter_username, twitter_url, wallet_address, balance_eth):
        with self._lock:
            try:
                with self._get_conn() as conn:
                    conn.execute("""
                        INSERT INTO accounts
                            (twitter_username, twitter_url, wallet_address, balance_eth, discovered_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        twitter_username,
                        twitter_url,
                        wallet_address.lower(),
                        balance_eth,
                        datetime.utcnow().isoformat()
                    ))
                    conn.commit()
                    return True
            except sqlite3.IntegrityError:
                with self._get_conn() as conn:
                    conn.execute("""
                        UPDATE accounts SET balance_eth = ?
                        WHERE twitter_username = ? AND wallet_address = ?
                    """, (balance_eth, twitter_username, wallet_address.lower()))
                    conn.commit()
                return False

    def get_accounts(self, limit=50):
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT twitter_username, twitter_url, wallet_address, balance_eth, discovered_at
                FROM accounts
                ORDER BY discovered_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self):
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(DISTINCT twitter_username) AS unique_accounts,
                    COUNT(DISTINCT wallet_address)   AS unique_wallets,
                    COUNT(*)                         AS total_records,
                    COALESCE(SUM(balance_eth), 0)    AS total_balance
                FROM accounts
            """).fetchone()
        return dict(row)
