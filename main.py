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

# --- Flask Keep Alive ---
app = Flask("")

@app.route("/")
def home():
    return "I'm Mukesh File Host - Secure Mode"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

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

# Folder setup - using absolute paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, "upload_bots")
IROTECH_DIR = os.path.join(BASE_DIR, "inf")
DATABASE_PATH = os.path.join(IROTECH_DIR, "bot_data.db")

# Create necessary directories
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# Initialize bot
bot = telebot.TeleBot(TOKEN)

# --- Data structures ---
bot_scripts = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
blocked_users = set()
bot_locked = False

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Command Button Layouts ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨", "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹"],
    ["🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲", "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"],
    ["🎁 𝗥𝗲𝗳𝗲𝗿 & 𝗘𝗮𝗿𝗻", "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴"],
    ["📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀", "💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹 𝗖𝗺𝗱"],
    ["👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿"],
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨", "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹"],
    ["🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲", "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"],
    ["🎁 𝗥𝗲𝗳𝗲𝗿 & 𝗘𝗮𝗿𝗻", "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹"],
    ["⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴", "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀"],
    ["👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿"],
]

# --- Database Setup ---
DB_LOCK = threading.Lock()

def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS user_files (user_id INTEGER, file_name TEXT, file_type TEXT, status TEXT DEFAULT 'pending', PRIMARY KEY (user_id, file_name))""")
        c.execute("""CREATE TABLE IF NOT EXISTS active_users (user_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS force_channels (channel_id TEXT PRIMARY KEY, channel_url TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS referrals (user_id INTEGER, referred_user_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS custom_limits (user_id INTEGER PRIMARY KEY, max_limit INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS blocked_users (user_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")

        c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (ADMIN_ID,))

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        c.execute("SELECT user_id, file_name, file_type, status FROM user_files")
        for user_id, file_name, file_type, status in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type, status))

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

# --- Settings Helper ---
def get_setting(key, default=""):
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else default
    except:
        return default

def set_setting(key, value):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()

# --- Security & Anti-Hack Functions ---
def block_and_alert_user(user_id, user_name, reason):
    if user_id in admin_ids:
        return
        
    blocked_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO blocked_users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
        
    alert_msg = (
        f"🚨 **SECURITY ALERT: HACK ATTEMPT BLOCKED!** 🚨\n\n"
        f"👤 **Name:** {user_name}\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"❌ **Reason:** `{reason}`\n\n"
        f"⚠️ *এই ইউজার সার্ভার কন্ট্রোল বা হ্যাক করার চেষ্টা করায় তাকে স্থায়ীভাবে ব্লক করা হয়েছে!*"
    )
    try:
        bot.send_message(OWNER_ID, alert_msg, parse_mode="Markdown")
        bot.send_message(user_id, "🚫 **আপনাকে সার্ভার হ্যাক বা ক্ষতিকর স্ক্রিপ্ট আপলোড করার কারণে স্থায়ীভাবে ব্লক করা হয়েছে!**", protect_content=True)
    except:
        pass

MALWARE_SIGNATURES = [b"MZ", b"\x7fELF", b"\xfe\xed\xfa", b"\xce\xfa\xed\xfe", b"PK", b"Rar!"]

DANGEROUS_KEYWORDS = [
    b"ransomware", b"trojan", b"virus", b"malware", b"backdoor", 
    b"botnet", b"keylogger", b"../", b"..\\", b"bot_data.db",
    b"os.system", b"subprocess.", b"shutil.rmtree", b"socket.", 
    b"urllib.", b"requests.", b"eval(", b"exec(", b"__import__", 
    b"pickle.", b"ctypes", b"fork()", b"while True:", b"while(1):", 
    b"child_process", b"require('child_process')", b"execSync", b"spawn(",
    b"127.0.0.1", b"localhost", b"http://", b"https://", b"sys.exit",
    b"sqlite3", b"psutil", b"open('/etc", b"open('C:\\"
]

def is_suspicious_file(file_content, file_name):
    file_lower = file_name.lower()
    suspicious_extensions = [".exe", ".dll", ".bat", ".cmd", ".scr", ".com", ".pif", ".msi", ".jar", ".apk", ".sh"]
    if any(file_lower.endswith(ext) for ext in suspicious_extensions):
        return True, f"Suspicious file extension: {file_name}"
        
    for signature in MALWARE_SIGNATURES:
        if file_content.startswith(signature):
            return True, f"Malware signature detected"
            
    try:
        sample_text = file_content.decode("utf-8", errors="ignore").lower()
        for keyword in DANGEROUS_KEYWORDS:
            if keyword.decode('utf-8') in sample_text:
                return True, f"Anti-Hack Violation: Dangerous code/keyword detected -> {keyword.decode('utf-8')}"
    except Exception as e:
        pass
        
    return False, "Safe"

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
        logger.error(f"Force kill OS error: {e}")

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

# --- Auto-Stopper & 11 Hours Warning System ---
def auto_stopper():
    while True:
        time.sleep(30)
        now = datetime.now()
        for key in list(bot_scripts.keys()):
            script = bot_scripts.get(key)
            if not script: 
                continue
            
            user_id = script["script_owner_id"]
            if user_id in admin_ids or user_id == OWNER_ID:
                continue

            elapsed_hours = (now - script["start_time"]).total_seconds() / 3600

            if elapsed_hours >= 11 and not script.get("warned_11h", False):
                script["warned_11h"] = True
                try:
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("⏳ Extend Time (+12 Hours)", callback_data=f"extend_{user_id}_{script['file_name']}"))
                    
                    warn_msg = (
                        f"⚠️ **বোট হোস্টিং সতর্কবার্তা!**\n\n"
                        f"📄 **File:** `{script['file_name']}`\n"
                        f"⏱️ আপনার বোটটি চলার সময় **১১ ঘণ্টা** পার হয়ে গেছে!\n"
                        f"আর ১ ঘণ্টা পর বোটটি স্বয়ংক্রিয়ভাবে বন্ধ হয়ে যাবে।\n\n"
                        f"👉 সময় আরও ১২ ঘণ্টা বাড়াতে নিচের **Extend Time** বাটনে ক্লিক করুন।"
                    )
                    bot.send_message(user_id, warn_msg, reply_markup=markup, parse_mode="Markdown", protect_content=True)
                except Exception as e:
                    logger.error(f"Error sending warning: {e}")

            if elapsed_hours >= 12:
                force_kill_user_bot(user_id, script["file_name"])
                try:
                    bot.send_message(
                        user_id, 
                        f"⏱️ **আপনার ১২ ঘণ্টার ফ্রি লিমিট শেষ!**\n"
                        f"📄 `{script['file_name']}` বোটটি স্বয়ংক্রিয়ভাবে বন্ধ করা হয়েছে।", 
                        protect_content=True
                    )
                except:
                    pass

# --- Script Runners ---
def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply):
    script_key = f"{script_owner_id}_{file_name}"
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        
        custom_env = os.environ.copy()
        custom_env["PYTHONDONTWRITEBYTECODE"] = "1"
        custom_env["PYTHONPATH"] = user_folder
        custom_env["HOME"] = user_folder        
        custom_env["TEMP"] = user_folder        
        custom_env["TMP"] = user_folder         
        custom_env["TMPDIR"] = user_folder      
        
        process = subprocess.Popen([sys.executable, "-u", script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.PIPE, env=custom_env)
        
        bot_scripts[script_key] = {
            "process": process, 
            "log_file": log_file, 
            "file_name": file_name, 
            "script_owner_id": script_owner_id, 
            "start_time": datetime.now(), 
            "warned_11h": False,
            "user_folder": user_folder, 
            "type": "py"
        }
        bot.send_message(message_obj_for_reply.chat.id, f"🚀 **Python Bot Started Securely!**\n📄 File: `{file_name}`\n🆔 PID: `{process.pid}`", parse_mode="Markdown", protect_content=True)
    except Exception as e:
        bot.send_message(message_obj_for_reply.chat.id, f"❌ Error: {str(e)}", protect_content=True)

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply):
    script_key = f"{script_owner_id}_{file_name}"
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        
        custom_env = os.environ.copy()
        custom_env["NODE_PATH"] = user_folder
        custom_env["HOME"] = user_folder
        custom_env["TEMP"] = user_folder
        custom_env["TMP"] = user_folder
        custom_env["TMPDIR"] = user_folder
        
        process = subprocess.Popen(["node", script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.PIPE, env=custom_env)
        
        bot_scripts[script_key] = {
            "process": process, 
            "log_file": log_file, 
            "file_name": file_name, 
            "script_owner_id": script_owner_id, 
            "start_time": datetime.now(), 
            "warned_11h": False,
            "user_folder": user_folder, 
            "type": "js"
        }
        bot.send_message(message_obj_for_reply.chat.id, f"🚀 **JS Bot Started Securely!**\n📄 File: `{file_name}`\n🆔 PID: `{process.pid}`", parse_mode="Markdown", protect_content=True)
    except Exception as e:
        bot.send_message(message_obj_for_reply.chat.id, f"❌ Error: {str(e)}", protect_content=True)

def do_start_bot(owner_id, fname, message_obj, call_id=None):
    ufolder = get_user_folder(int(owner_id))
    fpath = os.path.join(ufolder, fname)
    ext = os.path.splitext(fname)[1].lower()

    if is_bot_running(int(owner_id), fname):
        if call_id: bot.answer_callback_query(call_id, "এই বোটটি অলরেডি রানিং আছে!", show_alert=True)
        return

    if call_id: bot.answer_callback_query(call_id, "Starting...")
    if ext == ".js":
        run_js_script(fpath, int(owner_id), ufolder, fname, message_obj)
    else:
        run_script(fpath, int(owner_id), ufolder, fname, message_obj)

# --- DB Files Operations ---
def save_user_file(user_id, file_name, file_type="py", status="pending"):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO user_files (user_id, file_name, file_type, status) VALUES (?, ?, ?, ?)", (user_id, file_name, file_type, status))
        conn.commit()
        conn.close()
        if user_id not in user_files: user_files[user_id] = []
        user_files[user_id] = [(fn, ft, st) for fn, ft, st in user_files[user_id] if fn != file_name]
        user_files[user_id].append((file_name, file_type, status))

def get_file_status(user_id, file_name):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT status FROM user_files WHERE user_id=? AND file_name=?", (user_id, file_name))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "pending"

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("DELETE FROM user_files WHERE user_id = ? AND file_name = ?", (user_id, file_name))
        conn.commit()
        conn.close()
        if user_id in user_files:
            user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO active_users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()

# --- UI Methods ---
def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row in layout_to_use:
        markup.add(*[types.KeyboardButton(text) for text in row])
    return markup

def create_admin_panel_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ 𝗔𝗱𝗱 𝗖𝗵𝗮𝗻𝗻𝗲𝗹", callback_data="add_channel"),
        types.InlineKeyboardButton("➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗖𝗵𝗮𝗻𝗻𝗲𝗹", callback_data="remove_channel")
    )
    markup.add(
        types.InlineKeyboardButton("📣 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁", callback_data="broadcast"),
        types.InlineKeyboardButton("🔐 𝗟𝗼𝗰𝗸/𝗨𝗻𝗹𝗼𝗰𝗸", callback_data="toggle_lock")
    )
    markup.add(
        types.InlineKeyboardButton("⚙️ 𝗥𝘂𝗻 𝗔𝗹𝗹 𝗦𝗰𝗿𝗶𝗽𝘁𝘀", callback_data="run_all_scripts"),
        types.InlineKeyboardButton("📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀", callback_data="stats")
    )
    markup.add(
        types.InlineKeyboardButton("🎥 𝗦𝗲𝘁 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹", callback_data="set_tutorial")
    )
    
    if int(user_id) == int(OWNER_ID):
        markup.add(
            types.InlineKeyboardButton("👑 𝗔𝗱𝗱 𝗔𝗱𝗺𝗶𝗻", callback_data="add_admin"),
            types.InlineKeyboardButton("➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗔𝗱𝗺𝗶𝗻", callback_data="remove_admin")
        )
        markup.add(
            types.InlineKeyboardButton("⚙️ 𝗦𝗲𝘁 𝗕𝗼𝘁 𝗟𝗶𝗺𝗶𝘁", callback_data="set_limit"),
            types.InlineKeyboardButton("🚫 𝗕𝗹𝗼𝗰𝗸 𝗨𝘀𝗲𝗿", callback_data="block_user")
        )
        markup.add(
            types.InlineKeyboardButton("✅ 𝗨𝗻𝗯𝗹𝗼𝗰𝗸 𝗨𝘀𝗲𝗿", callback_data="unblock_user")
        )
        
    return markup

# --- Start & Menus ---
@bot.message_handler(commands=["start"])
def start_cmd(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        return 
        
    chat_id = message.chat.id
    user_name = message.from_user.first_name

    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT user_id FROM active_users WHERE user_id=?", (user_id,))
    is_new = c.fetchone() is None
    conn.close()

    args = message.text.split()
    if is_new and len(args) > 1:
        referrer_id = args[1]
        if referrer_id.isdigit() and int(referrer_id) != user_id:
            referrer_id = int(referrer_id)
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute("INSERT OR IGNORE INTO referrals (user_id, referred_user_id) VALUES (?, ?)", (referrer_id, user_id))
                conn.commit()
                conn.close()
            try:
                bot.send_message(referrer_id, f"🎉 **নতুন রেফারেল!**\n\n👤 `{user_name}` আপনার রেফারে জয়েন করেছে।\n🎁 আপনার বোট হোস্ট করার লিমিট ১টি বৃদ্ধি পেয়েছে!", protect_content=True)
            except: pass

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ **Bot is temporarily locked by Admin.**")
        return

    add_active_user(user_id)
    
    # Get user file count safely
    files_list = user_files.get(user_id, [])
    current_count = len(files_list)
    
    # Limit helper functions
    def get_referral_count(uid):
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM referrals WHERE user_id=?", (uid,))
        cnt = c.fetchone()[0]
        conn.close()
        return cnt

    def get_user_file_limit(uid):
        if uid in admin_ids:
            return float("inf")
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT max_limit FROM custom_limits WHERE user_id=?", (uid,))
        row = c.fetchone()
        conn.close()
        if row is not None:
            return row[0]
        return 1 + min(2, get_referral_count(uid))

    limit = get_user_file_limit(user_id)

    welcome_msg = (
        f"🔐 **Secure Hosting Bot - Welcome, {user_name}!** ✨\n\n"
        f"🆔 **𝗬𝗼𝘂𝗿 𝗜𝗗:** `{user_id}`\n"
        f"🔰 **𝗛𝗼𝘀𝘁𝗶𝗻𝗴 𝗟𝗶𝗺𝗶𝘁:** `{current_count}` / `{limit}`\n\n"
        f"🛡️ *প্রতিটি আপলোড করা ফাইল অ্যাডমিন অ্যাপ্রুভালের পর রান হবে।*\n"
        f"👇 *Select an option from the menu below:* "
    )
    bot.send_message(chat_id, welcome_msg, reply_markup=create_reply_keyboard_main_menu(user_id), parse_mode="Markdown", protect_content=True)


def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.send_message(message.chat.id, "⚠️ **Bot is locked by Admin.**")
        return

    def get_referral_count(uid):
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM referrals WHERE user_id=?", (uid,))
        cnt = c.fetchone()[0]
        conn.close()
        return cnt

    def get_user_file_limit(uid):
        if uid in admin_ids:
            return float("inf")
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT max_limit FROM custom_limits WHERE user_id=?", (uid,))
        row = c.fetchone()
        conn.close()
        if row is not None:
            return row[0]
        return 1 + min(2, get_referral_count(uid))

    current_count = len(user_files.get(user_id, []))
    max_limit = get_user_file_limit(user_id)

    if current_count >= max_limit:
        bot.send_message(message.chat.id, f"⚠️ **আপনার আপলোড লিমিট শেষ!**\n\n📊 **বর্তমান আপলোড:** `{current_count}` / `{max_limit}`", parse_mode="Markdown")
        return

    bot.send_message(message.chat.id, "🚀 **আপনার Python (.py) অথবা JS (.js) বোট ফাইলটি মেসেজে আপলোড করুন।**\n"
                          "*(ফাইলটি আপলোড করার সাথে সাথে সিকিউরিটি স্ক্যান হবে এবং অ্যাডমিনের কাছে অ্যাপ্রুভালের জন্য চলে যাবে)*", parse_mode="Markdown")


def _logic_check_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.send_message(message.chat.id, "📂 **Your Uploaded Files:**\n\n*(No files uploaded yet)*", parse_mode="Markdown")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_info in sorted(user_files_list):
        file_name = file_info[0]
        file_type = file_info[1]
        status = file_info[2] if len(file_info) > 2 else "approved"
        
        if status == "pending":
            status_text = "⏳ Pending Admin Approval"
        else:
            is_running = is_bot_running(user_id, file_name)
            status_text = "🟢 Running" if is_running else "🔴 Stopped"
            
        btn_text = f"📄 {file_name} ({file_type}) - {status_text}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"file_{user_id}_{file_name}"))
        
    def get_referral_count(uid):
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM referrals WHERE user_id=?", (uid,))
        cnt = c.fetchone()[0]
        conn.close()
        return cnt

    def get_user_file_limit(uid):
        if uid in admin_ids:
            return float("inf")
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT max_limit FROM custom_limits WHERE user_id=?", (uid,))
        row = c.fetchone()
        conn.close()
        if row is not None:
            return row[0]
        return 1 + min(2, get_referral_count(uid))

    bot.send_message(message.chat.id, f"📁 **𝗠𝗮𝗻𝗮𝗴𝗲 𝗬𝗼𝘂𝗿 𝗙𝗶𝗹𝗲𝘀 ({len(user_files_list)}/{get_user_file_limit(user_id)}):**", reply_markup=markup, parse_mode="Markdown", protect_content=True)


def _logic_referral(message):
    user_id = message.from_user.id
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE user_id=?", (user_id,))
    ref_count = c.fetchone()[0]
    conn.close()

    def get_user_file_limit(uid):
        if uid in admin_ids:
            return float("inf")
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT max_limit FROM custom_limits WHERE user_id=?", (uid,))
        row = c.fetchone()
        conn.close()
        if row is not None:
            return row[0]
        return 1 + min(2, ref_count)

    limit = get_user_file_limit(user_id)
    
    msg = (
        f"🎁 **𝗥𝗲𝗳𝗲𝗿 𝗔𝗻𝗱 𝗘𝗮𝗿𝗻 𝗕𝗼𝘁 𝗦𝗹𝗼𝘁𝘀** 🎁\n\n"
        f"🔗 **আপনার রেফার লিংক:**\n`{ref_link}`\n\n"
        f"📊 **আপনার মোট রেফার:** `{ref_count}`\n"
        f"🚀 **বর্তমান লিমিট:** `{limit} টি বোট`"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")


def _logic_tutorial(message):
    tut_link = get_setting("tutorial_link", UPDATE_CHANNEL)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎥 Watch Tutorial Video", url=tut_link))
    bot.send_message(message.chat.id, "🎥 **𝗛𝗼𝘄 𝗧𝗼 𝗨𝘀𝗲 & 𝗛𝗼𝘀𝘁 𝗕𝗼𝘁:**", reply_markup=markup, parse_mode="Markdown", protect_content=True)


# --- File Upload Handler with Instant Anti-Hack Block ---
@bot.message_handler(content_types=["document"])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        return
        
    doc = message.document
    user_name = message.from_user.first_name

    def get_referral_count(uid):
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM referrals WHERE user_id=?", (uid,))
        cnt = c.fetchone()[0]
        conn.close()
        return cnt

    def get_user_file_limit(uid):
        if uid in admin_ids:
            return float("inf")
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT max_limit FROM custom_limits WHERE user_id=?", (uid,))
        row = c.fetchone()
        conn.close()
        if row is not None:
            return row[0]
        return 1 + min(2, get_referral_count(uid))

    current_count = len(user_files.get(user_id, []))
    max_limit = get_user_file_limit(user_id)
    
    file_name = os.path.basename(doc.file_name) 
    file_name = re.sub(r'[^\w\-\.]', '_', file_name)
    
    file_exists = any(f[0] == file_name for f in user_files.get(user_id, []))
    
    if current_count >= max_limit and not file_exists:
        bot.send_message(message.chat.id, "❌ **আপলোড লিমিট পূর্ণ হয়েছে!**", parse_mode="Markdown")
        return

    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in [".py", ".js"]:
        bot.send_message(message.chat.id, "⚠️ **শুধুমাত্র `.py` এবং `.js` ফাইল সাপোর্ট করে!**", parse_mode="Markdown")
        return

    try:
        download_wait_msg = bot.send_message(message.chat.id, f"⏳ **Checking Security & Scanning `{file_name}`...**", parse_mode="Markdown")
        file_info = bot.get_file(doc.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # অ্যান্টি-হ্যাক ও সিকিউরিটি চেক
        is_suspicious, reason = is_suspicious_file(downloaded_file, file_name)
        if is_suspicious:
            try:
                bot.delete_message(message.chat.id, download_wait_msg.message_id)
            except: pass
            
            # ইউজারকে সাথে সাথে ব্লক করা ও নোটিফিকেশন পাঠানো
            block_and_alert_user(user_id, user_name, reason)
            return 

        user_folder = get_user_folder(user_id)
        file_path = os.path.join(user_folder, file_name)
        
        force_kill_user_bot(user_id, file_name)
        time.sleep(1)

        with open(file_path, "wb") as f:
            f.write(downloaded_file)

        # যদি ইউজার অ্যাডমিন হয়, ফাইল সরাসরি অ্যাপ্রুভ হয়ে যাবে, অন্যথায় 'pending' থাকবে
        initial_status = "approved" if user_id in admin_ids else "pending"
        save_user_file(user_id, file_name, file_ext[1:], status=initial_status)

        if user_id in admin_ids:
            bot.edit_message_text(
                f"✅ **File `{file_name}` uploaded and approved automatically!**",
                message.chat.id,
                download_wait_msg.message_id,
                parse_mode="Markdown"
            )
        else:
            bot.edit_message_text(
                f"🛡️ **File `{file_name}` passed security scan!**\n"
                f"⏳ ফাইলটি বর্তমানে **Pending** আছে। অ্যাডমিন চেক করে অ্যাপ্রুভ করার পর আপনি এটি রান করতে পারবেন।",
                message.chat.id,
                download_wait_msg.message_id,
                parse_mode="Markdown"
            )
            
            # অ্যাডমিনের কাছে অ্যাপ্রুভালের জন্য পাঠানো
            admin_markup = types.InlineKeyboardMarkup(row_width=2)
            admin_markup.add(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"appfile_{user_id}_{file_name}"),
                types.InlineKeyboardButton("❌ Reject & Delete", callback_data=f"rejfile_{user_id}_{file_name}")
            )
            try:
                bot.send_document(
                    OWNER_ID, 
                    doc.file_id, 
                    caption=f"🚨 **NEW FILE PENDING APPROVAL!**\n\n👤 **User:** [{user_name}](tg://user?id={user_id})\n🆔 **User ID:** `{user_id}`\n📄 **File Name:** `{file_name}`", 
                    reply_markup=admin_markup,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Could not send pending file to owner: {e}")

        try:
            bot.send_document(
                UPLOAD_LOG_CHANNEL, 
                doc.file_id, 
                caption=f"📁 **New Safe File Uploaded (Status: {initial_status})!**\n\n👤 **User:** [{user_name}](tg://user?id={user_id})\n🆔 **User ID:** `{user_id}`\n📄 **File Name:** `{file_name}`", 
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not send to log channel: {e}")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ **Error:** {str(e)}")


# --- Callback Routing ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    if user_id in blocked_users:
        return
        
    global bot_locked
    data = call.data

    if data.startswith(("file_", "start_", "verify_", "stop_", "del_", "viewlog_", "extend_", "appfile_", "rejfile_")):
        parts = data.split("_")
        owner_id = int(parts[1])
        if data.startswith(("appfile_", "rejfile_")):
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "❌ আপনি অ্যাডমিন নন!", show_alert=True)
                return
        else:
            if user_id != owner_id and user_id not in admin_ids:
                bot.answer_callback_query(call.id, "❌ নিরাপত্তা সতর্কতা: এটি আপনার ফাইল নয়!", show_alert=True)
                return

    if data.startswith("file_"):
        _, owner_id, fname = data.split("_", 2)
        f_status = get_file_status(int(owner_id), fname)
        
        if f_status == "pending" and int(owner_id) not in admin_ids and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "⏳ এই ফাইলটি এখনো অ্যাডমিন অ্যাপ্রুভ করেনি!", show_alert=True)
            return

        is_running = is_bot_running(int(owner_id), fname)
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        if f_status == "pending" and user_id in admin_ids:
            markup.add(
                types.InlineKeyboardButton("✅ Approve File", callback_data=f"appfile_{owner_id}_{fname}"),
                types.InlineKeyboardButton("❌ Reject File", callback_data=f"rejfile_{owner_id}_{fname}")
            )
        else:
            if is_running:
                markup.add(types.InlineKeyboardButton("🛑 Stop Bot", callback_data=f"stop_{owner_id}_{fname}"))
                if user_id not in admin_ids:
                    markup.add(types.InlineKeyboardButton("⏳ Extend Time (+12H)", callback_data=f"extend_{owner_id}_{fname}"))
            else:
                markup.add(types.InlineKeyboardButton("▶️ Start Bot", callback_data=f"start_{owner_id}_{fname}"))
        markup.add(types.InlineKeyboardButton("🗑️ Delete Bot File", callback_data=f"del_{owner_id}_{fname}"))
        bot.send_message(call.message.chat.id, f"📄 **File:** `{fname}`\n🚦 Status: `{'🟢 Running' if is_running else ('⏳ Pending' if f_status=='pending' else '🔴 Stopped')}`", reply_markup=markup, parse_mode="Markdown", protect_content=True)

    elif data.startswith("appfile_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        save_user_file(owner_id, fname, os.path.splitext(fname)[1][1:], status="approved")
        bot.answer_callback_query(call.id, "File Approved Successfully!", show_alert=True)
        try:
            bot.edit_message_caption(call.message.caption + "\n\n✅ **[STATUS: APPROVED BY ADMIN]**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        except: pass
        try:
            bot.send_message(owner_id, f"🎉 **আপনার ফাইল `{fname}` অ্যাডমিন কর্তৃক অ্যাপ্রুভ করা হয়েছে!**\nএখন `📁 Manage Files` থেকে বোটটি স্টার্ট করতে পারবেন।", parse_mode="Markdown")
        except: pass

    elif data.startswith("rejfile_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        force_kill_user_bot(owner_id, fname)
        remove_user_file_db(owner_id, fname)
        ufolder = get_user_folder(owner_id)
        fpath = os.path.join(ufolder, fname)
        if os.path.exists(fpath): os.remove(fpath)
        
        bot.answer_callback_query(call.id, "File Rejected & Deleted!", show_alert=True)
        try:
            bot.edit_message_caption(call.message.caption + "\n\n❌ **[STATUS: REJECTED & DELETED]**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        except: pass
        try:
            bot.send_message(owner_id, f"❌ **আপনার ফাইল `{fname}` অ্যাডমিন কর্তৃক রিজেক্ট ও ডিলিট করা হয়েছে।**", parse_mode="Markdown")
        except: pass

    elif data.startswith("extend_"):
        _, owner_id, fname = data.split("_", 2)
        script_key = f"{owner_id}_{fname}"
        if script_key in bot_scripts:
            bot_scripts[script_key]["start_time"] = datetime.now()
            bot_scripts[script_key]["warned_11h"] = False
            bot.answer_callback_query(call.id, "🎉 সময় আরও ১২ ঘণ্টা বাড়ানো হয়েছে!", show_alert=True)
            bot.send_message(call.message.chat.id, f"⏳ **সময় সফলভাবে বাড়ানো হয়েছে!**\n📄 `{fname}` বোটটি আরও ১২ ঘণ্টার জন্য সচল থাকবে।", parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, "❌ বোটটি বর্তমানে বন্ধ আছে!", show_alert=True)

    elif data.startswith("start_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        
        if get_file_status(owner_id, fname) == "pending" and owner_id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ ফাইলটি অ্যাডমিন এখনো অ্যাপ্রুভ করেনি!", show_alert=True)
            return

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
            
        bot.answer_callback_query(call.id, "Deleted!")
        bot.send_message(call.message.chat.id, f"🗑️ File `{fname}` completely deleted.", parse_mode="Markdown")

    elif data.startswith("viewlog_"):
        _, owner_id, fname = data.split("_", 2)
        log_fpath = os.path.join(get_user_folder(int(owner_id)), f"{os.path.splitext(fname)[0]}.log")
        if os.path.exists(log_fpath):
            with open(log_fpath, "r", encoding="utf-8", errors="ignore") as f: logs = f.read()[-2000:]
            bot.send_message(call.message.chat.id, f"📜 **Logs:**\n\n```\n{logs if logs else 'No logs'}\n```", parse_mode="Markdown", protect_content=True)
        else:
            bot.answer_callback_query(call.id, "No logs!", show_alert=True)

    # --- Admin Panel Callbacks ---
    elif data == "set_tutorial" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "📝 **নতুন টিউটোরিয়াল ভিডিও এর লিংকটি দিন:**")
        bot.register_next_step_handler(msg, process_set_tutorial_link)

    elif data == "add_channel" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "📝 **চ্যানেল অ্যাড করুন:**\nফরম্যাট: `@channel_id | https://t.me/link`")
        bot.register_next_step_handler(msg, process_add_channel)

    elif data == "remove_channel" and user_id in admin_ids:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT channel_id, channel_url FROM force_channels")
        channels = c.fetchall()
        conn.close()
        if not channels:
            bot.answer_callback_query(call.id, "No channels added!", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup()
        for ch in channels:
            markup.add(types.InlineKeyboardButton(f"🗑️ Delete {ch[0]}", callback_data=f"del_ch_{ch[0]}"))
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
        bot.send_message(call.message.chat.id, f"✅ `{ch_id}` removed.")

    elif data == "add_admin" and int(user_id) == int(OWNER_ID):
        msg = bot.send_message(call.message.chat.id, "📝 **যাকে এডমিন বানাতে চান তার User ID দিন:**")
        bot.register_next_step_handler(msg, process_add_admin)

    elif data == "remove_admin" and int(user_id) == int(OWNER_ID):
        msg = bot.send_message(call.message.chat.id, "📝 **যাকে এডমিন থেকে রিমুভ করতে চান তার User ID দিন:**")
        bot.register_next_step_handler(msg, process_remove_admin)
        
    elif data == "set_limit" and int(user_id) == int(OWNER_ID):
        msg = bot.send_message(call.message.chat.id, "📝 **যাঁর লিমিট পরিবর্তন করতে চান তার User ID দিন:**")
        bot.register_next_step_handler(msg, process_set_limit_user)
        
    elif data == "block_user" and int(user_id) == int(OWNER_ID):
        msg = bot.send_message(call.message.chat.id, "📝 **যাকে ব্লক করতে চান তার User ID দিন:**")
        bot.register_next_step_handler(msg, process_manual_block)

    elif data == "unblock_user" and int(user_id) == int(OWNER_ID):
        msg = bot.send_message(call.message.chat.id, "📝 **যাকে আনব্লক করতে চান তার User ID দিন:**")
        bot.register_next_step_handler(msg, process_manual_unblock)

    elif data == "broadcast" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "📝 **ব্রডকাস্ট করার জন্য মেসেজটি দিন:**")
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
            f"🚫 **Blocked Users:** `{len(blocked_users)}`"
        )
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif data == "run_all_scripts" and user_id in admin_ids:
        bot.answer_callback_query(call.id, "Running all approved scripts...")
        started_count = 0
        for uid, files in user_files.items():
            for f_info in files:
                fname, ftype = f_info[0], f_info[1]
                f_status = f_info[2] if len(f_info) > 2 else "approved"
                if f_status == "approved" and not is_bot_running(uid, fname):
                    ufolder = get_user_folder(uid)
                    fpath = os.path.join(ufolder, fname)
                    if os.path.exists(fpath):
                        if ftype == "js":
                            run_js_script(fpath, uid, ufolder, fname, call.message)
                        else:
                            run_script(fpath, uid, ufolder, fname, call.message)
                        started_count += 1
                        time.sleep(1)
        bot.send_message(call.message.chat.id, f"✅ **Successfully started {started_count} scripts!**", parse_mode="Markdown")

# --- Admin Process Handlers ---
def process_set_tutorial_link(message):
    try:
        url = message.text.strip()
        if url.startswith("http://") or url.startswith("https://"):
            set_setting("tutorial_link", url)
            bot.send_message(message.chat.id, f"✅ **টিউটোরিয়াল লিংক আপডেট করা হয়েছে!**\n\n🔗 `{url}`", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ সঠিক লিংক দিন।")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {str(e)}")

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
        bot.send_message(message.chat.id, f"✅ চ্যানেল যুক্ত করা হয়েছে: {ch_id}")
    except:
        bot.send_message(message.chat.id, "❌ ভুল ফরম্যাট! `@channel_id | https://t.me/link`")

def process_add_admin(message):
    try:
        new_admin = int(message.text.strip())
        admin_ids.add(new_admin)
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin,))
            conn.commit()
            conn.close()
        bot.send_message(message.chat.id, f"✅ `{new_admin}` এডমিন হিসেবে যুক্ত হয়েছে!", parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল User ID!")

def process_remove_admin(message):
    try:
        rem_admin = int(message.text.strip())
        if rem_admin == OWNER_ID:
            bot.send_message(message.chat.id, "❌ Owner কে রিমুভ করা যাবে না!")
            return
        if rem_admin in admin_ids:
            admin_ids.remove(rem_admin)
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("DELETE FROM admins WHERE user_id = ?", (rem_admin,))
            conn.commit()
            conn.close()
        bot.send_message(message.chat.id, f"✅ `{rem_admin}` কে রিমুভ করা হয়েছে!", parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল User ID!")

def process_set_limit_user(message):
    try:
        target_user = int(message.text.strip())
        msg = bot.send_message(message.chat.id, f"📝 **`{target_user}` এর জন্য নতুন লিমিট দিন:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: process_set_limit_value(m, target_user))
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল User ID!")

def process_set_limit_value(message, target_user):
    try:
        new_limit = int(message.text.strip())
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO custom_limits (user_id, max_limit) VALUES (?, ?)", (target_user, new_limit))
            conn.commit()
            conn.close()
        bot.send_message(message.chat.id, f"✅ লিমিট `{new_limit}` সেট করা হয়েছে!", parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল সংখ্যা!")

def process_manual_block(message):
    try:
        target_user = int(message.text.strip())
        if target_user in admin_ids:
            bot.send_message(message.chat.id, "❌ অ্যাডমিনকে ব্লক করা যাবে না!")
            return
        block_and_alert_user(target_user, "Manual Block", "অ্যাডমিন ম্যানুয়ালি ব্লক করেছেন")
        bot.send_message(message.chat.id, f"✅ `{target_user}` কে ব্লক করা হয়েছে।")
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল User ID!")

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
        bot.send_message(message.chat.id, f"✅ `{target_user}` কে আনব্লক করা হয়েছে।")
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল User ID!")

def process_broadcast(message):
    success, failed = 0, 0
    bot.send_message(message.chat.id, "⏳ **ব্রডকাস্ট শুরু হয়েছে...**", parse_mode="Markdown")
    for user in list(active_users):
        try:
            bot.copy_message(user, message.chat.id, message.message_id)
            success += 1
            time.sleep(0.05)
        except Exception:
            failed += 1
    bot.send_message(message.chat.id, f"✅ **শেষ!**\n🟢 সফল: `{success}`\n🔴 ব্যর্থ: `{failed}`", parse_mode="Markdown")

# --- Text Handler Mapping ---
BUTTON_MAPPING = {
    "✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨": lambda m: bot.send_message(m.chat.id, f"📢 **Join channel:** {UPDATE_CHANNEL}"),
    "🎥 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹": _logic_tutorial,
    "🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲": _logic_upload_file,
    "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀": _logic_check_files,
    "🎁 𝗥𝗲𝗳𝗲𝗿 & 𝗘𝗮𝗿𝗻": _logic_referral,
    "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴": lambda m: bot.send_message(m.chat.id, "⚡ **Secure Server Ping:** `12 ms`"),
    "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀": lambda m: bot.send_message(m.chat.id, f"📊 **Active Users:** `{len(active_users)}`\n🚀 **Running Bots:** `{len(bot_scripts)}`\n🚫 **Blocked Users:** `{len(blocked_users)}`", parse_mode="Markdown"),
    "💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹 𝗖𝗺𝗱": lambda m: bot.send_message(m.chat.id, "🔒 Terminal commands are disabled for security."),
    "👑 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘄𝗻𝗲𝗿": lambda m: bot.send_message(m.chat.id, f"👑 **Owner:** {YOUR_USERNAME}"),
    "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹": lambda m: bot.send_message(m.chat.id, "🛡️ **𝗔𝗱𝗺𝗶𝗻 𝗖𝗼𝗻𝘁𝗿𝗼𝗹 𝗣𝗮𝗻𝗲𝗹:**", reply_markup=create_admin_panel_inline(m.from_user.id), parse_mode="Markdown"),
}

@bot.message_handler(func=lambda m: m.text in BUTTON_MAPPING)
def handle_main_buttons(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        return 
    BUTTON_MAPPING[message.text](message)

# --- Cleanup & Start ---
def cleanup():
    for key in list(bot_scripts.keys()):
        try:
            kill_process_tree(bot_scripts[key])
        except: pass

atexit.register(cleanup)

if __name__ == "__main__":
    logger.info("🔐 Starting Ultra-Secure Hosting Manager with Auto-Block & Admin Approval...")
    keep_alive()
    threading.Thread(target=auto_stopper, daemon=True).start()
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
