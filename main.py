# -*- coding: utf-8 -*-

import atexit
from datetime import datetime
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import hashlib

from flask import Flask
from threading import Thread

import psutil
import telebot
from telebot import types


# ============================================================
# CONFIGURATION
# ============================================================

TOKEN = os.environ.get("BOT_TOKEN", "8910223271:AAEGc6ZTC4qE6FkOBLL13Xj0QwtQyfCI7CU").strip()

OWNER_ID = int(os.environ.get("OWNER_ID", "8814363793"))
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8814363793"))

YOUR_USERNAME = os.environ.get(
    "YOUR_USERNAME",
    "@Bmjakir69"
)

UPDATE_CHANNEL = os.environ.get(
    "UPDATE_CHANNEL",
    "https://t.me/JAKIRLABS"
)

UPLOAD_LOG_CHANNEL = os.environ.get(
    "UPLOAD_LOG_CHANNEL",
    "@ajajakkalqkqkqjajakl"
)


if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is missing. "
        "Set your Telegram bot token before starting the bot."
    )


# ============================================================
# FLASK KEEP ALIVE
# ============================================================

app = Flask("hosting_bot")


@app.route("/")
def home():
    return "Hosting Manager is running."


def run_flask():
    port = int(os.environ.get("PORT", "8080"))

    app.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False
    )


def keep_alive():
    thread = Thread(
        target=run_flask,
        daemon=True
    )

    thread.start()

    print("Flask Keep-Alive server started.")


# ============================================================
# DIRECTORIES
# ============================================================

BASE_DIR = os.path.abspath(
    os.path.dirname(__file__)
)

UPLOAD_BOTS_DIR = os.path.join(
    BASE_DIR,
    "upload_bots"
)

IROTECH_DIR = os.path.join(
    BASE_DIR,
    "inf"
)

DATABASE_PATH = os.path.join(
    IROTECH_DIR,
    "bot_data.db"
)


os.makedirs(
    UPLOAD_BOTS_DIR,
    exist_ok=True
)

os.makedirs(
    IROTECH_DIR,
    exist_ok=True
)


# ============================================================
# TELEGRAM BOT
# ============================================================

bot = telebot.TeleBot(
    TOKEN,
    parse_mode=None
)


# ============================================================
# GLOBAL DATA
# ============================================================

bot_scripts = {}

user_files = {}

active_users = set()

admin_ids = {
    OWNER_ID,
    ADMIN_ID
}

blocked_users = set()

bot_locked = False

DB_LOCK = threading.Lock()


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    )
)

logger = logging.getLogger(
    "HostingManager"
)


# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False,
        timeout=30
    )

    return conn


def init_db():

    logger.info(
        "Initializing database: %s",
        DATABASE_PATH
    )

    with DB_LOCK:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_files (
                user_id INTEGER,
                file_name TEXT,
                file_type TEXT,
                PRIMARY KEY (user_id, file_name)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_users (
                user_id INTEGER PRIMARY KEY
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS force_channels (
                channel_id TEXT PRIMARY KEY,
                channel_url TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                user_id INTEGER,
                referred_user_id INTEGER PRIMARY KEY
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_limits (
                user_id INTEGER PRIMARY KEY,
                max_limit INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id INTEGER PRIMARY KEY
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # ----------------------------------------------------
        # PENDING APPROVAL TABLE
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_data BLOB NOT NULL,
                user_name TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pending_status
            ON pending_files(status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pending_user
            ON pending_files(user_id)
        """)

        # ----------------------------------------------------
        # APPROVAL HISTORY
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approval_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pending_id INTEGER,
                user_id INTEGER,
                file_name TEXT,
                action TEXT,
                admin_id INTEGER,
                created_at TEXT
            )
        """)

        cursor.execute(
            """
            INSERT OR IGNORE INTO admins (user_id)
            VALUES (?)
            """,
            (OWNER_ID,)
        )

        if ADMIN_ID != OWNER_ID:

            cursor.execute(
                """
                INSERT OR IGNORE INTO admins (user_id)
                VALUES (?)
                """,
                (ADMIN_ID,)
            )

        conn.commit()

        conn.close()

    logger.info(
        "Database initialized successfully."
    )


# ============================================================
# LOAD DATABASE DATA
# ============================================================

def load_data():

    logger.info(
        "Loading data from database..."
    )

    try:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT user_id, file_name, file_type
            FROM user_files
            """
        )

        for row in cursor.fetchall():

            user_id, file_name, file_type = row

            if user_id not in user_files:

                user_files[user_id] = []

            if not any(
                item[0] == file_name
                for item in user_files[user_id]
            ):

                user_files[user_id].append(
                    (
                        file_name,
                        file_type
                    )
                )

        cursor.execute(
            """
            SELECT user_id
            FROM active_users
            """
        )

        for row in cursor.fetchall():

            active_users.add(
                row[0]
            )

        cursor.execute(
            """
            SELECT user_id
            FROM admins
            """
        )

        for row in cursor.fetchall():

            admin_ids.add(
                row[0]
            )

        cursor.execute(
            """
            SELECT user_id
            FROM blocked_users
            """
        )

        for row in cursor.fetchall():

            blocked_users.add(
                row[0]
            )

        conn.close()

        logger.info(
            "Database data loaded."
        )

    except Exception as error:

        logger.error(
            "Data loading error: %s",
            error,
            exc_info=True
        )


init_db()

load_data()


# ============================================================
# SETTINGS
# ============================================================

def get_setting(
    key,
    default=""
):

    try:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT value
            FROM settings
            WHERE key=?
            """,
            (key,)
        )

        row = cursor.fetchone()

        conn.close()

        if row:

            return row[0]

        return default

    except Exception:

        return default


def set_setting(
    key,
    value
):

    with DB_LOCK:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO settings
            (key, value)
            VALUES (?, ?)
            """,
            (
                key,
                value
            )
        )

        conn.commit()

        conn.close()


# ============================================================
# USER FILE LIMIT
# ============================================================

def get_referral_count(
    user_id
):

    try:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM referrals
            WHERE user_id=?
            """,
            (user_id,)
        )

        result = cursor.fetchone()

        conn.close()

        return int(
            result[0]
        )

    except Exception:

        return 0


def get_user_file_limit(
    user_id
):

    if (
        user_id == OWNER_ID
        or user_id in admin_ids
    ):

        return float("inf")

    try:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT max_limit
            FROM custom_limits
            WHERE user_id=?
            """,
            (user_id,)
        )

        row = cursor.fetchone()

        conn.close()

        if row is not None:

            return max(
                0,
                int(row[0])
            )

    except Exception:

        pass

    referral_count = get_referral_count(
        user_id
    )

    bonus = min(
        2,
        referral_count
    )

    return 1 + bonus


def get_user_file_count(
    user_id
):

    return len(
        user_files.get(
            user_id,
            []
        )
    )


# ============================================================
# FORCE SUBSCRIPTION
# ============================================================

def get_force_channels():

    try:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT channel_id, channel_url
            FROM force_channels
            """
        )

        channels = cursor.fetchall()

        conn.close()

        return channels

    except Exception:

        return []


def check_force_sub(
    user_id
):

    if user_id in admin_ids:

        return []

    channels = get_force_channels()

    not_joined = []

    for channel_id, channel_url in channels:

        try:

            target = str(
                channel_id
            ).strip()

            if target.lstrip("-").isdigit():

                target = int(
                    target
                )

            member = bot.get_chat_member(
                target,
                user_id
            )

            if member.status in (
                "left",
                "kicked",
                "restricted"
            ):

                not_joined.append(
                    (
                        channel_id,
                        channel_url
                    )
                )

        except Exception as error:

            logger.warning(
                "Force-sub check failed for %s: %s",
                channel_id,
                error
            )

            # Do not block users if Telegram
            # cannot check the channel.
            continue

    return not_joined


# ============================================================
# SECURITY SCANNER
# ============================================================

MALWARE_SIGNATURES = [
    b"MZ",
    b"\x7fELF",
    b"\xfe\xed\xfa",
    b"\xce\xfa\xed\xfe",
    b"Rar!",
]


DANGEROUS_KEYWORDS = [

    b"ransomware",
    b"trojan",
    b"virus",
    b"malware",
    b"backdoor",
    b"botnet",
    b"keylogger",

    b"../",
    b"..\\",

    b"bot_data.db",

    b"shutil.rmtree",

    b"pickle.loads",

    b"ctypes",

    b"fork()",

    b"child_process",
    b"require('child_process')"
]


def is_suspicious_file(
    file_content,
    file_name
):

    lower_name = (
        file_name.lower()
    )

    suspicious_extensions = [
        ".exe",
        ".dll",
        ".bat",
        ".cmd",
        ".scr",
        ".com",
        ".pif",
        ".msi",
        ".jar",
        ".apk",
        ".sh"
    ]

    for ext in suspicious_extensions:

        if lower_name.endswith(ext):

            return (
                True,
                "Suspicious file extension"
            )

    for signature in MALWARE_SIGNATURES:

        if file_content.startswith(
            signature
        ):

            return (
                True,
                "Executable/binary signature detected"
            )

    try:

        sample = file_content.decode(
            "utf-8",
            errors="ignore"
        ).lower()

        for keyword in DANGEROUS_KEYWORDS:

            text = keyword.decode(
                "utf-8",
                errors="ignore"
            )

            if text in sample:

                return (
                    True,
                    f"Dangerous keyword detected: {text}"
                )

    except Exception:

        pass

    return (
        False,
        "Safe"
    )


# ============================================================
# USER FOLDER
# ============================================================

def get_user_folder(
    user_id
):

    folder = os.path.join(
        UPLOAD_BOTS_DIR,
        str(int(user_id))
    )

    os.makedirs(
        folder,
        exist_ok=True
    )

    return folder


# ============================================================
# PROCESS MANAGEMENT
# ============================================================

def kill_process_tree(
    process_info
):

    if not process_info:

        return

    try:

        log_file = process_info.get(
            "log_file"
        )

        if log_file:

            try:

                if not log_file.closed:

                    log_file.close()

            except Exception:

                pass

        process = process_info.get(
            "process"
        )

        if not process:

            return

        pid = getattr(
            process,
            "pid",
            None
        )

        if pid:

            try:

                parent = psutil.Process(
                    pid
                )

                children = parent.children(
                    recursive=True
                )

                for child in children:

                    try:
                        child.kill()

                    except Exception:
                        pass

                try:
                    parent.kill()

                except Exception:
                    pass

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied
            ):

                pass

        try:
            process.terminate()

        except Exception:
            pass

        try:
            process.kill()

        except Exception:
            pass

    except Exception as error:

        logger.error(
            "Process kill error: %s",
            error
        )


def force_kill_user_bot(
    owner_id,
    file_name
):

    key = (
        f"{owner_id}_{file_name}"
    )

    info = bot_scripts.get(
        key
    )

    if info:

        kill_process_tree(
            info
        )

        bot_scripts.pop(
            key,
            None
        )

    user_folder = get_user_folder(
        owner_id
    )

    try:

        for proc in psutil.process_iter(
            ["pid", "cwd", "cmdline"]
        ):

            try:

                cwd = proc.info.get(
                    "cwd"
                )

                if not cwd:

                    continue

                if user_folder not in cwd:

                    continue

                cmdline = (
                    proc.info.get(
                        "cmdline"
                    )
                    or []
                )

                if not any(
                    file_name in str(arg)
                    for arg in cmdline
                ):

                    continue

                for child in proc.children(
                    recursive=True
                ):

                    try:
                        child.kill()

                    except Exception:
                        pass

                try:
                    proc.kill()

                except Exception:
                    pass

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess
            ):

                continue

    except Exception as error:

        logger.error(
            "OS process scan error: %s",
            error
        )


def is_bot_running(
    owner_id,
    file_name
):

    key = (
        f"{owner_id}_{file_name}"
    )

    info = bot_scripts.get(
        key
    )

    if info:

        process = info.get(
            "process"
        )

        if process:

            try:

                proc = psutil.Process(
                    process.pid
                )

                if (
                    proc.is_running()
                    and proc.status()
                    != psutil.STATUS_ZOMBIE
                ):

                    return True

            except Exception:

                pass

    return False


# ============================================================
# PENDING APPROVAL FUNCTIONS
# ============================================================

def add_pending_file(
    user_id,
    file_name,
    file_type,
    file_data,
    user_name
):

    with DB_LOCK:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO pending_files
            (
                user_id,
                file_name,
                file_type,
                file_data,
                user_name,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                file_name,
                file_type,
                sqlite3.Binary(
                    file_data
                ),
                user_name,
                "pending",
                datetime.now().isoformat()
            )
        )

        pending_id = cursor.lastrowid

        conn.commit()

        conn.close()

    return pending_id


def get_pending_file(
    pending_id
):

    try:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                id,
                user_id,
                file_name,
                file_type,
                file_data,
                user_name,
                status,
                created_at
            FROM pending_files
            WHERE id=?
            """,
            (pending_id,)
        )

        row = cursor.fetchone()

        conn.close()

        return row

    except Exception as error:

        logger.error(
            "Pending file read error: %s",
            error
        )

        return None


def get_pending_files():

    try:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                id,
                user_id,
                file_name,
                file_type,
                user_name,
                created_at
            FROM pending_files
            WHERE status='pending'
            ORDER BY id ASC
            """
        )

        rows = cursor.fetchall()

        conn.close()

        return rows

    except Exception:

        return []


def get_user_pending_count(
    user_id
):

    try:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM pending_files
            WHERE user_id=?
            AND status='pending'
            """,
            (user_id,)
        )

        result = cursor.fetchone()

        conn.close()

        return int(
            result[0]
        )

    except Exception:

        return 0


def update_pending_status(
    pending_id,
    status
):

    with DB_LOCK:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE pending_files
            SET status=?
            WHERE id=?
            AND status='pending'
            """,
            (
                status,
                pending_id
            )
        )

        changed = (
            cursor.rowcount > 0
        )

        conn.commit()

        conn.close()

    return changed


# ============================================================
# USER FILE DATABASE
# ============================================================

def save_user_file(
    user_id,
    file_name,
    file_type
):

    with DB_LOCK:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO user_files
            (
                user_id,
                file_name,
                file_type
            )
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                file_name,
                file_type
            )
        )

        conn.commit()

        conn.close()

    if user_id not in user_files:

        user_files[user_id] = []

    user_files[user_id] = [
        item
        for item in user_files[user_id]
        if item[0] != file_name
    ]

    user_files[user_id].append(
        (
            file_name,
            file_type
        )
    )


def remove_user_file_db(
    user_id,
    file_name
):

    with DB_LOCK:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM user_files
            WHERE user_id=?
            AND file_name=?
            """,
            (
                user_id,
                file_name
            )
        )

        conn.commit()

        conn.close()

    if user_id in user_files:

        user_files[user_id] = [
            item
            for item in user_files[user_id]
            if item[0] != file_name
        ]


def add_active_user(
    user_id
):

    active_users.add(
        user_id
    )

    with DB_LOCK:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR IGNORE INTO active_users
            (user_id)
            VALUES (?)
            """,
            (user_id,)
        )

        conn.commit()

        conn.close()


# ============================================================
# APPROVAL LOG
# ============================================================

def add_approval_log(
    pending_id,
    user_id,
    file_name,
    action,
    admin_id
):

    try:

        with DB_LOCK:

            conn = get_db()

            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO approval_logs
                (
                    pending_id,
                    user_id,
                    file_name,
                    action,
                    admin_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    pending_id,
                    user_id,
                    file_name,
                    action,
                    admin_id,
                    datetime.now().isoformat()
                )
            )

            conn.commit()

            conn.close()

    except Exception as error:

        logger.error(
            "Approval log error: %s",
            error
        )


# ============================================================
# NEXT PART
# ============================================================

# এই Part-এর পরের অংশে থাকবে:
#
# 1. Admin approval
# 2. Approve / Reject buttons
# 3. Upload handler
# 4. Start / Stop
# 5. Manage Files
# 6. Referral
# 7. Force Join
# 8. Admin Panel
# 9. Broadcast
# 10. Auto Stop
# 11. Main menu
# 12. Polling