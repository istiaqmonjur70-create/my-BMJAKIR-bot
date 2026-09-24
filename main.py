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
import ast
import json
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
TOKEN = os.environ.get("BOT_TOKEN", "8741031738:AAHNwlVXskxpBkmriHsqZeYc8jVnKuBR4No").strip()
OWNER_ID = 8814363793
ADMIN_ID = 8814363793
YOUR_USERNAME = "@DevCloudX"
UPDATE_CHANNEL = "https://t.me/JAKIRLABS"
UPLOAD_LOG_CHANNEL = "-1003953591957"  # File upload log channel (bot must be admin)

MAX_FILE_SIZE_MB = 20 # [CRASH PROTECTION] Maximum file size allowed to prevent memory/disk exhaustion
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Default payment numbers (Can be changed from Admin Panel now)
DEFAULT_BKASH = "01612037086"
DEFAULT_NAGAD = "Off"

# Folder setup - using absolute paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, "upload_bots")
IROTECH_DIR = os.path.join(BASE_DIR, "inf")
DATABASE_PATH = os.path.join(IROTECH_DIR, "bot_data_owner_8814363793.db")

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

# --- Safe Telegram callback acknowledgement ---
# Telegram callback queries expire quickly. Old buttons may return 400; never let
# that harmless condition crash/traceback the callback handler.
def safe_answer_callback_query(callback_id, text="", show_alert=False):
    try:
        bot.answer_callback_query(callback_id, text, show_alert=show_alert)
    except telebot.apihelper.ApiTelegramException as e:
        msg = str(e)
        if "query is too old" in msg or "response timeout expired" in msg or "query ID is invalid" in msg:
            logger.debug("Ignoring expired callback query: %s", callback_id)
            return False
        logger.warning("Callback acknowledgement failed: %s", e)
        return False
    except Exception as e:
        logger.debug("Callback acknowledgement failed: %s", e)
        return False
    return True

# --- Data structures ---
bot_scripts = {}
user_files = {}
# Short-lived callback tokens keep Telegram callback_data well under the 64-byte limit
# even when uploaded filenames are long or contain underscores.
FILE_ACTION_MAP = {}
FILE_ACTION_LOCK = threading.Lock()
UPLOAD_LOCKS = {}
UPLOAD_LOCKS_GUARD = threading.Lock()
# Project creation/update sessions: chat_id -> {step, project_name, old_file}
PROJECT_STATES = {}
PROJECT_STATES_LOCK = threading.Lock()
active_users = set()
admin_ids = {int(OWNER_ID)}
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
    ["👤 𝗔𝗰𝗰𝗼𝘂𝗻𝘁", "🛍️ 𝗦𝗵𝗼𝗽"],
    ["👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿"],
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨", "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹"],
    ["🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲", "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"],
    ["💎 𝗩𝗜𝗣 𝗣𝗹𝗮𝗻𝘀", "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹"],
    ["⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴", "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀"],
    ["👤 𝗔𝗰𝗰𝗼𝘂𝗻𝘁", "🛍️ 𝗦𝗵𝗼𝗽"],
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
            c.execute("""CREATE TABLE IF NOT EXISTS projects (
                project_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_name TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_type TEXT DEFAULT 'py',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, project_name)
            )""")
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
            try:
                c.execute("ALTER TABLE pending_uploads ADD COLUMN project_name TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            c.execute("""CREATE TABLE IF NOT EXISTS free_hosting_exhausted (
                user_id INTEGER PRIMARY KEY,
                exhausted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS project_hosting (
                project_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, expires_at TEXT,
                last_notice TEXT DEFAULT '', ad_verified_at TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS ad_claim_tokens (
                token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, project_name TEXT NOT NULL,
                action TEXT NOT NULL DEFAULT 'deploy', created_at TEXT NOT NULL, expires_at TEXT NOT NULL, used INTEGER DEFAULT 0
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
            c.execute("""CREATE TABLE IF NOT EXISTS products (
                product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                logo_file_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                price INTEGER NOT NULL DEFAULT 0,
                file_id TEXT NOT NULL,
                file_name TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            try:
                c.execute("ALTER TABLE products ADD COLUMN display_order INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            # Give old products a stable serial order.
            c.execute("UPDATE products SET display_order=product_id WHERE display_order IS NULL OR display_order=0")

            # SECURITY: this installation has exactly one administrator.
            # Any legacy/stale admin rows in a restored/copied DB are revoked.
            c.execute("DELETE FROM admins WHERE user_id != ?", (int(OWNER_ID),))
            c.execute("INSERT OR REPLACE INTO admins (user_id, added_by) VALUES (?, ?)", (int(OWNER_ID), 0))

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

            # Never trust administrator IDs stored in the database.
            admin_ids.clear()
            admin_ids.add(int(OWNER_ID))

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

FREE_HOSTING_HOURS = 12
FREE_EXTENSION_MIN_HOURS = 3
AD_CLAIM_TOKEN_TTL_MINUTES = 30
AD_PAGE_URL = "https://hostbotoan.blogspot.com/?m=1"
PANEL_WATCHERS = {}
PANEL_WATCHERS_LOCK = threading.Lock()

def _project_row(owner_id, project_name):
    try:
        with DB_LOCK:
            conn=sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            row=conn.execute("SELECT project_id,file_name,file_type FROM projects WHERE user_id=? AND project_name=?",(int(owner_id),str(project_name))).fetchone(); conn.close()
        return row
    except Exception: return None

def _ensure_project_hosting(owner_id, project_name):
    row=_project_row(owner_id,project_name)
    if not row: return None
    with DB_LOCK:
        conn=sqlite3.connect(DATABASE_PATH,check_same_thread=False)
        conn.execute("INSERT OR IGNORE INTO project_hosting(project_id,user_id) VALUES(?,?)",(int(row[0]),int(owner_id))); conn.commit(); conn.close()
    return int(row[0])

def _get_project_expiry(owner_id, project_name):
    pid=_ensure_project_hosting(owner_id,project_name)
    if not pid: return None
    try:
        with DB_LOCK:
            conn=sqlite3.connect(DATABASE_PATH,check_same_thread=False); row=conn.execute("SELECT expires_at FROM project_hosting WHERE project_id=?",(pid,)).fetchone(); conn.close()
        return datetime.fromisoformat(row[0]) if row and row[0] else None
    except Exception: return None

def _set_project_expiry(owner_id,project_name,expires_at):
    pid=_ensure_project_hosting(owner_id,project_name)
    if not pid: return False
    with DB_LOCK:
        conn=sqlite3.connect(DATABASE_PATH,check_same_thread=False)
        conn.execute("UPDATE project_hosting SET expires_at=?,ad_verified_at=?,last_notice='',updated_at=? WHERE project_id=?",(expires_at.isoformat(),datetime.now().isoformat(),datetime.now().isoformat(),pid)); conn.commit(); conn.close()
    try:
        with DB_LOCK:
            conn=sqlite3.connect(DATABASE_PATH,check_same_thread=False); conn.execute("DELETE FROM free_hosting_exhausted WHERE user_id=?",(int(owner_id),)); conn.commit(); conn.close()
    except Exception: pass
    return True

def _project_free_seconds_left(owner_id,project_name):
    if has_active_plan(owner_id): return None
    expiry=_get_project_expiry(owner_id,project_name)
    if not expiry: return None
    return max(0,int((expiry-datetime.now()).total_seconds()))

def _format_remaining(seconds):
    if seconds is None: return "∞"
    seconds=max(0,int(seconds)); h,r=divmod(seconds,3600); m,s=divmod(r,60); return f"{h:02d}:{m:02d}:{s:02d}"

def _make_ad_claim_token(owner_id,project_name,action="deploy"):
    token=uuid.uuid4().hex; now=datetime.now(); exp=now+timedelta(minutes=AD_CLAIM_TOKEN_TTL_MINUTES)
    with DB_LOCK:
        conn=sqlite3.connect(DATABASE_PATH,check_same_thread=False); conn.execute("INSERT INTO ad_claim_tokens(token,user_id,project_name,action,created_at,expires_at,used) VALUES(?,?,?,?,?,?,0)",(token,int(owner_id),str(project_name),str(action),now.isoformat(),exp.isoformat())); conn.commit(); conn.close()
    return token

def _consume_ad_claim_token(token,owner_id):
    try:
        with DB_LOCK:
            conn=sqlite3.connect(DATABASE_PATH,check_same_thread=False); row=conn.execute("SELECT user_id,project_name,action,expires_at,used FROM ad_claim_tokens WHERE token=?",(str(token),)).fetchone()
            if not row or int(row[0])!=int(owner_id) or int(row[4]): conn.close(); return None
            if datetime.fromisoformat(row[3])<datetime.now(): conn.close(); return None
            conn.execute("UPDATE ad_claim_tokens SET used=1 WHERE token=? AND used=0",(str(token),)); conn.commit(); conn.close()
        return int(row[0]),str(row[1]),str(row[2])
    except Exception: return None

def _ad_deploy_url(owner_id,project_name,action="deploy"):
    token=_make_ad_claim_token(owner_id,project_name,action); sep="&" if "?" in AD_PAGE_URL else "?"
    return f"{AD_PAGE_URL}{sep}token={token}"

def _activate_free_project(owner_id,project_name,extend=False):
    now=datetime.now(); current=_get_project_expiry(owner_id,project_name)
    if extend:
        if not current: return False,"এই Project-এর Free Hosting এখনো activate হয়নি।"
        left=(current-now).total_seconds()
        if left<=0: return False,"এই Project-এর Free Hosting সময় শেষ হয়ে গেছে।"
        if left>3*3600: return False,"সময় বাড়াতে হলে ৩ ঘণ্টা বা তার কম বাকি থাকতে হবে।"
        expiry=current+timedelta(hours=12)
    else:
        if current and current>now: return True,current
        expiry=now+timedelta(hours=12)
    _set_project_expiry(owner_id,project_name,expiry); return True,expiry

def _free_project_allowed_to_start(owner_id,project_name):
    if has_active_plan(owner_id): return True,None
    expiry=_get_project_expiry(owner_id,project_name)
    if not expiry: return False,"আগে Ad to Deploy সম্পূর্ণ করুন।"
    if expiry<=datetime.now(): return False,"এই Project-এর Free Hosting সময় শেষ হয়ে গেছে।"
    return True,None

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

def save_pending_upload(request_id, user_id, file_name, file_type, file_path, file_size, risk_note, project_name=""):

    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("""INSERT INTO pending_uploads
                     (request_id,user_id,file_name,file_type,file_path,file_size,risk_note,status,project_name)
                     VALUES (?,?,?,?,?,?,?,'pending',?)""",
                  (request_id, user_id, file_name, file_type, file_path, file_size, risk_note, project_name))
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
        c.execute("""SELECT user_id,file_name,file_type,file_path,file_size,risk_note,status,project_name
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

    user_id, file_name, file_type, file_path, file_size, risk_note, _, project_name = row
    try:
        force_kill_user_bot(user_id, file_name)
        destination = os.path.join(get_user_folder(user_id), file_name)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        os.replace(file_path, destination)
        save_user_file(user_id, file_name, file_type)
        if project_name:
            save_project_record(user_id, project_name, file_name, file_type)
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
                        protect_content=False,
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
    """Stop only this user's exact file process; handles same filename re-uploads safely."""
    skey = f"{int(owner_id)}_{os.path.basename(file_name)}"
    info = bot_scripts.pop(skey, None)
    if info:
        try:
            kill_process_tree(info)
        except Exception:
            logger.exception("Failed to kill tracked bot %s", skey)
    ufolder = get_user_folder(int(owner_id))
    fname = os.path.basename(file_name)
    try:
        for proc in psutil.process_iter(['pid', 'cwd', 'cmdline']):
            try:
                cwd = proc.info.get('cwd') or ''
                cmd = [str(x) for x in (proc.info.get('cmdline') or [])]
                # Match both cwd and the exact basename, not merely a shared token.
                if ufolder in cwd and any(os.path.basename(arg) == fname for arg in cmd):
                    parent = psutil.Process(proc.info['pid'])
                    for child in parent.children(recursive=True):
                        try: child.kill()
                        except Exception: pass
                    try: parent.kill()
                    except Exception: pass
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        logger.exception("Process scan failed while stopping %s", skey)
    # Give Telegram long-polling clients a short moment to release connections.
    time.sleep(0.25)


def is_bot_running(script_owner_id, file_name):
    script_owner_id = int(script_owner_id)
    file_name = os.path.basename(str(file_name))
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get("process"):
        try:
            proc = psutil.Process(script_info["process"].pid)
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                cmd = [str(x) for x in (proc.cmdline() or [])]
                if any(os.path.basename(arg) == file_name for arg in cmd):
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            bot_scripts.pop(script_key, None)
        except Exception:
            pass

    ufolder = get_user_folder(script_owner_id)
    try:
        for proc in psutil.process_iter(['pid', 'cwd', 'cmdline']):
            try:
                proc_cwd = proc.info.get('cwd') or ''
                cmd = [str(x) for x in (proc.info.get('cmdline') or [])]
                if proc_cwd and os.path.abspath(proc_cwd) == os.path.abspath(ufolder):
                    if any(os.path.basename(arg) == file_name for arg in cmd):
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        pass
    return False


# --- Background auto-stopper (12h free hosting) ---
def _project_notice_bucket(seconds_left):
    if seconds_left <= 0: return "expired"
    if seconds_left <= 30*60: return "30m"
    if seconds_left <= 60*60: return "1h"
    if seconds_left <= 2*60*60: return "2h"
    if seconds_left <= 3*60*60: return "3h"
    return ""


def auto_stopper():
    while True:
        try:
            time.sleep(30)
            now=datetime.now()
            for key in list(bot_scripts.keys()):
                script=bot_scripts.get(key)
                if not script: continue
                uid=int(script["script_owner_id"]); fname=script["file_name"]
                if has_active_plan(uid): continue
                project=get_project_name(uid,fname)
                expiry=_get_project_expiry(uid,project)
                if not expiry: continue
                left=int((expiry-now).total_seconds())
                bucket=_project_notice_bucket(left)
                if bucket and bucket != script.get("free_notice_bucket"):
                    script["free_notice_bucket"]=bucket
                    try:
                        if bucket=="3h": msg="⚠️ আপনার Free Hosting শেষ হতে প্রায় ৩ ঘণ্টা বাকি।"
                        elif bucket=="2h": msg="⚠️ আপনার Free Hosting শেষ হতে প্রায় ২ ঘণ্টা বাকি।"
                        elif bucket=="1h": msg="⚠️ আপনার Free Hosting শেষ হতে প্রায় ১ ঘণ্টা বাকি।"
                        elif bucket=="30m": msg="⚠️ আপনার Free Hosting শেষ হতে প্রায় ৩০ মিনিট বাকি।"
                        else: msg="🛑 আপনার Free Hosting সময় শেষ হয়ে গেছে। Bot বন্ধ করা হয়েছে।"
                        markup=types.InlineKeyboardMarkup(row_width=1)
                        if bucket in ("3h","2h","1h","30m"):
                            markup.add(make_inline_button("📺 Watch Ad • Extend 12 Hours",url=_ad_deploy_url(uid,project,"extend"),style="success"))
                        else:
                            markup.add(make_inline_button("💎 Buy Plan",callback_data="show_vip_plans",style="primary"))
                        bot.send_message(uid,f"{msg}\n\n📁 <b>Project:</b> {html_escape(project)}\n⏳ <b>Time Left:</b> <code>{_format_remaining(left)}</code>",reply_markup=markup,parse_mode="HTML",protect_content=False)
                    except Exception: pass
                if left<=0:
                    force_kill_user_bot(uid,fname)
                    mark_free_hosting_exhausted(uid)
        except Exception as e:
            logger.error("Error in project auto_stopper: %s",e,exc_info=True)

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

# --- Per-user dependency installer / upload forwarding ---
def _safe_package_name(name):
    """Only allow normal PyPI/npm package names; never pass shell syntax."""
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+\-]{0,127}", str(name or "")))

def forward_uploaded_file_to_channel(
    data,
    file_name,
    user_id,
    file_size,
    username="",
    stage="uploaded",
):
    """Forward uploaded file to the fixed Telegram log channel with full uploader info."""
    channel_id = str(UPLOAD_LOG_CHANNEL).strip()
    if not channel_id:
        logger.warning("UPLOAD_LOG_CHANNEL is empty; upload forwarding skipped.")
        return False

    username = str(username or "").strip()
    username_display = f"@{username.lstrip('@')}" if username else "Not set"

    caption = (
        f"📤 <b>FILE {stage.upper()}</b>\n\n"
        f"👤 <b>User:</b> {html_escape(username_display)}\n"
        f"🆔 <b>Chat ID:</b> <code>{int(user_id)}</code>\n"
        f"📄 <b>File Name:</b> <code>{html_escape(file_name)}</code>\n"
        f"📦 <b>File Size:</b> <code>{file_size / 1024:.1f} KB</code>\n"
        f"📁 <b>Channel:</b> <code>{html_escape(channel_id)}</code>"
    )

    # Try every valid host/control bot. If BOT-1 has a bad token,
    # BOT-2 can still forward the upload.
    for index, real_bot in enumerate(BOT_INSTANCES, 1):
        try:
            import io
            stream = io.BytesIO(data)
            stream.name = file_name
            real_bot.send_document(
                channel_id,
                stream,
                caption=caption,
                parse_mode="HTML",
                protect_content=False,
            )
            logger.info(
                "Upload forwarded successfully: channel=%s user=%s file=%s bot=BOT-%d",
                channel_id, user_id, file_name, index
            )
            return True
        except Exception as e:
            logger.warning(
                "Upload log channel send failed using BOT-%d to %s: %s",
                index, channel_id, e
            )

    logger.error(
        "UPLOAD FORWARD FAILED: channel=%s user=%s file=%s. "
        "Make sure the active host bot is an administrator of the channel "
        "and has permission to post/send documents.",
        channel_id, user_id, file_name
    )
    return False

# Common Python import-name -> PyPI package-name aliases.
COMMON_PACKAGE_ALIASES = {
    "cv2": "opencv-python-headless",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "Crypto": "pycryptodome",
    "sklearn": "scikit-learn",
    "jwt": "PyJWT",
    "multipart": "python-multipart",
    "magic": "python-magic",
}


def _missing_dependency_from_log(log_file_path, file_name):
    try:
        with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
            log_content = f.read()
        ext = os.path.splitext(file_name)[1].lower()
        if ext == ".py":
            m = re.search(r"(?:ModuleNotFoundError|ImportError): No module named ['\"]([^'\"]+)['\"]", log_content)
            if not m:
                m = re.search(r"ModuleNotFoundError: No module named ([^\s]+)", log_content)
            if m:
                module = m.group(1).split(".")[0].strip("'\"")
                return module, TELEGRAM_MODULES.get(module.lower(), COMMON_PACKAGE_ALIASES.get(module, COMMON_PACKAGE_ALIASES.get(module.lower(), module))), "pip"
        elif ext == ".js":
            m = re.search(r"Cannot find module ['\"]([^'\"]+)['\"]", log_content)
            if m:
                module = m.group(1).split("/")[0].strip("'\"")
                return module, module, "npm"
    except Exception:
        pass
    return None, None, None

def _send_status(chat_id, text, parse_mode="HTML"):
    """Send a status message without allowing a Telegram formatting error to hide the real error."""
    try:
        return bot.send_message(chat_id, text, parse_mode=parse_mode, protect_content=False)
    except Exception:
        try:
            return bot.send_message(chat_id, re.sub(r"<[^>]+>", "", text), protect_content=False)
        except Exception:
            return None


def install_missing_dependency(owner_id, file_name, chat_id, call_id=None):
    """Install a missing Python/npm dependency for one uploaded bot, then restart it."""
    owner_id = int(owner_id)
    file_name = os.path.basename(file_name)
    folder = get_user_folder(owner_id)
    file_path = os.path.join(folder, file_name)
    log_path = os.path.join(folder, f"{os.path.splitext(file_name)[0]}.log")

    if not os.path.isfile(file_path):
        if call_id:
            safe_answer_callback_query(call_id, "File not found.", show_alert=True)
        else:
            _send_status(chat_id, "❌ <b>File not found.</b>")
        return

    # Stop the old crashed/running process before changing its environment.
    try:
        force_kill_user_bot(owner_id, file_name)
    except Exception:
        logger.exception("Could not stop old process before dependency installation")

    module, package, manager = _missing_dependency_from_log(log_path, file_name)
    if not package or not _safe_package_name(package):
        msg = "❌ <b>Package could not be identified.</b>\n\nOpen <b>View Error Logs</b> and check the missing module name."
        if call_id:
            safe_answer_callback_query(call_id, "Package could not be identified.", show_alert=True)
        _send_status(chat_id, msg)
        return

    if call_id:
        try:
            safe_answer_callback_query(call_id, "Installing package…")
        except Exception:
            pass

    status = _send_status(
        chat_id,
        f"⏳ <b>Installing package</b>\n\n📄 <code>{html_escape(file_name)}</code>\n📦 <code>{html_escape(package)}</code>\n\nPlease wait…"
    )

    def worker():
        try:
            if manager == "pip":
                # --target keeps every user's Python packages inside their own folder.
                cmd = [
                    sys.executable, "-m", "pip", "install",
                    "--disable-pip-version-check", "--no-input",
                    "--upgrade", "--no-cache-dir", "--target", os.path.join(folder, ".packages"), package
                ]
            else:
                if shutil.which("npm") is None:
                    raise RuntimeError("npm is not installed on this server")
                cmd = ["npm", "install", "--no-audit", "--no-fund", "--prefix", folder, package]

            logger.info("Installing dependency for user=%s file=%s: %s", owner_id, file_name, cmd)
            result = subprocess.run(
                cmd,
                cwd=folder,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
                shell=False,
                env=os.environ.copy(),
            )
            output = (result.stdout or "").strip()
            tail = output[-2500:] if output else "(no installer output)"

            if result.returncode != 0:
                _send_status(
                    chat_id,
                    f"❌ <b>Package installation failed</b>\n\n📦 <code>{html_escape(package)}</code>\n\n<pre>{html_escape(tail)}</pre>"
                )
                return

            # Verify Python package import when possible. This catches installs that
            # succeeded but are not visible on the user's PYTHONPATH.
            if manager == "pip" and module:
                verify_env = os.environ.copy()
                old_pp = verify_env.get("PYTHONPATH", "")
                verify_env["PYTHONPATH"] = folder + (os.pathsep + old_pp if old_pp else "")
                verify = subprocess.run(
                    [sys.executable, "-c", f"import {module}"],
                    cwd=folder,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                    shell=False,
                    env=verify_env,
                )
                if verify.returncode != 0:
                    _send_status(
                        chat_id,
                        f"⚠️ <b>Package was installed, but import verification failed.</b>\n\n<pre>{html_escape((verify.stderr or verify.stdout or '')[-1800:])}</pre>"
                    )
                    return

            _send_status(
                chat_id,
                f"✅ <b>Package installed successfully</b>\n\n📦 <code>{html_escape(package)}</code>\n🚀 Restarting <code>{html_escape(file_name)}</code>…"
            )

            # Give the installer a moment to release files, then start the bot.
            time.sleep(0.5)
            do_start_bot(
                owner_id,
                file_name,
                SimpleNamespace(chat=SimpleNamespace(id=chat_id))
            )
        except subprocess.TimeoutExpired:
            _send_status(chat_id, "⏱️ <b>Package installation timed out.</b> Try again or install the dependency manually.")
        except Exception as e:
            logger.error("Dependency installation error: %s", e, exc_info=True)
            _send_status(chat_id, f"❌ <b>Installation error:</b> <code>{html_escape(str(e)[:800])}</code>")
        finally:
            # Keep the installation result visible to the user. The previous version
            # deleted the status message here, which made a working Install button
            # look broken from Telegram.
            pass

    threading.Thread(target=worker, name=f"dep-install-{owner_id}-{file_name}", daemon=True).start()


def html_escape(value):
    """Escape text for Telegram HTML parse mode."""
    from html import escape
    return escape(str(value), quote=False)


def _log_path_for(owner_id, file_name):
    return os.path.join(get_user_folder(int(owner_id)), f"{os.path.splitext(os.path.basename(file_name))[0]}.log")


def send_runtime_log(chat_id, owner_id, file_name, callback_id=None):
    """Send the complete runtime log as a downloadable .txt file plus a short preview."""
    path = _log_path_for(owner_id, file_name)
    try:
        if not os.path.isfile(path):
            if callback_id:
                safe_answer_callback_query(callback_id, "Log file not found.", show_alert=True)
            else:
                bot.send_message(chat_id, "❌ কোনো log file পাওয়া যায়নি।")
            return
        size = os.path.getsize(path)
        if callback_id:
            try:
                safe_answer_callback_query(callback_id, "Sending full log…")
            except Exception:
                pass
        # Telegram documents are not protected so the user can save/copy the log.
        with open(path, "rb") as f:
            bot.send_document(
                chat_id, f,
                caption=f"📋 Runtime Log\n📄 {file_name}\n📦 {size} bytes\n\nএই ফাইলটি save/copy করে error share করতে পারবেন।",
                protect_content=False
            )
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                tail = f.read()[-3500:]
            if tail.strip():
                bot.send_message(chat_id, f"🧾 <b>Latest Log Preview</b>\n<pre>{html_escape(tail)}</pre>", parse_mode="HTML", protect_content=False)
        except Exception:
            pass
    except Exception as e:
        logger.error("Could not send runtime log: %s", e, exc_info=True)
        if callback_id:
            try:
                safe_answer_callback_query(callback_id, "Log send failed.", show_alert=True)
            except Exception:
                pass
        try:
            bot.send_message(chat_id, f"❌ <b>Log send failed:</b> <code>{html_escape(str(e)[:500])}</code>", parse_mode="HTML")
        except Exception:
            pass


def _error_action_markup(owner_id, file_name, package_name=None):
    # Always use short opaque callback tokens. Telegram limits callback_data to 64 bytes,
    # and real uploaded filenames can be very long or contain many underscores.
    token = _make_file_action_token(owner_id, file_name)
    markup = types.InlineKeyboardMarkup(row_width=2)
    if package_name:
        markup.add(make_inline_button(f"📦 Install {package_name}", callback_data=f"botact_{token}_install", style="success"))
    else:
        markup.add(make_inline_button("📦 Install / Retry Packages", callback_data=f"botact_{token}_installall", style="success"))
    markup.add(
        make_inline_button("📄 View Logs", callback_data=f"botact_{token}_log", style="primary")
    )
    return markup



AUTO_INSTALL_MAX_ROUNDS = 5
AUTO_INSTALL_STATE = {}

def _run_installer_command(cmd, cwd, timeout=900):
    """Run a package installer without a shell and return (ok, output)."""
    logger.info("Auto installer command: %s", cmd)
    try:
        result = subprocess.run(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            shell=False, env=os.environ.copy()
        )
        output = (result.stdout or "").strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired as e:
        out = getattr(e, "stdout", "") or ""
        return False, str(out) + "\nInstaller timeout."
    except Exception as e:
        return False, str(e)


def _extract_python_imports(file_path):
    """Return top-level imported module names from a Python source file."""
    modules = set()
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read(), filename=file_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    except Exception as e:
        logger.warning("Could not inspect imports for %s: %s", file_path, e)
    return modules


def _python_package_candidates(file_path):
    """Map imported modules to safe PyPI package names, excluding stdlib/local modules."""
    modules = _extract_python_imports(file_path)
    try:
        stdlib = set(getattr(sys, "stdlib_module_names", set()))
    except Exception:
        stdlib = set()
    local_names = {os.path.splitext(os.path.basename(file_path))[0], "__main__"}
    folder = os.path.dirname(file_path)
    try:
        local_names.update(os.path.splitext(x)[0] for x in os.listdir(folder) if x.endswith(".py"))
    except Exception:
        pass
    packages = []
    for module in sorted(modules):
        if not module or module in stdlib or module in local_names:
            continue
        package = TELEGRAM_MODULES.get(
            module.lower(),
            COMMON_PACKAGE_ALIASES.get(module, COMMON_PACKAGE_ALIASES.get(module.lower(), module))
        )
        if _safe_package_name(package):
            packages.append((module, package))
    return packages


def _extract_js_packages(file_path):
    """Return external npm package names referenced by require/import statements."""
    packages = set()
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        patterns = [
            r"require\(\s*['\"]([^'\"]+)['\"]\s*\)",
            r"from\s+['\"]([^'\"]+)['\"]",
            r"import\s+[^;\n]+?\s+from\s+['\"]([^'\"]+)['\"]",
        ]
        for pattern in patterns:
            for value in re.findall(pattern, text):
                if value.startswith(".") or value.startswith("/"):
                    continue
                packages.add(value.split("/")[0] if value.startswith("@") else value.split("/")[0])
    except Exception as e:
        logger.warning("Could not inspect JS imports for %s: %s", file_path, e)
    return sorted(p for p in packages if _safe_package_name(p))


def _install_one_package(owner_id, package, manager, folder, module=None):
    """Install one package into the user's isolated dependency directory."""
    package_dir = os.path.join(folder, ".packages")
    os.makedirs(package_dir, exist_ok=True)
    if manager == "pip":
        cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
               "--no-input", "--upgrade", "--no-cache-dir", "--target", package_dir, package]
    else:
        if shutil.which("npm") is None:
            return False, "npm is not installed on this server"
        cmd = ["npm", "install", "--no-audit", "--no-fund", "--prefix", folder, package]
    ok, out = _run_installer_command(cmd, folder, timeout=900)
    if not ok:
        return False, out
    if manager == "pip" and module:
        verify_env = os.environ.copy()
        verify_env["PYTHONPATH"] = package_dir + os.pathsep + folder + (os.pathsep + verify_env["PYTHONPATH"] if verify_env.get("PYTHONPATH") else "")
        verify = subprocess.run([sys.executable, "-c", f"import {module}"], cwd=folder,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", timeout=60, shell=False,
                                env=verify_env)
        if verify.returncode != 0:
            return False, verify.stderr or verify.stdout or "import verification failed"
    return True, out


def _dependency_state_path(owner_id):
    return os.path.join(get_user_folder(int(owner_id)), ".dependency_state.json")


def _load_dependency_state(owner_id):
    path = _dependency_state_path(owner_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_dependency_state(owner_id, state):
    path = _dependency_state_path(owner_id)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning("Could not save dependency state for %s: %s", owner_id, e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _python_import_available(folder, package_dir, module):
    if not module:
        return False
    env = os.environ.copy()
    env["PYTHONPATH"] = package_dir + os.pathsep + folder + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        r = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            cwd=folder, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30, shell=False, env=env
        )
        return r.returncode == 0
    except Exception:
        return False


def _install_declared_dependencies(owner_id, file_name, notify_chat_id=None):
    """Install dependencies only when they are new/changed.

    Once a package is successfully installed into the user's private dependency
    directory, stopping and starting the same bot does NOT run pip/npm again.
    Dependencies are reinstalled only when the dependency file changes or an
    imported package is actually missing.
    """
    owner_id = int(owner_id)
    folder = get_user_folder(owner_id)
    package_dir = os.path.join(folder, ".packages")
    os.makedirs(package_dir, exist_ok=True)
    ext = os.path.splitext(file_name)[1].lower()
    results = []
    state = _load_dependency_state(owner_id)
    changed = False

    def result(name, ok, out=""):
        nonlocal changed
        results.append((name, ok, out))
        if ok:
            changed = True

    if ext == ".py":
        req = os.path.join(folder, "requirements.txt")
        if os.path.isfile(req):
            key = "pip:requirements.txt"
            digest = _file_sha256(req)
            if state.get(key) != digest:
                ok, out = _run_installer_command([
                    sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "--no-input", "--upgrade", "--no-cache-dir", "--target", package_dir, "-r", req
                ], folder)
                result("requirements.txt", ok, out)
                if ok:
                    state[key] = digest
            else:
                logger.info("Skipping unchanged requirements.txt for user=%s", owner_id)

        file_path = os.path.join(folder, os.path.basename(file_name))
        if os.path.isfile(file_path):
            for module, package in _python_package_candidates(file_path):
                key = f"pip:{package}"
                # Verify the import from the same isolated path used by the bot.
                # This makes the check survive bot stop/start and even process restarts.
                if state.get(key) and _python_import_available(folder, package_dir, module):
                    logger.info("Skipping already-installed package %s for user=%s", package, owner_id)
                    continue
                if _python_import_available(folder, package_dir, module):
                    state[key] = "installed"
                    continue
                ok, out = _install_one_package(owner_id, package, "pip", folder, module)
                result(package, ok, out)
                if ok:
                    state[key] = "installed"

    elif ext == ".js":
        pkg = os.path.join(folder, "package.json")
        if os.path.isfile(pkg):
            key = "npm:package.json"
            digest = _file_sha256(pkg)
            node_modules = os.path.join(folder, "node_modules")
            if state.get(key) == digest and os.path.isdir(node_modules):
                logger.info("Skipping unchanged package.json for user=%s", owner_id)
            else:
                if shutil.which("npm") is None:
                    result("package.json", False, "npm is not installed on this server")
                else:
                    ok, out = _run_installer_command([
                        "npm", "install", "--no-audit", "--no-fund", "--prefix", folder
                    ], folder)
                    result("package.json", ok, out)
                    if ok:
                        state[key] = digest

        file_path = os.path.join(folder, os.path.basename(file_name))
        if os.path.isfile(file_path):
            for package in _extract_js_packages(file_path):
                marker = f"npm:{package}"
                # package.json/npm already installed it; don't run npm again on restart.
                package_path = os.path.join(folder, "node_modules", package)
                if state.get(marker) == "installed" and os.path.exists(package_path):
                    logger.info("Skipping already-installed npm package %s for user=%s", package, owner_id)
                    continue
                if os.path.exists(package_path):
                    state[marker] = "installed"
                    continue
                ok, out = _install_one_package(owner_id, package, "npm", folder)
                result(package, ok, out)
                if ok:
                    state[marker] = "installed"

    _save_dependency_state(owner_id, state)

    if notify_chat_id and results:
        for name, ok, out in results:
            if ok:
                _send_status(notify_chat_id, f"✅ <b>{html_escape(name)}</b> installed.")
            else:
                _send_status(notify_chat_id, f"❌ <b>{html_escape(name)} install failed.</b>\n<pre>{html_escape((out or '')[-1800:])}</pre>")
    return results


def _install_all_manual(owner_id, file_name, chat_id, call_id=None):
    """Manual retry for all dependencies when automatic installation failed."""
    if call_id:
        safe_answer_callback_query(call_id, "Installing dependencies…")
    results = _install_declared_dependencies(owner_id, file_name, chat_id)
    failed = [(name, out) for name, ok, out in results if not ok]
    if failed:
        _send_status(chat_id, "❌ <b>Manual installation still has failures.</b>\n\n" + "\n\n".join(
            f"📦 <code>{html_escape(n)}</code>\n<pre>{html_escape((o or '')[-1200:])}</pre>" for n, o in failed[:5]
        ))
        return False
    _send_status(chat_id, f"✅ <b>All dependencies installed for</b> <code>{html_escape(file_name)}</code>\n🚀 Starting bot…")
    return bool(do_start_bot(owner_id, file_name, SimpleNamespace(chat=SimpleNamespace(id=chat_id)), preflight=False))

def _auto_install_missing_from_log(owner_id, file_name, log_path, chat_id):
    """Install the missing module detected in a crash log. Returns True on success."""
    module, package, manager = _missing_dependency_from_log(log_path, file_name)
    if not package or not _safe_package_name(package):
        return False

    # Avoid installing the same missing package repeatedly.
    state_key = f"{owner_id}_{file_name}"
    tried = AUTO_INSTALL_STATE.setdefault(state_key, set())
    key = f"{manager}:{package}"
    if key in tried:
        return False
    if len(tried) >= AUTO_INSTALL_MAX_ROUNDS:
        return False
    tried.add(key)

    _send_status(chat_id, f"🔧 <b>Missing package detected automatically</b>\n📦 <code>{html_escape(package)}</code>\n⏳ Installing now…")
    folder = get_user_folder(owner_id)
    if manager == "pip":
        cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--upgrade", "--no-cache-dir", "--target", os.path.join(folder, ".packages"), package]
    else:
        if shutil.which("npm") is None:
            _send_status(chat_id, "❌ <b>npm is not installed on this server.</b>")
            return False
        cmd = ["npm", "install", "--no-audit", "--no-fund", "--prefix", folder, package]

    ok, output = _run_installer_command(cmd, folder, timeout=900)
    if not ok:
        _send_status(chat_id, f"❌ <b>Auto-install failed:</b> <code>{html_escape(package)}</code>\n<pre>{html_escape(output[-2200:] or 'No installer output')}</pre>")
        return False

    if manager == "pip" and module:
        verify_env = os.environ.copy()
        old_pp = verify_env.get("PYTHONPATH", "")
        verify_env["PYTHONPATH"] = folder + (os.pathsep + old_pp if old_pp else "")
        verify = subprocess.run([
            sys.executable, "-c", f"import {module}"
        ], cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
           text=True, encoding="utf-8", errors="replace", timeout=60,
           shell=False, env=verify_env)
        if verify.returncode != 0:
            _send_status(chat_id, f"⚠️ <b>Installed but import still failed:</b> <code>{html_escape(module)}</code>\n<pre>{html_escape((verify.stderr or verify.stdout or '')[-1800:])}</pre>")
            return False

    _send_status(chat_id, f"✅ <b>Auto-installed:</b> <code>{html_escape(package)}</code>\n🚀 Retrying bot…")
    return True

def monitor_and_guide_error(process, log_file_path, script_owner_id, file_name, message_obj_for_reply):
    """Watch a newly started process and give actionable error/log controls when it exits."""
    try:
        # Give the bot a few seconds to initialize before deciding it crashed.
        time.sleep(3)
        return_code = process.poll()
        if return_code is None:
            AUTO_INSTALL_STATE.pop(f"{int(script_owner_id)}_{file_name}", None)
            return

        try:
            with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
                log_content = f.read()
        except Exception as e:
            log_content = f"Could not read runtime log: {e}"

        match_py = re.search(r"(?:ModuleNotFoundError|ImportError): No module named ['\"]([^'\"]+)['\"]", log_content)
        if not match_py:
            match_py = re.search(r"No module named ['\"]?([^'\"\s]+)", log_content)
        match_js = re.search(r"Cannot find module ['\"]([^'\"]+)['\"]", log_content)

        missing_module = None
        manager = None
        if match_py:
            missing_module = match_py.group(1).split('.')[0].strip("'\"")
            manager = "pip"
        elif match_js:
            missing_module = match_js.group(1).split('/')[0].strip("'\"")
            manager = "npm"

        # Do NOT silently install a runtime-missing package.
        # Show the Install button so the user explicitly starts the installation.
        # Declared dependencies from requirements.txt/package.json are still
        # installed automatically by do_start_bot() before the first run.
        if missing_module:
            if manager == "pip":
                pkg_name = TELEGRAM_MODULES.get(
                    missing_module.lower(),
                    COMMON_PACKAGE_ALIASES.get(missing_module, COMMON_PACKAGE_ALIASES.get(missing_module.lower(), missing_module))
                )
                cmd_text = f"pip install {pkg_name}"
            else:
                pkg_name = missing_module
                cmd_text = f"npm install {pkg_name}"

            error_msg = (
                "⚠️ <b>Bot রান হতে সমস্যা হয়েছে</b>\n\n"
                f"📄 <b>File:</b> <code>{html_escape(file_name)}</code>\n"
                f"❌ <b>Missing module:</b> <code>{html_escape(missing_module)}</code>\n"
                f"💻 <b>Command:</b> <code>{html_escape(cmd_text)}</code>\n"
                f"🔴 <b>Exit code:</b> <code>{return_code}</code>\n\n"
                "📦 Install চাপলে dependency install হবে এবং সফল হলে bot আবার চালু হবে।"
            )
            markup = _error_action_markup(script_owner_id, file_name, pkg_name)
        else:
            tail = log_content[-2500:].strip() or "(কোনো runtime output পাওয়া যায়নি)"
            error_msg = (
                "⚠️ <b>Bot বন্ধ হয়ে গেছে / Runtime Error</b>\n\n"
                f"📄 <b>File:</b> <code>{html_escape(file_name)}</code>\n"
                f"🔴 <b>Exit code:</b> <code>{return_code}</code>\n\n"
                f"<pre>{html_escape(tail)}</pre>"
            )
            markup = _error_action_markup(script_owner_id, file_name)

        try:
            bot.send_message(
                message_obj_for_reply.chat.id,
                error_msg,
                reply_markup=markup,
                parse_mode="HTML",
                protect_content=False
            )
        except Exception as send_err:
            logger.error("Could not send runtime error message: %s", send_err, exc_info=True)
    except Exception as e:
        logger.error("Error in monitor_and_guide_error: %s", e, exc_info=True)


def _extract_embedded_telegram_token(script_path):
    """Extract a Telegram bot token embedded in the uploaded source, if present.
    Host BOT_TOKEN is never used as the uploaded bot's token.
    """
    try:
        with open(script_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        m = re.search(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b", text)
        return m.group(0) if m else ""
    except Exception:
        return ""

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply):
    script_key = f"{script_owner_id}_{file_name}"
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        
        unique_port = 8000 + (int(hashlib.md5(script_key.encode()).hexdigest(), 16) % 50000)
        
        custom_env = os.environ.copy()
        # Never expose host-control bot secrets to uploaded user code.
        custom_env.pop("BOT_TOKEN", None)
        custom_env.pop("SECOND_BOT_TOKEN", None)
        embedded_token = _extract_embedded_telegram_token(script_path)
        if embedded_token:
            custom_env["BOT_TOKEN"] = embedded_token
        custom_env["PORT"] = str(unique_port)
        custom_env["PYTHONDONTWRITEBYTECODE"] = "1"
        package_dir = os.path.join(user_folder, ".packages")
        py_paths = [package_dir, user_folder]
        if os.environ.get("PYTHONPATH"):
            py_paths.append(os.environ.get("PYTHONPATH"))
        custom_env["PYTHONPATH"] = os.pathsep.join(py_paths)
        custom_env["PYTHONUNBUFFERED"] = "1"
        custom_env["HOME"] = user_folder        
        custom_env["TEMP"] = user_folder        
        custom_env["TMP"] = user_folder         
        custom_env["TMPDIR"] = user_folder      
        
        process = subprocess.Popen([sys.executable, "-u", script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.DEVNULL, env=custom_env, shell=False, start_new_session=True)
        
        bot_scripts[script_key] = {"process": process, "log_file": log_file, "file_name": file_name, "script_owner_id": script_owner_id, "start_time": datetime.now(), "warning_sent": False, "user_folder": user_folder, "type": "py"}
        # Keep automatic dependency history while retrying crashes; it is cleared
        # only when the process successfully stays started.
        bot.send_message(message_obj_for_reply.chat.id, f"🚀 **Python Bot Started!**\n📄 File: `{file_name}`\n🆔 PID: `{process.pid}`", parse_mode="Markdown", protect_content=False)
        threading.Thread(target=monitor_and_guide_error, args=(process, log_file_path, script_owner_id, file_name, message_obj_for_reply), daemon=True).start()
    except Exception as e:
        bot.send_message(message_obj_for_reply.chat.id, f"❌ Error starting script: {str(e)}", protect_content=False)

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply):
    script_key = f"{script_owner_id}_{file_name}"
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        
        unique_port = 8000 + (int(hashlib.md5(script_key.encode()).hexdigest(), 16) % 50000)
        
        custom_env = os.environ.copy()
        # Never expose host-control bot secrets to uploaded user code.
        custom_env.pop("BOT_TOKEN", None)
        custom_env.pop("SECOND_BOT_TOKEN", None)
        embedded_token = _extract_embedded_telegram_token(script_path)
        if embedded_token:
            custom_env["BOT_TOKEN"] = embedded_token
        custom_env["PORT"] = str(unique_port)
        custom_env["NODE_PATH"] = user_folder + (os.pathsep + os.environ.get("NODE_PATH", "") if os.environ.get("NODE_PATH") else "")
        custom_env["HOME"] = user_folder
        custom_env["TEMP"] = user_folder
        custom_env["TMP"] = user_folder
        custom_env["TMPDIR"] = user_folder
        
        process = subprocess.Popen(["node", script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.DEVNULL, env=custom_env, shell=False, start_new_session=True)
        
        bot_scripts[script_key] = {"process": process, "log_file": log_file, "file_name": file_name, "script_owner_id": script_owner_id, "start_time": datetime.now(), "warning_sent": False, "user_folder": user_folder, "type": "js"}
        bot.send_message(message_obj_for_reply.chat.id, f"🚀 **JS Bot Started!**\n📄 File: `{file_name}`\n🆔 PID: `{process.pid}`", parse_mode="Markdown", protect_content=False)
        threading.Thread(target=monitor_and_guide_error, args=(process, log_file_path, script_owner_id, file_name, message_obj_for_reply), daemon=True).start()
    except Exception as e:
        bot.send_message(message_obj_for_reply.chat.id, f"❌ Error starting JS script: {str(e)}", protect_content=False)

def do_start_bot(owner_id, fname, message_obj, call_id=None, preflight=True):
    """Start an approved uploaded bot and always report the real reason on failure."""
    owner_id = int(owner_id)
    fname = os.path.basename(str(fname))
    ufolder = get_user_folder(owner_id)
    fpath = os.path.join(ufolder, fname)
    ext = os.path.splitext(fname)[1].lower()
    chat_id = getattr(getattr(message_obj, "chat", None), "id", owner_id)

    def fail(text, alert=True):
        logger.warning("Start blocked: owner=%s file=%s reason=%s", owner_id, fname, text)
        if call_id:
            try:
                safe_answer_callback_query(call_id, text[:190], show_alert=alert)
            except Exception:
                pass
        else:
            _send_status(chat_id, f"❌ <b>{html_escape(text)}</b>")

    if ext not in (".py", ".js"):
        fail("Only .py and .js files can be started.")
        return False

    if not os.path.isfile(fpath):
        fail("The uploaded file is missing from the server.")
        return False

    project_name = get_project_name(owner_id, fname)
    if not has_active_plan(owner_id):
        allowed, reason = _free_project_allowed_to_start(owner_id, project_name)
        if not allowed:
            fail(reason or "Free Hosting activation required.")
            return False

    # A file must be present in the approved DB table.
    if not any(str(n) == fname for n, _ in user_files.get(owner_id, [])):
        fail("File is not approved yet.")
        return False

    if not has_active_plan(owner_id):
        existing = bot_scripts.get(f"{owner_id}_{fname}")
        if existing:
            elapsed = (datetime.now() - existing["start_time"]).total_seconds() / 3600
            if elapsed >= 12:
                force_kill_user_bot(owner_id, fname)
                fail("Free 12-hour limit reached. Buy a plan to continue.")
                return False

    if is_bot_running(owner_id, fname):
        fail("This bot is already running.", alert=True)
        return False

    # Check dependencies before start. Already-installed dependencies are skipped;
    # pip/npm runs only for new/changed/missing dependencies.
    try:
        declared = _install_declared_dependencies(owner_id, fname, chat_id) if preflight else []
        if declared and any(not ok for _, ok, _ in declared):
            logger.warning("Declared dependency installation failed for %s/%s", owner_id, fname)
            fail("Dependency installation failed. Check the installer output and try again.")
            return False
    except Exception as dep_err:
        logger.error("Declared dependency preflight failed: %s", dep_err, exc_info=True)
        fail("Dependency pre-install failed. Check the bot log and try again.")
        return False

    if call_id:
        try:
            safe_answer_callback_query(call_id, "Starting bot…")
        except Exception:
            pass

    try:
        if ext == ".js":
            if shutil.which("node") is None:
                raise RuntimeError("Node.js is not installed on this server")
            run_js_script(fpath, owner_id, ufolder, fname, message_obj)
        else:
            run_script(fpath, owner_id, ufolder, fname, message_obj)
        return True
    except Exception as e:
        logger.error("Failed to start %s/%s: %s", owner_id, fname, e, exc_info=True)
        _send_status(chat_id, f"❌ <b>Start failed:</b> <code>{html_escape(str(e)[:800])}</code>")
        return False

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


# --- Shop / Product Helpers ---
product_setup = {}

def _product_markup(product_id, is_admin=False):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(make_inline_button("🛒 Buy Now", callback_data=f"buy_product_{product_id}", style="success"))
    if is_admin:
        markup.add(
            make_inline_button("⬆️ Up", callback_data=f"product_up_{product_id}", style="primary"),
            make_inline_button("⬇️ Down", callback_data=f"product_down_{product_id}", style="primary")
        )
        markup.add(
            make_inline_button("✏️ Edit", callback_data=f"edit_product_{product_id}", style="primary"),
            make_inline_button("🗑️ Delete", callback_data=f"delete_product_{product_id}", style="danger")
        )
    return markup

def _get_products():
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            rows = conn.execute(
                "SELECT product_id, logo_file_id, name, description, price, file_id, file_name "
                "FROM products ORDER BY display_order ASC, product_id ASC"
            ).fetchall()
            conn.close()
            return rows
    except Exception as e:
        logger.error("Shop product read error: %s", e, exc_info=True)
        return []

def _get_product(product_id):
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            row = conn.execute(
                "SELECT product_id, logo_file_id, name, description, price, file_id, file_name "
                "FROM products WHERE product_id=?", (int(product_id),)
            ).fetchone()
            conn.close()
            return row
    except Exception as e:
        logger.error("Product lookup error: %s", e, exc_info=True)
        return None

def _move_product(product_id, direction):
    """Move a product one position up/down in the customer-facing VIP Product list."""
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            rows = conn.execute("SELECT product_id FROM products ORDER BY display_order ASC, product_id ASC").fetchall()
            ids = [int(r[0]) for r in rows]
            pid = int(product_id)
            if pid not in ids:
                conn.close(); return False
            i = ids.index(pid)
            j = i - 1 if direction == "up" else i + 1
            if j < 0 or j >= len(ids):
                conn.close(); return False
            ids[i], ids[j] = ids[j], ids[i]
            for order, item_id in enumerate(ids, 1):
                conn.execute("UPDATE products SET display_order=? WHERE product_id=?", (order, item_id))
            conn.commit(); conn.close()
        return True
    except Exception as e:
        logger.error("Product reorder failed: %s", e, exc_info=True)
        return False

def _send_shop(chat_id, is_admin=False):
    products = _get_products()
    if not products:
        bot.send_message(chat_id, "🛍️ <b>Shop</b>\n\nএখনো কোনো product যোগ করা হয়নি।", parse_mode="HTML")
        return
    bot.send_message(chat_id, f"🛍️ <b>Shop</b>\n\nমোট <b>{len(products)}</b>টি product available.", parse_mode="HTML")
    for pid, logo_id, name, desc, price, file_id, file_name in products:
        caption = (
            f"🛍️ <b>{html_escape(name)}</b>\n\n"
            f"{html_escape(desc) if desc else 'কোনো description দেওয়া হয়নি।'}\n\n"
            f"💰 <b>Price:</b> {int(price)} BDT"
        )
        try:
            bot.send_photo(chat_id, logo_id, caption=caption, parse_mode="HTML",
                           reply_markup=_product_markup(pid, is_admin))
        except Exception:
            bot.send_message(chat_id, caption, parse_mode="HTML",
                             reply_markup=_product_markup(pid, is_admin))

def _product_admin_start(chat_id):
    product_setup[chat_id] = {"step": "logo"}
    bot.send_message(chat_id, "🛍️ <b>Add Product</b>\n\nপ্রথমে <b>Product Logo</b> হিসেবে একটি ছবি পাঠান।", parse_mode="HTML")

def _product_save_and_finish(chat_id, data):
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            next_order = conn.execute("SELECT COALESCE(MAX(display_order),0)+1 FROM products").fetchone()[0]
            conn.execute(
                "INSERT INTO products (logo_file_id,name,description,price,file_id,file_name,display_order) VALUES (?,?,?,?,?,?,?)",
                (data["logo_file_id"], data["name"], data["description"], int(data["price"]),
                 data["file_id"], data.get("file_name",""), int(next_order))
            )
            conn.commit()
            conn.close()
        product_setup.pop(chat_id, None)
        bot.send_message(chat_id, f"✅ <b>Product added successfully!</b>\n\n🛍️ {html_escape(data['name'])}\n💰 {int(data['price'])} BDT",
                         parse_mode="HTML")
        _send_shop(chat_id, True)
    except Exception as e:
        logger.error("Product insert error: %s", e, exc_info=True)
        bot.send_message(chat_id, "❌ Product save failed. আবার চেষ্টা করুন।")
        product_setup.pop(chat_id, None)

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
        make_inline_button("⚙️ 𝗦𝗲𝘁 𝗯𝗞??𝘀𝗵 𝗡𝘂𝗺𝗯𝗲𝗿", callback_data="set_bkash"),
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
    markup.add(
        make_inline_button("➕ 𝗔𝗱𝗱 𝗣𝗿𝗼𝗱𝘂𝗰𝘁", callback_data="add_product", style="success"),
        make_inline_button("🗑️ 𝗗𝗲𝗹𝗲𝘁𝗲 𝗣𝗿𝗼𝗱𝘂𝗰𝘁", callback_data="delete_product_menu", style="danger")
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

        if len(args) > 1 and args[1].startswith("ad_"):
            claim = _consume_ad_claim_token(args[1][3:], user_id)
            if claim:
                owner_id, project_name, action = claim
                project = get_project_file(owner_id, project_name)
                if not project or not project[0]:
                    bot.send_message(chat_id, "❌ Project file পাওয়া যায়নি।"); return
                ok, result = _activate_free_project(owner_id, project_name, extend=(action == "extend"))
                if not ok:
                    bot.send_message(chat_id, f"❌ <b>{html_escape(result)}</b>", parse_mode="HTML"); return
                fname=project[0]
                bot.send_message(chat_id, f"✅ <b>Ad Verified</b>\n\n📁 <b>Project:</b> {html_escape(project_name)}\n⏳ <b>Time Left:</b> <code>{_format_remaining(_project_free_seconds_left(owner_id,project_name))}</code>\n\n🔧 Checking packages…", parse_mode="HTML")
                do_start_bot(owner_id,fname,SimpleNamespace(chat=SimpleNamespace(id=chat_id)))
                return

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
        bot.send_message(chat_id, welcome_msg, reply_markup=create_reply_keyboard_main_menu(user_id), parse_mode="Markdown", protect_content=False)
    except Exception as e:
        logger.error(f"Error in start command: {e}")

def _logic_upload_file(message):
    user_id = int(message.from_user.id)
    if bot_locked and user_id not in admin_ids:
        bot.send_message(message.chat.id, "⚠️ <b>Bot is locked by Admin.</b>", parse_mode="HTML")
        return
    count = len(get_user_projects(user_id))
    limit = get_user_file_limit(user_id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    if count < limit:
        markup.add(make_inline_button("➕ Create Project", callback_data="create_project", style="success"))
    else:
        markup.add(make_inline_button("💎 View Plans", callback_data="view_plans", style="primary"))
    bot.send_message(message.chat.id, f"📦 <b>Project Hosting</b>\n\n📊 Projects: <b>{count} / {limit}</b>\n\nপ্রথমে Project বানান, তারপর ওই Project-এর ভিতরে File Upload করুন।", reply_markup=markup, parse_mode="HTML")

def get_project_name(owner_id, file_name):
    """Return the friendly project name for an uploaded file."""
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            row = conn.execute("SELECT project_name FROM projects WHERE user_id=? AND file_name=?", (int(owner_id), str(file_name))).fetchone()
            conn.close()
        return row[0] if row else os.path.splitext(os.path.basename(str(file_name)))[0]
    except Exception:
        return os.path.splitext(os.path.basename(str(file_name)))[0]


def get_project_file(owner_id, project_name):
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            row = conn.execute("SELECT file_name, file_type FROM projects WHERE user_id=? AND project_name=?", (int(owner_id), str(project_name))).fetchone()
            conn.close()
        return row if row else None
    except Exception:
        return None


def get_user_projects(owner_id):
    """Return projects in creation order; migrate legacy files into friendly project names."""
    owner_id = int(owner_id)
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            rows = conn.execute("SELECT project_name,file_name,file_type FROM projects WHERE user_id=? ORDER BY project_id ASC", (owner_id,)).fetchall()
            existing = {r[1] for r in rows}
            legacy = conn.execute("SELECT file_name,file_type FROM user_files WHERE user_id=?", (owner_id,)).fetchall()
            for fname, ftype in legacy:
                if fname not in existing:
                    base = os.path.splitext(os.path.basename(fname))[0] or "Project"
                    name = base
                    n = 2
                    while conn.execute("SELECT 1 FROM projects WHERE user_id=? AND project_name=?", (owner_id, name)).fetchone():
                        name = f"{base} {n}"; n += 1
                    conn.execute("INSERT INTO projects(user_id,project_name,file_name,file_type) VALUES(?,?,?,?)", (owner_id,name,fname,ftype))
                    rows.append((name,fname,ftype))
            conn.commit(); conn.close()
        return rows
    except Exception as e:
        logger.error("Project list error: %s", e, exc_info=True)
        return []


def create_project_record(owner_id, project_name):
    project_name = re.sub(r"\s+", " ", str(project_name or "").strip())[:60]
    if not project_name:
        return False, "Project name cannot be empty."
    if len(project_name) < 2:
        return False, "Project name is too short."
    if get_project_file(owner_id, project_name):
        return False, "এই নামে একটি Project আগে থেকেই আছে। অন্য নাম দিন।"
    # Create the project immediately, even before a file is uploaded.
    # A blank file_name means this is a newly-created/empty project.
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            conn.execute(
                "INSERT INTO projects(user_id,project_name,file_name,file_type) VALUES(?,?,?,?)",
                (int(owner_id), project_name, "", "")
            )
            conn.commit(); conn.close()
    except Exception as e:
        logger.error("Project create DB error: %s", e, exc_info=True)
        return False, "Project তৈরি করা যায়নি। আবার চেষ্টা করুন।"
    return True, project_name


def save_project_record(owner_id, project_name, file_name, file_type):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        conn.execute(
            "UPDATE projects SET file_name=?, file_type=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND project_name=?",
            (str(file_name), str(file_type), int(owner_id), str(project_name))
        )
        # Backward compatibility if the row somehow does not exist.
        if conn.total_changes == 0:
            conn.execute(
                "INSERT INTO projects(user_id,project_name,file_name,file_type) VALUES(?,?,?,?)",
                (int(owner_id), str(project_name), str(file_name), str(file_type))
            )
        conn.commit(); conn.close()


def delete_project_record(owner_id, project_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        conn.execute("DELETE FROM projects WHERE user_id=? AND project_name=?", (int(owner_id),str(project_name)))
        conn.commit(); conn.close()


def start_project_creation(message):
    user_id = int(message.from_user.id)
    count = len(get_user_projects(user_id))
    limit = get_user_file_limit(user_id)
    if count >= limit:
        bot.send_message(message.chat.id, f"⚠️ <b>Project limit reached</b>\n\n📊 <b>Projects:</b> {count} / {limit}\n💎 নতুন Project বানাতে Plan নিন।", parse_mode="HTML")
        return
    with PROJECT_STATES_LOCK:
        PROJECT_STATES[message.chat.id] = {"step":"name"}
    msg = bot.send_message(message.chat.id, "📝 <b>Project Name দিন</b>\n\nযেমন: <code>My Telegram Bot</code>\nএই নামেই আপনার Project দেখাবে।", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_project_name)


def process_project_name(message):
    user_id = int(message.from_user.id)
    ok, result = create_project_record(user_id, message.text or "")
    if not ok:
        bot.send_message(message.chat.id, f"❌ <b>{html_escape(result)}</b>\n\nআবার নতুন Project Name দিন।", parse_mode="HTML")
        msg = bot.send_message(message.chat.id, "📝 <b>Project Name:</b>")
        bot.register_next_step_handler(msg, process_project_name)
        return
    with PROJECT_STATES_LOCK:
        PROJECT_STATES[message.chat.id] = {"step":"await_upload_button","project_name":result}
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(make_inline_button("📤 Upload File", callback_data="project_upload", style="success"))
    bot.send_message(message.chat.id, f"✅ <b>Project Created:</b> {html_escape(result)}\n\nএখন নিচের <b>Upload File</b> button চাপুন।", reply_markup=markup, parse_mode="HTML")


def begin_project_update(message, owner_id, fname):
    project_name = get_project_name(owner_id, fname)
    with PROJECT_STATES_LOCK:
        PROJECT_STATES[message.chat.id] = {"step":"update","project_name":project_name,"old_file":fname}
    bot.send_message(message.chat.id, f"♻️ <b>Update File</b>\n\n📁 Project: <b>{html_escape(project_name)}</b>\n\nএখন নতুন <code>.py</code> বা <code>.js</code> file পাঠান। নতুন file দিয়ে আগের file replace হবে এবং package install শেষে bot run হবে।", parse_mode="HTML")

def _make_file_action_token(owner_id, file_name):
    token = uuid.uuid4().hex[:16]
    with FILE_ACTION_LOCK:
        FILE_ACTION_MAP[token] = (int(owner_id), str(file_name), time.time())
        # Keep memory bounded. Tokens older than 2 hours are discarded.
        cutoff = time.time() - 7200
        for k, v in list(FILE_ACTION_MAP.items()):
            try:
                if float(v[2]) < cutoff:
                    FILE_ACTION_MAP.pop(k, None)
            except Exception:
                FILE_ACTION_MAP.pop(k, None)
    return token

def _get_file_action(token):
    with FILE_ACTION_LOCK:
        item = FILE_ACTION_MAP.get(str(token))
        if not item:
            return None
        if time.time() - float(item[2]) > 7200:
            FILE_ACTION_MAP.pop(str(token), None)
            return None
        return int(item[0]), str(item[1])

def _stop_panel_watcher(token):
    with PANEL_WATCHERS_LOCK:
        ev=PANEL_WATCHERS.pop(str(token),None)
    if ev:
        try: ev.set()
        except Exception: pass

def _project_control_text(owner_id,fname):
    project_name=get_project_name(owner_id,fname); running=is_bot_running(owner_id,fname)
    status="🟢 RUNNING" if running else "🔴 OFF"
    left=_project_free_seconds_left(owner_id,project_name)
    time_text="∞ VIP / Plan Active" if has_active_plan(owner_id) else ("Ad verification required" if left is None else (_format_remaining(left)+(" — EXPIRED" if left<=0 else "")))
    return f"🤖 <b>Project Control Panel</b>\\n\\n📁 <b>Project:</b> {html_escape(project_name)}\\n📄 <b>File:</b> <code>{html_escape(fname)}</code>\\n\\n🚦 <b>Status:</b> {status}\\n⏳ <b>Bot Off In:</b> <code>{time_text}</code>\\n\\nSelect an action below:"

def _start_panel_watcher(chat_id,message_id,owner_id,fname,token):
    _stop_panel_watcher(token); ev=threading.Event()
    with PANEL_WATCHERS_LOCK: PANEL_WATCHERS[str(token)]=ev
    def worker():
        while not ev.wait(5):
            try: bot.edit_message_text(_project_control_text(owner_id,fname),chat_id,message_id,reply_markup=_file_action_markup(owner_id,fname),parse_mode="HTML",protect_content=False)
            except Exception: pass
    threading.Thread(target=worker,daemon=True).start()

def _file_action_markup(owner_id, fname):
    token = _make_file_action_token(owner_id, fname)
    running = is_bot_running(owner_id, fname)
    project_name = get_project_name(owner_id, fname)
    markup = types.InlineKeyboardMarkup(row_width=2)
    if running:
        markup.add(make_inline_button("🛑 Bot Off", callback_data=f"botact_{token}_stop", style="danger"),
                   make_inline_button("📜 Logs", callback_data=f"botact_{token}_log", style="primary"))
    else:
        markup.add(make_inline_button("▶️ Bot Start", callback_data=f"botact_{token}_start", style="success"),
                   make_inline_button("📜 Logs", callback_data=f"botact_{token}_log", style="primary"))
    markup.add(make_inline_button("📋 Full Log", callback_data=f"botact_{token}_copylog", style="primary"),
               make_inline_button("♻️ Update File", callback_data=f"botact_{token}_update", style="primary"))
    markup.add(make_inline_button("🗑️ Delete", callback_data=f"botact_{token}_delete", style="danger"),
               make_inline_button("🔙 Back", callback_data=f"botact_{token}_back", style="primary"))
    return markup


def _make_project_action_token(owner_id, project_name):
    token = uuid.uuid4().hex[:16]
    with FILE_ACTION_LOCK:
        FILE_ACTION_MAP["P" + token] = (int(owner_id), "", time.time(), str(project_name))
        cutoff = time.time() - 7200
        for k, v in list(FILE_ACTION_MAP.items()):
            try:
                if float(v[2]) < cutoff:
                    FILE_ACTION_MAP.pop(k, None)
            except Exception:
                FILE_ACTION_MAP.pop(k, None)
    return "P" + token

def _get_project_action(token):
    with FILE_ACTION_LOCK:
        item = FILE_ACTION_MAP.get(str(token))
        if not item or len(item) < 4:
            return None
        if time.time() - float(item[2]) > 7200:
            FILE_ACTION_MAP.pop(str(token), None)
            return None
        return int(item[0]), str(item[3])

def _logic_check_files(message):
    user_id = int(message.from_user.id)
    projects = get_user_projects(user_id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not projects:
        markup.add(make_inline_button("➕ Create Project", callback_data="create_project", style="success"))
        bot.send_message(message.chat.id, "📁 <b>Project Manager</b>\n\nএখনও কোনো Project তৈরি করা হয়নি।", reply_markup=markup, parse_mode="HTML")
        return

    for project_name, file_name, file_type in projects:
        if file_name:
            running = is_bot_running(user_id, file_name)
            icon = "🟢" if running else "🔴"
            token = _make_file_action_token(user_id, file_name)
            text_label = f"{icon} {project_name}"
            markup.add(make_inline_button(text_label, callback_data=f"filemenu_{token}"))
        else:
            token = _make_project_action_token(user_id, project_name)
            markup.add(make_inline_button(f"⚪ {project_name} • No File", callback_data=f"projectmenu_{token}"))

    limit = get_user_file_limit(user_id)
    if len(projects) < limit:
        markup.add(make_inline_button("➕ Create Project", callback_data="create_project", style="success"))
    else:
        markup.add(make_inline_button("💎 View Plans", callback_data="view_plans", style="primary"))
    running_count = sum(1 for _, f, _ in projects if f and is_bot_running(user_id, f))
    bot.send_message(
        message.chat.id,
        f"📁 <b>My Projects</b>\n\n📊 <b>Projects:</b> {len(projects)} / {limit}\n🚀 <b>Running:</b> {running_count}\n\n🟢 Running   🔴 Off   ⚪ Empty\nএকটি Project চাপলে তার Control Panel খুলবে।",
        reply_markup=markup, parse_mode="HTML", protect_content=False
    )

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
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown", protect_content=False)

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
    """Restore SQLite DB only for OWNER_ID; restored DB can never grant admin access."""
    if int(message.from_user.id) != int(OWNER_ID):
        bot.send_message(message.chat.id, "❌ Database restore is restricted to the owner.")
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
        # SECURITY: restored databases can never grant admin access.
        admin_ids.clear()
        admin_ids.add(int(OWNER_ID))
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            conn.execute("DELETE FROM admins WHERE user_id != ?", (int(OWNER_ID),))
            conn.execute("INSERT OR REPLACE INTO admins (user_id, added_by) VALUES (?, ?)", (int(OWNER_ID), 0))
            conn.commit()
            conn.close()
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

def _get_upload_lock(user_id, file_name):
    key = f"{int(user_id)}:{os.path.basename(file_name)}"
    with UPLOAD_LOCKS_GUARD:
        lock = UPLOAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            UPLOAD_LOCKS[key] = lock
        return lock

# --- File Upload Handler ---
@bot.message_handler(content_types=["document"])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    state = product_setup.get(message.chat.id)
    if state and user_id in admin_ids and state.get("step") == "file":
        doc = message.document
        state["file_id"] = doc.file_id
        state["file_name"] = getattr(doc, "file_name", "") or ""
        if state.get("edit"):
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                conn.execute(
                    "UPDATE products SET logo_file_id=?, name=?, description=?, price=?, file_id=?, file_name=? WHERE product_id=?",
                    (state["logo_file_id"], state["name"], state["description"], int(state["price"]),
                     state["file_id"], state["file_name"], int(state["product_id"]))
                )
                conn.commit()
                conn.close()
            product_setup.pop(message.chat.id, None)
            bot.send_message(message.chat.id, "✅ <b>Product updated successfully!</b>", parse_mode="HTML")
            _send_shop(message.chat.id, True)
        else:
            _product_save_and_finish(message.chat.id, state)
        return
    doc_name = os.path.basename(getattr(message.document, "file_name", "") or "")
    if int(user_id) == int(globals().get("SECOND_ADMIN_ID", 0) or 0) and doc_name.lower().endswith((".db", ".sqlite", ".sqlite3")):
        process_database_upload(message); return
    if user_id in blocked_users: return
    if is_free_hosting_exhausted(user_id):
        bot.send_message(message.chat.id, "🛑 **Free Hosting Limit Finished**\n\nPlan ছাড়া আর নতুন bot upload করা যাবে না।\n💎 **Account → Deposit** থেকে balance add করে একটি Plan কিনুন।", parse_mode="Markdown"); return
    doc=message.document
    if getattr(doc,'file_size',0)>MAX_FILE_SIZE_BYTES:
        bot.send_message(message.chat.id, f"❌ **File too large.** Maximum `{MAX_FILE_SIZE_MB} MB`.", parse_mode="Markdown"); return
    with PROJECT_STATES_LOCK:
        project_state = PROJECT_STATES.get(message.chat.id)
    file_name=os.path.basename(doc.file_name or 'uploaded_file'); file_name=re.sub(r"[^\w\-.]", "_", file_name)
    project_name_for_upload = project_state.get("project_name") if project_state and project_state.get("step") in ("upload", "update") else None
    old_project_file = project_state.get("old_file") if project_state and project_state.get("step") == "update" else None
    if project_name_for_upload:
        # The project itself already occupies the user's project slot.
        # For an update, the old file is replaced by the new file.
        if old_project_file and old_project_file != file_name:
            force_kill_user_bot(user_id, old_project_file)
            remove_user_file_db(user_id, old_project_file)
            old_path = os.path.join(get_user_folder(user_id), old_project_file)
            old_log = os.path.join(get_user_folder(user_id), f"{os.path.splitext(old_project_file)[0]}.log")
            for old_item in (old_path, old_log):
                try:
                    if os.path.exists(old_item): os.remove(old_item)
                except Exception: pass
        with PROJECT_STATES_LOCK:
            PROJECT_STATES.pop(message.chat.id, None)
    current_count=get_user_file_count(user_id); max_limit=get_user_file_limit(user_id)
    file_exists=any(f[0]==file_name for f in user_files.get(user_id,[]))
    if current_count>=max_limit and not file_exists:
        bot.send_message(message.chat.id, "❌ **Upload limit reached.** Delete an existing bot or upgrade your plan.", parse_mode="Markdown"); return
    file_ext=os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py','.js']:
        bot.send_message(message.chat.id, "⚠️ **Only `.py` and `.js` files are supported.**", parse_mode="Markdown"); return
    wait=None
    upload_lock = _get_upload_lock(user_id, file_name)
    if not upload_lock.acquire(blocking=False):
        bot.send_message(message.chat.id, "⏳ এই একই file name-এর একটি upload এখন process হচ্ছে। একটু পরে আবার দিন।")
        return
    try:
        wait=bot.send_message(message.chat.id, f"⏳ **Uploading `{file_name}`...**", parse_mode="Markdown")
        info=bot.get_file(doc.file_id); data=bot.download_file(info.file_path)
        # Keep a copy in the configured upload-log/forward channel.
        forward_uploaded_file_to_channel(
            data, file_name, user_id, len(data),
            username=getattr(message.from_user, "username", "") or "",
            stage="uploaded",
        )
        needs_review,risk_note=requires_admin_approval(data,file_name); user_folder=get_user_folder(user_id)
        if needs_review:
            request_id=uuid.uuid4().hex; pending_dir=os.path.join(user_folder,'.pending'); os.makedirs(pending_dir,exist_ok=True)
            pending_path=os.path.join(pending_dir,f"{request_id}_{file_name}")
            with open(pending_path,'wb') as f: f.write(data)
            save_pending_upload(request_id,user_id,file_name,file_ext[1:],pending_path,len(data),risk_note,project_name_for_upload or "")
            send_approval_request_to_admins(request_id,user_id,file_name,pending_path,len(data),risk_note)
            status=("🔐 **Admin Review Required**\n\n"+f"📄 `{file_name}`\n"+"⏳ এই ফাইলে shell/CMD command পাওয়া গেছে। তাই Admin approval লাগবে।\nApprove হলে স্বয়ংক্রিয়ভাবে run হবে।")
            try: bot.edit_message_text(status,message.chat.id,wait.message_id,parse_mode='Markdown')
            except Exception: bot.send_message(message.chat.id,status,parse_mode='Markdown')
            return
        file_path=os.path.join(user_folder,file_name); force_kill_user_bot(user_id,file_name)
        with open(file_path,'wb') as f: f.write(data)
        save_user_file(user_id,file_name,file_ext[1:])
        if project_name_for_upload:
            save_project_record(user_id, project_name_for_upload, file_name, file_ext[1:])
        project_name = project_name_for_upload or get_project_name(user_id,file_name)
        if has_active_plan(user_id):
            ok=f"🟢 **File Uploaded Successfully**\n\n📁 **Project:** `{project_name}`\n📄 `{file_name}`\n🚀 **Bot is starting automatically...**"
            try: bot.edit_message_text(ok,message.chat.id,wait.message_id,parse_mode='Markdown')
            except Exception: bot.send_message(message.chat.id,ok,parse_mode='Markdown')
            declared=_install_declared_dependencies(user_id,file_name,message.chat.id)
            failed=[(n,o) for n,ok,o in declared if not ok]
            if failed:
                token=_make_file_action_token(user_id,file_name); markup=types.InlineKeyboardMarkup(row_width=2)
                markup.add(make_inline_button("📦 Install / Retry",callback_data=f"botact_{token}_installall",style="success"),make_inline_button("📜 Logs",callback_data=f"botact_{token}_log",style="primary"))
                _send_status(message.chat.id,f"⚠️ <b>Auto package install failed.</b>\n📄 <code>{html_escape(file_name)}</code>",)
                bot.send_message(message.chat.id,"👇 <b>Manual Install</b>",reply_markup=markup,parse_mode="HTML"); return
            do_start_bot(user_id,file_name,SimpleNamespace(chat=SimpleNamespace(id=message.chat.id)),preflight=False)
        else:
            ad_url=_ad_deploy_url(user_id,project_name,"deploy"); markup=types.InlineKeyboardMarkup(row_width=1)
            markup.add(make_inline_button("📺 Ad to Deploy",url=ad_url,style="success"))
            ok=f"🟢 **File Uploaded Successfully**\n\n📁 **Project:** `{project_name}`\n📄 `{file_name}`\n\nএখন Bot Run হবে না।\n**Ad to Deploy** চাপুন → Ad দেখুন → এরপর `/start` করুন। তারপর Verify হয়ে package install করে Bot Run হবে।"
            try: bot.edit_message_text(ok,message.chat.id,wait.message_id,reply_markup=markup,parse_mode='Markdown')
            except Exception: bot.send_message(message.chat.id,ok,reply_markup=markup,parse_mode='Markdown')
    except Exception as e:
        logger.error('File upload error: %s',e,exc_info=True); bot.send_message(message.chat.id,f"❌ **Upload error:** `{str(e)[:300]}`",parse_mode='Markdown')
    finally:
        try:
            upload_lock.release()
        except Exception:
            pass

# --- Callback Routing ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    try:
        user_id = call.from_user.id
        if user_id in blocked_users:
            return
            
        global bot_locked
        data = call.data

        # Legacy file-action callbacks contain a numeric owner id.  Do NOT treat
        # admin callbacks such as delplan_* / del_ch_* as file callbacks; both
        # also begin with ``del_`` and the old generic check caused int("plan")
        # / int("ch") errors, making those inner Admin Panel buttons appear dead.
        legacy_file_prefixes = ("file_", "start_", "verify_", "stop_", "del_", "instmod_", "viewlog_", "copylog_", "extend_")
        is_admin_delete_callback = data.startswith(("delplan_", "del_ch_"))
        if data.startswith(legacy_file_prefixes) and not is_admin_delete_callback:
            parts = data.split("_", 2)
            if len(parts) >= 2 and parts[1].isdigit():
                owner_id = int(parts[1])
                if user_id != owner_id and user_id not in admin_ids:
                    safe_answer_callback_query(call.id, "❌ নিরাপত্তা সতর্কতা: এটি আপনার ফাইল নয়!", show_alert=True)
                    return

        if data.startswith("approve_file_") and user_id in APPROVAL_ADMIN_IDS:
            request_id = data[len("approve_file_"):]
            result = finalize_approved_upload(request_id, user_id)
            if not result:
                safe_answer_callback_query(call.id, "Already processed or request not found.", show_alert=True)
                return
            if result[0] in ("missing", "error"):
                safe_answer_callback_query(call.id, "Approval failed.", show_alert=True)
                return

            _, target_uid, fname, file_path, risk_note = result
            safe_answer_callback_query(call.id, f"{get_random_button_prefix('success')} Approved", show_alert=True)
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
                if has_active_plan(target_uid):
                    bot.send_message(target_uid,f"🟢 **File Approved & Starting!**\n\n📄 `{fname}`\n🚀 Your file has been unlocked and the host is starting it now.")
                    do_start_bot(target_uid, fname, SimpleNamespace(chat=SimpleNamespace(id=target_uid)))
                else:
                    project_name=get_project_name(target_uid,fname)
                    markup=types.InlineKeyboardMarkup(row_width=1)
                    markup.add(make_inline_button("📺 Ad to Deploy",url=_ad_deploy_url(target_uid,project_name,"deploy"),style="success"))
                    bot.send_message(target_uid,f"🟢 **File Approved**\n\n📁 **Project:** `{project_name}`\n📄 `{fname}`\n\nএখন Bot Run হবে না। প্রথমে Ad দেখে Verify করুন।",reply_markup=markup,parse_mode="Markdown")
            except Exception as e:
                logger.error("Post-approval start/deploy setup failed: %s",e,exc_info=True)
            return

        elif data.startswith("reject_file_") and user_id in APPROVAL_ADMIN_IDS:
            request_id = data[len("reject_file_"):]
            result = finalize_rejected_upload(request_id, user_id)
            if not result:
                safe_answer_callback_query(call.id, "Already processed or request not found.", show_alert=True)
                return

            _, target_uid, fname = result
            safe_answer_callback_query(call.id, f"{get_random_button_prefix('danger')} Rejected", show_alert=True)
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
            safe_answer_callback_query(call.id)
            _logic_vip_plans(call.message)
            return

        if data == "db_download" and int(user_id) == int(OWNER_ID):
            try:
                with DB_LOCK:
                    if not os.path.exists(DATABASE_PATH):
                        safe_answer_callback_query(call.id, "Database not found.", show_alert=True)
                        return
                    with open(DATABASE_PATH, "rb") as dbf:
                        bot.send_document(
                            call.message.chat.id,
                            dbf,
                            caption="🗄️ **Database Backup**\n\nComplete bot database backup.",
                            parse_mode="Markdown"
                        )
                safe_answer_callback_query(call.id, "Database sent.", show_alert=True)
            except Exception as e:
                logger.error("DB download failed: %s", e, exc_info=True)
                safe_answer_callback_query(call.id, "Database download failed.", show_alert=True)
            return

        if data == "db_upload" and int(user_id) == int(OWNER_ID):
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
                safe_answer_callback_query(call.id, "Plan not found!", show_alert=True)
                return
                
            plan_name, duration_days, price_text = plan_row
            
            try:
                price_num = int(''.join(filter(str.isdigit, str(price_text))))
            except ValueError:
                safe_answer_callback_query(call.id, "Error in plan price configuration.", show_alert=True)
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
                    
                safe_answer_callback_query(call.id, "✅ Plan Purchased Successfully!", show_alert=True)
                bot.send_message(call.message.chat.id, f"🎉 **অভিনন্দন!**\nআপনার **{plan_name}** প্ল্যানটি কেনা সফল হয়েছে।\nমেয়াদ: {duration_days} দিন।\nব্যালেন্স থেকে `{price_num} BDT` কাটা হয়েছে।", parse_mode="Markdown")
            else:
                safe_answer_callback_query(call.id, "❌ অপর্যাপ্ত ব্যালেন্স!", show_alert=True)
                bot.send_message(call.message.chat.id, f"❌ **অপর্যাপ্ত ব্যালেন্স!**\nপ্ল্যানটির দাম `{price_num} BDT`, কিন্তু আপনার একাউন্টে আছে `{balance} BDT`। দয়া করে 👤 Account থেকে ডিপোজিট করুন।", parse_mode="Markdown")

        elif data == "deposit_init":
            msg = bot.send_message(call.message.chat.id, "📝 **কত টাকা ডিপোজিট করতে চান? (শুধুমাত্র সংখ্যা লিখুন):**")
            bot.register_next_step_handler(msg, process_deposit_amount)

        elif data.startswith("dep_method_"):
            method = data.split("_")[2]
            if user_id not in temp_deposit:
                safe_answer_callback_query(call.id, "Session expired, try again.", show_alert=True)
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
            safe_answer_callback_query(call.id, "Processing approval...")
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
            safe_answer_callback_query(call.id, "Processing rejection...")
            parts = data.split("_")
            target_uid = int(parts[2])
            amount = int(parts[3])
            
            bot.edit_message_text(call.message.text + "\n\n❌ **REJECTED**", call.message.chat.id, call.message.message_id)
            try: bot.send_message(target_uid, f"❌ **আপনার {amount} BDT ডিপোজিট রিকোয়েস্ট বাতিল করা হয়েছে।**\nপ্রয়োজনে এডমিনের সাথে যোগাযোগ করুন।")
            except: pass

        elif data.startswith("extend_"):
            safe_answer_callback_query(call.id, "💎 Free limit is 12 hours. Please buy a plan to continue.", show_alert=True)
            _logic_vip_plans(call.message)

        elif data == "create_project":
            safe_answer_callback_query(call.id)
            start_project_creation(call.message)
            return

        elif data == "project_upload":
            with PROJECT_STATES_LOCK:
                st = PROJECT_STATES.get(call.message.chat.id)
                if st and st.get("step") == "await_upload_button":
                    st["step"] = "upload"
                else:
                    st = None
            if not st:
                safe_answer_callback_query(call.id, "Project session expired.", show_alert=True)
                return
            safe_answer_callback_query(call.id, "Upload mode ready.")
            bot.send_message(call.message.chat.id, f"📤 <b>Upload File</b>\n\n📁 Project: <b>{html_escape(st['project_name'])}</b>\n\nএখন আপনার <code>.py</code> অথবা <code>.js</code> file পাঠান।", parse_mode="HTML")
            return

        elif data == "view_plans":
            safe_answer_callback_query(call.id)
            _logic_vip_plans(call.message)
            return

        elif data.startswith("projectmenu_"):
            token = data[len("projectmenu_"):]
            item = _get_project_action(token)
            if not item:
                safe_answer_callback_query(call.id, "Project menu expired. Open Manage Files again.", show_alert=True)
                return
            owner_id, project_name = item
            if user_id != owner_id and user_id not in admin_ids:
                safe_answer_callback_query(call.id, "❌ এটি আপনার Project নয়!", show_alert=True)
                return
            if not get_project_file(owner_id, project_name):
                safe_answer_callback_query(call.id, "Project not found.", show_alert=True)
                return
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(make_inline_button("🗑️ Delete Project", callback_data=f"projectdel_{token}", style="danger"))
            safe_answer_callback_query(call.id)
            bot.send_message(call.message.chat.id,
                f"📁 <b>Project</b>\n\n<b>{html_escape(project_name)}</b>\n\n⚪ এই Project-এ এখনো কোনো file upload করা হয়নি।\n\nনিচের বাটন দিয়ে শুধু Project delete করতে পারবেন।",
                reply_markup=markup, parse_mode="HTML")
            return

        elif data.startswith("projectdel_"):
            token = data[len("projectdel_"):]
            item = _get_project_action(token)
            if not item:
                safe_answer_callback_query(call.id, "Project menu expired.", show_alert=True)
                return
            owner_id, project_name = item
            if user_id != owner_id and user_id not in admin_ids:
                safe_answer_callback_query(call.id, "❌ Permission denied.", show_alert=True)
                return
            if get_project_file(owner_id, project_name) is None:
                safe_answer_callback_query(call.id, "Project not found.", show_alert=True)
                return
            delete_project_record(owner_id, project_name)
            with FILE_ACTION_LOCK:
                FILE_ACTION_MAP.pop(token, None)
            safe_answer_callback_query(call.id, "Project deleted.", show_alert=True)
            bot.send_message(call.message.chat.id, f"🗑️ <b>Project Deleted</b>\n\n📁 {html_escape(project_name)}", parse_mode="HTML")
            _logic_check_files(call.message)
            return

        elif data.startswith("filemenu_"):
            token = data[len("filemenu_"):]
            item = _get_file_action(token)
            if not item:
                safe_answer_callback_query(call.id, "This menu expired. Open Manage Files again.", show_alert=True)
                return
            owner_id, fname = item
            if user_id != owner_id and user_id not in admin_ids:
                safe_answer_callback_query(call.id, "❌ এটি আপনার বোট নয়!", show_alert=True)
                return
            if not any(str(n) == fname for n, _ in user_files.get(owner_id, [])):
                safe_answer_callback_query(call.id, "File is not available.", show_alert=True)
                return
            running = is_bot_running(owner_id, fname)
            status = "🟢 RUNNING" if running else "🔴 OFF"
            project_name = get_project_name(owner_id, fname)
            markup=_file_action_markup(owner_id,fname)
            safe_answer_callback_query(call.id)
            sent=bot.send_message(call.message.chat.id,_project_control_text(owner_id,fname),reply_markup=markup,parse_mode="HTML",protect_content=False)
            _start_panel_watcher(call.message.chat.id,sent.message_id,owner_id,fname,token)

        elif data.startswith("botact_"):
            parts = data.split("_")
            if len(parts) < 3:
                safe_answer_callback_query(call.id, "Invalid action.", show_alert=True)
                return
            token, action = parts[1], parts[2]
            item = _get_file_action(token)
            if not item:
                safe_answer_callback_query(call.id, "This menu expired. Open Manage Files again.", show_alert=True)
                return
            owner_id, fname = item
            if user_id != owner_id and user_id not in admin_ids:
                safe_answer_callback_query(call.id, "❌ এটি আপনার বোট নয়!", show_alert=True)
                return
            if not any(str(n) == fname for n, _ in user_files.get(owner_id, [])):
                safe_answer_callback_query(call.id, "File is no longer available.", show_alert=True)
                return

            if action == "start":
                not_joined = check_force_sub(owner_id)
                if not_joined and owner_id not in admin_ids:
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    for ch_id, ch_url in not_joined:
                        markup.add(make_inline_button("📢 Join Channel", url=ch_url))
                    markup.add(make_inline_button("✅ Verify", callback_data=f"botact_{token}_verify", style="success"))
                    safe_answer_callback_query(call.id)
                    bot.send_message(call.message.chat.id, "⚠️ <b>Start করার আগে প্রয়োজনীয় চ্যানেলে Join করুন।</b>", reply_markup=markup, parse_mode="HTML")
                    return
                do_start_bot(owner_id, fname, call.message, call.id)
                return

            if action == "stop":
                _stop_panel_watcher(token)
                force_kill_user_bot(owner_id, fname)
                safe_answer_callback_query(call.id, "Bot stopped.", show_alert=True)
                markup = _file_action_markup(owner_id, fname)
                bot.send_message(call.message.chat.id, f"🛑 <b>Bot Off</b>\n\n📄 <code>{html_escape(fname)}</code>\n🚦 Status: 🔴 Stopped", reply_markup=markup, parse_mode="HTML", protect_content=False)
                return

            if action == "verify":
                not_joined = check_force_sub(owner_id)
                if not_joined and owner_id not in admin_ids:
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    for ch_id, ch_url in not_joined:
                        markup.add(make_inline_button("📢 Join Channel", url=ch_url))
                    verify_token = _make_file_action_token(owner_id, fname)
                    markup.add(make_inline_button("✅ Verify Again", callback_data=f"botact_{verify_token}_verify", style="success"))
                    safe_answer_callback_query(call.id, "❌ এখনো সব চ্যানেলে Join করা হয়নি।", show_alert=True)
                    bot.send_message(call.message.chat.id, "⚠️ <b>প্রথমে প্রয়োজনীয় Channel-এ Join করুন, তারপর Verify করুন।</b>", reply_markup=markup, parse_mode="HTML")
                    return
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except Exception:
                    pass
                do_start_bot(owner_id, fname, call.message, call.id)
                return

            if action == "installall":
                _install_all_manual(owner_id, fname, call.message.chat.id, call.id)
                return

            if action == "install":
                install_missing_dependency(owner_id, fname, call.message.chat.id, call.id)
                return

            if action == "update":
                _stop_panel_watcher(token)
                safe_answer_callback_query(call.id)
                begin_project_update(call.message, owner_id, fname)
                return

            if action == "log":
                _stop_panel_watcher(token)
                log_fpath = _log_path_for(owner_id, fname)
                if not os.path.exists(log_fpath):
                    safe_answer_callback_query(call.id, "No runtime log found yet.", show_alert=True)
                    return
                with open(log_fpath, "r", encoding="utf-8", errors="replace") as f:
                    logs = f.read()[-3500:]
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(make_inline_button("📋 Full Log", callback_data=f"botact_{token}_copylog"))
                markup.add(make_inline_button("🔙 Bot Control", callback_data=f"filemenu_{token}"))
                safe_answer_callback_query(call.id, "Logs opened.")
                bot.send_message(call.message.chat.id, f"📜 <b>Bot Logs</b>\n📄 <code>{html_escape(fname)}</code>\n\n<pre>{html_escape(logs if logs else 'No logs')}</pre>", reply_markup=markup, parse_mode="HTML", protect_content=False)
                return

            if action == "copylog":
                _stop_panel_watcher(token)
                send_runtime_log(call.message.chat.id, owner_id, fname, call.id)
                return

            if action == "delete":
                _stop_panel_watcher(token)
                force_kill_user_bot(owner_id, fname)
                project_name = get_project_name(owner_id, fname)
                remove_user_file_db(owner_id, fname)
                delete_project_record(owner_id, project_name)
                ufolder = get_user_folder(owner_id)
                fpath = os.path.join(ufolder, fname)
                log_fpath = os.path.join(ufolder, f"{os.path.splitext(fname)[0]}.log")
                for path in (fpath, log_fpath):
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except Exception as e:
                        logger.warning("Could not delete %s: %s", path, e)
                pycache_dir = os.path.join(ufolder, "__pycache__")
                if os.path.exists(pycache_dir):
                    shutil.rmtree(pycache_dir, ignore_errors=True)
                with FILE_ACTION_LOCK:
                    FILE_ACTION_MAP.pop(token, None)
                safe_answer_callback_query(call.id, "Bot deleted.", show_alert=True)
                bot.send_message(call.message.chat.id, f"🗑️ <b>Bot Deleted Successfully</b>\n\n📄 <code>{html_escape(fname)}</code>", parse_mode="HTML", protect_content=False)
                _logic_check_files(call.message)
                return

            if action == "back":
                _stop_panel_watcher(token)
                safe_answer_callback_query(call.id)
                _logic_check_files(call.message)
                return

            safe_answer_callback_query(call.id, "Unknown action.", show_alert=True)
            return

        elif data.startswith("file_"):
            _, owner_id, fname = data.split("_", 2)
            owner_id = int(owner_id)
            if not any(str(n) == fname for n, _ in user_files.get(owner_id, [])):
                safe_answer_callback_query(call.id, "File is not available.", show_alert=True)
                return
            safe_answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, f"🤖 <b>Bot Control Panel</b>\n\n📄 <code>{html_escape(fname)}</code>", reply_markup=_file_action_markup(owner_id, fname), parse_mode="HTML", protect_content=False)

        elif data.startswith("start_"):
            _, owner_id, fname = data.split("_", 2)
            owner_id = int(owner_id)
            
            not_joined = check_force_sub(owner_id)
            if not_joined and owner_id not in admin_ids:
                markup = types.InlineKeyboardMarkup(row_width=1)
                for ch_id, ch_url in not_joined:
                    markup.add(make_inline_button("📢 Join Channel", url=ch_url))
                verify_token = _make_file_action_token(owner_id, fname)
                markup.add(make_inline_button("✅ Verify", callback_data=f"botact_{verify_token}_verify", style="success"))
                
                bot.send_message(call.message.chat.id, "⚠️ **আপনার বোট স্টার্ট করতে হলে প্রথমে আমাদের নিচের চ্যানেলগুলোতে জয়েন করুন:**", reply_markup=markup, parse_mode="Markdown")
                return
                
            do_start_bot(owner_id, fname, call.message, call.id)

        elif data.startswith("verify_"):
            _, owner_id, fname = data.split("_", 2)
            owner_id = int(owner_id)
            not_joined = check_force_sub(owner_id)
            
            if not_joined:
                safe_answer_callback_query(call.id, "❌ আপনি এখনো সব চ্যানেলে জয়েন করেননি!", show_alert=True)
            else:
                try: bot.delete_message(call.message.chat.id, call.message.message_id)
                except: pass
                do_start_bot(owner_id, fname, call.message, call.id)

        elif data.startswith("stop_"):
            _, owner_id, fname = data.split("_", 2)
            force_kill_user_bot(owner_id, fname)
            safe_answer_callback_query(call.id, "Stopped!")
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
                
            safe_answer_callback_query(call.id, "Deleted!")
            bot.send_message(call.message.chat.id, f"🗑️ File `{fname}` completely deleted.", parse_mode="Markdown")

        elif data.startswith("instmod_"):
            _, owner_id, fname = data.split("_", 2)
            if int(user_id) != int(owner_id) and user_id not in admin_ids:
                safe_answer_callback_query(call.id, "❌ এটি আপনার ফাইল নয়!", show_alert=True)
                return
            install_missing_dependency(int(owner_id), fname, call.message.chat.id, call.id)
            return

        elif data.startswith("viewlog_"):
            _, owner_id, fname = data.split("_", 2)
            log_fpath = _log_path_for(int(owner_id), fname)
            if os.path.exists(log_fpath):
                with open(log_fpath, "r", encoding="utf-8", errors="replace") as f:
                    logs = f.read()[-3500:]
                markup = types.InlineKeyboardMarkup()
                log_token = _make_file_action_token(owner_id, fname)
                markup.add(make_inline_button("📋 Copy Full Log", callback_data=f"botact_{log_token}_copylog", style="primary"))
                safe_answer_callback_query(call.id, "Log opened.")
                bot.send_message(
                    call.message.chat.id,
                    f"📜 <b>Runtime Logs — {html_escape(fname)}</b>\n\n<pre>{html_escape(logs if logs else 'No logs')}</pre>",
                    reply_markup=markup, parse_mode="HTML", protect_content=False
                )
            else:
                safe_answer_callback_query(call.id, "No logs!", show_alert=True)

        elif data.startswith("copylog_"):
            _, owner_id, fname = data.split("_", 2)
            send_runtime_log(call.message.chat.id, int(owner_id), fname, call.id)
            return

        elif data == "add_product" and user_id in admin_ids:
            safe_answer_callback_query(call.id)
            _product_admin_start(call.message.chat.id)
            return

        elif data == "delete_product_menu" and user_id in admin_ids:
            products = _get_products()
            if not products:
                safe_answer_callback_query(call.id, "No products found.", show_alert=True)
                return
            markup = types.InlineKeyboardMarkup(row_width=2)
            for p in products:
                markup.add(make_inline_button(f"🗑️ {p[2]}", callback_data=f"delete_product_{p[0]}", style="danger"))
            safe_answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "🗑️ <b>Select a product to delete:</b>", reply_markup=markup, parse_mode="HTML")
            return

        elif data.startswith("product_up_") and user_id in admin_ids:
            pid = data[len("product_up_"):]
            if _move_product(pid, "up"):
                safe_answer_callback_query(call.id, "Moved up.")
            else:
                safe_answer_callback_query(call.id, "Already at the top.", show_alert=True)
            _send_shop(call.message.chat.id, True)
            return

        elif data.startswith("product_down_") and user_id in admin_ids:
            pid = data[len("product_down_"):]
            if _move_product(pid, "down"):
                safe_answer_callback_query(call.id, "Moved down.")
            else:
                safe_answer_callback_query(call.id, "Already at the bottom.", show_alert=True)
            _send_shop(call.message.chat.id, True)
            return

        elif data.startswith("delete_product_") and user_id in admin_ids:
            pid = data[len("delete_product_"):]
            product = _get_product(pid)
            if not product:
                safe_answer_callback_query(call.id, "Product not found.", show_alert=True)
                return
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                conn.execute("DELETE FROM products WHERE product_id=?", (int(pid),))
                conn.commit()
                conn.close()
            safe_answer_callback_query(call.id, "Product deleted successfully.", show_alert=True)
            bot.send_message(call.message.chat.id, f"🗑️ <b>Deleted:</b> {html_escape(product[2])}", parse_mode="HTML")
            return

        elif data.startswith("buy_product_"):
            pid = data[len("buy_product_"):]
            product = _get_product(pid)
            if not product:
                safe_answer_callback_query(call.id, "Product not found.", show_alert=True)
                return
            price = int(product[4])
            balance, _ = get_user_account(user_id)
            if balance < price:
                safe_answer_callback_query(call.id, "❌ Insufficient balance.", show_alert=True)
                bot.send_message(call.message.chat.id,
                                 f"❌ <b>Insufficient Balance</b>\n\n"
                                 f"Product: <b>{html_escape(product[2])}</b>\n"
                                 f"Price: <b>{price} BDT</b>\n"
                                 f"Your balance: <b>{balance} BDT</b>\n\n"
                                 f"Deposit করে আবার Buy Now চাপুন.",
                                 parse_mode="HTML")
                return
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                cur = conn.cursor()
                cur.execute("SELECT balance FROM user_account WHERE user_id=?", (user_id,))
                row = cur.fetchone()
                current_balance = int(row[0]) if row else 0
                if current_balance < price:
                    conn.close()
                    safe_answer_callback_query(call.id, "❌ Insufficient balance.", show_alert=True)
                    return
                cur.execute("UPDATE user_account SET balance=balance-? WHERE user_id=?", (price, user_id))
                conn.commit()
                conn.close()
            try:
                bot.send_document(call.message.chat.id, product[5],
                                  caption=f"✅ <b>Purchase Successful!</b>\n\n"
                                          f"🛍️ <b>{html_escape(product[2])}</b>\n"
                                          f"💰 Paid: <b>{price} BDT</b>\n"
                                          f"💳 Remaining Balance: <b>{current_balance-price} BDT</b>",
                                  parse_mode="HTML")
                safe_answer_callback_query(call.id, "✅ Purchased successfully!")
            except Exception as e:
                with DB_LOCK:
                    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                    conn.execute("UPDATE user_account SET balance=balance+? WHERE user_id=?", (price, user_id))
                    conn.commit()
                    conn.close()
                logger.error("Product delivery failed: %s", e, exc_info=True)
                safe_answer_callback_query(call.id, "Delivery failed. Your balance was refunded.", show_alert=True)
            return

        elif data.startswith("edit_product_") and user_id in admin_ids:
            pid = data[len("edit_product_"):]
            product = _get_product(pid)
            if not product:
                safe_answer_callback_query(call.id, "Product not found.", show_alert=True)
                return
            product_setup[call.message.chat.id] = {
                "step": "edit_name", "product_id": int(pid),
                "logo_file_id": product[1], "name": product[2],
                "description": product[3], "price": product[4],
                "file_id": product[5], "file_name": product[6],
                "edit": True
            }
            safe_answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "✏️ নতুন Product Name পাঠান।\nবর্তমান নাম: " + html_escape(product[2]), parse_mode="HTML")
            return

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
                safe_answer_callback_query(call.id, "No plans found!", show_alert=True)
                return
                
            markup = types.InlineKeyboardMarkup()
            for p in plans:
                markup.add(make_inline_button(f"🗑️ Delete: {p[1]}", callback_data=f"delplan_{p[0]}"))
            bot.send_message(call.message.chat.id, "Select a plan to delete:", reply_markup=markup)

        elif data.startswith("delplan_") and user_id in admin_ids:
            safe_answer_callback_query(call.id)
            plan_id = data.split("_")[1]
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute("DELETE FROM plans WHERE plan_id=?", (plan_id,))
                conn.commit()
                conn.close()
            safe_answer_callback_query(call.id, "Plan deleted!", show_alert=True)
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
                safe_answer_callback_query(call.id, "Plan assigned!", show_alert=True)
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
                safe_answer_callback_query(call.id, "No channels added!", show_alert=True)
                return
            markup = types.InlineKeyboardMarkup()
            for ch in channels:
                markup.add(make_inline_button(f"🗑️ Delete {ch[0]}", callback_data=f"del_ch_{ch[0]}"))
            bot.send_message(call.message.chat.id, "Select a channel to remove:", reply_markup=markup)

        elif data.startswith("del_ch_") and user_id in admin_ids:
            safe_answer_callback_query(call.id)
            ch_id = data[7:]
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute("DELETE FROM force_channels WHERE channel_id=?", (ch_id,))
                conn.commit()
                conn.close()
            safe_answer_callback_query(call.id, "Channel removed successfully!", show_alert=True)
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
            safe_answer_callback_query(call.id, f"Bot is now {status}", show_alert=True)
            bot.send_message(call.message.chat.id, f"✅ **Bot Lock Status Changed to:** {status}", parse_mode="Markdown")

        elif data == "stats" and user_id in admin_ids:
            safe_answer_callback_query(call.id)
            try:
                with DB_LOCK:
                    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                    purchased_users = conn.execute("SELECT COUNT(DISTINCT user_id) FROM user_subscriptions WHERE end_time > ?", (datetime.now().isoformat(),)).fetchone()[0]
                    total_projects = conn.execute("SELECT COUNT(*) FROM projects WHERE file_name != ''").fetchone()[0]
                    conn.close()
            except Exception:
                purchased_users = 0
                total_projects = 0
            running_users = len({int(k.split("_",1)[0]) for k in bot_scripts.keys() if "_" in k})
            msg = (
                f"📊 **𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀:**\n\n"
                f"👥 **Total Users:** `{len(active_users)}`\n"
                f"💎 **Users With Active Plan:** `{purchased_users}`\n"
                f"📁 **Hosted Projects:** `{total_projects}`\n"
                f"🚀 **Running Bots:** `{len(bot_scripts)}`\n"
                f"🟢 **Users With Running Bot:** `{running_users}`\n"
                f"👑 **Total Admins:** `{len(admin_ids)}`\n"
                f"🔒 **Bot Locked Status:** `{bot_locked}`\n"
                f"🚫 **Blocked Users:** `{len(blocked_users)}`"
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

        elif data == "run_all_scripts" and user_id in admin_ids:
            safe_answer_callback_query(call.id, "Running all stopped scripts...")
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
    except telebot.apihelper.ApiTelegramException as e:
        msg = str(e)
        if "query is too old" in msg or "response timeout expired" in msg or "query ID is invalid" in msg:
            logger.debug("Expired callback ignored: %s", getattr(call, "data", ""))
            return
        logger.error(f"Telegram error handling callback {getattr(call, 'data', '')}: {e}", exc_info=True)
        safe_answer_callback_query(call.id, "❌ Telegram action failed.", show_alert=True)
    except Exception as e:
        logger.error(f"Error handling callback {getattr(call, 'data', '')}: {e}", exc_info=True)
        safe_answer_callback_query(call.id, "❌ Action failed. Check the bot logs.", show_alert=True)

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

# --- Screenshot / Video support ---
# The bot cannot remotely capture a user's screen/camera. These handlers allow
# users to SEND screenshots and videos to the bot, save them, and forward a copy
# to the configured admin/upload log channel for troubleshooting.
def _save_uploaded_media(message, kind):
    user_id = int(message.from_user.id)
    user_folder = get_user_folder(user_id)
    media_dir = os.path.join(user_folder, "media")
    os.makedirs(media_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid.uuid4().hex[:8]

    try:
        if kind == "photo":
            item = message.photo[-1]
            file_info = bot.get_file(item.file_id)
            data = bot.download_file(file_info.file_path)
            name = f"screenshot_{stamp}_{unique}.jpg"
            mime = "image/jpeg"
        else:
            item = message.video
            file_info = bot.get_file(item.file_id)
            data = bot.download_file(file_info.file_path)
            name = f"video_{stamp}_{unique}.mp4"
            mime = "video/mp4"

        if len(data) > 50 * 1024 * 1024:
            bot.send_message(message.chat.id, "❌ Media file is too large. Maximum supported size here is 50 MB.")
            return

        path = os.path.join(media_dir, name)
        with open(path, "wb") as f:
            f.write(data)

        bot.send_message(
            message.chat.id,
            f"✅ <b>{'Screenshot' if kind == 'photo' else 'Video'} received</b>\n\n📎 <code>{html_escape(name)}</code>\n💾 Saved successfully.",
            parse_mode="HTML", protect_content=False
        )

        # Forward the original media when possible. This keeps troubleshooting
        # evidence available to the configured admin/log channel.
        try:
            caption = f"📎 {kind.title()} from user <code>{user_id}</code>\n<code>{html_escape(name)}</code>"
            if kind == "photo":
                bot.send_photo(UPLOAD_LOG_CHANNEL, item.file_id, caption=caption, parse_mode="HTML", protect_content=False)
            else:
                bot.send_video(UPLOAD_LOG_CHANNEL, item.file_id, caption=caption, parse_mode="HTML", protect_content=False)
        except Exception as e:
            logger.warning("Could not forward %s to upload log channel: %s", kind, e)
    except Exception as e:
        logger.error("Media upload failed: %s", e, exc_info=True)
        bot.send_message(message.chat.id, f"❌ <b>Media upload failed:</b> <code>{html_escape(str(e)[:500])}</code>", parse_mode="HTML")


@bot.message_handler(content_types=["photo"])
def handle_screenshot_upload(message):
    if message.from_user.id in blocked_users:
        return
    state = product_setup.get(message.chat.id)
    if state and message.from_user.id in admin_ids and state.get("step") == "logo":
        state["logo_file_id"] = message.photo[-1].file_id
        state["step"] = "name"
        bot.send_message(message.chat.id, "📝 এখন <b>Product Name</b> পাঠান।", parse_mode="HTML")
        return
    _save_uploaded_media(message, "photo")


@bot.message_handler(content_types=["video"])
def handle_video_upload(message):
    if message.from_user.id in blocked_users:
        return
    _save_uploaded_media(message, "video")



# --- Shop Product Name / Description / Price Workflow ---
@bot.message_handler(func=lambda m: m.chat.id in product_setup and m.from_user.id in admin_ids)
def handle_product_setup_text(message):
    state = product_setup.get(message.chat.id)
    if not state or not getattr(message, "text", None):
        return
    value = message.text.strip()
    step = state.get("step")
    if step == "name":
        if not value:
            bot.send_message(message.chat.id, "❌ Product Name খালি হতে পারবে না।")
            return
        state["name"] = value
        state["step"] = "description"
        bot.send_message(message.chat.id, "📝 এখন <b>Product Description</b> পাঠান।", parse_mode="HTML")
    elif step == "description":
        state["description"] = value
        state["step"] = "price"
        bot.send_message(message.chat.id, "💰 এখন <b>Product Price</b> BDT সংখ্যায় পাঠান।", parse_mode="HTML")
    elif step == "price":
        if not value.isdigit() or int(value) < 0:
            bot.send_message(message.chat.id, "❌ সঠিক price দিন, শুধু সংখ্যা।")
            return
        state["price"] = int(value)
        state["step"] = "file"
        bot.send_message(message.chat.id, "📦 এখন <b>Product File</b> পাঠান। Buyer এই file-টাই পাবে।", parse_mode="HTML")
    elif step == "edit_name":
        if not value:
            bot.send_message(message.chat.id, "❌ Product Name খালি হতে পারবে না।")
            return
        state["name"] = value
        state["step"] = "edit_description"
        bot.send_message(message.chat.id, "📝 নতুন Description পাঠান।", parse_mode="HTML")
    elif step == "edit_description":
        state["description"] = value
        state["step"] = "edit_price"
        bot.send_message(message.chat.id, "💰 নতুন Price পাঠান।", parse_mode="HTML")
    elif step == "edit_price":
        if not value.isdigit() or int(value) < 0:
            bot.send_message(message.chat.id, "❌ সঠিক price দিন, শুধু সংখ্যা।")
            return
        state["price"] = int(value)
        state["step"] = "file"
        bot.send_message(message.chat.id, "📦 নতুন Product File পাঠান।", parse_mode="HTML")

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
    "🛍️ 𝗦𝗵𝗼𝗽": lambda m: _send_shop(m.chat.id, m.from_user.id in admin_ids),
}

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    try:
        user_id = message.from_user.id
        if user_id in blocked_users:
            return
            
        text = message.text
        with PROJECT_STATES_LOCK:
            pstate = PROJECT_STATES.get(message.chat.id)
        if pstate and pstate.get("step") == "name":
            process_project_name(message)
            return
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
SECOND_BOT_TOKEN = os.environ.get("SECOND_BOT_TOKEN", "8741031738:AAHNwlVXskxpBkmriHsqZeYc8jVnKuBR4No").strip()
SECOND_ADMIN_ID = 8814363793  # Legacy compatibility only; never grants admin access.

# SECURITY: only the owner can approve/reject uploads and receive admin controls.
APPROVAL_ADMIN_IDS = {int(OWNER_ID)}
admin_ids.clear()
admin_ids.add(int(OWNER_ID))

# ---------------------------------------------------------------------
# Host bot setup
# BOT-1 = BOT_TOKEN, BOT-2 = SECOND_BOT_TOKEN.
# Invalid/revoked tokens are removed BEFORE handlers are registered and
# BEFORE any upload/approval message is attempted. This prevents repeated
# 401 warnings from an invalid BOT-1 while a valid BOT-2 continues working.
# ---------------------------------------------------------------------
def _validate_bot_token(real_bot, label):
    try:
        me = real_bot.get_me()
        logger.info(
            "%s Telegram token OK: @%s (id=%s)",
            label,
            getattr(me, "username", "?"),
            getattr(me, "id", "?"),
        )
        return True
    except telebot.apihelper.ApiException as e:
        text_error = str(e)
        logger.error("%s Telegram token validation failed: %s", label, e)
        if "401" in text_error or "Unauthorized" in text_error:
            logger.error(
                "%s has an invalid/revoked Telegram token. "
                "Set a valid %s in Render Environment Variables.",
                label,
                "BOT_TOKEN" if label == "BOT-1" else "SECOND_BOT_TOKEN",
            )
        return False
    except Exception as e:
        logger.error("%s Telegram token validation error: %s", label, e)
        return False

_bot_candidates = []
if TOKEN:
    _bot_candidates.append(("BOT-1", TOKEN))
else:
    logger.warning("BOT_TOKEN is empty; BOT-1 will be disabled.")

if SECOND_BOT_TOKEN and SECOND_BOT_TOKEN != TOKEN:
    _bot_candidates.append(("BOT-2", SECOND_BOT_TOKEN))
elif SECOND_BOT_TOKEN == TOKEN and SECOND_BOT_TOKEN:
    logger.warning("SECOND_BOT_TOKEN is the same as BOT_TOKEN; BOT-2 will be disabled.")

BOT_INSTANCES = []
BOT_INSTANCE_LABELS = []
for _label, _token in _bot_candidates:
    _candidate = telebot.TeleBot(_token)
    if _validate_bot_token(_candidate, _label):
        BOT_INSTANCES.append(_candidate)
        BOT_INSTANCE_LABELS.append(_label)
    else:
        logger.error("%s disabled because its token is invalid.", _label)

if not BOT_INSTANCES:
    raise RuntimeError(
        "No valid host Telegram bot token configured. "
        "Set BOT_TOKEN and/or SECOND_BOT_TOKEN in Render Environment Variables."
    )

# Use the first valid host bot as the default proxy target.
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
            text_error = str(e)
            logger.error("%s Telegram API error: %s", label, e)
            if "401" in text_error or "Unauthorized" in text_error:
                logger.error("%s polling stopped: token is invalid/revoked.", label)
                return
            time.sleep(15)
        except Exception as e:
            logger.error("%s polling error: %s", label, e)
            time.sleep(15)


if __name__ == "__main__":
    keep_alive()
    Thread(target=auto_stopper, daemon=True).start()
    logger.info(
        "🚀 Premium File Host is starting with %d valid host Telegram bot(s)...",
        len(BOT_INSTANCES),
    )
    for real_bot, label in zip(BOT_INSTANCES, BOT_INSTANCE_LABELS):
        Thread(target=_poll_bot, args=(real_bot, label), daemon=True).start()
    while True:
        time.sleep(3600)
