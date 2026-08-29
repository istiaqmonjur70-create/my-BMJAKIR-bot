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
import uuid
from flask import Flask
from threading import Thread
import psutil
import telebot
from telebot import types
from types import SimpleNamespace

# --- Flask Keep Alive ---
app = Flask("")

@app.route("/")
def home():
    return "I'm Mukesh File Host - Running Successfully"

def run_flask():
    try:
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        print(f"Flask Keep-Alive error: {e}")

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive server started.")

# --- Configuration ---
TOKEN = "8910223271:AAEGc6ZTC4qE6FkOBLL13Xj0QwtQyfCI7CU"
OWNER_ID = 8814363793
ADMIN_ID = 8814363793
YOUR_USERNAME = "@Bmjakir69"
UPDATE_CHANNEL = "https://t.me/JAKIRLABS"
UPLOAD_LOG_CHANNEL = "@ajajakkalqkqkqjajakl" # ফাইল আপলোড নোটিফিকেশন চ্যানেল

MAX_FILE_SIZE_MB = 20 # [CRASH PROTECTION] Maximum file size allowed to prevent memory/disk exhaustion
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Default payment numbers (Can be changed from Admin Panel now)
DEFAULT_BKASH = "01612037086"
DEFAULT_NAGAD = "Off"

# Folder setup - using absolute paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, "upload_bots")
IROTECH_DIR = os.path.join(BASE_DIR, "inf")
DATABASE_PATH = os.path.join(IROTECH_DIR, "bot_data.db")

# Create necessary directories
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# --- Multi-Bot Proxy ---
class BotProxy:
    def __init__(self):
        self._local = threading.local()
        self._default = None
        self._handlers = []

    def bind(self, real_bot):
        self._local.bot = real_bot

    def _target(self):
        return getattr(self._local, "bot", None) or self._default

    def message_handler(self, *args, **kwargs):
        def decorator(func):
            self._handlers.append(("message", args, kwargs, func))
            return func
        return decorator

    def callback_query_handler(self, *args, **kwargs):
        def decorator(func):
            self._handlers.append(("callback", args, kwargs, func))
            return func
        return decorator

    def register_next_step_handler(self, message, callback, *args, **kwargs):
        target = self._target()
        if target is None:
            raise RuntimeError("No active Telegram bot context")
        bound_bot = target
        def wrapped(next_message):
            self.bind(bound_bot)
            return callback(next_message, *args, **kwargs)
        return bound_bot.register_next_step_handler(message, wrapped)

    def __getattr__(self, name):
        target = self._target()
        if target is None:
            raise RuntimeError(f"No active Telegram bot for .{name}()")
        return getattr(target, name)

bot = BotProxy()

# --- Data structures ---
bot_scripts = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
blocked_users = set()
bot_locked = False
temp_deposit = {} # Temporary store for deposit steps

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Command Button Layouts ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨", "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹"],
    ["🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲", "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"],
    ["💎 𝗩𝗜𝗣 𝗣𝗹𝗮𝗻𝘀", "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴"],
    ["👤 𝗔𝗰𝗰𝗼𝘂𝗻𝘁", "🔐 𝗦𝗲𝗰𝘂𝗿𝗶𝘁𝘆"],
    ["👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿"],
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨", "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹"],
    ["🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲", "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"],
    ["💎 𝗩𝗜𝗣 𝗣𝗹𝗮𝗻𝘀", "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹"],
    ["⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴", "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀"],
    ["👤 𝗔𝗰𝗰𝗼𝘂𝗻𝘁", "👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿"],
]

# --- Database Setup ---
DB_LOCK = threading.Lock()

def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS user_files (user_id INTEGER, file_name TEXT, file_type TEXT, PRIMARY KEY (user_id, file_name))""")
            c.execute("""CREATE TABLE IF NOT EXISTS active_users (user_id INTEGER PRIMARY KEY)""")
            c.execute("""CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER DEFAULT 0
            )""")
            # Backward-compatible migration for older databases.
            try:
                c.execute("ALTER TABLE admins ADD COLUMN added_by INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            c.execute("""CREATE TABLE IF NOT EXISTS force_channels (channel_id TEXT PRIMARY KEY, channel_url TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS custom_limits (user_id INTEGER PRIMARY KEY, max_limit INTEGER)""")
            c.execute("""CREATE TABLE IF NOT EXISTS blocked_users (user_id INTEGER PRIMARY KEY)""")
            c.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS pending_uploads (
                request_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                risk_note TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_by INTEGER
            )""")
            c.execute("""CREATE INDEX IF NOT EXISTS idx_pending_uploads_user
                         ON pending_uploads(user_id, status)""")
            c.execute("""CREATE TABLE IF NOT EXISTS free_hosting_exhausted (
                user_id INTEGER PRIMARY KEY,
                exhausted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            
            # New Tables for Account & Balances
            c.execute("""CREATE TABLE IF NOT EXISTS user_account (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 0,
                total_referrals INTEGER DEFAULT 0
            )""")
            
            # VIP Plans Tables
            c.execute("""CREATE TABLE IF NOT EXISTS plans (
                plan_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                name TEXT, 
                description TEXT, 
                bot_limit INTEGER, 
                duration_days INTEGER, 
                price TEXT
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS user_subscriptions (
                user_id INTEGER PRIMARY KEY, 
                plan_id INTEGER, 
                end_time TIMESTAMP, 
                notified_warning BOOLEAN DEFAULT 0
            )""")

            c.execute("INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)", (OWNER_ID, 0))
            if ADMIN_ID != OWNER_ID:
                c.execute("INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)", (ADMIN_ID, 0))

            conn.commit()
            conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("Loading data from database...")
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()

            c.execute("SELECT user_id, file_name, file_type FROM user_files")
            for user_id, file_name, file_type in c.fetchall():
                if user_id not in user_files:
                    user_files[user_id] = []
                user_files[user_id].append((file_name, file_type))

            c.execute("SELECT user_id FROM active_users")
            active_users.update(user_id for (user_id,) in c.fetchall())

            c.execute("SELECT user_id FROM admins")
            admin_ids.update(user_id for (user_id,) in c.fetchall())

            c.execute("SELECT user_id FROM blocked_users")
            blocked_users.update(user_id for (user_id,) in c.fetchall())

            conn.close()
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)

init_db()
load_data()

# --- Settings & Account Helper ---
def get_user_account(user_id):
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("SELECT balance, total_referrals FROM user_account WHERE user_id=?", (user_id,))
            row = c.fetchone()
            if row: 
                conn.close()
                return row
            else:
                c.execute("INSERT OR IGNORE INTO user_account (user_id) VALUES (?)", (user_id,))
                conn.commit()
                conn.close()
                return (0, 0)
    except Exception as e:
        logger.error(f"DB Error in get_user_account: {e}")
        return (0, 0)

def get_setting(key, default=""):
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = c.fetchone()
            conn.close()
            return row[0] if row else default
    except:
        return default

def set_setting(key, value):
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
            conn.close()
    except Exception as e:
        logger.error(f"DB Error in set_setting: {e}")

# --- Limits & Plans Helper ---
def get_user_file_limit(user_id):
    if user_id == OWNER_ID or user_id in admin_ids:
        return float("inf")
    
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            
            c.execute("""SELECT p.bot_limit, u.end_time 
                         FROM user_subscriptions u 
                         JOIN plans p ON u.plan_id = p.plan_id 
                         WHERE u.user_id = ?""", (user_id,))
            sub_row = c.fetchone()
            
            if sub_row:
                bot_limit, end_time_str = sub_row
                end_time = datetime.fromisoformat(end_time_str)
                if datetime.now() < end_time:
                    conn.close()
                    return bot_limit
            
            c.execute("SELECT max_limit FROM custom_limits WHERE user_id=?", (user_id,))
            row = c.fetchone()
            conn.close()
            
            if row is not None:
                return row[0]
    except Exception as e:
        logger.error(f"Error checking file limit: {e}")
        
    return 1

def is_vip_user(user_id):
    return get_user_file_limit(user_id) > 1

def has_active_plan(user_id):
    """True only when the user has a currently active paid/admin-assigned plan."""
    if int(user_id) in {int(OWNER_ID), int(ADMIN_ID), int(globals().get("SECOND_ADMIN_ID", 0) or 0)}:
        return True
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("SELECT end_time FROM user_subscriptions WHERE user_id=?", (int(user_id),))
            row = c.fetchone()
            conn.close()
        if row:
            return datetime.now() < datetime.fromisoformat(row[0])
    except Exception as e:
        logger.error("Plan check failed: %s", e)
    return False

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

# --- Force Sub Check ---
def get_force_channels():
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("SELECT channel_id, channel_url FROM force_channels")
            channels = c.fetchall()
            conn.close()
            return channels
    except Exception as e:
        logger.error(f"Error getting channels: {e}")
        return []

def check_force_sub(user_id):
    if user_id in admin_ids:
        return []
        
    channels = get_force_channels()
    not_joined = []
    
    for ch_id, ch_url in channels:
        try:
            chat_target = ch_id.strip()
            if chat_target.lstrip('-').isdigit():
                chat_target = int(chat_target)
            
            member = bot.get_chat_member(chat_target, user_id)
            if member.status in ['left', 'kicked', 'restricted']:
                not_joined.append((ch_id, ch_url))
        except Exception as e:
            pass
            
    return not_joined

# --- Upload Safety Rule ---
# Normal source files are allowed. Only common shell/CMD command execution APIs require admin approval.
# References such as bot_data.db are NOT blocked.

# --- Upload Security Review ---
SHELL_RISK_PATTERNS = [
    (r"\bos\.system\s*\(", "os.system()"),
    (r"\bsubprocess\.(run|Popen|call|check_call|check_output)\s*\(", "subprocess API"),
    (r"\bshell\s*=\s*True\b", "shell=True"),
    (r"\bchild_process\.(exec|spawn|execFile)\s*\(", "Node child_process"),
    (r"\b(?:cmd\.exe|powershell(?:\.exe)?|bash\s+-c|sh\s+-c)\b", "shell command"),
    (r"\beval\s*\(", "eval()"),
    (r"\bexec\s*\(", "exec()"),
]

def security_review(file_content, file_name):
    try:
        text_content = file_content.decode("utf-8", errors="ignore")
    except Exception:
        text_content = ""
    hits = []
    for pattern, label in SHELL_RISK_PATTERNS:
        if re.search(pattern, text_content, flags=re.IGNORECASE):
            hits.append(label)
    if hits:
        return "⚠️ Review Warning: " + ", ".join(dict.fromkeys(hits)) + "."
    return "🟢 Basic static review: no common shell/command API detected."

def requires_admin_approval(file_content, file_name):
    try:
        text_content = file_content.decode("utf-8", errors="ignore")
    except Exception:
        text_content = ""
    hits = []
    for pattern, label in SHELL_RISK_PATTERNS:
        if re.search(pattern, text_content, flags=re.IGNORECASE):
            hits.append(label)
    if hits:
        return True, "⚠️ Shell/CMD review required: " + ", ".join(dict.fromkeys(hits))
    return False, ""

def is_free_hosting_exhausted(user_id):
    if has_active_plan(user_id): return False
    try:
        with DB_LOCK:
            conn=sqlite3.connect(DATABASE_PATH, check_same_thread=False); c=conn.cursor()
            c.execute("SELECT 1 FROM free_hosting_exhausted WHERE user_id=?", (int(user_id),)); row=c.fetchone(); conn.close(); return row is not None
    except Exception as e:
        logger.error("Free hosting exhausted check failed: %s", e); return False

def mark_free_hosting_exhausted(user_id):
    try:
        with DB_LOCK:
            conn=sqlite3.connect(DATABASE_PATH, check_same_thread=False); c=conn.cursor()
            c.execute("INSERT OR REPLACE INTO free_hosting_exhausted (user_id, exhausted_at) VALUES (?, CURRENT_TIMESTAMP)", (int(user_id),)); conn.commit(); conn.close()
    except Exception as e:
        logger.error("Failed to mark free hosting exhausted: %s", e)

def _button_style(kind=None):
    """Return Telegram Bot API button style: primary, danger or success.
    Uses semantic style when supplied; otherwise rotates randomly.
    """
    import random
    if kind in ("success", "danger", "primary"):
        return kind
    return random.choice(("primary", "danger", "success"))


def make_inline_button(text, *args, **kwargs):
    """Create an InlineKeyboardButton with native Telegram background style.
    Requires a recent pyTelegramBotAPI; falls back safely on older versions.
    """
    style = kwargs.pop("style", None)
    if style is None:
        cb = str(kwargs.get("callback_data", "")).lower()
        label = str(text).lower()
        if any(x in cb or x in label for x in ("reject", "remove", "delete", "stop", "block", "cancel")):
            style = "danger"
        elif any(x in cb or x in label for x in ("approve", "success", "verify", "buy", "add", "unlock", "start")):
            style = "success"
        else:
            style = _button_style()
    try:
        return types.InlineKeyboardButton(text, *args, style=style, **kwargs)
    except TypeError:
        # Older pyTelegramBotAPI versions may not expose the new style field.
        return types.InlineKeyboardButton(text, *args, **kwargs)


def make_reply_button(text, *args, **kwargs):
    style = kwargs.pop("style", None) or _button_style()
    try:
        return types.KeyboardButton(text, *args, style=style, **kwargs)
    except TypeError:
        return types.KeyboardButton(text, *args, **kwargs)

def get_random_button_prefix(kind="normal"):
    choices = {
        "success": ["🟢", "🟩", "💚"],
        "danger": ["🔴", "🟥", "❌"],
        "normal": ["🔵", "🟦", "🟣"],
    }
    import random
    return random.choice(choices.get(kind, choices["normal"]))

def save_pending_upload(request_id, user_id, file_name, file_type, file_path, file_size, risk_note):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("""INSERT INTO pending_uploads
                     (request_id,user_id,file_name,file_type,file_path,file_size,risk_note,status)
                     VALUES (?,?,?,?,?,?,?,'pending')""",
                  (request_id, user_id, file_name, file_type, file_path, file_size, risk_note))
        conn.commit()
        conn.close()

def claim_pending_upload(request_id, admin_id, new_status):
    if new_status not in ("approved", "rejected"):
        return None
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("""SELECT user_id,file_name,file_type,file_path,file_size,risk_note,status
                     FROM pending_uploads WHERE request_id=?""", (request_id,))
        row = c.fetchone()
        if not row or row[6] != "pending":
            conn.close()
            return None
        c.execute("""UPDATE pending_uploads
                     SET status=?, approved_by=?
                     WHERE request_id=? AND status='pending'""",
                  (new_status, admin_id, request_id))
        conn.commit()
        conn.close()
        return row

def finalize_approved_upload(request_id, admin_id):
    # Claim only after confirming the pending file exists.
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("""SELECT user_id,file_name,file_type,file_path,file_size,risk_note,status
                     FROM pending_uploads WHERE request_id=?""", (request_id,))
        row = c.fetchone()
        if not row or row[6] != "pending":
            conn.close()
            return None
        if not os.path.exists(row[3]):
            conn.close()
            return ("missing", row[0], row[1])
        c.execute("""UPDATE pending_uploads SET status='approved', approved_by=?
                     WHERE request_id=? AND status='pending'""", (admin_id, request_id))
        conn.commit()
        conn.close()

    user_id, file_name, file_type, file_path, file_size, risk_note, _ = row
    try:
        force_kill_user_bot(user_id, file_name)
        destination = os.path.join(get_user_folder(user_id), file_name)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        os.replace(file_path, destination)
        save_user_file(user_id, file_name, file_type)
        return ("approved", user_id, file_name, destination, risk_note)
    except Exception as e:
        logger.error("Approval finalize error: %s", e, exc_info=True)
        return ("error", user_id, file_name, str(e))

def finalize_rejected_upload(request_id, admin_id):
    row = claim_pending_upload(request_id, admin_id, "rejected")
    if not row:
        return None
    user_id, file_name, file_type, file_path, file_size, risk_note, _ = row
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass
    return ("rejected", user_id, file_name)

def send_approval_request_to_admins(request_id, user_id, file_name, file_path, file_size, risk_note):
    caption = (
        "🔐 <b>FILE APPROVAL REQUEST</b>\n\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"📄 File: <code>{file_name}</code>\n"
        f"📦 Size: <code>{file_size / 1024:.1f} KB</code>\n\n"
        f"{risk_note}\n\n"
        "⚠️ <b>Run is blocked until one admin approves.</b>\n"
        "Only the first valid approval will unlock this file."
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        make_inline_button(
            f"{get_random_button_prefix('success')} Approve & Run",
            callback_data=f"approve_file_{request_id}"
        ),
        make_inline_button(
            f"{get_random_button_prefix('danger')} Reject",
            callback_data=f"reject_file_{request_id}"
        ),
    )
    sent = 0
    for admin_uid in sorted(APPROVAL_ADMIN_IDS):
        for real_bot in BOT_INSTANCES:
            try:
                with open(file_path, "rb") as upload_stream:
                    real_bot.send_document(
                        admin_uid,
                        upload_stream,
                        caption=caption,
                        parse_mode="HTML",
                        protect_content=True,
                        reply_markup=markup
                    )
                sent += 1
                break
            except Exception as e:
                logger.warning("Approval notification failed for admin %s: %s", admin_uid, e)
    return sent

# --- Process Helpers ---
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def kill_process_tree(process_info):
    try:
        if "log_file" in process_info and not process_info["log_file"].closed:
            try:
                process_info["log_file"].close()
            except:
                pass
            
        process = process_info.get("process")
        if process:
            if hasattr(process, "pid"):
                try:
                    parent = psutil.Process(process.pid)
                    for child in parent.children(recursive=True):
                        try:
                            child.kill()
                        except:
                            pass
                    try:
                        parent.kill()
                    except:
                        pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
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
        logger.error(f"❌ Error killing process tree: {e}")

def force_kill_user_bot(owner_id, file_name):
    skey = f"{owner_id}_{file_name}"
    if skey in bot_scripts:
        kill_process_tree(bot_scripts[skey])
        try:
            del bot_scripts[skey]
        except:
            pass

    ufolder = get_user_folder(int(owner_id))
    try:
        for proc in psutil.process_iter(['pid', 'cwd', 'cmdline']):
            try:
                proc_cwd = proc.info.get('cwd')
                if proc_cwd and ufolder in proc_cwd:
                    cmd = proc.info.get('cmdline') or []
                    if any(file_name in str(arg) for arg in cmd):
                        try:
                            for child in proc.children(recursive=True):
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
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        pass

def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get("process"):
        try:
            proc = psutil.Process(script_info["process"].pid)
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                return True
        except:
            pass
            
    ufolder = get_user_folder(int(script_owner_id))
    try:
        for proc in psutil.process_iter(['cwd', 'cmdline']):
            try:
                proc_cwd = proc.info.get('cwd')
                if proc_cwd and ufolder in proc_cwd:
                    cmd = proc.info.get('cmdline') or []
                    if any(file_name in str(arg) for arg in cmd):
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except:
        pass
        
    return False

# --- Background auto-stopper (12h free hosting) ---
def auto_stopper():
    while True:
        try:
            time.sleep(60)
            now = datetime.now()
            for key in list(bot_scripts.keys()):
                script = bot_scripts.get(key)
                if not script:
                    continue
                user_id = int(script["script_owner_id"])
                if not has_active_plan(user_id):
                    elapsed_hours = (now - script["start_time"]).total_seconds() / 3600
                    if elapsed_hours >= 11 and not script.get("warning_sent"):
                        script["warning_sent"] = True
                        markup = types.InlineKeyboardMarkup()
                        markup.add(make_inline_button(
                            f"{get_random_button_prefix('success')} 𝗕𝘂𝘆 𝗣𝗹𝗮𝗻",
                            callback_data="show_vip_plans"
                        ))
                        try:
                            bot.send_message(
                                user_id,
                                f"⚠️ **Free Hosting Notice**\\n\\n"
                                f"📄 `{script['file_name']}`\\n"
                                f"⏳ আর প্রায় ১ ঘণ্টা পর আপনার ১২ ঘণ্টার Free Hosting limit শেষ হবে।\\n\\n"
                                f"💎 চালু রাখতে **Account → Deposit** থেকে balance add করে একটি Plan কিনুন।",
                                reply_markup=markup, protect_content=True
                            )
                        except:
                            pass
                    elif elapsed_hours >= 12:
                        mark_free_hosting_exhausted(user_id)
                        force_kill_user_bot(user_id, script["file_name"])
                        try:
                            markup = types.InlineKeyboardMarkup()
                            markup.add(make_inline_button(
                                f"{get_random_button_prefix('success')} 𝗕𝘂𝘆 𝗣𝗹𝗮𝗻",
                                callback_data="show_vip_plans"
                            ))
                            bot.send_message(
                                user_id,
                                f"🛑 **Free Hosting Limit Finished**\\n\\n"
                                f"📄 `{script['file_name']}` বন্ধ করা হয়েছে।\\n"
                                f"⏱️ Plan ছাড়া সর্বোচ্চ ১২ ঘণ্টা Free Hosting ব্যবহার করা যাবে।\\n\\n"
                                f"💎 আবার চালু করতে **Account → Deposit** থেকে balance add করে Plan কিনুন।\n"
                                f"🚫 Plan ছাড়া নতুন bot upload বা start করা যাবে না.",
                                reply_markup=markup, protect_content=True
                            )
                        except:
                            pass
        except Exception as e:
            logger.error(f"Error in auto_stopper thread: {e}")

# --- Plan Expiry Checker ---
def subscription_checker():
    while True:
        try:
            time.sleep(3600)
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                now = datetime.now()
                c.execute("""SELECT u.user_id, p.name, u.end_time, u.notified_warning 
                             FROM user_subscriptions u JOIN plans p ON u.plan_id = p.plan_id""")
                subs = c.fetchall()
                conn.close()
                
            for uid, pname, etime_str, notified in subs:
                end_time = datetime.fromisoformat(etime_str)
                time_left = end_time - now
                
                if time_left.total_seconds() <= 0:
                    with DB_LOCK:
                        conn_del = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                        c_del = conn_del.cursor()
                        c_del.execute("DELETE FROM user_subscriptions WHERE user_id=?", (uid,))
                        conn_del.commit()
                        conn_del.close()
                    try:
                        bot.send_message(uid, f"⚠️ **আপনার '{pname}' প্ল্যানের মেয়াদ শেষ!**\nআপনার লিমিট আগের মতো ১টি বটে নেমে এসেছে।")
                    except:
                        pass
                elif time_left.total_seconds() <= 86400 and not notified:
                    with DB_LOCK:
                        conn_up = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                        c_up = conn_up.cursor()
                        c_up.execute("UPDATE user_subscriptions SET notified_warning=1 WHERE user_id=?", (uid,))
                        conn_up.commit()
                        conn_up.close()
                    try:
                        bot.send_message(uid, f"⚠️ **সতর্কতা:** আপনার **{pname}** প্ল্যানের মেয়াদ শেষ হতে ১ দিনেরও কম সময় বাকি! নিরবচ্ছিন্ন সেবা পেতে প্ল্যানটি পুনরায় রিনিউ করুন।")
                    except:
                        pass
        except Exception as e:
            logger.error(f"Error in subscription_checker thread: {e}")

threading.Thread(target=subscription_checker, daemon=True).start()

# --- Script Runners ---
TELEGRAM_MODULES = {"telebot": "pyTelegramBotAPI", "telegram": "python-telegram-bot", "aiogram": "aiogram", "pyrogram": "pyrogram", "telethon": "telethon", "flask": "Flask", "psutil": "psutil"}

def monitor_and_guide_error(process, log_file_path, script_owner_id, file_name, message_obj_for_reply):
    try:
        time.sleep(3)
        if process.poll() is not None:
            try:
                with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                    log_content = f.read()

                match_py = re.search(r"(?:ModuleNotFoundError|ImportError): No module named '(.+?)'", log_content)
                match_js = re.search(r"Cannot find module '(.+?)'", log_content)

                missing_module = None
                if match_py: missing_module = match_py.group(1).split(".")[0].strip("'\"")
                elif match_js: missing_module = match_js.group(1).split("/")[0].strip("'\"")

                if missing_module:
                    pkg_name = TELEGRAM_MODULES.get(missing_module.lower(), missing_module)
                    ext = os.path.splitext(file_name)[1].lower()
                    cmd_text = f"npm install {pkg_name}" if ext == ".js" else f"pip install {pkg_name}"
                    error_msg = f"⚠️ **ফাইল রান হতে সমস্যা হয়েছে!**\n\n📄 **File:** `{file_name}`\n❌ **সমস্যা:** আপনার কোডে `{missing_module}` মডিউলটি মিসিং আছে।\n💻 **প্রয়োজনীয় কমান্ড:** `{cmd_text}`"
                    
                    markup = types.InlineKeyboardMarkup()
                    markup.add(make_inline_button(
                        f"{get_random_button_prefix('normal')} View Error Logs",
                        callback_data=f"viewlog_{script_owner_id}_{file_name}"
                    ))
                    error_msg += "\n\n🔐 Automatic package installation is disabled. Install dependencies manually outside the host if needed."
                    bot.send_message(message_obj_for_reply.chat.id, error_msg, reply_markup=markup, parse_mode="Markdown", protect_content=True)
                else:
                    markup = types.InlineKeyboardMarkup()
                    markup.add(make_inline_button("📄 View Error Logs", callback_data=f"viewlog_{script_owner_id}_{file_name}"))
                    bot.send_message(message_obj_for_reply.chat.id, f"⚠️ **আপনার কোডে ভুল (Syntax/Runtime Error) পাওয়া গেছে!**\n📄 **File:** `{file_name}`", reply_markup=markup, parse_mode="Markdown", protect_content=True)
            except: pass
    except Exception as e:
        logger.error(f"Error in monitor_and_guide_error: {e}")

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply):
    script_key = f"{script_owner_id}_{file_name}"
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        
        unique_port = 8000 + (int(hashlib.md5(script_key.encode()).hexdigest(), 16) % 50000)
        
        custom_env = os.environ.copy()
        custom_env["PORT"] = str(unique_port)
        custom_env["PYTHONDONTWRITEBYTECODE"] = "1"
        custom_env["PYTHONPATH"] = user_folder
        custom_env["HOME"] = user_folder        
        custom_env["TEMP"] = user_folder        
        custom_env["TMP"] = user_folder         
        custom_env["TMPDIR"] = user_folder      
        
        process = subprocess.Popen([sys.executable, "-u", script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.DEVNULL, env=custom_env, shell=False, start_new_session=True)
        
        bot_scripts[script_key] = {"process": process, "log_file": log_file, "file_name": file_name, "script_owner_id": script_owner_id, "start_time": datetime.now(), "warning_sent": False, "user_folder": user_folder, "type": "py"}
        bot.send_message(message_obj_for_reply.chat.id, f"🚀 **Python Bot Started!**\n📄 File: `{file_name}`\n🆔 PID: `{process.pid}`", parse_mode="Markdown", protect_content=True)
        threading.Thread(target=monitor_and_guide_error, args=(process, log_file_path, script_owner_id, file_name, message_obj_for_reply), daemon=True).start()
    except Exception as e:
        bot.send_message(message_obj_for_reply.chat.id, f"❌ Error starting script: {str(e)}", protect_content=True)

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply):
    script_key = f"{script_owner_id}_{file_name}"
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        
        unique_port = 8000 + (int(hashlib.md5(script_key.encode()).hexdigest(), 16) % 50000)
        
        custom_env = os.environ.copy()
        custom_env["PORT"] = str(unique_port)
        custom_env["NODE_PATH"] = user_folder
        custom_env["HOME"] = user_folder
        custom_env["TEMP"] = user_folder
        custom_env["TMP"] = user_folder
        custom_env["TMPDIR"] = user_folder
        
        process = subprocess.Popen(["node", script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.DEVNULL, env=custom_env, shell=False, start_new_session=True)
        
        bot_scripts[script_key] = {"process": process, "log_file": log_file, "file_name": file_name, "script_owner_id": script_owner_id, "start_time": datetime.now(), "warning_sent": False, "user_folder": user_folder, "type": "js"}
        bot.send_message(message_obj_for_reply.chat.id, f"🚀 **JS Bot Started!**\n📄 File: `{file_name}`\n🆔 PID: `{process.pid}`", parse_mode="Markdown", protect_content=True)
        threading.Thread(target=monitor_and_guide_error, args=(process, log_file_path, script_owner_id, file_name, message_obj_for_reply), daemon=True).start()
    except Exception as e:
        bot.send_message(message_obj_for_reply.chat.id, f"❌ Error starting JS script: {str(e)}", protect_content=True)

def do_start_bot(owner_id, fname, message_obj, call_id=None):
    owner_id = int(owner_id)
    ufolder = get_user_folder(owner_id)
    fpath = os.path.join(ufolder, fname)
    ext = os.path.splitext(fname)[1].lower()

    if is_free_hosting_exhausted(owner_id):
        text = "⏱️ Free 12-hour hosting has ended. Buy a plan from Account → Deposit to continue."
        if call_id: bot.answer_callback_query(call_id, text, show_alert=True)
        else: bot.send_message(message_obj.chat.id, "🛑 **Free Hosting Limit Finished**\n\n💎 Account → Deposit থেকে balance add করে একটি Plan কিনুন।", parse_mode="Markdown")
        return

    # A file must exist in the approved user_files table before it can run.
    if not any(str(n) == str(fname) for n, _ in user_files.get(owner_id, [])):
        if call_id:
            bot.answer_callback_query(call_id, "🔐 File is not approved yet.", show_alert=True)
        else:
            bot.send_message(message_obj.chat.id, "🔐 **File locked:** admin approval is required before it can run.")
        return

    # Free users can host for at most 12 hours per running process.
    if not has_active_plan(owner_id):
        # Existing free run can be continued only while its 12h timer is active.
        existing = bot_scripts.get(f"{owner_id}_{fname}")
        if existing:
            elapsed = (datetime.now() - existing["start_time"]).total_seconds() / 3600
            if elapsed >= 12:
                force_kill_user_bot(owner_id, fname)
                if call_id:
                    bot.answer_callback_query(call_id, "⏱️ Free 12-hour limit reached. Buy a plan.", show_alert=True)
                return

    if is_bot_running(owner_id, fname):
        if call_id: bot.answer_callback_query(call_id, "এই বোটটি অলরেডি রানিং আছে!", show_alert=True)
        return

    if call_id: bot.answer_callback_query(call_id, "Starting...")
    if ext == ".js":
        run_js_script(fpath, int(owner_id), ufolder, fname, message_obj)
    else:
        run_script(fpath, int(owner_id), ufolder, fname, message_obj)

# --- DB Files Operations ---
def save_user_file(user_id, file_name, file_type="py"):
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)", (user_id, file_name, file_type))
            conn.commit()
            conn.close()
            if user_id not in user_files: user_files[user_id] = []
            user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
    except Exception as e:
        logger.error(f"Error saving file to DB: {e}")

def remove_user_file_db(user_id, file_name):
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("DELETE FROM user_files WHERE user_id = ? AND file_name = ?", (user_id, file_name))
            conn.commit()
            conn.close()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
    except Exception as e:
        logger.error(f"Error removing file from DB: {e}")

def add_active_user(user_id):
    active_users.add(user_id)
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO active_users (user_id) VALUES (?)", (user_id,))
            conn.commit()
            conn.close()
    except Exception as e:
        logger.error(f"Error adding active user: {e}")

# --- UI Methods ---
def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row in layout_to_use:
        markup.add(*[make_reply_button(text) for text in row])
    return markup

def create_admin_panel_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        make_inline_button(f"{get_random_button_prefix('success')} 𝗔𝗱𝗱 𝗣𝗹𝗮𝗻", callback_data="add_plan"),
        make_inline_button(f"{get_random_button_prefix('danger')} 𝗥𝗲𝗺𝗼𝘃𝗲 𝗣𝗹𝗮𝗻", callback_data="remove_plan")
    )
    markup.add(
        make_inline_button("✅ 𝗔𝗽𝗽𝗿𝗼𝘃𝗲 𝗣𝗹𝗮𝗻 (Give VIP)", callback_data="give_plan")
    )
    markup.add(
        make_inline_button("➕ 𝗔𝗱𝗱 𝗖𝗵𝗮𝗻𝗻𝗲𝗹", callback_data="add_channel"),
        make_inline_button("➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗖𝗵𝗮𝗻𝗻𝗲𝗹", callback_data="remove_channel")
    )
    markup.add(
        make_inline_button("⚙️ 𝗦𝗲𝘁 𝗯𝗞𝗮𝘀𝗵 𝗡𝘂𝗺𝗯𝗲𝗿", callback_data="set_bkash"),
        make_inline_button("⚙️ 𝗦𝗲𝘁 𝗡𝗮𝗴𝗮𝗱 𝗡𝘂𝗺𝗯𝗲𝗿", callback_data="set_nagad")
    )
    markup.add(
        make_inline_button("📣 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁", callback_data="broadcast"),
        make_inline_button(f"{get_random_button_prefix('normal')} 𝗟𝗼𝗰𝗸/𝗨𝗻𝗹𝗼𝗰𝗸", callback_data="toggle_lock")
    )
    markup.add(
        make_inline_button("⚙️ 𝗥𝘂𝗻 𝗔𝗹𝗹 𝗦𝗰𝗿𝗶𝗽𝘁𝘀", callback_data="run_all_scripts"),
        make_inline_button("📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀", callback_data="stats")
    )
    markup.add(
        make_inline_button("🎥 𝗦𝗲𝘁 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹", callback_data="set_tutorial")
    )
    
    core_admins = {int(OWNER_ID), int(globals().get("SECOND_ADMIN_ID", 0) or 0)}
    if int(user_id) in core_admins:
        markup.add(
            make_inline_button("🟩 𝗔𝗱𝗱 𝗔𝗱𝗺𝗶𝗻", callback_data="add_admin"),
            make_inline_button("🟥 𝗥𝗲𝗺𝗼𝘃𝗲 𝗠𝘆 𝗔𝗱𝗺𝗶𝗻", callback_data="remove_admin")
        )
        markup.add(
            make_inline_button("🟦 𝗦𝗲𝘁 𝗕𝗼𝘁 𝗟𝗶𝗺𝗶𝘁", callback_data="set_limit"),
            make_inline_button("🟥 𝗕𝗹𝗼𝗰𝗸 𝗨𝘀𝗲𝗿", callback_data="block_user")
        )
        markup.add(make_inline_button("🟩 𝗨𝗻𝗯𝗹𝗼𝗰𝗸 𝗨𝘀𝗲𝗿", callback_data="unblock_user"))

    if int(user_id) == int(globals().get("SECOND_ADMIN_ID", 0) or 0):
        markup.add(
            make_inline_button("🟦 𝗗𝗕 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱", callback_data="db_download"),
            make_inline_button("🟨 𝗗𝗕 𝗨𝗽𝗹𝗼𝗮𝗱", callback_data="db_upload")
        )
    return markup


# --- Start & Menus ---
@bot.message_handler(commands=["start"])
def start_cmd(message):
    try:
        user_id = message.from_user.id
        if user_id in blocked_users:
            return 
            
        chat_id = message.chat.id
        user_name = message.from_user.first_name
        args = message.text.split()

        if bot_locked and user_id not in admin_ids:
            bot.send_message(chat_id, "⚠️ **Bot is temporarily locked by Admin.**")
            return

        add_active_user(user_id)
        
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("SELECT user_id FROM user_account WHERE user_id=?", (user_id,))
            if not c.fetchone():
                c.execute("INSERT INTO user_account (user_id, balance, total_referrals) VALUES (?, 0, 0)", (user_id,))
                if len(args) > 1:
                    ref_id = args[1]
                    if ref_id.isdigit() and int(ref_id) != user_id:
                        c.execute("UPDATE user_account SET total_referrals = total_referrals + 1 WHERE user_id=?", (int(ref_id),))
            conn.commit()
            conn.close()

        limit = get_user_file_limit(user_id)
        is_vip = is_vip_user(user_id)
        vip_status = "💎 VIP Member" if is_vip else "🆓 Free User"

        welcome_msg = (
            f"✨ **𝗪𝗲𝗹𝗰𝗼𝗺𝗲, {user_name}!** ✨\n\n"
            f"🆔 **𝗬𝗼𝘂𝗿 𝗜𝗗:** `{user_id}`\n"
            f"🔰 **𝗦𝘁𝗮𝘁𝘂𝘀:** `{vip_status}`\n"
            f"🔰 **𝗛𝗼𝘀𝘁𝗶𝗻𝗴 𝗟𝗶𝗺𝗶𝘁:** `{get_user_file_count(user_id)}` / `{limit}`\n\n"
            f"🔐 *Secure hosting is active — every upload needs admin approval.*\n"
            f"💡 *Python (.py) & JS (.js) hosting supported.*\n"
            f"👇 *Choose an option below to continue:* "
        )
        bot.send_message(chat_id, welcome_msg, reply_markup=create_reply_keyboard_main_menu(user_id), parse_mode="Markdown", protect_content=True)
    except Exception as e:
        logger.error(f"Error in start command: {e}")

def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.send_message(message.chat.id, "⚠️ **Bot is locked by Admin.**")
        return

    current_count = get_user_file_count(user_id)
    max_limit = get_user_file_limit(user_id)

    if current_count >= max_limit:
        bot.send_message(message.chat.id, f"⚠️ **আপনার আপলোড লিমিট শেষ!**\n\n📊 **বর্তমান আপলোড:** `{current_count}` / `{max_limit}`\n"
                              f"নতুন কোনো ফাইল রান করাতে `📁 Manage Files` থেকে যেকোনো একটি বোট ডিলিট করুন অথবা VIP Plan কিনুন।", parse_mode="Markdown")
        return

    bot.send_message(message.chat.id, "🚀 **আপনার Python (.py) অথবা JS (.js) বোট ফাইলটি মেসেজে আপলোড করুন।**\n"
                          "*(ফাইল দেওয়ার পর ফাইলটি সেভ হবে। এরপর Manage Files থেকে বোটটি চালু করতে হবে)*", parse_mode="Markdown")

def _logic_check_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.send_message(message.chat.id, "📂 **Your Uploaded Files:**\n\n*(No files uploaded yet)*", parse_mode="Markdown")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        status_icon = "🟢 Running" if is_running else "🔴 Stopped"
        btn_text = f"📄 {file_name} ({file_type}) - {status_icon}"
        markup.add(make_inline_button(btn_text, callback_data=f"file_{user_id}_{file_name}"))
    bot.send_message(message.chat.id, f"📁 **𝗠𝗮𝗻𝗮𝗴𝗲 𝗬𝗼𝘂𝗿 𝗙𝗶𝗹𝗲𝘀 ({len(user_files_list)}/{get_user_file_limit(user_id)}):**", reply_markup=markup, parse_mode="Markdown", protect_content=True)

def _logic_vip_plans(message):
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("SELECT plan_id, name, description, bot_limit, duration_days, price FROM plans")
            plans = c.fetchall()
            conn.close()

        if not plans:
            bot.send_message(message.chat.id, "❌ বর্তমানে কোনো VIP Plan নেই। এডমিনের সাথে যোগাযোগ করুন।")
            return

        bot.send_message(message.chat.id, "🌟 **আমাদের ভিআইপি (VIP) প্ল্যানসমূহ:**\nপছন্দমতো প্ল্যান বেছে নিন এবং নিরবচ্ছিন্ন আনলিমিটেড হোস্টিং উপভোগ করুন!", parse_mode="Markdown")
        
        for plan in plans:
            plan_id, name, desc, limit, days, price = plan
            plan_msg = (
                f"**{name}**\n"
                f"📝 **বিস্তারিত:** {desc}\n"
                f"🤖 **বট লিমিট:** `{limit} টি বোট`\n"
                f"⏳ **মেয়াদ:** `{days} দিন`\n"
                f"💰 **মূল্য:** `{price}`"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(make_inline_button("🛒 Buy Now", callback_data=f"buy_plan_{plan_id}"))
            bot.send_message(message.chat.id, plan_msg, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in VIP plans: {e}")
        bot.send_message(message.chat.id, "❌ Error loading plans.")

def _logic_tutorial(message):
    tut_link = get_setting("tutorial_link", UPDATE_CHANNEL)
    markup = types.InlineKeyboardMarkup()
    markup.add(make_inline_button("🎥 Watch Tutorial Video", url=tut_link))
    msg = (
        "🎥 **𝗛𝗼𝘄 𝗧𝗼 𝗨𝘀𝗲 & 𝗛𝗼𝘀𝘁 𝗕𝗼𝘁:**\n\n"
        "কীভাবে ফাইল আপলোড করতে হয় এবং সহজে আপনার বোট রান করাতে হয় তা শিখতে নিচের বাটনে ক্লিক করে ভিডিওটি দেখুন।"
    )
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown", protect_content=True)

def _logic_account(message):
    user_id = message.from_user.id
    balance, refs = get_user_account(user_id)
    try:
        bot_username = bot.get_me().username
    except:
        bot_username = "your_bot_username"
        
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    
    msg = (
        f"👤 **??𝘆 𝗔𝗰𝗰𝗼𝘂𝗻𝘁**\n\n"
        f"💰 **𝗕𝗮𝗹𝗮𝗻𝗰𝗲:** `{balance} BDT`\n"
        f"👥 **𝗧𝗼𝘁𝗮𝗹 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹𝘀:** `{refs}`\n"
        f"🔗 **𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗟𝗶𝗻𝗸:**\n`{ref_link}`\n\n"
        f"*(Note: রেফার করলে কোনো বোনাস থাকবে না)*"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(make_inline_button("💳 𝗗𝗲𝗽𝗼𝘀𝗶𝘁 (Add Money)", callback_data="deposit_init"))
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

def process_database_upload(message):
    """Restore SQLite DB only for SECOND_ADMIN_ID."""
    if int(message.from_user.id) != int(globals().get("SECOND_ADMIN_ID", 0) or 0):
        bot.send_message(message.chat.id, "❌ Database restore is restricted to the second bot admin.")
        return
    doc = getattr(message, "document", None)
    if not doc:
        bot.send_message(message.chat.id, "❌ Please send a `.db` or `.sqlite` file.")
        return
    name = os.path.basename(doc.file_name or "")
    if not name.lower().endswith((".db", ".sqlite", ".sqlite3")):
        bot.send_message(message.chat.id, "❌ Only SQLite `.db/.sqlite/.sqlite3` files are accepted.")
        return
    try:
        info = bot.get_file(doc.file_id)
        data = bot.download_file(info.file_path)
        if len(data) > 100 * 1024 * 1024:
            bot.send_message(message.chat.id, "❌ Database backup is too large (max 100 MB).")
            return

        tmp = DATABASE_PATH + ".restore.tmp"
        backup = DATABASE_PATH + ".before_restore.bak"
        with DB_LOCK:
            with open(tmp, "wb") as f:
                f.write(data)
            check = sqlite3.connect(tmp)
            try:
                result = check.execute("PRAGMA integrity_check").fetchone()
            finally:
                check.close()
            if not result or str(result[0]).lower() != "ok":
                os.remove(tmp)
                bot.send_message(message.chat.id, "❌ Database integrity check failed. Current database was not changed.")
                return
            if os.path.exists(DATABASE_PATH):
                shutil.copy2(DATABASE_PATH, backup)
            os.replace(tmp, DATABASE_PATH)

        # Refresh in-memory caches from restored DB.
        user_files.clear()
        active_users.clear()
        blocked_users.clear()
        admin_ids.clear()
        admin_ids.update({int(OWNER_ID), int(ADMIN_ID)})
        if int(globals().get("SECOND_ADMIN_ID", 0) or 0):
            admin_ids.add(int(globals().get("SECOND_ADMIN_ID")))
        load_data()

        bot.send_message(
            message.chat.id,
            "✅ **Database Restored Successfully**\n\n"
            "🛡️ Integrity check: passed\n"
            "💾 Previous DB backup: `.before_restore.bak`\n"
            "🔄 In-memory data: refreshed",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error("Database restore failed: %s", e, exc_info=True)
        try:
            if os.path.exists(DATABASE_PATH + ".restore.tmp"):
                os.remove(DATABASE_PATH + ".restore.tmp")
        except Exception:
            pass
        bot.send_message(message.chat.id, f"❌ **Database restore failed:** `{str(e)[:300]}`", parse_mode="Markdown")

# --- File Upload Handler ---
@bot.message_handler(content_types=["document"])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    doc_name = os.path.basename(getattr(message.document, "file_name", "") or "")
    if int(user_id) == int(globals().get("SECOND_ADMIN_ID", 0) or 0) and doc_name.lower().endswith((".db", ".sqlite", ".sqlite3")):
        process_database_upload(message); return
    if user_id in blocked_users: return
    if is_free_hosting_exhausted(user_id):
        bot.send_message(message.chat.id, "🛑 **Free Hosting Limit Finished**\n\nPlan ছাড়া আর নতুন bot upload করা যাবে না।\n💎 **Account → Deposit** থেকে balance add করে একটি Plan কিনুন।", parse_mode="Markdown"); return
    doc=message.document
    if getattr(doc,'file_size',0)>MAX_FILE_SIZE_BYTES:
        bot.send_message(message.chat.id, f"❌ **File too large.** Maximum `{MAX_FILE_SIZE_MB} MB`.", parse_mode="Markdown"); return
    current_count=get_user_file_count(user_id); max_limit=get_user_file_limit(user_id)
    file_name=os.path.basename(doc.file_name or 'uploaded_file'); file_name=re.sub(r"[^\w\-.]", "_", file_name)
    file_exists=any(f[0]==file_name for f in user_files.get(user_id,[]))
    if current_count>=max_limit and not file_exists:
        bot.send_message(message.chat.id, "❌ **Upload limit reached.** Delete an existing bot or upgrade your plan.", parse_mode="Markdown"); return
    file_ext=os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py','.js']:
        bot.send_message(message.chat.id, "⚠️ **Only `.py` and `.js` files are supported.**", parse_mode="Markdown"); return
    wait=None
    try:
        wait=bot.send_message(message.chat.id, f"⏳ **Uploading `{file_name}`...**", parse_mode="Markdown")
        info=bot.get_file(doc.file_id); data=bot.download_file(info.file_path)
        needs_review,risk_note=requires_admin_approval(data,file_name); user_folder=get_user_folder(user_id)
        if needs_review:
            request_id=uuid.uuid4().hex; pending_dir=os.path.join(user_folder,'.pending'); os.makedirs(pending_dir,exist_ok=True)
            pending_path=os.path.join(pending_dir,f"{request_id}_{file_name}")
            with open(pending_path,'wb') as f: f.write(data)
            save_pending_upload(request_id,user_id,file_name,file_ext[1:],pending_path,len(data),risk_note)
            send_approval_request_to_admins(request_id,user_id,file_name,pending_path,len(data),risk_note)
            status=("🔐 **Admin Review Required**\n\n"+f"📄 `{file_name}`\n"+"⏳ এই ফাইলে shell/CMD command পাওয়া গেছে। তাই Admin approval লাগবে।\nApprove হলে স্বয়ংক্রিয়ভাবে run হবে।")
            try: bot.edit_message_text(status,message.chat.id,wait.message_id,parse_mode='Markdown')
            except Exception: bot.send_message(message.chat.id,status,parse_mode='Markdown')
            return
        file_path=os.path.join(user_folder,file_name); force_kill_user_bot(user_id,file_name)
        with open(file_path,'wb') as f: f.write(data)
        save_user_file(user_id,file_name,file_ext[1:])
        ok=f"🟢 **File Uploaded Successfully**\n\n📄 `{file_name}`\n🚀 Your bot is starting automatically..."
        try: bot.edit_message_text(ok,message.chat.id,wait.message_id,parse_mode='Markdown')
        except Exception: bot.send_message(message.chat.id,ok,parse_mode='Markdown')
        do_start_bot(user_id,file_name,SimpleNamespace(chat=SimpleNamespace(id=message.chat.id)))
    except Exception as e:
        logger.error('File upload error: %s',e,exc_info=True); bot.send_message(message.chat.id,f"❌ **Upload error:** `{str(e)[:300]}`",parse_mode='Markdown')

# --- Callback Routing ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    try:
        user_id = call.from_user.id
        if user_id in blocked_users:
            return
            
        global bot_locked
        data = call.data

        if data.startswith(("file_", "start_", "verify_", "stop_", "del_", "instmod_", "viewlog_", "extend_")):
            parts = data.split("_")
            owner_id = int(parts[1])
            if user_id != owner_id and user_id not in admin_ids:
                bot.answer_callback_query(call.id, "❌ নিরাপত্তা সতর্কতা: এটি আপনার ফাইল নয়!", show_alert=True)
                return

        if data.startswith("approve_file_") and user_id in APPROVAL_ADMIN_IDS:
            request_id = data[len("approve_file_"):]
            result = finalize_approved_upload(request_id, user_id)
            if not result:
                bot.answer_callback_query(call.id, "Already processed or request not found.", show_alert=True)
                return
            if result[0] in ("missing", "error"):
                bot.answer_callback_query(call.id, "Approval failed.", show_alert=True)
                return

            _, target_uid, fname, file_path, risk_note = result
            bot.answer_callback_query(call.id, f"{get_random_button_prefix('success')} Approved", show_alert=True)
            try:
                bot.edit_message_caption(
                    f"🟢 <b>APPROVED</b>\n\n📄 <code>{fname}</code>\n👤 User: <code>{target_uid}</code>\n{risk_note}",
                    call.message.chat.id, call.message.message_id, parse_mode="HTML"
                )
            except Exception:
                pass
            for admin_uid in sorted(APPROVAL_ADMIN_IDS):
                if admin_uid == user_id:
                    continue
                for real_bot in BOT_INSTANCES:
                    try:
                        real_bot.send_message(admin_uid, f"🟢 **File approved successfully**\n📄 `{fname}`\n👤 User: `{target_uid}`")
                        break
                    except Exception:
                        pass
            try:
                bot.send_message(
                    target_uid,
                    f"🟢 **File Approved & Starting!**\n\n"
                    f"📄 `{fname}`\n"
                    
                    "🚀 Your file has been unlocked and the host is starting it now."
                )
            except Exception:
                pass
            try:
                do_start_bot(target_uid, fname, SimpleNamespace(chat=SimpleNamespace(id=target_uid)))
            except Exception as e:
                logger.error("Auto-start after approval failed: %s", e, exc_info=True)
                try:
                    bot.send_message(target_uid, f"⚠️ File approved, but auto-start failed. Open Manage Files and start `{fname}` manually.")
                except Exception:
                    pass
            return

        elif data.startswith("reject_file_") and user_id in APPROVAL_ADMIN_IDS:
            request_id = data[len("reject_file_"):]
            result = finalize_rejected_upload(request_id, user_id)
            if not result:
                bot.answer_callback_query(call.id, "Already processed or request not found.", show_alert=True)
                return

            _, target_uid, fname = result
            bot.answer_callback_query(call.id, f"{get_random_button_prefix('danger')} Rejected", show_alert=True)
            try:
                bot.edit_message_caption(
                    f"🔴 <b>FILE REJECTED</b>\n\n📄 <code>{fname}</code>\n👤 User: <code>{target_uid}</code>\n\n❌ Rejected successfully.",
                    call.message.chat.id, call.message.message_id, parse_mode="HTML"
                )
            except Exception:
                pass
            for admin_uid in sorted(APPROVAL_ADMIN_IDS):
                if admin_uid == user_id:
                    continue
                for real_bot in BOT_INSTANCES:
                    try:
                        real_bot.send_message(admin_uid, f"🔴 **File rejected successfully**\n📄 `{fname}`\n👤 User: `{target_uid}`")
                        break
                    except Exception:
                        pass
            try:
                bot.send_message(target_uid, f"🔴 **File Rejected**\n\n📄 `{fname}`\n\n❌ Your file was rejected.\n📤 You can upload another file.")
            except Exception:
                pass
            return

        if data == "show_vip_plans":
            bot.answer_callback_query(call.id)
            _logic_vip_plans(call.message)
            return

        if data == "db_download" and int(user_id) == int(globals().get("SECOND_ADMIN_ID", 0) or 0):
            try:
                with DB_LOCK:
                    if not os.path.exists(DATABASE_PATH):
                        bot.answer_callback_query(call.id, "Database not found.", show_alert=True)
                        return
                    with open(DATABASE_PATH, "rb") as dbf:
                        bot.send_document(
                            call.message.chat.id,
                            dbf,
                            caption="🗄️ **Database Backup**\n\nComplete bot database backup.",
                            parse_mode="Markdown"
                        )
                bot.answer_callback_query(call.id, "Database sent.", show_alert=True)
            except Exception as e:
                logger.error("DB download failed: %s", e, exc_info=True)
                bot.answer_callback_query(call.id, "Database download failed.", show_alert=True)
            return

        if data == "db_upload" and int(user_id) == int(globals().get("SECOND_ADMIN_ID", 0) or 0):
            msg = bot.send_message(
                call.message.chat.id,
                "⬆️ **Database Restore Mode**\n\n"
                "শুধু `.db` / `.sqlite` file পাঠান।\n"
                "⚠️ Current database-এর automatic backup তৈরি হবে, তারপর restore হবে."
            )
            bot.register_next_step_handler(msg, process_database_upload)
            return

        if data.startswith("buy_plan_"):
            plan_id = int(data.split("_")[2])
            
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute("SELECT name, duration_days, price FROM plans WHERE plan_id=?", (plan_id,))
                plan_row = c.fetchone()
                conn.close()
            
            if not plan_row:
                bot.answer_callback_query(call.id, "Plan not found!", show_alert=True)
                return
                
            plan_name, duration_days, price_text = plan_row
            
            try:
                price_num = int(''.join(filter(str.isdigit, str(price_text))))
            except ValueError:
                bot.answer_callback_query(call.id, "Error in plan price configuration.", show_alert=True)
                return
                
            balance, _ = get_user_account(user_id)
            
            if balance >= price_num:
                with DB_LOCK:
                    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                    c = conn.cursor()
                    c.execute("UPDATE user_account SET balance = balance - ? WHERE user_id=?", (price_num, user_id))
                    end_time = datetime.now() + timedelta(days=duration_days)
                    c.execute("INSERT OR REPLACE INTO user_subscriptions (user_id, plan_id, end_time, notified_warning) VALUES (?, ?, ?, 0)", (user_id, plan_id, end_time.isoformat()))
                    conn.commit()
                    conn.close()
                    
                bot.answer_callback_query(call.id, "✅ Plan Purchased Successfully!", show_alert=True)
                bot.send_message(call.message.chat.id, f"🎉 **অভিনন্দন!**\nআপনার **{plan_name}** প্ল্যানটি কেনা সফল হয়েছে।\nমেয়াদ: {duration_days} দিন।\nব্যালেন্স থেকে `{price_num} BDT` কাটা হয়েছে।", parse_mode="Markdown")
            else:
                bot.answer_callback_query(call.id, "❌ অপর্যাপ্ত ব্যালেন্স!", show_alert=True)
                bot.send_message(call.message.chat.id, f"❌ **অপর্যাপ্ত ব্যালেন্স!**\nপ্ল্যানটির দাম `{price_num} BDT`, কিন্তু আপনার একাউন্টে আছে `{balance} BDT`। দয়া করে 👤 Account থেকে ডিপোজিট করুন।", parse_mode="Markdown")

        elif data == "deposit_init":
            msg = bot.send_message(call.message.chat.id, "📝 **কত টাকা ডিপোজিট করতে চান? (শুধুমাত্র সংখ্যা লিখুন):**")
            bot.register_next_step_handler(msg, process_deposit_amount)

        elif data.startswith("dep_method_"):
            method = data.split("_")[2]
            if user_id not in temp_deposit:
                bot.answer_callback_query(call.id, "Session expired, try again.", show_alert=True)
                return
            temp_deposit[user_id]["method"] = method
            
            bkash_no = get_setting("bkash_number", DEFAULT_BKASH)
            nagad_no = get_setting("nagad_number", DEFAULT_NAGAD)
            
            number = bkash_no if method == "bkash" else nagad_no
            method_name = "বিকাশ (bKash)" if method == "bkash" else "নগদ (Nagad)"
            
            msg = bot.send_message(call.message.chat.id, 
                f"💳 **{method_name} পেমেন্ট**\n\n"
                f"🔹 **Number:** `{number}` (Send Money)\n"
                f"🔹 **Amount:** `{temp_deposit[user_id]['amount']} BDT`\n\n"
                f"📝 টাকা পাঠিয়ে **নিচে Transaction ID (TRX ID)** টি লিখুন:"
            )
            bot.register_next_step_handler(msg, process_deposit_trx)

        elif data.startswith("dep_app_") and user_id in admin_ids:
            parts = data.split("_")
            target_uid = int(parts[2])
            amount = int(parts[3])
            
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute("UPDATE user_account SET balance = balance + ? WHERE user_id=?", (amount, target_uid))
                conn.commit()
                conn.close()
            
            bot.edit_message_text(call.message.text + "\n\n✅ **APPROVED**", call.message.chat.id, call.message.message_id)
            try: bot.send_message(target_uid, f"✅ **আপনার {amount} BDT ডিপোজিট সফল হয়েছে এবং একাউন্টে যোগ করা হয়েছে!**")
            except: pass

        elif data.startswith("dep_rej_") and user_id in admin_ids:
            parts = data.split("_")
            target_uid = int(parts[2])
            amount = int(parts[3])
            
            bot.edit_message_text(call.message.text + "\n\n❌ **REJECTED**", call.message.chat.id, call.message.message_id)
            try: bot.send_message(target_uid, f"❌ **আপনার {amount} BDT ডিপোজিট রিকোয়েস্ট বাতিল করা হয়েছে।**\nপ্রয়োজনে এডমিনের সাথে যোগাযোগ করুন।")
            except: pass

        elif data.startswith("extend_"):
            bot.answer_callback_query(call.id, "💎 Free limit is 12 hours. Please buy a plan to continue.", show_alert=True)
            _logic_vip_plans(call.message)

        elif data.startswith("file_"):
            _, owner_id, fname = data.split("_", 2)
            is_running = is_bot_running(int(owner_id), fname)
            markup = types.InlineKeyboardMarkup(row_width=2)
            if is_running:
                markup.add(make_inline_button("🛑 Stop Bot", callback_data=f"stop_{owner_id}_{fname}"))
            else:
                markup.add(make_inline_button("▶️ Start Bot", callback_data=f"start_{owner_id}_{fname}"))
            markup.add(make_inline_button("🗑️ Delete Bot File", callback_data=f"del_{owner_id}_{fname}"))
            bot.send_message(call.message.chat.id, f"📄 **File:** `{fname}`\n🚦 Status: `{'🟢 Running' if is_running else '🔴 Stopped'}`", reply_markup=markup, parse_mode="Markdown", protect_content=True)

        elif data.startswith("start_"):
            _, owner_id, fname = data.split("_", 2)
            owner_id = int(owner_id)
            
            not_joined = check_force_sub(owner_id)
            if not_joined and owner_id not in admin_ids:
                markup = types.InlineKeyboardMarkup(row_width=1)
                for ch_id, ch_url in not_joined:
                    markup.add(make_inline_button("📢 Join Channel", url=ch_url))
                markup.add(make_inline_button("✅ Verify", callback_data=f"verify_{owner_id}_{fname}"))
                
                bot.send_message(call.message.chat.id, "⚠️ **আপনার বোট স্টার্ট করতে হলে প্রথমে আমাদের নিচের চ্যানেলগুলোতে জয়েন করুন:**", reply_markup=markup, parse_mode="Markdown")
                return
                
            do_start_bot(owner_id, fname, call.message, call.id)

        elif data.startswith("verify_"):
            _, owner_id, fname = data.split("_", 2)
            owner_id = int(owner_id)
            not_joined = check_force_sub(owner_id)
            
            if not_joined:
                bot.answer_callback_query(call.id, "❌ আপনি এখনো সব চ্যানেলে জয়েন করেননি!", show_alert=True)
            else:
                try: bot.delete_message(call.message.chat.id, call.message.message_id)
                except: pass
                do_start_bot(owner_id, fname, call.message, call.id)

        elif data.startswith("stop_"):
            _, owner_id, fname = data.split("_", 2)
            force_kill_user_bot(owner_id, fname)
            bot.answer_callback_query(call.id, "Stopped!")
            bot.send_message(call.message.chat.id, f"🛑 Script `{fname}` stopped successfully.", parse_mode="Markdown")

        elif data.startswith("del_"):
            _, owner_id, fname = data.split("_", 2)
            force_kill_user_bot(owner_id, fname)
                
            remove_user_file_db(int(owner_id), fname)
            ufolder = get_user_folder(int(owner_id))
            fpath = os.path.join(ufolder, fname)
            log_fpath = os.path.join(ufolder, f"{os.path.splitext(fname)[0]}.log")
            if os.path.exists(fpath): os.remove(fpath)
            if os.path.exists(log_fpath): os.remove(log_fpath)
            pycache_dir = os.path.join(ufolder, "__pycache__")
            if os.path.exists(pycache_dir): shutil.rmtree(pycache_dir, ignore_errors=True)
                
            bot.answer_callback_query(call.id, "Deleted!")
            bot.send_message(call.message.chat.id, f"🗑️ File `{fname}` completely deleted.", parse_mode="Markdown")

        elif data.startswith("instmod_"):
            bot.answer_callback_query(
                call.id,
                "Automatic package/shell installation is disabled for security.",
                show_alert=True
            )
            return

        elif data.startswith("viewlog_"):
            _, owner_id, fname = data.split("_", 2)
            log_fpath = os.path.join(get_user_folder(int(owner_id)), f"{os.path.splitext(fname)[0]}.log")
            if os.path.exists(log_fpath):
                with open(log_fpath, "r", encoding="utf-8", errors="ignore") as f: logs = f.read()[-2000:]
                bot.send_message(call.message.chat.id, f"📜 **Logs:**\n\n```\n{logs if logs else 'No logs'}\n```", parse_mode="Markdown", protect_content=True)
            else:
                bot.answer_callback_query(call.id, "No logs!", show_alert=True)

        elif data == "set_bkash" and user_id in admin_ids:
            msg = bot.send_message(call.message.chat.id, "📝 **বিকাশ পেমেন্ট নাম্বার দিন:**")
            bot.register_next_step_handler(msg, process_set_bkash)

        elif data == "set_nagad" and user_id in admin_ids:
            msg = bot.send_message(call.message.chat.id, "📝 **নগদ পেমেন্ট নাম্বার দিন:**")
            bot.register_next_step_handler(msg, process_set_nagad)

        elif data == "add_plan" and user_id in admin_ids:
            msg = bot.send_message(call.message.chat.id, "📝 **প্ল্যানের নাম এবং লোগো/ইমোজি দিন:** (যেমন: 💎 VIP Premium)")
            bot.register_next_step_handler(msg, process_plan_name)
            
        elif data == "remove_plan" and user_id in admin_ids:
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute("SELECT plan_id, name FROM plans")
                plans = c.fetchall()
                conn.close()
            
            if not plans:
                bot.answer_callback_query(call.id, "No plans found!", show_alert=True)
                return
                
            markup = types.InlineKeyboardMarkup()
            for p in plans:
                markup.add(make_inline_button(f"🗑️ Delete: {p[1]}", callback_data=f"delplan_{p[0]}"))
            bot.send_message(call.message.chat.id, "Select a plan to delete:", reply_markup=markup)

        elif data.startswith("delplan_") and user_id in admin_ids:
            plan_id = data.split("_")[1]
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute("DELETE FROM plans WHERE plan_id=?", (plan_id,))
                conn.commit()
                conn.close()
            bot.answer_callback_query(call.id, "Plan deleted!", show_alert=True)
            bot.send_message(call.message.chat.id, "✅ **প্ল্যান ডিলিট করা হয়েছে!**", parse_mode="Markdown")

        elif data == "give_plan" and user_id in admin_ids:
            msg = bot.send_message(call.message.chat.id, "📝 **যাকে প্ল্যান দিতে চান তার User ID দিন:**")
            bot.register_next_step_handler(msg, process_give_plan_userid)

        elif data.startswith("assign_plan_") and user_id in admin_ids:
            parts = data.split("_")
            target_uid = int(parts[2])
            plan_id = int(parts[3])
            
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute("SELECT duration_days, name FROM plans WHERE plan_id=?", (plan_id,))
                row = c.fetchone()
            
            if row:
                duration_days, plan_name = row
                end_time = datetime.now() + timedelta(days=duration_days)
                with DB_LOCK:
                    c.execute("INSERT OR REPLACE INTO user_subscriptions (user_id, plan_id, end_time, notified_warning) VALUES (?, ?, ?, 0)", (target_uid, plan_id, end_time.isoformat()))
                    conn.commit()
                bot.answer_callback_query(call.id, "Plan assigned!", show_alert=True)
                bot.send_message(call.message.chat.id, f"✅ User `{target_uid}` কে সফলভাবে **{plan_name}** দেওয়া হয়েছে!", parse_mode="Markdown")
                
                try:
                    bot.send_message(target_uid, f"🎉 **অভিনন্দন!**\nআপনাকে **{plan_name}** দেওয়া হয়েছে।\nমেয়াদ: {duration_days} দিন।\nনিরবচ্ছিন্ন হোস্টিং উপভোগ করুন!", parse_mode="Markdown")
                except:
                    pass
            try: conn.close()
            except: pass

        elif data == "set_tutorial" and user_id in admin_ids:
            msg = bot.send_message(call.message.chat.id, "📝 **নতুন টিউটোরিয়াল ভিডিও এর লিংকটি দিন (যেমন: https://youtu.be/...):**")
            bot.register_next_step_handler(msg, process_set_tutorial_link)

        elif data == "add_channel" and user_id in admin_ids:
            msg = bot.send_message(call.message.chat.id, "📝 **চ্যানেল অ্যাড করুন:**\nফরম্যাট: `@channel_id | https://t.me/link`")
            bot.register_next_step_handler(msg, process_add_channel)

        elif data == "remove_channel" and user_id in admin_ids:
            channels = get_force_channels()
            if not channels:
                bot.answer_callback_query(call.id, "No channels added!", show_alert=True)
                return
            markup = types.InlineKeyboardMarkup()
            for ch in channels:
                markup.add(make_inline_button(f"🗑️ Delete {ch[0]}", callback_data=f"del_ch_{ch[0]}"))
            bot.send_message(call.message.chat.id, "Select a channel to remove:", reply_markup=markup)

        elif data.startswith("del_ch_") and user_id in admin_ids:
            ch_id = data[7:]
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute("DELETE FROM force_channels WHERE channel_id=?", (ch_id,))
                conn.commit()
                conn.close()
            bot.answer_callback_query(call.id, "Channel removed successfully!", show_alert=True)
            bot.send_message(call.message.chat.id, f"✅ `{ch_id}` removed from Force Sub channels.")

        elif data == "add_admin" and int(user_id) in {int(OWNER_ID), int(globals().get("SECOND_ADMIN_ID", 0) or 0)}:
            msg = bot.send_message(call.message.chat.id, "📝 **যাকে এডমিন বানাতে চান তার User ID দিন:**")
            bot.register_next_step_handler(msg, process_add_admin)

        elif data == "remove_admin" and int(user_id) in {int(OWNER_ID), int(globals().get("SECOND_ADMIN_ID", 0) or 0)}:
            msg = bot.send_message(call.message.chat.id, "📝 **যাকে এডমিন থেকে রিমুভ করতে চান তার User ID দিন:**")
            bot.register_next_step_handler(msg, process_remove_admin)
            
        elif data == "set_limit" and int(user_id) == int(OWNER_ID):
            msg = bot.send_message(call.message.chat.id, "📝 **যাঁর লিমিট পরিবর্তন করতে চান তার User ID দিন (Manual):**")
            bot.register_next_step_handler(msg, process_set_limit_user)
            
        elif data == "block_user" and int(user_id) == int(OWNER_ID):
            msg = bot.send_message(call.message.chat.id, "📝 **যাকে ব্লক করতে চান তার User ID দিন:**")
            bot.register_next_step_handler(msg, process_manual_block)

        elif data == "unblock_user" and int(user_id) == int(OWNER_ID):
            msg = bot.send_message(call.message.chat.id, "📝 **যাকে আনব্লক করতে চান তার User ID দিন:**")
            bot.register_next_step_handler(msg, process_manual_unblock)

        elif data == "broadcast" and user_id in admin_ids:
            msg = bot.send_message(call.message.chat.id, "📝 **ব্রডকাস্ট করার জন্য মেসেজটি দিন:**\n(যেকোনো মেসেজ বা ছবি পাঠাতে পারেন)")
            bot.register_next_step_handler(msg, process_broadcast)

        elif data == "toggle_lock" and user_id in admin_ids:
            bot_locked = not bot_locked
            status = "🔒 Locked" if bot_locked else "🔓 Unlocked"
            bot.answer_callback_query(call.id, f"Bot is now {status}", show_alert=True)
            bot.send_message(call.message.chat.id, f"✅ **Bot Lock Status Changed to:** {status}", parse_mode="Markdown")

        elif data == "stats" and user_id in admin_ids:
            bot.answer_callback_query(call.id)
            msg = (
                f"📊 **𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀:**\n\n"
                f"👥 **Total Users:** `{len(active_users)}`\n"
                f"👑 **Total Admins:** `{len(admin_ids)}`\n"
                f"🚀 **Running Bots:** `{len(bot_scripts)}`\n"
                f"🔒 **Bot Locked Status:** `{bot_locked}`\n"
                f"🚫 **Blocked Users:** `{len(blocked_users)}`"
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

        elif data == "run_all_scripts" and user_id in admin_ids:
            bot.answer_callback_query(call.id, "Running all stopped scripts...")
            started_count = 0
            for uid, files in user_files.items():
                for fname, ftype in files:
                    if not is_bot_running(uid, fname):
                        ufolder = get_user_folder(uid)
                        fpath = os.path.join(ufolder, fname)
                        if os.path.exists(fpath) and any(str(n) == str(fname) for n, _ in user_files.get(int(uid), [])):
                            if ftype == "js":
                                run_js_script(fpath, uid, ufolder, fname, call.message)
                            else:
                                run_script(fpath, uid, ufolder, fname, call.message)
                            started_count += 1
                            time.sleep(1)
            bot.send_message(call.message.chat.id, f"✅ **Successfully started {started_count} scripts!**", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error handling callback {call.data}: {e}")

# --- Deposit Input Process Handlers ---
def process_deposit_amount(message):
    try:
        if message.text.isdigit():
            amount = int(message.text)
            if amount < 10:
                bot.send_message(message.chat.id, "❌ সর্বনিম্ন ১০ টাকা ডিপোজিট করতে হবে।")
                return
            temp_deposit[message.from_user.id] = {"amount": amount}
            
            markup = types.InlineKeyboardMarkup()
            markup.add(make_inline_button("🟣 bKash", callback_data="dep_method_bkash"),
                       make_inline_button("🟠 Nagad", callback_data="dep_method_nagad"))
            bot.send_message(message.chat.id, "💳 **পেমেন্ট মেথড সিলেক্ট করুন:**", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "❌ সঠিক পরিমাণ লিখুন (শুধুমাত্র সংখ্যা)।")
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Error processing deposit.")

def process_deposit_trx(message):
    try:
        user_id = message.from_user.id
        trx_id = message.text.strip()
        
        if user_id not in temp_deposit:
            bot.send_message(message.chat.id, "❌ সেশন শেষ হয়ে গেছে, আবার ডিপোজিট অপশনে ক্লিক করুন।")
            return
            
        amount = temp_deposit[user_id]["amount"]
        method = temp_deposit[user_id]["method"]
        del temp_deposit[user_id]
        
        admin_msg = (
            f"💰 **New Deposit Request**\n\n"
            f"👤 **User ID:** `{user_id}`\n"
            f"💵 **Amount:** `{amount}` BDT\n"
            f"🏦 **Method:** `{method.upper()}`\n"
            f"🔑 **TRX ID:** `{trx_id}`"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(
            make_inline_button("✅ Approve", callback_data=f"dep_app_{user_id}_{amount}"),
            make_inline_button("❌ Reject", callback_data=f"dep_rej_{user_id}_{amount}")
        )
        # Deposit review is available to both Core Admins.
        deposit_admins = {int(OWNER_ID), int(globals().get("SECOND_ADMIN_ID", 0) or 0)}
        sent = 0
        for admin_uid in sorted(x for x in deposit_admins if x):
            for real_bot in BOT_INSTANCES:
                try:
                    real_bot.send_message(admin_uid, admin_msg, reply_markup=markup, parse_mode="Markdown")
                    sent += 1
                    break
                except Exception:
                    pass
        bot.send_message(message.chat.id, "⏳ **আপনার ডিপোজিট রিকোয়েস্ট Core Adminদের কাছে পাঠানো হয়েছে। খুব শীঘ্রই review হবে।**")
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Error processing transaction ID.")

# --- Setting Process Handlers ---
def process_set_bkash(message):
    set_setting("bkash_number", message.text.strip())
    bot.send_message(message.chat.id, f"✅ **বিকাশ নাম্বার সেট করা হয়েছে:** {message.text.strip()}", parse_mode="Markdown")

def process_set_nagad(message):
    set_setting("nagad_number", message.text.strip())
    bot.send_message(message.chat.id, f"✅ **নগদ নাম্বার সেট করা হয়েছে:** {message.text.strip()}", parse_mode="Markdown")

# --- Plan Creation Process Handlers ---
admin_plan_temp = {}

def process_plan_name(message):
    name = message.text.strip()
    admin_plan_temp[message.chat.id] = {"name": name}
    msg = bot.send_message(message.chat.id, "📝 **প্ল্যানের বিস্তারিত বিবরণ দিন:**")
    bot.register_next_step_handler(msg, process_plan_desc)

def process_plan_desc(message):
    admin_plan_temp[message.chat.id]["desc"] = message.text.strip()
    msg = bot.send_message(message.chat.id, "📝 **কয়টি বট হোস্ট করা যাবে? (শুধুমাত্র সংখ্যা দিন):**")
    bot.register_next_step_handler(msg, process_plan_limit)

def process_plan_limit(message):
    try:
        limit = int(message.text.strip())
        admin_plan_temp[message.chat.id]["limit"] = limit
        msg = bot.send_message(message.chat.id, "📝 **মেয়াদ কতদিন? (শুধুমাত্র সংখ্যা দিন):**")
        bot.register_next_step_handler(msg, process_plan_days)
    except:
        bot.send_message(message.chat.id, "❌ সংখ্যা দিন। পুনরায় Add Plan এ ক্লিক করুন।")

def process_plan_days(message):
    try:
        days = int(message.text.strip())
        admin_plan_temp[message.chat.id]["days"] = days
        msg = bot.send_message(message.chat.id, "📝 **প্ল্যানের দাম কত? (শুধুমাত্র সংখ্যা দিন, যেমন: 150):**")
        bot.register_next_step_handler(msg, process_plan_price)
    except:
        bot.send_message(message.chat.id, "❌ সংখ্যা দিন। পুনরায় Add Plan এ ক্লিক করুন।")

def process_plan_price(message):
    price = message.text.strip()
    data = admin_plan_temp.get(message.chat.id)
    if not data: return
    
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT INTO plans (name, description, bot_limit, duration_days, price) VALUES (?, ?, ?, ?, ?)", 
                 (data["name"], data["desc"], data["limit"], data["days"], price))
        conn.commit()
        conn.close()
        
    bot.send_message(message.chat.id, f"✅ **প্ল্যান সফলভাবে অ্যাড হয়েছে!**\n\nনাম: {data['name']}\nলিমিট: {data['limit']}\nদিন: {data['days']}\nদাম: {price}", parse_mode="Markdown")

def process_give_plan_userid(message):
    try:
        target_uid = int(message.text.strip())
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("SELECT plan_id, name FROM plans")
            plans = c.fetchall()
            conn.close()
        
        if not plans:
            bot.send_message(message.chat.id, "❌ কোনো প্ল্যান তৈরি করা নেই। আগে Add Plan করুন।")
            return
            
        markup = types.InlineKeyboardMarkup()
        for p in plans:
            markup.add(make_inline_button(f"✅ Give: {p[1]}", callback_data=f"assign_plan_{target_uid}_{p[0]}"))
        
        bot.send_message(message.chat.id, f"User `{target_uid}` কে কোন প্ল্যান দিতে চান সিলেক্ট করুন:", reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, "❌ ভুল User ID!")

# --- Other Admin Process Handlers ---
def process_set_tutorial_link(message):
    try:
        url = message.text.strip()
        if url.startswith("http://") or url.startswith("https://"):
            set_setting("tutorial_link", url)
            bot.send_message(message.chat.id, f"✅ **টিউটোরিয়াল লিংক সফলভাবে আপডেট করা হয়েছে!**\n\n🔗 `{url}`", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ **ভুল লিংক!** সঠিক লিংক দিন (http:// বা https:// দিয়ে শুরু হতে হবে)।")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ **Error:** {str(e)}")

def process_add_channel(message):
    try:
        parts = [p.strip() for p in message.text.split("|")]
        ch_id, ch_url = parts[0], parts[1]
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO force_channels (channel_id, channel_url) VALUES (?, ?)", (ch_id, ch_url))
            conn.commit()
            conn.close()
        bot.send_message(message.chat.id, f"✅ চ্যানেল সফলভাবে যুক্ত করা হয়েছে: {ch_id}")
    except:
        bot.send_message(message.chat.id, "❌ ভুল ফরম্যাট! সঠিক নিয়মে দিন: `@channel_id | https://t.me/link`")

def process_add_admin(message):
    try:
        new_admin = int(message.text.strip())
        actor = int(message.from_user.id)
        protected = {int(OWNER_ID), int(globals().get("SECOND_ADMIN_ID", 0) or 0)}
        if actor not in protected:
            bot.send_message(message.chat.id, "❌ Permission denied.")
            return
        if new_admin in protected:
            bot.send_message(message.chat.id, "🛡️ Core Admin-কে add/remove করা যাবে না.")
            return
        admin_ids.add(new_admin)
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO admins (user_id, added_by) VALUES (?, ?)", (new_admin, actor))
            conn.commit()
            conn.close()
        bot.send_message(message.chat.id, f"✅ `{new_admin}` সফলভাবে আপনার admin list-এ যুক্ত হয়েছে!\\n🔐 শুধু আপনিই এই admin-কে remove করতে পারবেন.", parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল User ID! সঠিক সংখ্যা দিন.")


def process_remove_admin(message):
    try:
        rem_admin = int(message.text.strip())
        actor = int(message.from_user.id)
        protected = {int(OWNER_ID), int(globals().get("SECOND_ADMIN_ID", 0) or 0)}
        # Core accounts are intentionally invisible to the self-admin removal flow.
        # Do not reveal their protected status; report the same result as a missing admin.
        if rem_admin in protected:
            bot.send_message(message.chat.id, "❌ Admin not found.")
            return
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("SELECT added_by FROM admins WHERE user_id=?", (rem_admin,))
            row = c.fetchone()
            if not row:
                conn.close()
                bot.send_message(message.chat.id, "❌ Admin not found.")
                return
            if int(row[0] or 0) != actor:
                conn.close()
                # Do not expose who added the admin or which protected relationship exists.
                bot.send_message(message.chat.id, "❌ Admin not found.")
                return
            c.execute("DELETE FROM admins WHERE user_id=?", (rem_admin,))
            conn.commit()
            conn.close()
        admin_ids.discard(rem_admin)
        bot.send_message(message.chat.id, f"✅ `{rem_admin}` আপনার admin list থেকে remove করা হয়েছে.", parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল User ID! সঠিক সংখ্যা দিন.")


def process_set_limit_user(message):
    try:
        target_user = int(message.text.strip())
        msg = bot.send_message(message.chat.id, f"📝 **`{target_user}` এর জন্য নতুন লিমিট (কয়টি বোট রান করতে পারবে) দিন:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: process_set_limit_value(m, target_user))
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল User ID! সঠিক সংখ্যা দিন।")

def process_set_limit_value(message, target_user):
    try:
        new_limit = int(message.text.strip())
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO custom_limits (user_id, max_limit) VALUES (?, ?)", (target_user, new_limit))
            conn.commit()
            conn.close()
        bot.send_message(message.chat.id, f"✅ **Success!**\n`{target_user}` এর নতুন বোট লিমিট `{new_limit}` সেট করা হয়েছে!", parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল লিমিট! সঠিক সংখ্যা দিন।")

def process_manual_block(message):
    try:
        target_user = int(message.text.strip())
        if target_user in admin_ids:
            bot.send_message(message.chat.id, "❌ অ্যাডমিনকে ব্লক করা যাবে না!")
            return
        
        blocked_users.add(target_user)
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO blocked_users (user_id) VALUES (?)", (target_user,))
            conn.commit()
            conn.close()
            
        bot.send_message(message.chat.id, f"✅ `{target_user}` কে সফলভাবে ব্লক করা হয়েছে।")
        try: bot.send_message(target_user, "🚫 **আপনাকে বট থেকে স্থায়ীভাবে ব্লক করা হয়েছে!**\nকারণ: এডমিন রুলস ভঙ্গের কারণে ব্লক করেছেন।")
        except: pass
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল User ID! সঠিক সংখ্যা দিন।")

def process_manual_unblock(message):
    try:
        target_user = int(message.text.strip())
        if target_user in blocked_users:
            blocked_users.remove(target_user)
            
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("DELETE FROM blocked_users WHERE user_id = ?", (target_user,))
            conn.commit()
            conn.close()
            
        bot.send_message(message.chat.id, f"✅ `{target_user}` কে সফলভাবে আনব্লক করা হয়েছে।")
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল User ID! সঠিক সংখ্যা দিন।")

def process_broadcast(message):
    success = 0
    failed = 0
    bot.send_message(message.chat.id, "⏳ **ব্রডকাস্ট শুরু হয়েছে...**", parse_mode="Markdown")
    for user in list(active_users):
        try:
            bot.copy_message(user, message.chat.id, message.message_id)
            success += 1
            time.sleep(0.05)
        except Exception:
            failed += 1
    bot.send_message(message.chat.id, f"✅ **ব্রডকাস্ট শেষ!**\n\n🟢 **সফল:** `{success}`\n🔴 **ব্যর্থ:** `{failed}`", parse_mode="Markdown")

# --- Text Handler Mapping ---
BUTTON_MAPPING = {
    "✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨": lambda m: bot.send_message(m.chat.id, f"📢 **Join channel:** {UPDATE_CHANNEL}"),
    "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹": _logic_tutorial,
    "🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲": _logic_upload_file,
    "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀": _logic_check_files,
    "💎 𝗩𝗜𝗣 𝗣𝗹𝗮𝗻𝘀": _logic_vip_plans,
    "👤 𝗔𝗰𝗰𝗼𝘂𝗻𝘁": _logic_account,
    "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴": lambda m: bot.send_message(m.chat.id, "⚡ **Bot Latency:** `12 ms` (Server Active)"),
    "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀": lambda m: bot.send_message(m.chat.id, f"📊 **Active Users:** `{len(active_users)}`\n🚀 **Running Bots:** `{len(bot_scripts)}`\n🚫 **Blocked Users:** `{len(blocked_users)}`", parse_mode="Markdown"),
    "🔐 𝗦𝗲𝗰𝘂𝗿𝗶𝘁𝘆": lambda m: bot.send_message(
        m.chat.id,
        "🔐 **Premium Security Mode Active**\n\n"
        "• Every upload requires admin approval\n"
        "• One admin approval unlocks a file\n"
        "• Automatic shell/CMD/package installation is disabled\n"
        "• Pending files remain locked",
        parse_mode="Markdown"
    ),
}

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    try:
        user_id = message.from_user.id
        if user_id in blocked_users:
            return
            
        text = message.text
        if text == "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹" and user_id in admin_ids:
            bot.send_message(
                message.chat.id,
                "🛡️ **𝗔𝗗𝗠𝗜𝗡 𝗖𝗢𝗡𝗧𝗥𝗢𝗟 𝗖𝗘𝗡𝗧𝗘𝗥**\n\n"
                "🔐 Secure review • Hosting control • User management",
                reply_markup=create_admin_panel_inline(user_id)
            )
            return
            
        if text == "👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿":
            bot.send_message(message.chat.id, f"👑 **Owner:** {YOUR_USERNAME}")
            return

        action = BUTTON_MAPPING.get(text)
        if action:
            action(message)
    except Exception as e:
        logger.error(f"Error handling message text: {e}")

# =====================================================================
# SECOND BOT CONFIGURATION
# Keep these values after the main code as requested.
# Replace only the two placeholders below.
# =====================================================================
SECOND_BOT_TOKEN = "8878740674:AAGjpP6fs05vFSdqnNrGYA371GKVgS6vZy4"
SECOND_ADMIN_ID = 8970341588

APPROVAL_ADMIN_IDS = {int(OWNER_ID), int(ADMIN_ID)}
if SECOND_ADMIN_ID:
    APPROVAL_ADMIN_IDS.add(int(SECOND_ADMIN_ID))
    admin_ids.add(int(SECOND_ADMIN_ID))
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        conn.execute("INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)", (int(SECOND_ADMIN_ID), 0))
        conn.commit()
        conn.close()

BOT_INSTANCES = [telebot.TeleBot(TOKEN)]
if SECOND_BOT_TOKEN and SECOND_BOT_TOKEN != "PUT_NEW_BOT_TOKEN_HERE":
    BOT_INSTANCES.append(telebot.TeleBot(SECOND_BOT_TOKEN))

bot._default = BOT_INSTANCES[0]

def _register_proxy_handlers():
    for real_bot in BOT_INSTANCES:
        for kind, args, kwargs, func in bot._handlers:
            def wrapped(update, _func=func, _real_bot=real_bot):
                bot.bind(_real_bot)
                return _func(update)
            if kind == "message":
                real_bot.message_handler(*args, **kwargs)(wrapped)
            else:
                real_bot.callback_query_handler(*args, **kwargs)(wrapped)

_register_proxy_handlers()

# --- App Start ---
def _poll_bot(real_bot, label):
    bot.bind(real_bot)
    logger.info("%s polling started.", label)
    while True:
        try:
            real_bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except telebot.apihelper.ApiException as e:
            logger.error("%s Telegram API error: %s", label, e)
            time.sleep(15)
        except Exception as e:
            logger.error("%s polling error: %s", label, e)
            time.sleep(15)

if __name__ == "__main__":
    keep_alive()
    Thread(target=auto_stopper, daemon=True).start()
    logger.info("🚀 Premium File Host is starting with %d Telegram bot(s)...", len(BOT_INSTANCES))
    for idx, real_bot in enumerate(BOT_INSTANCES, 1):
        Thread(target=_poll_bot, args=(real_bot, f"BOT-{idx}"), daemon=True).start()
    while True:
        time.sleep(3600)
0)
