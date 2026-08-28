# -*- coding: utf-8 -*-

import atexit
from datetime import datetime, timedelta
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
# FLASK KEEP ALIVE
# ============================================================

app = Flask("")


@app.route("/")
def home():
    return "I'm Mukesh File Host"


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive server started.")


# ============================================================
# CONFIGURATION
# ============================================================

# IMPORTANT:
# Set your new Telegram bot token in environment variable BOT_TOKEN.
# Example:
# BOT_TOKEN=YOUR_NEW_TOKEN

TOKEN = os.environ.get("BOT_TOKEN", "8910223271:AAEGc6ZTC4qE6FkOBLL13Xj0QwtQyfCI7CU")

OWNER_ID = 8814363793
ADMIN_ID = 8814363793

YOUR_USERNAME = "@Bmjakir69"

UPDATE_CHANNEL = "https://t.me/JAKIRLABS"

UPLOAD_LOG_CHANNEL = "@ajajakkalqkqkqjajakl"


if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is not set. "
        "Please add your NEW Telegram bot token."
    )


# ============================================================
# FOLDER SETUP
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

# Pending files are stored here BEFORE admin approval.
PENDING_DIR = os.path.join(
    BASE_DIR,
    "pending_uploads"
)


os.makedirs(
    UPLOAD_BOTS_DIR,
    exist_ok=True
)

os.makedirs(
    IROTECH_DIR,
    exist_ok=True
)

os.makedirs(
    PENDING_DIR,
    exist_ok=True
)


# ============================================================
# TELEGRAM BOT
# ============================================================

bot = telebot.TeleBot(TOKEN)


# ============================================================
# GLOBAL DATA
# ============================================================

bot_scripts = {}

user_files = {}

active_users = set()

admin_ids = {
    ADMIN_ID,
    OWNER_ID
}

blocked_users = set()

bot_locked = False

DB_LOCK = threading.Lock()

PENDING_LOCK = threading.Lock()


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

logger = logging.getLogger(__name__)


# ============================================================
# COMMAND BUTTON LAYOUTS
# ============================================================

COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    [
        "✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨",
        "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹"
    ],
    [
        "🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲",
        "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"
    ],
    [
        "🎁 𝗥𝗲𝗳𝗲𝗿 & 𝗘𝗮𝗿𝗻",
        "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴"
    ],
    [
        "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀",
        "💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹 𝗖𝗺𝗱"
    ],
    [
        "👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿"
    ],
]


ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    [
        "✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨",
        "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹"
    ],
    [
        "🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲",
        "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"
    ],
    [
        "🎁 𝗥𝗲𝗳𝗲𝗿 & 𝗘𝗮𝗿𝗻",
        "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹"
    ],
    [
        "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴",
        "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀"
    ],
    [
        "👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿"
    ],
]


# ============================================================
# DATABASE SETUP
# ============================================================

def init_db():

    logger.info(
        f"Initializing database at: {DATABASE_PATH}"
    )

    try:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        # Existing tables
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_files (
                user_id INTEGER,
                file_name TEXT,
                file_type TEXT,
                PRIMARY KEY (user_id, file_name)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS active_users (
                user_id INTEGER PRIMARY KEY
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS force_channels (
                channel_id TEXT PRIMARY KEY,
                channel_url TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                user_id INTEGER,
                referred_user_id INTEGER PRIMARY KEY
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS custom_limits (
                user_id INTEGER PRIMARY KEY,
                max_limit INTEGER
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id INTEGER PRIMARY KEY
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # ====================================================
        # NEW ADMIN APPROVAL TABLE
        # ====================================================

        c.execute("""
            CREATE TABLE IF NOT EXISTS pending_uploads (
                request_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                temp_path TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                reviewed_by INTEGER DEFAULT NULL
            )
        """)

        # Add owner/admin
        c.execute(
            "INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
            (OWNER_ID,)
        )

        if ADMIN_ID != OWNER_ID:

            c.execute(
                "INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
                (ADMIN_ID,)
            )

        conn.commit()

        conn.close()

        logger.info(
            "Database initialized successfully."
        )

    except Exception as e:

        logger.error(
            f"Database initialization error: {e}",
            exc_info=True
        )


# ============================================================
# LOAD DATA
# ============================================================

def load_data():

    logger.info(
        "Loading data from database..."
    )

    try:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            "SELECT user_id, file_name, file_type FROM user_files"
        )

        for user_id, file_name, file_type in c.fetchall():

            if user_id not in user_files:

                user_files[user_id] = []

            user_files[user_id].append(
                (
                    file_name,
                    file_type
                )
            )

        c.execute(
            "SELECT user_id FROM active_users"
        )

        active_users.update(
            user_id
            for (user_id,) in c.fetchall()
        )

        c.execute(
            "SELECT user_id FROM admins"
        )

        admin_ids.update(
            user_id
            for (user_id,) in c.fetchall()
        )

        c.execute(
            "SELECT user_id FROM blocked_users"
        )

        blocked_users.update(
            user_id
            for (user_id,) in c.fetchall()
        )

        conn.close()

        logger.info(
            "Data loaded successfully."
        )

    except Exception as e:

        logger.error(
            f"Error loading data: {e}",
            exc_info=True
        )


init_db()
load_data()


# ============================================================
# SETTINGS HELPERS
# ============================================================

def get_setting(
    key,
    default=""
):

    try:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            "SELECT value FROM settings WHERE key=?",
            (key,)
        )

        row = c.fetchone()

        conn.close()

        return row[0] if row else default

    except:

        return default


def set_setting(
    key,
    value
):

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
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
# SECURITY BLOCK SYSTEM
# ============================================================

def block_and_alert_user(
    user_id,
    user_name,
    reason
):

    if user_id in admin_ids:
        return

    blocked_users.add(user_id)

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            """
            INSERT OR IGNORE INTO blocked_users
            (user_id)
            VALUES (?)
            """,
            (user_id,)
        )

        conn.commit()

        conn.close()

    alert_msg = (
        "🚨 **SECURITY ALERT: USER BLOCKED!** 🚨\n\n"
        f"👤 **Name:** {user_name}\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"❌ **Reason:** `{reason}`\n\n"
        "⚠️ *এই ইউজারকে সার্ভার হ্যাক বা "
        "ক্ষতিকর কোড আপলোডের কারণে ব্লক করা হয়েছে!*"
    )

    try:

        bot.send_message(
            OWNER_ID,
            alert_msg,
            parse_mode="Markdown"
        )

        bot.send_message(
            user_id,
            "🚫 **আপনাকে ক্ষতিকর কার্যকলাপের কারণে "
            "বট থেকে স্থায়ীভাবে ব্লক করা হয়েছে!**",
            protect_content=True
        )

    except:

        pass


# ============================================================
# LIMITS & REFERRAL
# ============================================================

def get_referral_count(
    user_id
):

    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )

    c = conn.cursor()

    c.execute(
        """
        SELECT COUNT(*)
        FROM referrals
        WHERE user_id=?
        """,
        (user_id,)
    )

    count = c.fetchone()[0]

    conn.close()

    return count


def get_user_file_limit(
    user_id
):

    if (
        user_id == OWNER_ID
        or user_id in admin_ids
    ):
        return float("inf")

    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )

    c = conn.cursor()

    c.execute(
        """
        SELECT max_limit
        FROM custom_limits
        WHERE user_id=?
        """,
        (user_id,)
    )

    row = c.fetchone()

    conn.close()

    if row is not None:
        return row[0]

    ref_count = get_referral_count(
        user_id
    )

    bonus = min(
        2,
        ref_count
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
# FORCE SUB
# ============================================================

def get_force_channels():

    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )

    c = conn.cursor()

    c.execute(
        """
        SELECT channel_id, channel_url
        FROM force_channels
        """
    )

    channels = c.fetchall()

    conn.close()

    return channels


def check_force_sub(
    user_id
):

    if user_id in admin_ids:
        return []

    channels = get_force_channels()

    not_joined = []

    for ch_id, ch_url in channels:

        try:

            chat_target = ch_id.strip()

            if chat_target.lstrip("-").isdigit():

                chat_target = int(
                    chat_target
                )

            member = bot.get_chat_member(
                chat_target,
                user_id
            )

            if member.status in [
                "left",
                "kicked",
                "restricted"
            ]:

                not_joined.append(
                    (
                        ch_id,
                        ch_url
                    )
                )

        except Exception as e:

            logger.warning(
                f"Force Sub error for "
                f"{user_id} in {ch_id}: {e}"
            )

    return not_joined


# ============================================================
# MALWARE / SECURITY CHECK
# ============================================================

MALWARE_SIGNATURES = [
    b"MZ",
    b"\x7fELF",
    b"\xfe\xed\xfa",
    b"\xce\xfa\xed\xfe",
    b"PK",
    b"Rar!"
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
    b"os.system",
    b"subprocess.call",
    b"subprocess.Popen",
    b"shutil.rmtree",
    b"socket.socket",
    b"urllib.request",
    b"requests.get",
    b"requests.post",
    b"eval(",
    b"exec(",
    b"__import__",
    b"pickle.loads",
    b"ctypes",
    b"fork()",
    b"while True:",
    b"while(1):",
    b"child_process",
    b"require('child_process')"
]


def is_suspicious_file(
    file_content,
    file_name
):

    file_lower = file_name.lower()

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

    if any(
        file_lower.endswith(ext)
        for ext in suspicious_extensions
    ):

        return (
            True,
            f"Suspicious file extension: {file_name}"
        )

    for signature in MALWARE_SIGNATURES:

        if file_content.startswith(signature):

            return (
                True,
                "Malware signature detected"
            )

    try:

        sample_text = (
            file_content
            .decode(
                "utf-8",
                errors="ignore"
            )
            .lower()
        )

        for keyword in DANGEROUS_KEYWORDS:

            if keyword.decode(
                "utf-8"
            ) in sample_text:

                return (
                    True,
                    "Security Violation: "
                    "Dangerous code/keyword detected -> "
                    f"{keyword.decode('utf-8')}"
                )

    except:

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

    user_folder = os.path.join(
        UPLOAD_BOTS_DIR,
        str(user_id)
    )

    os.makedirs(
        user_folder,
        exist_ok=True
    )

    return user_folder


# ============================================================
# PROCESS HELPERS
# ============================================================

def kill_process_tree(
    process_info
):

    try:

        if (
            "log_file" in process_info
            and not process_info["log_file"].closed
        ):

            try:
                process_info["log_file"].close()
            except:
                pass

        process = process_info.get(
            "process"
        )

        if process:

            if hasattr(
                process,
                "pid"
            ):

                try:

                    parent = psutil.Process(
                        process.pid
                    )

                    for child in parent.children(
                        recursive=True
                    ):

                        try:
                            child.kill()
                        except:
                            pass

                    try:
                        parent.kill()
                    except:
                        pass

                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied
                ):

                    pass

            try:
                process.terminate()
            except:
                pass

            try:
                process.kill()
            except:
                pass

    except Exception as e:

        logger.error(
            f"Error killing process tree: {e}"
        )


def force_kill_user_bot(
    owner_id,
    file_name
):

    skey = f"{owner_id}_{file_name}"

    if skey in bot_scripts:

        kill_process_tree(
            bot_scripts[skey]
        )

        try:
            del bot_scripts[skey]
        except:
            pass

    ufolder = get_user_folder(
        int(owner_id)
    )

    try:

        for proc in psutil.process_iter(
            [
                "pid",
                "cwd",
                "cmdline"
            ]
        ):

            try:

                proc_cwd = proc.info.get(
                    "cwd"
                )

                if (
                    proc_cwd
                    and ufolder in proc_cwd
                ):

                    cmd = (
                        proc.info.get(
                            "cmdline"
                        )
                        or []
                    )

                    if any(
                        file_name in str(arg)
                        for arg in cmd
                    ):

                        try:

                            for child in proc.children(
                                recursive=True
                            ):

                                try:
                                    child.kill()
                                except:
                                    pass

                        except:
                            pass

                        try:
                            proc.kill()
                        except:
                            pass

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess
            ):

                continue

    except Exception as e:

        logger.error(
            f"Force kill OS error: {e}"
        )


def is_bot_running(
    script_owner_id,
    file_name
):

    script_key = (
        f"{script_owner_id}_{file_name}"
    )

    script_info = bot_scripts.get(
        script_key
    )

    if (
        script_info
        and script_info.get("process")
    ):

        try:

            proc = psutil.Process(
                script_info["process"].pid
            )

            if (
                proc.is_running()
                and proc.status()
                != psutil.STATUS_ZOMBIE
            ):

                return True

        except:
            pass

    ufolder = get_user_folder(
        int(script_owner_id)
    )

    try:

        for proc in psutil.process_iter(
            [
                "cwd",
                "cmdline"
            ]
        ):

            try:

                proc_cwd = proc.info.get(
                    "cwd"
                )

                if (
                    proc_cwd
                    and ufolder in proc_cwd
                ):

                    cmd = (
                        proc.info.get(
                            "cmdline"
                        )
                        or []
                    )

                    if any(
                        file_name in str(arg)
                        for arg in cmd
                    ):

                        return True

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess
            ):

                pass

    except:

        pass

    return False


# ============================================================
# AUTO STOPPER
# ============================================================

def auto_stopper():

    while True:

        time.sleep(30)

        now = datetime.now()

        for key in list(
            bot_scripts.keys()
        ):

            script = bot_scripts.get(
                key
            )

            if not script:
                continue

            user_id = script[
                "script_owner_id"
            ]

            # Admin/Owner lifetime
            if (
                user_id in admin_ids
                or user_id == OWNER_ID
            ):

                continue

            elapsed_hours = (
                now
                - script["start_time"]
            ).total_seconds() / 3600

            # 11 hour warning
            if (
                elapsed_hours >= 11
                and not script.get(
                    "warned_11h",
                    False
                )
            ):

                script[
                    "warned_11h"
                ] = True

                try:

                    markup = (
                        types.InlineKeyboardMarkup()
                    )

                    markup.add(
                        types.InlineKeyboardButton(
                            "⏳ Extend Time (+12 Hours)",
                            callback_data=(
                                f"extend_{user_id}_"
                                f"{script['file_name']}"
                            )
                        )
                    )

                    warn_msg = (
                        "⚠️ **বোট হোস্টিং সতর্কবার্তা!**\n\n"
                        f"📄 **File:** "
                        f"`{script['file_name']}`\n"
                        "⏱️ আপনার বোটটি চলার সময় "
                        "**১১ ঘণ্টা** পার হয়ে গেছে!\n"
                        "আর ১ ঘণ্টা পর বোটটি "
                        "স্বয়ংক্রিয়ভাবে বন্ধ হয়ে যাবে।\n\n"
                        "👉 সময় আরও ১২ ঘণ্টা বাড়াতে "
                        "নিচের **Extend Time** বাটনে ক্লিক করুন।"
                    )

                    bot.send_message(
                        user_id,
                        warn_msg,
                        reply_markup=markup,
                        parse_mode="Markdown",
                        protect_content=True
                    )

                except Exception as e:

                    logger.error(
                        f"Error sending warning: {e}"
                    )

            # 12 hour stop
            if elapsed_hours >= 12:

                force_kill_user_bot(
                    user_id,
                    script["file_name"]
                )

                try:

                    bot.send_message(
                        user_id,
                        (
                            "⏱️ **আপনার ১২ ঘণ্টার "
                            "ফ্রি লিমিট শেষ!**\n"
                            f"📄 `{script['file_name']}` "
                            "বোটটি স্বয়ংক্রিয়ভাবে "
                            "বন্ধ করা হয়েছে।\n"
                            "প্রয়োজনে আবার "
                            "`📁 Manage Files` থেকে "
                            "স্টার্ট করতে পারবেন।"
                        ),
                        protect_content=True
                    )

                except:
                    pass


# ============================================================
# TELEGRAM MODULE MAP
# ============================================================

TELEGRAM_MODULES = {
    "telebot": "pyTelegramBotAPI",
    "telegram": "python-telegram-bot",
    "aiogram": "aiogram",
    "pyrogram": "pyrogram",
    "telethon": "telethon",
    "flask": "Flask",
    "psutil": "psutil"
}


# ============================================================
# ERROR MONITOR
# ============================================================

def monitor_and_guide_error(
    process,
    log_file_path,
    script_owner_id,
    file_name,
    message_obj_for_reply
):

    time.sleep(3)

    if process.poll() is not None:

        try:

            with open(
                log_file_path,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:

                log_content = f.read()

            match_py = re.search(
                r"(?:ModuleNotFoundError|ImportError): "
                r"No module named '(.+?)'",
                log_content
            )

            match_js = re.search(
                r"Cannot find module '(.+?)'",
                log_content
            )

            missing_module = None

            if match_py:

                missing_module = (
                    match_py.group(1)
                    .split(".")[0]
                    .strip("'\"")
                )

            elif match_js:

                missing_module = (
                    match_js.group(1)
                    .split("/")[0]
                    .strip("'\"")
                )

            if missing_module:

                pkg_name = (
                    TELEGRAM_MODULES.get(
                        missing_module.lower(),
                        missing_module
                    )
                )

                ext = os.path.splitext(
                    file_name
                )[1].lower()

                cmd_text = (
                    f"npm install {pkg_name}"
                    if ext == ".js"
                    else f"pip install {pkg_name}"
                )

                error_msg = (
                    "⚠️ **ফাইল রান হতে সমস্যা হয়েছে!**\n\n"
                    f"📄 **File:** `{file_name}`\n"
                    f"❌ **সমস্যা:** আপনার কোডে "
                    f"`{missing_module}` মডিউলটি "
                    "মিসিং আছে।\n"
                    f"💻 **প্রয়োজনীয় কমান্ড:** "
                    f"`{cmd_text}`"
                )

                markup = (
                    types.InlineKeyboardMarkup()
                )

                markup.add(
                    types.InlineKeyboardButton(
                        f"📦 Install {pkg_name}",
                        callback_data=(
                            f"instmod_"
                            f"{script_owner_id}_"
                            f"{missing_module}_"
                            f"{file_name}"
                        )
                    )
                )

                markup.add(
                    types.InlineKeyboardButton(
                        "📄 View Error Logs",
                        callback_data=(
                            f"viewlog_"
                            f"{script_owner_id}_"
                            f"{file_name}"
                        )
                    )
                )

                bot.send_message(
                    message_obj_for_reply.chat.id,
                    error_msg,
                    reply_markup=markup,
                    parse_mode="Markdown",
                    protect_content=True
                )

            else:

                markup = (
                    types.InlineKeyboardMarkup()
                )

                markup.add(
                    types.InlineKeyboardButton(
                        "📄 View Error Logs",
                        callback_data=(
                            f"viewlog_"
                            f"{script_owner_id}_"
                            f"{file_name}"
                        )
                    )
                )

                bot.send_message(
                    message_obj_for_reply.chat.id,
                    (
                        "⚠️ **আপনার কোডে ভুল "
                        "(Syntax/Runtime Error) "
                        "পাওয়া গেছে!**\n"
                        f"📄 **File:** `{file_name}`"
                    ),
                    reply_markup=markup,
                    parse_mode="Markdown",
                    protect_content=True
                )

        except:

            pass


# ============================================================
# PYTHON SCRIPT RUNNER
# ============================================================

def run_script(
    script_path,
    script_owner_id,
    user_folder,
    file_name,
    message_obj_for_reply
):

    script_key = (
        f"{script_owner_id}_{file_name}"
    )

    try:

        log_file_path = os.path.join(
            user_folder,
            f"{os.path.splitext(file_name)[0]}.log"
        )

        log_file = open(
            log_file_path,
            "w",
            encoding="utf-8",
            errors="ignore"
        )

        unique_port = (
            8000
            + (
                int(
                    hashlib.md5(
                        script_key.encode()
                    ).hexdigest(),
                    16
                )
                % 50000
            )
        )

        custom_env = os.environ.copy()

        custom_env["PORT"] = str(
            unique_port
        )

        custom_env[
            "PYTHONDONTWRITEBYTECODE"
        ] = "1"

        custom_env[
            "PYTHONPATH"
        ] = user_folder

        custom_env[
            "HOME"
        ] = user_folder

        custom_env[
            "TEMP"
        ] = user_folder

        custom_env[
            "TMP"
        ] = user_folder

        custom_env[
            "TMPDIR"
        ] = user_folder

        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                script_path
            ],
            cwd=user_folder,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.PIPE,
            env=custom_env
        )

        bot_scripts[
            script_key
        ] = {
            "process": process,
            "log_file": log_file,
            "file_name": file_name,
            "script_owner_id": script_owner_id,
            "start_time": datetime.now(),
            "warned_11h": False,
            "user_folder": user_folder,
            "type": "py"
        }

        bot.send_message(
            message_obj_for_reply.chat.id,
            (
                "🚀 **Python Bot Started!**\n"
                f"📄 File: `{file_name}`\n"
                f"🆔 PID: `{process.pid}`"
            ),
            parse_mode="Markdown",
            protect_content=True
        )

        threading.Thread(
            target=monitor_and_guide_error,
            args=(
                process,
                log_file_path,
                script_owner_id,
                file_name,
                message_obj_for_reply
            ),
            daemon=True
        ).start()

    except Exception as e:

        bot.send_message(
            message_obj_for_reply.chat.id,
            f"❌ Error: {str(e)}",
            protect_content=True
        )


# ============================================================
# JS SCRIPT RUNNER
# ============================================================

def run_js_script(
    script_path,
    script_owner_id,
    user_folder,
    file_name,
    message_obj_for_reply
):

    script_key = (
        f"{script_owner_id}_{file_name}"
    )

    try:

        log_file_path = os.path.join(
            user_folder,
            f"{os.path.splitext(file_name)[0]}.log"
        )

        log_file = open(
            log_file_path,
            "w",
            encoding="utf-8",
            errors="ignore"
        )

        unique_port = (
            8000
            + (
                int(
                    hashlib.md5(
                        script_key.encode()
                    ).hexdigest(),
                    16
                )
                % 50000
            )
        )

        custom_env = os.environ.copy()

        custom_env[
            "PORT"
        ] = str(unique_port)

        custom_env[
            "NODE_PATH"
        ] = user_folder

        custom_env[
            "HOME"
        ] = user_folder

        custom_env[
            "TEMP"
        ] = user_folder

        custom_env[
            "TMP"
        ] = user_folder

        custom_env[
            "TMPDIR"
        ] = user_folder

        process = subprocess.Popen(
            [
                "node",
                script_path
            ],
            cwd=user_folder,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.PIPE,
            env=custom_env
        )

        bot_scripts[
            script_key
        ] = {
            "process": process,
            "log_file": log_file,
            "file_name": file_name,
            "script_owner_id": script_owner_id,
            "start_time": datetime.now(),
            "warned_11h": False,
            "user_folder": user_folder,
            "type": "js"
        }

        bot.send_message(
            message_obj_for_reply.chat.id,
            (
                "🚀 **JS Bot Started!**\n"
                f"📄 File: `{file_name}`\n"
                f"🆔 PID: `{process.pid}`"
            ),
            parse_mode="Markdown",
            protect_content=True
        )

        threading.Thread(
            target=monitor_and_guide_error,
            args=(
                process,
                log_file_path,
                script_owner_id,
                file_name,
                message_obj_for_reply
            ),
            daemon=True
        ).start()

    except Exception as e:

        bot.send_message(
            message_obj_for_reply.chat.id,
            f"❌ Error: {str(e)}",
            protect_content=True
        )


# ============================================================
# START BOT
# ============================================================

def do_start_bot(
    owner_id,
    fname,
    message_obj,
    call_id=None
):

    ufolder = get_user_folder(
        int(owner_id)
    )

    fpath = os.path.join(
        ufolder,
        fname
    )

    ext = os.path.splitext(
        fname
    )[1].lower()

    # Extra path safety
    if not os.path.abspath(
        fpath
    ).startswith(
        os.path.abspath(ufolder)
        + os.sep
    ):

        if call_id:

            bot.answer_callback_query(
                call_id,
                "❌ Invalid file path!",
                show_alert=True
            )

        return

    if not os.path.exists(fpath):

        if call_id:

            bot.answer_callback_query(
                call_id,
                "❌ File not found!",
                show_alert=True
            )

        return

    if is_bot_running(
        int(owner_id),
        fname
    ):

        if call_id:

            bot.answer_callback_query(
                call_id,
                "এই বোটটি অলরেডি রানিং আছে!",
                show_alert=True
            )

        return

    if call_id:

        bot.answer_callback_query(
            call_id,
            "Starting..."
        )

    if ext == ".js":

        run_js_script(
            fpath,
            int(owner_id),
            ufolder,
            fname,
            message_obj
        )

    else:

        run_script(
            fpath,
            int(owner_id),
            ufolder,
            fname,
            message_obj
        )


# ============================================================
# DB FILE OPERATIONS
# ============================================================

def save_user_file(
    user_id,
    file_name,
    file_type="py"
):

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            """
            INSERT OR REPLACE INTO user_files
            (user_id, file_name, file_type)
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
            f
            for f in user_files[user_id]
            if f[0] != file_name
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

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            """
            DELETE FROM user_files
            WHERE user_id = ?
            AND file_name = ?
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
                f
                for f in user_files[user_id]
                if f[0] != file_name
            ]


def add_active_user(
    user_id
):

    active_users.add(
        user_id
    )

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
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
# ADMIN APPROVAL SYSTEM
# ============================================================

def create_pending_upload(
    user_id,
    file_name,
    file_type,
    downloaded_file
):

    request_id = hashlib.sha256(
        (
            f"{user_id}:"
            f"{file_name}:"
            f"{time.time_ns()}"
        ).encode()
    ).hexdigest()[:16]

    temp_name = (
        f"{request_id}_{file_name}"
    )

    temp_path = os.path.join(
        PENDING_DIR,
        temp_name
    )

    with open(
        temp_path,
        "wb"
    ) as f:

        f.write(
            downloaded_file
        )

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            """
            INSERT INTO pending_uploads
            (
                request_id,
                user_id,
                file_name,
                file_type,
                temp_path,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                request_id,
                user_id,
                file_name,
                file_type,
                temp_path,
                datetime.now().isoformat()
            )
        )

        conn.commit()

        conn.close()

    return request_id


def get_pending_upload(
    request_id
):

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            """
            SELECT
                request_id,
                user_id,
                file_name,
                file_type,
                temp_path,
                status,
                created_at,
                reviewed_by
            FROM pending_uploads
            WHERE request_id=?
            """,
            (request_id,)
        )

        row = c.fetchone()

        conn.close()

    return row


def set_pending_status(
    request_id,
    status,
    admin_id
):

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            """
            UPDATE pending_uploads
            SET
                status=?,
                reviewed_by=?
            WHERE request_id=?
            AND status='pending'
            """,
            (
                status,
                admin_id,
                request_id
            )
        )

        changed = c.rowcount

        conn.commit()

        conn.close()

    return changed > 0


def delete_pending_record(
    request_id
):

    with DB_LOCK:

        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False
        )

        c = conn.cursor()

        c.execute(
            """
            DELETE FROM pending_uploads
            WHERE request_id=?
            """,
            (request_id,)
        )

        conn.commit()

        conn.close()


def approve_pending_upload(
    request_id,
    admin_id
):

    with PENDING_LOCK:

        row = get_pending_upload(
            request_id
        )

        if not row:

            return (
                False,
                "Approval request not found."
            )

        (
            req_id,
            user_id,
            file_name,
            file_type,
            temp_path,
            status,
            created_at,
            reviewed_by
        ) = row

        if status != "pending":

            return (
                False,
                f"This request is already {status}."
            )

        if not os.path.exists(
            temp_path
        ):

            set_pending_status(
                request_id,
                "failed",
                admin_id
            )

            return (
                False,
                "Pending file no longer exists."
            )

        # Prevent double approval
        if not set_pending_status(
            request_id,
            "approved",
            admin_id
        ):

            return (
                False,
                "This request was already processed."
            )

        try:

            user_folder = get_user_folder(
                int(user_id)
            )

            final_path = os.path.join(
                user_folder,
                file_name
            )

            final_path = os.path.abspath(
                final_path
            )

            safe_folder = (
                os.path.abspath(
                    user_folder
                )
                + os.sep
            )

            if not final_path.startswith(
                safe_folder
            ):

                return (
                    False,
                    "Invalid file path."
                )

            # Move ONLY AFTER approval
            shutil.move(
                temp_path,
                final_path
            )

            # Add to hosting list ONLY AFTER approval
            save_user_file(
                int(user_id),
                file_name,
                file_type
            )

            delete_pending_record(
                request_id
            )

            return (
                True,
                {
                    "user_id": user_id,
                    "file_name": file_name,
                    "file_type": file_type
                }
            )

        except Exception as e:

            logger.error(
                f"Approval error for "
                f"{request_id}: {e}",
                exc_info=True
            )

            try:

                if os.path.exists(
                    temp_path
                ):

                    os.remove(
                        temp_path
                    )

            except:
                pass

            return (
                False,
                str(e)
            )


def reject_pending_upload(
    request_id,
    admin_id
):

    with PENDING_LOCK:

        row = get_pending_upload(
            request_id
        )

        if not row:

            return (
                False,
                "Approval request not found."
            )

        (
            req_id,
            user_id,
            file_name,
            file_type,
            temp_path,
            status,
            created_at,
            reviewed_by
        ) = row

        if status != "pending":

            return (
                False,
                f"This request is already {status}."
            )

        if not set_pending_status(
            request_id,
            "rejected",
            admin_id
        ):

            return (
                False,
                "This request was already processed."
            )

        try:

            if os.path.exists(
                temp_path
            ):

                os.remove(
                    temp_path
                )

        except Exception as e:

            logger.warning(
                f"Could not remove "
                f"rejected file: {e}"
            )

        delete_pending_record(
            request_id
        )

        return (
            True,
            {
                "user_id": user_id,
                "file_name": file_name
            }
        )


def send_approval_request_to_all_admins(
    request_id,
    user_id,
    user_name,
    file_name,
    file_type,
    file_size
):

    markup = types.InlineKeyboardMarkup(
        row_width=2
    )

    markup.add(
        types.InlineKeyboardButton(
            "✅ APPROVE",
            callback_data=(
                f"approve_{request_id}"
            )
        ),
        types.InlineKeyboardButton(
            "❌ REJECT",
            callback_data=(
                f"reject_{request_id}"
            )
        )
    )

    approval_text = (
        "🔐 **NEW HOSTING APPROVAL REQUEST**\n\n"
        f"👤 **User:** {user_name}\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"📄 **File:** `{file_name}`\n"
        f"📦 **Type:** `{file_type.upper()}`\n"
        f"💾 **Size:** `{file_size}`\n\n"
        "🛡️ **Status:** `PENDING ADMIN APPROVAL`\n\n"
        "⚠️ User cannot start/host this file "
        "until an admin approves it."
    )

    sent = 0

    for admin_id in list(
        admin_ids
    ):

        try:

            bot.send_message(
                admin_id,
                approval_text,
                reply_markup=markup,
                parse_mode="Markdown",
                protect_content=True
            )

            sent += 1

        except Exception as e:

            logger.warning(
                f"Could not send approval "
                f"request to admin "
                f"{admin_id}: {e}"
            )

    return sent


# ============================================================
# UI METHODS
# ============================================================

def create_reply_keyboard_main_menu(
    user_id
):

    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )

    layout_to_use = (
        ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC
        if user_id in admin_ids
        else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    )

    for row in layout_to_use:

        markup.add(
            *[
                types.KeyboardButton(text)
                for text in row
            ]
        )

    return markup


def create_admin_panel_inline(
    user_id
):

    markup = types.InlineKeyboardMarkup(
        row_width=2
    )

    markup.add(
        types.InlineKeyboardButton(
            "➕ 𝗔𝗱𝗱 𝗖𝗵𝗮𝗻𝗻𝗲𝗹",
            callback_data="add_channel"
        ),
        types.InlineKeyboardButton(
            "➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗖𝗵𝗮𝗻𝗻𝗲𝗹",
            callback_data="remove_channel"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "📣 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁",
            callback_data="broadcast"
        ),
        types.InlineKeyboardButton(
            "🔐 𝗟𝗼𝗰𝗸/𝗨𝗻𝗹𝗼𝗰𝗸",
            callback_data="toggle_lock"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "⚙️ 𝗥𝘂𝗻 𝗔𝗹𝗹 𝗦𝗰𝗿𝗶𝗽𝘁𝘀",
            callback_data="run_all_scripts"
        ),
        types.InlineKeyboardButton(
            "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀",
            callback_data="stats"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "🎥 𝗦𝗲?? 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹",
            callback_data="set_tutorial"
        )
    )

    if int(user_id) == int(OWNER_ID):

        markup.add(
            types.InlineKeyboardButton(
                "👑 𝗔𝗱𝗱 𝗔𝗱𝗺𝗶𝗻",
                callback_data="add_admin"
            ),
            types.InlineKeyboardButton(
                "➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗔𝗱𝗺𝗶𝗻",
                callback_data="remove_admin"
            )
        )

        markup.add(
            types.InlineKeyboardButton(
                "⚙️ 𝗦𝗲𝘁 𝗕𝗼𝘁 𝗟𝗶𝗺𝗶𝘁",
                callback_data="set_limit"
            ),
            types.InlineKeyboardButton(
                "🚫 𝗕𝗹𝗼𝗰𝗸 𝗨𝘀𝗲𝗿",
                callback_data="block_user"
            )
        )

        markup.add(
            types.InlineKeyboardButton(
                "✅ 𝗨𝗻𝗯𝗹𝗼𝗰𝗸 𝗨𝘀𝗲𝗿",
                callback_data="unblock_user"
            )
        )

    return markup


# ============================================================
# START COMMAND
# ============================================================

@bot.message_handler(
    commands=["start"]
)
def start_cmd(message):

    user_id = message.from_user.id

    if user_id in blocked_users:
        return

    chat_id = message.chat.id

    user_name = (
        message.from_user.first_name
        or "User"
    )

    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )

    c = conn.cursor()

    c.execute(
        """
        SELECT user_id
        FROM active_users
        WHERE user_id=?
        """,
        (user_id,)
    )

    is_new = c.fetchone() is None

    conn.close()

    args = message.text.split()

    if (
        is_new
        and len(args) > 1
    ):

        referrer_id = args[1]

        if (
            referrer_id.isdigit()
            and int(referrer_id) != user_id
        ):

            referrer_id = int(
                referrer_id
            )

            with DB_LOCK:

                conn = sqlite3.connect(
                    DATABASE_PATH,
                    check_same_thread=False
                )

                c = conn.cursor()

                c.execute(
                    """
                    INSERT OR IGNORE INTO referrals
                    (user_id, referred_user_id)
                    VALUES (?, ?)
                    """,
                    (
                        referrer_id,
                        user_id
                    )
                )

                conn.commit()

                conn.close()

            try:

                bot.send_message(
                    referrer_id,
                    (
                        "🎉 **নতুন রেফারেল!**\n\n"
                        f"👤 `{user_name}` "
                        "আপনার রেফারে জয়েন করেছে।\n"
                        "🎁 আপনার বোট হোস্ট করার "
                        "লিমিট ১টি বৃদ্ধি পেয়েছে!"
                    ),
                    protect_content=True
                )

            except:

                pass

    if (
        bot_locked
        and user_id not in admin_ids
    ):

        bot.send_message(
            chat_id,
            "⚠️ **Bot is temporarily locked by Admin.**"
        )

        return

    add_active_user(
        user_id
    )

    limit = get_user_file_limit(
        user_id
    )

    welcome_msg = (
        f"✨ **𝗪𝗲𝗹𝗰𝗼𝗺𝗲, {user_name}!** ✨\n\n"
        f"🆔 **𝗬𝗼𝘂𝗿 𝗜𝗗:** `{user_id}`\n"
        f"🔰 **𝗛𝗼𝘀𝘁𝗶𝗻𝗴 𝗟𝗶𝗺𝗶𝘁:** "
        f"`{get_user_file_count(user_id)}` / `{limit}`\n\n"
        "💡 **আপনি সম্পূর্ণ ফ্রিতে আপনার "
        "Python (.py) ও JS (.js) বোট "
        "১২ ঘণ্টার জন্য রান করতে পারবেন।**\n\n"
        "🔐 **নতুন Security Rule:**\n"
        "প্রতিটি Upload আগে Security Scan হবে।\n"
        "তারপর Admin Approval লাগবে।\n"
        "Admin Approve না করলে ফাইল Host করা যাবে না।\n\n"
        "👇 *Select an option from the menu below:*"
    )

    bot.send_message(
        chat_id,
        welcome_msg,
        reply_markup=create_reply_keyboard_main_menu(
            user_id
        ),
        parse_mode="Markdown",
        protect_content=True
    )


# ============================================================
# UPLOAD MENU
# ============================================================

def _logic_upload_file(
    message
):

    user_id = message.from_user.id

    if (
        bot_locked
        and user_id not in admin_ids
    ):

        bot.send_message(
            message.chat.id,
            "⚠️ **Bot is locked by Admin.**"
        )

        return

    current_count = get_user_file_count(
        user_id
    )

    max_limit = get_user_file_limit(
        user_id
    )

    if current_count >= max_limit:

        bot.send_message(
            message.chat.id,
            (
                "⚠️ **আপনার আপলোড লিমিট শেষ!**\n\n"
                f"📊 **বর্তমান আপলোড:** "
                f"`{current_count}` / `{max_limit}`\n"
                "নতুন কোনো ফাইল রান করাতে "
                "`📁 Manage Files` থেকে "
                "যেকোনো একটি বোট ডিলিট করুন "
                "অথবা রেফার করুন।"
            ),
            parse_mode="Markdown"
        )

        return

    bot.send_message(
        message.chat.id,
        (
            "🚀 **আপনার Python (.py) অথবা "
            "JS (.js) বোট ফাইলটি আপলোড করুন।**\n\n"
            "🔐 File upload করার পর:\n"
            "1️⃣ Security Scan হবে\n"
            "2️⃣ Admin-এর কাছে Approval যাবে\n"
            "3️⃣ Admin Approve করলে Host করা যাবে\n\n"
            "⚠️ **Admin Approval ছাড়া কোনো "
            "ফাইল Start হবে না।**"
        ),
        parse_mode="Markdown"
    )


# ============================================================
# MANAGE FILES
# ============================================================

def _logic_check_files(
    message
):

    user_id = message.from_user.id

    user_files_list = user_files.get(
        user_id,
        []
    )

    if not user_files_list:

        bot.send_message(
            message.chat.id,
            (
                "📂 **Your Uploaded Files:**\n\n"
                "*(No approved files uploaded yet)*"
            ),
            parse_mode="Markdown"
        )

        return

    markup = types.InlineKeyboardMarkup(
        row_width=1
    )

    for file_name, file_type in sorted(
        user_files_list
    ):

        is_running = is_bot_running(
            user_id,
            file_name
        )

        status_icon = (
            "🟢 Running"
            if is_running
            else "🔴 Stopped"
        )

        btn_text = (
            f"📄 {file_name} "
            f"({file_type}) - "
            f"{status_icon}"
        )

        markup.add(
            types.InlineKeyboardButton(
                btn_text,
                callback_data=(
                    f"file_{user_id}_{file_name}"
                )
            )
        )

    bot.send_message(
        message.chat.id,
        (
            f"📁 **𝗠𝗮𝗻𝗮𝗴𝗲 𝗬𝗼𝘂𝗿 𝗙𝗶𝗹𝗲𝘀 "
            f"({len(user_files_list)}/"
            f"{get_user_file_limit(user_id)}):**"
        ),
        reply_markup=markup,
        parse_mode="Markdown",
        protect_content=True
    )


# ============================================================
# REFERRAL
# ============================================================

def _logic_referral(
    message
):

    user_id = message.from_user.id

    bot_info = bot.get_me()

    ref_link = (
        f"https://t.me/"
        f"{bot_info.username}"
        f"?start={user_id}"
    )

    ref_count = get_referral_count(
        user_id
    )

    limit = get_user_file_limit(
        user_id
    )

    msg = (
        "🎁 **𝗥𝗲𝗳𝗲𝗿 𝗔𝗻𝗱 𝗘𝗮𝗿𝗻 "
        "𝗕𝗼𝘁 𝗦𝗹𝗼𝘁𝘀** 🎁\n\n"
        "বন্ধুদের রেফার করে সম্পূর্ণ ফ্রিতে "
        "আপনার বোট হোস্টিং লিমিট বাড়ান!\n"
        "প্রতিটি রেফারের জন্য আপনি "
        "**১টি এক্সট্রা বোট রান করার লিমিট** "
        "পাবেন (সর্বোচ্চ ৩টি বোট)।\n\n"
        f"🔗 **আপনার রেফার লিংক:**\n"
        f"`{ref_link}`\n\n"
        f"📊 **আপনার মোট রেফার:** "
        f"`{ref_count}`\n"
        f"🚀 **বর্তমান লিমিট:** "
        f"`{limit} টি বোট`"
    )

    bot.send_message(
        message.chat.id,
        msg,
        parse_mode="Markdown"
    )


# ============================================================
# TUTORIAL
# ============================================================

def _logic_tutorial(
    message
):

    tut_link = get_setting(
        "tutorial_link",
        UPDATE_CHANNEL
    )

    markup = types.InlineKeyboardMarkup()

    markup.add(
        types.InlineKeyboardButton(
            "🎥 Watch Tutorial Video",
            url=tut_link
        )
    )

    msg = (
        "🎥 **𝗛𝗼𝘄 𝗧𝗼 𝗨𝘀𝗲 & 𝗛𝗼𝘀𝘁 𝗕𝗼𝘁:**\n\n"
        "কীভাবে ফাইল আপলোড করতে হয় এবং "
        "সহজে আপনার বোট রান করতে হয় তা "
        "শিখতে নিচের বাটনে ক্লিক করুন।"
    )

    bot.send_message(
        message.chat.id,
        msg,
        reply_markup=markup,
        parse_mode="Markdown",
        protect_content=True
    )


# ============================================================
# FILE UPLOAD HANDLER
# ============================================================

@bot.message_handler(
    content_types=["document"]
)
def handle_file_upload_doc(
    message
):

    user_id = message.from_user.id

    if user_id in blocked_users:
        return

    if (
        bot_locked
        and user_id not in admin_ids
    ):

        bot.send_message(
            message.chat.id,
            "🔒 **Bot is currently locked by Admin.**",
            parse_mode="Markdown"
        )

        return

    doc = message.document

    user_name = (
        message.from_user.first_name
        or "Unknown User"
    )

    current_count = get_user_file_count(
        user_id
    )

    max_limit = get_user_file_limit(
        user_id
    )

    file_name = os.path.basename(
        doc.file_name or "unknown_file"
    )

    file_name = re.sub(
        r"[^\w\-\.]",
        "_",
        file_name
    )

    file_exists = any(
        f[0] == file_name
        for f in user_files.get(
            user_id,
            []
        )
    )

    if (
        current_count >= max_limit
        and not file_exists
    ):

        bot.send_message(
            message.chat.id,
            (
                "❌ **আপলোড লিমিট পূর্ণ হয়েছে!**\n\n"
                f"📊 Current: "
                f"`{current_count}` / `{max_limit}`\n\n"
                "🎁 Referral করে limit বাড়ান।"
            ),
            parse_mode="Markdown"
        )

        return

    file_ext = os.path.splitext(
        file_name
    )[1].lower()

    if file_ext not in [
        ".py",
        ".js"
    ]:

        bot.send_message(