import sqlite3
from datetime import datetime
from config import DB_FILE


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._init_tables()

    def _init_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_promocodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                promo_code TEXT NOT NULL,
                issued_at TEXT NOT NULL
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS help_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                answered BOOLEAN DEFAULT 0
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_chats (
                user_id INTEGER PRIMARY KEY,
                admin_id INTEGER NOT NULL,
                started_at TEXT NOT NULL
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)
        self.conn.commit()
        # Миграция из старой таблицы users, если есть
        self._migrate_old_users()

    def _migrate_old_users(self):
        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        if self.cursor.fetchone():
            self.cursor.execute("SELECT COUNT(*) FROM users")
            if self.cursor.fetchone()[0] > 0:
                self.cursor.execute("""
                    INSERT INTO user_promocodes (user_id, promo_code, issued_at)
                    SELECT user_id, promo_code, issued_at FROM users
                """)
                self.conn.commit()
            self.cursor.execute("DROP TABLE users")

    # Методы для работы с промокодами
    def user_already_received(self, user_id):
        self.cursor.execute(
            "SELECT 1 FROM user_promocodes WHERE user_id = ? LIMIT 1", (user_id,)
        )
        return self.cursor.fetchone() is not None

    def save_promocode(self, user_id, promo_code):
        issued_at = datetime.now().isoformat()
        self.cursor.execute(
            "INSERT INTO user_promocodes (user_id, promo_code, issued_at) VALUES (?, ?, ?)",
            (user_id, promo_code, issued_at),
        )
        self.conn.commit()

    def get_user_promocodes(self, user_id):
        self.cursor.execute(
            "SELECT promo_code, issued_at FROM user_promocodes WHERE user_id = ? ORDER BY issued_at DESC",
            (user_id,),
        )
        return self.cursor.fetchall()

    def get_last_promocode(self, user_id):
        self.cursor.execute(
            "SELECT promo_code, issued_at FROM user_promocodes WHERE user_id = ? ORDER BY issued_at DESC LIMIT 1",
            (user_id,),
        )
        return self.cursor.fetchone()

    # Методы для чатов и заявок
    def start_chat_session(self, user_id, admin_id=0):
        started_at = datetime.now().isoformat()
        self.cursor.execute(
            "INSERT OR REPLACE INTO active_chats (user_id, admin_id, started_at) VALUES (?, ?, ?)",
            (user_id, admin_id, started_at),
        )
        self.conn.commit()

    def set_chat_admin(self, user_id, admin_id):
        self.cursor.execute(
            "UPDATE active_chats SET admin_id = ? WHERE user_id = ?",
            (admin_id, user_id),
        )
        self.conn.commit()

    def end_chat_session(self, user_id):
        self.cursor.execute("DELETE FROM active_chats WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def is_in_chat(self, user_id):
        self.cursor.execute("SELECT 1 FROM active_chats WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    def get_chat_admin(self, user_id):
        self.cursor.execute(
            "SELECT admin_id FROM active_chats WHERE user_id = ?", (user_id,)
        )
        row = self.cursor.fetchone()
        return row[0] if row else 0

    def get_active_chats(self):
        self.cursor.execute(
            "SELECT user_id, admin_id, started_at FROM active_chats ORDER BY started_at DESC"
        )
        return self.cursor.fetchall()

    def save_help_request(self, user_id, message_text):
        created_at = datetime.now().isoformat()
        self.cursor.execute(
            "INSERT INTO help_requests (user_id, message, created_at) VALUES (?, ?, ?)",
            (user_id, message_text, created_at),
        )
        self.conn.commit()

    def mark_request_answered(self, user_id):
        self.cursor.execute(
            "UPDATE help_requests SET answered = 1 WHERE user_id = ? AND answered = 0",
            (user_id,),
        )
        self.conn.commit()

    # Администраторы
    def add_admin(self, user_id):
        self.cursor.execute(
            "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,)
        )
        self.conn.commit()

    def remove_admin(self, user_id):
        self.cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def get_all_admins(self):
        self.cursor.execute("SELECT user_id FROM admins")
        return [row[0] for row in self.cursor.fetchall()]

    def close(self):
        self.conn.close()
