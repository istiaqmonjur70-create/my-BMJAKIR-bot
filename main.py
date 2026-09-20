# -*- coding: utf-8 -*-
import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import signal
import threading
import re
import sys
import atexit
import requests
import hashlib
import mimetypes
import struct
from threading import Thread

# --- Flask Keep Alive ---
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return "I'am mukesh File Host"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive server started.")
# --- End Flask Keep Alive ---

# --- Configuration ---
TOKEN = '8991450999:AAHVKEFc6SJVm3WY1__jnTXgkHn9K6MaYmA'
OWNER_ID = 8814363793
ADMIN_ID = 8814363793
YOUR_USERNAME = '@DevCloudX'
UPDATE_CHANNEL = 'https://t.me/JAKIRLABS'
# Folder setup
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

# SQLite stability: one process-wide lock + WAL + busy timeout.
DB_LOCK = threading.RLock()

def db_connect():
    conn = sqlite3.connect(DATABASE_PATH, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

# File upload limits
SUBSCRIBED_USER_LIMIT = 1
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# Free user limit settings
FREE_USER_LIMIT_SETTINGS = {
    "limit": 1,
    "time": 12,
    "host_time": 12
}

# Create necessary directories
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# Initialize bot
bot = telebot.TeleBot(TOKEN)

# --- Data structures ---
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False

# --- OTP GURU Bot Data ---
all_users = []
all_files = []
admin_list = [8814363793, OWNER_ID]
user_limits = {}
user_upload_times = {}
file_stop_status = {}
# ======================================================

# --- Malware Detection Configuration ---
MALWARE_SIGNATURES = [
    b'MZ',
    b'\x7fELF',
    b'\xfe\xed\xfa',
    b'\xce\xfa\xed\xfe',
    b'PK',
    b'Rar!',
]

ENCRYPTED_FILE_INDICATORS = [
    b'openssl',
    b'encrypted',
    b'cipher',
    b'AES',
    b'DES',
    b'RSA',
    b'GPG',
    b'PGP',
]

SUSPICIOUS_KEYWORDS = [
    b'ransomware',
    b'trojan',
    b'virus',
    b'malware',
    b'backdoor',
    b'exploit',
    b'payload',
    b'botnet',
    b'keylogger',
    b'rootkit',
]

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Command Button Layouts (User - Bengali) ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["💎 আপডেট চ্যানেল"],
    ["💎 ফাইল আপলোড করুন", "💎 ফাইল দেখুন"],
    ["💎 ডিপোজিট", "💎 আমার প্রোফাইল"],
    ["💎 প্রিমিয়াম প্লান 🌟"],
    ["💎 সাপোর্ট"]
]

# --- Command Button Layouts (Admin - English Capital) ---
ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["UPDATES CHANNEL"],
    ["UPLOAD FILE", "CHECK FILES"],
    ["BOT SPEED", "STATISTICS"],
    ["SUBSCRIPTIONS", "LOCK BOT"],
    ["RUNNING ALL CODE", "Rakib Admin Panel"],
    ["CONTACT OWNER"]
]

# --- OTP GURU Bot Command Layouts (REMOVED BAN/UNBAN, ALL USERS, ALL FILES, STOP & DELETE) ---
OTP_USER_BUTTONS = [
    ["আমার প্রোফাইল", "ডিপোজিট"],
    ["প্রিমিয়াম প্লান 🌟"],
    ["BACK TO MAIN"]
]

OTP_ADMIN_BUTTONS = [
    ["ADMIN LIST"],
    ["SET LIMIT", "FREE BOT LIMIT"],
    ["Set Premium Plan for All User 🌟", "DEPOSITE SYSTEM"],
    ["FORCE JOIN", "SET SUPPORT LINK"],
    ["BACK TO ADMIN PANEL"]
]

# --- OTP Admin List Sub-menu Buttons ---
OTP_ADMIN_LIST_BUTTONS = [
    ["ADD ADMIN"],
    ["REMOVE ADMIN"],
    ["TRANSFER OWNERSHIP"],
    ["SHOW ALL ADMINS"],
    ["BACK TO ADMIN PANEL"]
]

# --- OTP Deposite Sub-menu Buttons ---
OTP_DEPOSITE_BUTTONS = [
    ["SHOW ALL DEPOSITE REQUEST"],
    ["SET DEPOSIT NUMBER AND ID"],
    ["DELETE PAYMENT METHOD"],
    ["BACK TO ADMIN PANEL"]
]

# --- Premium Plan Sub-menu Buttons ---
PREMIUM_PLAN_ADMIN_BUTTONS = [
    ["Add Your Premium Plan"],
    ["Remove Plan"],
    ["Reset All Plans"],
    ["BACK TO ADMIN PANEL"]
]

PREMIUM_PLAN_USER_BUTTONS = [
    ["Buy Plan"],
    ["Deposit"],
    ["BACK TO MAIN"]
]

# --- DEPOSIT SYSTEM BUTTONS ---
DEPOSIT_USER_BUTTONS = [
    ["আমার ডিপোজিট রিকোয়েস্ট"],
    ["BACK TO MAIN"]
]

DEPOSIT_ADMIN_BUTTONS = [
    ["SHOW ALL DEPOSITE REQUEST"],
    ["SET DEPOSIT NUMBER AND ID"],
    ["DELETE PAYMENT METHOD"],
    ["BACK TO ADMIN PANEL"]
]

# --- Database Setup ---
def init_db():
    """Initialize the database with required tables"""
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    
    try:
        os.makedirs(IROTECH_DIR, exist_ok=True)
        logger.info(f"✅ Directory created: {IROTECH_DIR}")
    except Exception as e:
        logger.error(f"❌ Failed to create directory: {e}")
    
    try:
        conn = db_connect()
        c = conn.cursor()
        
        c.execute('PRAGMA foreign_keys = ON')
        c.execute('PRAGMA busy_timeout=30000')
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA synchronous=NORMAL')
        
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT, upload_time TEXT, is_stopped INTEGER DEFAULT 0,
                      PRIMARY KEY (user_id, file_name))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS free_user_settings
                     (id INTEGER PRIMARY KEY, limit_value INTEGER, time_value INTEGER, host_time INTEGER)''')
        
        c.execute('INSERT OR IGNORE INTO free_user_settings (id, limit_value, time_value, host_time) VALUES (1, ?, ?, ?)', 
                  (FREE_USER_LIMIT_SETTINGS["limit"], FREE_USER_LIMIT_SETTINGS["time"], FREE_USER_LIMIT_SETTINGS["host_time"]))
        
        c.execute('''CREATE TABLE IF NOT EXISTS premium_plans (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     file_limit INTEGER,
                     days INTEGER,
                     price INTEGER
                     )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS user_premium
                     (user_id INTEGER PRIMARY KEY, plan_id INTEGER, expiry TEXT, file_limit INTEGER)''')
        
        # ===== DEPOSIT TABLES =====
        c.execute('''CREATE TABLE IF NOT EXISTS payment_methods (
                     name TEXT PRIMARY KEY,
                     number_or_address TEXT,
                     min_deposit REAL DEFAULT 10.0,
                     icon_key TEXT DEFAULT 'card'
                     )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS deposits_new (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER,
                     amount REAL,
                     method TEXT,
                     trx_id TEXT UNIQUE,
                     status TEXT DEFAULT 'pending',
                     approved_by INTEGER,
                     approved_at TIMESTAMP,
                     screenshot_file_id TEXT,
                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                     )''')
        try:
            c.execute('ALTER TABLE deposits_new ADD COLUMN screenshot_file_id TEXT')
        except sqlite3.OperationalError:
            pass
        
        c.execute('''CREATE TABLE IF NOT EXISTS user_balances
                     (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS settings
                     (key TEXT PRIMARY KEY, value TEXT)''')
        
        # Insert default payment methods
        default_methods = [
            ('bKash', '01792804304', 10.0, 'bkash'),
            ('Nagad', '01792804304', 10.0, 'nagad'),
            ('Binance', '986591895', 10.0, 'binance')
        ]
        for m_name, m_num, m_min, m_icon in default_methods:
            c.execute("INSERT OR REPLACE INTO payment_methods (name, number_or_address, min_deposit, icon_key) VALUES (?, ?, ?, ?)",
                      (m_name, m_num, m_min, m_icon))
        # Remove methods you no longer want to offer.
        c.execute("DELETE FROM payment_methods WHERE LOWER(name) IN ('upay', 'rocket')")
        
        # Insert default settings
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_commission', '10')")
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('usdt_rate', '120')")
        # Preserve admin-configured free user settings across restarts.
        
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Database initialized successfully.")
        logger.info(f"📁 Database path: {DATABASE_PATH}")
        
        conn = db_connect()
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = c.fetchall()
        logger.info(f"📊 Tables: {[t[0] for t in tables]}")
        conn.close()
        
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)
        try:
            if os.path.exists(DATABASE_PATH):
                os.remove(DATABASE_PATH)
                logger.info("🔄 Removed corrupted database, retrying...")
                time.sleep(1)
                init_db()
        except Exception as retry_e:
            logger.error(f"❌ Retry failed: {retry_e}")

def load_data():
    """Load data from database into memory"""
    global plan_id_counter
    logger.info("Loading data from database...")
    try:
        conn = db_connect()
        c = conn.cursor()

        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"⚠️ Invalid expiry date format for user {user_id}: {expiry}. Skipping.")

        c.execute('SELECT user_id, file_name, file_type, upload_time, is_stopped FROM user_files')
        for user_id, file_name, file_type, upload_time, is_stopped in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))
            if is_stopped:
                if user_id not in file_stop_status:
                    file_stop_status[user_id] = []
                file_stop_status[user_id].append(file_name)

        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())

        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())

        c.execute('SELECT limit_value, time_value, host_time FROM free_user_settings WHERE id = 1')
        row = c.fetchone()
        if row:
            FREE_USER_LIMIT_SETTINGS["limit"] = row[0]
            FREE_USER_LIMIT_SETTINGS["time"] = row[1]
            FREE_USER_LIMIT_SETTINGS["host_time"] = row[2]

        c.execute('SELECT id, file_limit, days, price FROM premium_plans')
        for row in c.fetchall():
            premium_plans.append({
                "id": row[0],
                "file_limit": row[1],
                "days": row[2],
                "price": row[3]
            })
            if row[0] >= plan_id_counter:
                plan_id_counter = row[0] + 1

        c.execute('SELECT user_id, plan_id, expiry, file_limit FROM user_premium')
        for row in c.fetchall():
            try:
                user_premium_plans[row[0]] = {
                    "plan_id": row[1],
                    "expiry": datetime.fromisoformat(row[2]),
                    "file_limit": row[3]
                }
            except ValueError:
                logger.warning(f"⚠️ Invalid expiry date for user {row[0]}")

        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users, {len(user_subscriptions)} subscriptions, {len(admin_ids)} admins.")
        logger.info(f"Free user limit: {FREE_USER_LIMIT_SETTINGS['limit']} files per {FREE_USER_LIMIT_SETTINGS['time']} hours")
        logger.info(f"Free user host time: {FREE_USER_LIMIT_SETTINGS['host_time']} hours")
        logger.info(f"Premium plans: {len(premium_plans)}")
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)

# --- Premium Plan Variables ---
premium_plans = []
user_premium_plans = {}
plan_id_counter = 1

# Initialize DB and Load Data at startup
init_db()
load_data()
# --- End Database Setup ---

# --- OTP GURU Bot Database Functions ---
def add_otp_user(user_id, name, username):
    """Add user to OTP GURU bot"""
    user_exists = False
    for u in all_users:
        if u["id"] == user_id:
            user_exists = True
            break
    
    if not user_exists:
        new_user = {
            "id": user_id,
            "name": name,
            "username": username or "@unknown",
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "balance": 0,
            "files_count": 0
        }
        all_users.append(new_user)
        logger.info(f"✅ New OTP user added: {name} ({user_id})")
        return True
    return False

def get_otp_user_data(user_id):
    """Get user data from OTP GURU bot"""
    for user in all_users:
        if user["id"] == user_id:
            return user
    return None

def update_otp_user_balance(user_id, amount):
    """Update user balance"""
    for user in all_users:
        if user["id"] == user_id:
            user["balance"] = user.get("balance", 0) + amount
            return True
    return False

# ==================== DEPOSIT SYSTEM FUNCTIONS ====================

def get_setting(key):
    """Get setting from database"""
    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = ?", (key,))
        res = c.fetchone()
        conn.close()
        return res[0] if res else ""
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return ""

def set_setting(key, value):
    """Set setting in database"""
    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error setting {key}: {e}")
        return False

def get_user_balance_db(user_id):
    """Get user balance from database"""
    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute("SELECT balance FROM user_balances WHERE user_id = ?", (user_id,))
        res = c.fetchone()
        conn.close()
        return res[0] if res else 0.0
    except Exception as e:
        logger.error(f"Error getting balance for {user_id}: {e}")
        return 0.0

def update_user_balance_db(user_id, amount):
    """Update user balance"""
    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO user_balances (user_id, balance) VALUES (?, COALESCE((SELECT balance FROM user_balances WHERE user_id = ?), 0) + ?)",
                  (user_id, user_id, amount))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating balance for {user_id}: {e}")
        return False

def get_payment_methods():
    """Get all payment methods"""
    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute("SELECT name, number_or_address, min_deposit, icon_key FROM payment_methods")
        methods = c.fetchall()
        conn.close()
        return [{"name": m[0], "number": m[1], "min_deposit": m[2], "icon": m[3]} for m in methods]
    except Exception as e:
        logger.error(f"Error getting payment methods: {e}")
        return []

def get_payment_method(name):
    """Get payment method by name"""
    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute("SELECT name, number_or_address, min_deposit FROM payment_methods WHERE name = ?", (name,))
        res = c.fetchone()
        conn.close()
        if res:
            return {"name": res[0], "number": res[1], "min_deposit": res[2]}
        return None
    except Exception as e:
        logger.error(f"Error getting payment method {name}: {e}")
        return None

def create_deposit_request(user_id, amount, method, trx_id, screenshot_file_id):
    """Create a deposit request with mandatory payment screenshot."""
    with DB_LOCK:
        conn = db_connect()
        try:
            c = conn.cursor()
            c.execute("SELECT id FROM deposits_new WHERE trx_id = ? AND status IN ('pending', 'approved')", (trx_id,))
            if c.fetchone():
                return None, "Duplicate transaction ID"
            c.execute(
                "INSERT INTO deposits_new (user_id, amount, method, trx_id, status, screenshot_file_id) VALUES (?, ?, ?, ?, 'pending', ?)",
                (user_id, amount, method, trx_id, screenshot_file_id)
            )
            deposit_id = c.lastrowid
            conn.commit()
            return deposit_id, None
        except sqlite3.IntegrityError:
            conn.rollback()
            return None, "Duplicate transaction ID"
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error creating deposit: {e}", exc_info=True)
            return None, str(e)
        finally:
            conn.close()

def get_pending_deposits():
    with DB_LOCK:
        conn = db_connect()
        try:
            c = conn.cursor()
            c.execute("SELECT id, user_id, amount, method, trx_id, created_at, screenshot_file_id FROM deposits_new WHERE status = 'pending' ORDER BY created_at DESC")
            return c.fetchall()
        except Exception as e:
            logger.error(f"Error getting pending deposits: {e}")
            return []
        finally:
            conn.close()

def approve_deposit(deposit_id, admin_id):
    """Atomically approve a pending deposit and credit balance once."""
    with DB_LOCK:
        conn = db_connect()
        try:
            c = conn.cursor()
            c.execute("SELECT user_id, amount, method FROM deposits_new WHERE id = ? AND status = 'pending'", (deposit_id,))
            dep = c.fetchone()
            if not dep:
                return False, "Deposit not found or already processed"
            user_id, amount, method = dep
            credited_amount = float(amount)
            if str(method).lower() == 'binance':
                try:
                    rate = float(get_setting('usdt_rate') or '120')
                except (TypeError, ValueError):
                    rate = 120.0
                credited_amount = float(amount) * rate
            c.execute(
                "UPDATE deposits_new SET status='approved', approved_by=?, approved_at=? WHERE id=? AND status='pending'",
                (admin_id, datetime.now(), deposit_id)
            )
            if c.rowcount != 1:
                conn.rollback()
                return False, "Deposit was already processed"
            c.execute(
                "INSERT OR REPLACE INTO user_balances (user_id, balance) VALUES (?, COALESCE((SELECT balance FROM user_balances WHERE user_id=?),0)+?)",
                (user_id, user_id, credited_amount)
            )
            conn.commit()
            return True, credited_amount
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error approving deposit {deposit_id}: {e}", exc_info=True)
            return False, str(e)
        finally:
            conn.close()

def reject_deposit(deposit_id, admin_id):
    with DB_LOCK:
        conn = db_connect()
        try:
            c = conn.cursor()
            c.execute("UPDATE deposits_new SET status='rejected', approved_by=?, approved_at=? WHERE id=? AND status='pending'", (admin_id, datetime.now(), deposit_id))
            changed = c.rowcount == 1
            conn.commit()
            return changed
        except Exception as e:
            conn.rollback()
            logger.error(f"Error rejecting deposit {deposit_id}: {e}")
            return False
        finally:
            conn.close()

def get_user_deposits(user_id):
    with DB_LOCK:
        conn = db_connect()
        try:
            c = conn.cursor()
            c.execute("SELECT id, amount, method, trx_id, status, created_at, screenshot_file_id FROM deposits_new WHERE user_id=? ORDER BY created_at DESC", (user_id,))
            return c.fetchall()
        except Exception as e:
            logger.error(f"Error getting user deposits: {e}")
            return []
        finally:
            conn.close()

def save_payment_method(name, number, min_deposit):
    with DB_LOCK:
        conn = db_connect()
        try:
            c = conn.cursor()
            name_lower = name.lower()
            icon_key = 'card'
            if 'bkash' in name_lower: icon_key = 'bkash'
            elif 'nagad' in name_lower: icon_key = 'nagad'
            elif 'binance' in name_lower: icon_key = 'binance'
            c.execute("INSERT OR REPLACE INTO payment_methods (name, number_or_address, min_deposit, icon_key) VALUES (?, ?, ?, ?)", (name, number, min_deposit, icon_key))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving payment method: {e}")
            return False
        finally:
            conn.close()

def delete_payment_method(name):
    with DB_LOCK:
        conn = db_connect()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM payment_methods WHERE name = ?", (name,))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Error deleting payment method: {e}")
            return False
        finally:
            conn.close()

# ==================== END DEPOSIT FUNCTIONS ====================

# --- Premium Plan Database Functions ---
def save_premium_plan(file_limit, days, price):
    """Save premium plan to database"""
    global plan_id_counter
    try:
        conn = db_connect()
        c = conn.cursor()
        
        c.execute('INSERT INTO premium_plans (file_limit, days, price) VALUES (?, ?, ?)',
                  (file_limit, days, price))
        conn.commit()
        
        plan_id = c.lastrowid
        
        plan = {
            "id": plan_id,
            "file_limit": file_limit,
            "days": days,
            "price": price
        }
        premium_plans.append(plan)
        
        if plan_id >= plan_id_counter:
            plan_id_counter = plan_id + 1
            
        conn.close()
        logger.info(f"✅ Premium plan added: {file_limit} files, {days} days, {price} price (ID: {plan_id})")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving premium plan: {e}")
        return False

def remove_premium_plan(plan_id):
    """Remove premium plan from database"""
    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute('DELETE FROM premium_plans WHERE id = ?', (plan_id,))
        conn.commit()
        conn.close()
        global premium_plans
        premium_plans = [p for p in premium_plans if p["id"] != plan_id]
        logger.info(f"✅ Premium plan removed: {plan_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Error removing premium plan: {e}")
        return False

def reset_all_plans():
    """Reset all premium plans"""
    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute('DELETE FROM premium_plans')
        c.execute("DELETE FROM sqlite_sequence WHERE name='premium_plans'")
        conn.commit()
        conn.close()
        
        global premium_plans, plan_id_counter
        premium_plans = []
        plan_id_counter = 1
        
        logger.info(f"✅ All plans reset")
        return True
    except Exception as e:
        logger.error(f"❌ Error resetting plans: {e}")
        return False

def save_user_premium_plan(user_id, plan_id, expiry, file_limit):
    """Save user premium plan to database"""
    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO user_premium (user_id, plan_id, expiry, file_limit) VALUES (?, ?, ?, ?)',
                  (user_id, plan_id, expiry.isoformat(), file_limit))
        conn.commit()
        conn.close()
        user_premium_plans[user_id] = {
            "plan_id": plan_id,
            "expiry": expiry,
            "file_limit": file_limit
        }
        logger.info(f"✅ User {user_id} premium plan activated")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving user premium plan: {e}")
        return False

def get_user_premium_plan(user_id):
    """Get user premium plan"""
    return user_premium_plans.get(user_id)

def get_user_file_limit(user_id):
    """Get the file upload limit for a user"""
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    
    premium = get_user_premium_plan(user_id)
    if premium and premium["expiry"] > datetime.now():
        return premium["file_limit"]
    
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    
    limit = FREE_USER_LIMIT_SETTINGS["limit"]
    return float("inf") if limit == 0 else limit

def get_user_host_time(user_id):
    """Get the host time for a user's files"""
    if user_id == OWNER_ID: return float('inf')
    if user_id in admin_ids: return float('inf')
    
    premium = get_user_premium_plan(user_id)
    if premium and premium["expiry"] > datetime.now():
        return float('inf')
    
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return 168
    
    host_time = FREE_USER_LIMIT_SETTINGS["host_time"]
    return float("inf") if host_time == 0 else host_time

def get_user_upload_count_in_time(user_id):
    """Get number of uploads in current time window"""
    upload_times = user_upload_times.get(user_id, [])
    time_limit_hours = FREE_USER_LIMIT_SETTINGS["time"]
    
    premium = get_user_premium_plan(user_id)
    if premium and premium["expiry"] > datetime.now():
        return 0
    
    if time_limit_hours == 0:
        return 0
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(hours=time_limit_hours)
    return len([t for t in upload_times if t > cutoff_time])

def stop_user_file(user_id, file_name):
    """Stop a user's file"""
    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute('UPDATE user_files SET is_stopped = 1 WHERE user_id = ? AND file_name = ?', (user_id, file_name))
        conn.commit()
        conn.close()
        
        if user_id not in file_stop_status:
            file_stop_status[user_id] = []
        if file_name not in file_stop_status[user_id]:
            file_stop_status[user_id].append(file_name)
        
        script_key = f"{user_id}_{file_name}"
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]
        
        logger.info(f"🛑 File stopped: {file_name} for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Error stopping file: {e}")
        return False

# --- Auto Checker Functions ---
def check_and_stop_expired_files():
    """Check and stop files that have expired"""
    logger.info("🔍 Checking for expired files...")
    
    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute('SELECT user_id, file_name, upload_time FROM user_files WHERE is_stopped = 0')
        files = c.fetchall()
        conn.close()
        
        current_time = datetime.now()
        stopped_count = 0
        
        for user_id, file_name, upload_time_str in files:
            try:
                upload_time = datetime.fromisoformat(upload_time_str)
                host_time_hours = get_user_host_time(user_id)
                
                if host_time_hours != float('inf'):
                    expiry_time = upload_time + timedelta(hours=host_time_hours)
                    if current_time > expiry_time:
                        if stop_user_file(user_id, file_name):
                            stopped_count += 1
                            try:
                                bot.send_message(
                                    user_id,
                                    f"⏰ *আপনার ফাইল হোস্ট করার সময় শেষ হয়েছে!*\n"
                                    f"━━━━━━━━━━━━━━━━━\n\n"
                                    f"📄 ফাইল: `{file_name}`\n"
                                    f"⏰ সময় শেষ: {host_time_hours} ঘন্টা\n\n"
                                    f"💡 *আবার ফাইল আপলোড করতে পারেন*",
                                    parse_mode='Markdown'
                                )
                            except:
                                pass
                            
                            for admin_id in admin_list:
                                try:
                                    bot.send_message(
                                        admin_id,
                                        f"⏰ *একটি ফাইল অটো স্টপ হয়েছে!*\n"
                                        f"━━━━━━━━━━━━━━━━━\n\n"
                                        f"👤 ইউজার: `{user_id}`\n"
                                        f"📄 ফাইল: `{file_name}`\n"
                                        f"⏰ হোস্ট সময় শেষ: {host_time_hours} ঘন্টা",
                                        parse_mode='Markdown'
                                    )
                                except:
                                    pass
            except Exception as e:
                logger.error(f"Error processing file {file_name} for user {user_id}: {e}")
        
        if stopped_count > 0:
            logger.info(f"✅ Stopped {stopped_count} expired files")
            
    except Exception as e:
        logger.error(f"❌ Error checking expired files: {e}")

def check_and_stop_subscription_expired():
    """Check and stop files for users with expired subscriptions"""
    logger.info("🔍 Checking for expired subscriptions...")
    
    try:
        current_time = datetime.now()
        stopped_count = 0
        
        for user_id, premium_data in list(user_premium_plans.items()):
            if premium_data["expiry"] <= current_time:
                conn = db_connect()
                c = conn.cursor()
                c.execute('SELECT file_name FROM user_files WHERE user_id = ? AND is_stopped = 0', (user_id,))
                files = c.fetchall()
                conn.close()
                
                for file_name in files:
                    if stop_user_file(user_id, file_name[0]):
                        stopped_count += 1
                        try:
                            bot.send_message(
                                user_id,
                                f"⏰ *আপনার প্রিমিয়াম প্লান শেষ হয়েছে!*\n"
                                f"━━━━━━━━━━━━━━━━━\n\n"
                                f"📄 ফাইল: `{file_name[0]}`\n"
                                f"💡 *আবার প্রিমিয়াম কিনতে পারেন*",
                                parse_mode='Markdown'
                            )
                        except:
                            pass
                
                del user_premium_plans[user_id]
                try:
                    conn = db_connect()
                    c = conn.cursor()
                    c.execute('DELETE FROM user_premium WHERE user_id = ?', (user_id,))
                    conn.commit()
                    conn.close()
                except:
                    pass
                
                for admin_id in admin_list:
                    try:
                        bot.send_message(
                            admin_id,
                            f"⏰ *একটি প্রিমিয়াম প্লান শেষ হয়েছে!*\n"
                            f"━━━━━━━━━━━━━━━━━\n\n"
                            f"👤 ইউজার: `{user_id}`\n"
                            f"📄 ফাইল স্টপ: {len(files)} টি",
                            parse_mode='Markdown'
                        )
                    except:
                        pass
        
        for user_id, sub_data in list(user_subscriptions.items()):
            if sub_data["expiry"] <= current_time:
                conn = db_connect()
                c = conn.cursor()
                c.execute('SELECT file_name FROM user_files WHERE user_id = ? AND is_stopped = 0', (user_id,))
                files = c.fetchall()
                conn.close()
                
                for file_name in files:
                    if stop_user_file(user_id, file_name[0]):
                        stopped_count += 1
                
                del user_subscriptions[user_id]
                try:
                    conn = db_connect()
                    c = conn.cursor()
                    c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
                    conn.commit()
                    conn.close()
                except:
                    pass
        
        if stopped_count > 0:
            logger.info(f"✅ Stopped {stopped_count} files due to expired subscriptions")
            
    except Exception as e:
        logger.error(f"❌ Error checking expired subscriptions: {e}")

def auto_checker():
    """Auto checker thread - runs every minute"""
    while True:
        try:
            check_and_stop_expired_files()
            check_and_stop_subscription_expired()
            time.sleep(60)
        except Exception as e:
            logger.error(f"❌ Auto checker error: {e}")
            time.sleep(60)

# Start auto checker thread
auto_checker_thread = Thread(target=auto_checker, daemon=True)
auto_checker_thread.start()
logger.info("🔄 Auto checker started!")

# --- Helper Functions ---
def get_user_folder(user_id):
    """Get or create user's folder for storing files"""
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_count(user_id):
    """Get the number of files uploaded by a user"""
    return len(user_files.get(user_id, []))

def is_bot_running(script_owner_id, file_name):
    """Check if a bot script is currently running"""
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not is_running:
                logger.warning(f"Process {script_info['process'].pid} for {script_key} found in memory but not running/zombie. Cleaning up.")
                if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                    try:
                        script_info['log_file'].close()
                    except Exception as log_e:
                        logger.error(f"Error closing log file during zombie cleanup {script_key}: {log_e}")
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            logger.warning(f"Process for {script_key} not found (NoSuchProcess). Cleaning up.")
            if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                try:
                    script_info['log_file'].close()
                except Exception as log_e:
                    logger.error(f"Error closing log file during cleanup of non-existent process {script_key}: {log_e}")
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            return False
        except Exception as e:
            logger.error(f"Error checking process status for {script_key}: {e}", exc_info=True)
            return False
    return False

def kill_process_tree(process_info):
    """Kill a process and all its children"""
    pid = None
    log_file_closed = False
    script_key = process_info.get('script_key', 'N/A')

    try:
        if 'log_file' in process_info and hasattr(process_info['log_file'], 'close') and not process_info['log_file'].closed:
            try:
                process_info['log_file'].close()
                log_file_closed = True
                logger.info(f"Closed log file for {script_key} (PID: {process_info.get('process', {}).get('pid', 'N/A')})")
            except Exception as log_e:
                logger.error(f"Error closing log file during kill for {script_key}: {log_e}")

        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            pid = process.pid
            if pid:
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    logger.info(f"Attempting to kill process tree for {script_key} (PID: {pid}, Children: {[c.pid for c in children]})")

                    for child in children:
                        try:
                            child.terminate()
                            logger.info(f"Terminated child process {child.pid} for {script_key}")
                        except psutil.NoSuchProcess:
                            logger.warning(f"Child process {child.pid} for {script_key} already gone.")
                        except Exception as e:
                            logger.error(f"Error terminating child {child.pid} for {script_key}: {e}. Trying kill...")
                            try:
                                child.kill()
                                logger.info(f"Killed child process {child.pid} for {script_key}")
                            except Exception as e2:
                                logger.error(f"Failed to kill child {child.pid} for {script_key}: {e2}")

                    gone, alive = psutil.wait_procs(children, timeout=1)
                    for p in alive:
                        logger.warning(f"Child process {p.pid} for {script_key} still alive. Killing.")
                        try:
                            p.kill()
                        except Exception as e:
                            logger.error(f"Failed to kill child {p.pid} for {script_key} after wait: {e}")

                    try:
                        parent.terminate()
                        logger.info(f"Terminated parent process {pid} for {script_key}")
                        try:
                            parent.wait(timeout=1)
                        except psutil.TimeoutExpired:
                            logger.warning(f"Parent process {pid} for {script_key} did not terminate. Killing.")
                            parent.kill()
                            logger.info(f"Killed parent process {pid} for {script_key}")
                    except psutil.NoSuchProcess:
                        logger.warning(f"Parent process {pid} for {script_key} already gone.")
                    except Exception as e:
                        logger.error(f"Error terminating parent {pid} for {script_key}: {e}. Trying kill...")
                        try:
                            parent.kill()
                            logger.info(f"Killed parent process {pid} for {script_key}")
                        except Exception as e2:
                            logger.error(f"Failed to kill parent {pid} for {script_key}: {e2}")

                except psutil.NoSuchProcess:
                    logger.warning(f"Process {pid or 'N/A'} for {script_key} not found during kill. Already terminated?")
            else:
                logger.error(f"Process PID is None for {script_key}.")
        elif log_file_closed:
            logger.warning(f"Process object missing for {script_key}, but log file closed.")
        else:
            logger.error(f"Process object missing for {script_key}, and no log file. Cannot kill.")
    except Exception as e:
        logger.error(f"❌ Unexpected error killing process tree for PID {pid or 'N/A'} ({script_key}): {e}", exc_info=True)

# --- Telegram Modules Mapping ---
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'python_telegram_bot': 'python-telegram-bot',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'bs4': 'beautifulsoup4',
    'requests': 'requests',
    'pillow': 'Pillow',
    'cv2': 'opencv-python',
    'yaml': 'PyYAML',
    'dotenv': 'python-dotenv',
    'dateutil': 'python-dateutil',
    'pandas': 'pandas',
    'numpy': 'numpy',
    'flask': 'Flask',
    'django': 'Django',
    'sqlalchemy': 'SQLAlchemy',
    'psutil': 'psutil',
    'asyncio': None,
    'json': None,
    'datetime': None,
    'os': None,
    'sys': None,
    're': None,
    'time': None,
    'math': None,
    'random': None,
    'logging': None,
    'threading': None,
    'subprocess': None,
    'zipfile': None,
    'tempfile': None,
    'shutil': None,
    'sqlite3': None,
    'atexit': None
}

# --- Script Running Functions ---
def attempt_install_pip(module_name, message):
    package_name = TELEGRAM_MODULES.get(module_name.lower(), module_name) 
    if package_name is None: 
        logger.info(f"Module '{module_name}' is core. Skipping pip install.")
        return False 
    try:
        bot.reply_to(message, f"🐍 Module `{module_name}` not found. Installing `{package_name}`...", parse_mode='Markdown')
        command = [sys.executable, '-m', 'pip', 'install', package_name]
        logger.info(f"Running install: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            logger.info(f"Installed {package_name}. Output:\n{result.stdout}")
            bot.reply_to(message, f"✅ Package `{package_name}` (for `{module_name}`) installed.", parse_mode='Markdown')
            return True
        else:
            error_msg = f"❌ Failed to install `{package_name}` for `{module_name}`.\nLog:\n```\n{result.stderr or result.stdout}\n```"
            logger.error(error_msg)
            if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (Log truncated)"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            return False
    except Exception as e:
        error_msg = f"❌ Error installing `{package_name}`: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, error_msg)
        return False

def attempt_install_npm(module_name, user_folder, message):
    try:
        bot.reply_to(message, f"🟠 Node package `{module_name}` not found. Installing locally...", parse_mode='Markdown')
        command = ['npm', 'install', module_name]
        logger.info(f"Running npm install: {' '.join(command)} in {user_folder}")
        result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=user_folder, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            logger.info(f"Installed {module_name}. Output:\n{result.stdout}")
            bot.reply_to(message, f"✅ Node package `{module_name}` installed locally.", parse_mode='Markdown')
            return True
        else:
            error_msg = f"❌ Failed to install Node package `{module_name}`.\nLog:\n```\n{result.stderr or result.stdout}\n```"
            logger.error(error_msg)
            if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (Log truncated)"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            return False
    except FileNotFoundError:
         error_msg = "❌ Error: 'npm' not found. Ensure Node.js/npm are installed and in PATH."
         logger.error(error_msg)
         bot.reply_to(message, error_msg)
         return False
    except Exception as e:
        error_msg = f"❌ Error installing Node package `{module_name}`: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, error_msg)
        return False

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    """Run Python script"""
    max_attempts = 2 
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run '{file_name}' after {max_attempts} attempts. Check logs.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"Attempt {attempt} to run Python script: {script_path} (Key: {script_key}) for user {script_owner_id}")

    try:
        if not os.path.exists(script_path):
             bot.reply_to(message_obj_for_reply, f"❌ Error: Script '{file_name}' not found at '{script_path}'!")
             logger.error(f"Script not found: {script_path} for user {script_owner_id}")
             if script_owner_id in user_files:
                 user_files[script_owner_id] = [f for f in user_files.get(script_owner_id, []) if f[0] != file_name]
             remove_user_file_db(script_owner_id, file_name)
             return

        if script_owner_id in file_stop_status and file_name in file_stop_status[script_owner_id]:
            bot.reply_to(message_obj_for_reply, f"⏰ *এই ফাইলটি স্টপ করা হয়েছে!*\n\n📄 ফাইল: `{file_name}`\n💡 *আবার আপলোড করতে পারেন*", parse_mode='Markdown')
            return

        if attempt == 1:
            check_command = [sys.executable, script_path]
            logger.info(f"Running Python pre-check: {' '.join(check_command)}")
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode
                logger.info(f"Python Pre-check early. RC: {return_code}. Stderr: {stderr[:200]}...")
                if return_code != 0 and stderr:
                    match_py = re.search(r"ModuleNotFoundError: No module named '(.+?)'", stderr)
                    if match_py:
                        module_name = match_py.group(1).strip().strip("'\"")
                        logger.info(f"Detected missing Python module: {module_name}")
                        if attempt_install_pip(module_name, message_obj_for_reply):
                            logger.info(f"Install OK for {module_name}. Retrying run_script...")
                            bot.reply_to(message_obj_for_reply, f"🔄 Install successful. Retrying '{file_name}'...")
                            time.sleep(2)
                            threading.Thread(target=run_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                            return
                        else:
                            bot.reply_to(message_obj_for_reply, f"❌ Install failed. Cannot run '{file_name}'.")
                            return
                    else:
                         error_summary = stderr[:500]
                         bot.reply_to(message_obj_for_reply, f"❌ Error in script pre-check for '{file_name}':\n```\n{error_summary}\n```\nFix the script.", parse_mode='Markdown')
                         return
            except subprocess.TimeoutExpired:
                logger.info("Python Pre-check timed out (>5s), imports likely OK. Killing check process.")
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()
                logger.info("Python Check process killed. Proceeding to long run.")
            except FileNotFoundError:
                 logger.error(f"Python interpreter not found: {sys.executable}")
                 bot.reply_to(message_obj_for_reply, f"❌ Error: Python interpreter '{sys.executable}' not found.")
                 return
            except Exception as e:
                 logger.error(f"Error in Python pre-check for {script_key}: {e}", exc_info=True)
                 bot.reply_to(message_obj_for_reply, f"❌ Unexpected error in script pre-check for '{file_name}': {e}")
                 return
            finally:
                 if check_proc and check_proc.poll() is None:
                     logger.warning(f"Python Check process {check_proc.pid} still running. Killing.")
                     check_proc.kill(); check_proc.communicate()

        logger.info(f"Starting long-running Python process for {script_key}")
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None; process = None
        try: log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
             logger.error(f"Failed to open log file '{log_file_path}' for {script_key}: {e}", exc_info=True)
             bot.reply_to(message_obj_for_reply, f"❌ Failed to open log file '{log_file_path}': {e}")
             return
        try:
            startupinfo = None; creationflags = 0
            if os.name == 'nt':
                 startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                 startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                [sys.executable, script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
                stdin=subprocess.PIPE, startupinfo=startupinfo, creationflags=creationflags,
                encoding='utf-8', errors='ignore'
            )
            logger.info(f"Started Python process {process.pid} for {script_key}")
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id,
                'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'py', 'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, f"✅ Python script '{file_name}' started! (PID: {process.pid}) (For User: {script_owner_id})")
        except FileNotFoundError:
             logger.error(f"Python interpreter {sys.executable} not found for long run {script_key}")
             bot.reply_to(message_obj_for_reply, f"❌ Error: Python interpreter '{sys.executable}' not found.")
             if log_file and not log_file.closed: log_file.close()
             if script_key in bot_scripts: del bot_scripts[script_key]
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            error_msg = f"❌ Error starting Python script '{file_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            bot.reply_to(message_obj_for_reply, error_msg)
            if process and process.poll() is None:
                 logger.warning(f"Killing potentially started Python process {process.pid} for {script_key}")
                 kill_process_tree({'process': process, 'log_file': log_file, 'script_key': script_key})
            if script_key in bot_scripts: del bot_scripts[script_key]
    except Exception as e:
        error_msg = f"❌ Unexpected error running Python script '{file_name}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message_obj_for_reply, error_msg)
        if script_key in bot_scripts:
             logger.warning(f"Cleaning up {script_key} due to error in run_script.")
             kill_process_tree(bot_scripts[script_key])
             del bot_scripts[script_key]

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    """Run JS script"""
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run '{file_name}' after {max_attempts} attempts. Check logs.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"Attempt {attempt} to run JS script: {script_path} (Key: {script_key}) for user {script_owner_id}")

    try:
        if not os.path.exists(script_path):
             bot.reply_to(message_obj_for_reply, f"❌ Error: Script '{file_name}' not found at '{script_path}'!")
             logger.error(f"JS Script not found: {script_path} for user {script_owner_id}")
             if script_owner_id in user_files:
                 user_files[script_owner_id] = [f for f in user_files.get(script_owner_id, []) if f[0] != file_name]
             remove_user_file_db(script_owner_id, file_name)
             return

        if script_owner_id in file_stop_status and file_name in file_stop_status[script_owner_id]:
            bot.reply_to(message_obj_for_reply, f"⏰ *এই ফাইলটি স্টপ করা হয়েছে!*\n\n📄 ফাইল: `{file_name}`\n💡 *আবার আপলোড করতে পারেন*", parse_mode='Markdown')
            return

        if attempt == 1:
            check_command = ['node', script_path]
            logger.info(f"Running JS pre-check: {' '.join(check_command)}")
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode
                logger.info(f"JS Pre-check early. RC: {return_code}. Stderr: {stderr[:200]}...")
                if return_code != 0 and stderr:
                    match_js = re.search(r"Cannot find module '(.+?)'", stderr)
                    if match_js:
                        module_name = match_js.group(1).strip().strip("'\"")
                        if not module_name.startswith('.') and not module_name.startswith('/'):
                             logger.info(f"Detected missing Node module: {module_name}")
                             if attempt_install_npm(module_name, user_folder, message_obj_for_reply):
                                 logger.info(f"NPM Install OK for {module_name}. Retrying run_js_script...")
                                 bot.reply_to(message_obj_for_reply, f"🔄 NPM Install successful. Retrying '{file_name}'...")
                                 time.sleep(2)
                                 threading.Thread(target=run_js_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                                 return
                             else:
                                 bot.reply_to(message_obj_for_reply, f"❌ NPM Install failed. Cannot run '{file_name}'.")
                                 return
                        else: logger.info(f"Skipping npm install for relative/core: {module_name}")
                    error_summary = stderr[:500]
                    bot.reply_to(message_obj_for_reply, f"❌ Error in JS script pre-check for '{file_name}':\n```\n{error_summary}\n```\nFix script or install manually.", parse_mode='Markdown')
                    return
            except subprocess.TimeoutExpired:
                logger.info("JS Pre-check timed out (>5s), imports likely OK. Killing check process.")
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()
                logger.info("JS Check process killed. Proceeding to long run.")
            except FileNotFoundError:
                 error_msg = "❌ Error: 'node' not found. Ensure Node.js is installed for JS files."
                 logger.error(error_msg)
                 bot.reply_to(message_obj_for_reply, error_msg)
                 return
            except Exception as e:
                 logger.error(f"Error in JS pre-check for {script_key}: {e}", exc_info=True)
                 bot.reply_to(message_obj_for_reply, f"❌ Unexpected error in JS pre-check for '{file_name}': {e}")
                 return
            finally:
                 if check_proc and check_proc.poll() is None:
                     logger.warning(f"JS Check process {check_proc.pid} still running. Killing.")
                     check_proc.kill(); check_proc.communicate()

        logger.info(f"Starting long-running JS process for {script_key}")
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None; process = None
        try: log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Failed to open log file '{log_file_path}' for JS script {script_key}: {e}", exc_info=True)
            bot.reply_to(message_obj_for_reply, f"❌ Failed to open log file '{log_file_path}': {e}")
            return
        try:
            startupinfo = None; creationflags = 0
            if os.name == 'nt':
                 startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                 startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                ['node', script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
                stdin=subprocess.PIPE, startupinfo=startupinfo, creationflags=creationflags,
                encoding='utf-8', errors='ignore'
            )
            logger.info(f"Started JS process {process.pid} for {script_key}")
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id,
                'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'js', 'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, f"✅ JS script '{file_name}' started! (PID: {process.pid}) (For User: {script_owner_id})")
        except FileNotFoundError:
             error_msg = "❌ Error: 'node' not found for long run. Ensure Node.js is installed."
             logger.error(error_msg)
             if log_file and not log_file.closed: log_file.close()
             bot.reply_to(message_obj_for_reply, error_msg)
             if script_key in bot_scripts: del bot_scripts[script_key]
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            error_msg = f"❌ Error starting JS script '{file_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            bot.reply_to(message_obj_for_reply, error_msg)
            if process and process.poll() is None:
                 logger.warning(f"Killing potentially started JS process {process.pid} for {script_key}")
                 kill_process_tree({'process': process, 'log_file': log_file, 'script_key': script_key})
            if script_key in bot_scripts: del bot_scripts[script_key]
    except Exception as e:
        error_msg = f"❌ Unexpected error running JS script '{file_name}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message_obj_for_reply, error_msg)
        if script_key in bot_scripts:
             logger.warning(f"Cleaning up {script_key} due to error in run_js_script.")
             kill_process_tree(bot_scripts[script_key])
             del bot_scripts[script_key]

# --- Database Operations ---
def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = db_connect()
        c = conn.cursor()
        try:
            upload_time = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type, upload_time, is_stopped) VALUES (?, ?, ?, ?, 0)',
                      (user_id, file_name, file_type, upload_time))
            conn.commit()
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
            
            if user_id in file_stop_status and file_name in file_stop_status[user_id]:
                file_stop_status[user_id].remove(file_name)
            
            logger.info(f"Saved file '{file_name}' ({file_type}) for user {user_id}")
        except sqlite3.Error as e: logger.error(f"❌ SQLite error saving file for user {user_id}, {file_name}: {e}")
        except Exception as e: logger.error(f"❌ Unexpected error saving file for {user_id}, {file_name}: {e}", exc_info=True)
        finally: conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = db_connect()
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
                if not user_files[user_id]: del user_files[user_id]
            if user_id in file_stop_status and file_name in file_stop_status[user_id]:
                file_stop_status[user_id].remove(file_name)
                if not file_stop_status[user_id]: del file_stop_status[user_id]
            logger.info(f"Removed file '{file_name}' for user {user_id} from DB")
        except sqlite3.Error as e: logger.error(f"❌ SQLite error removing file for {user_id}, {file_name}: {e}")
        except Exception as e: logger.error(f"❌ Unexpected error removing file for {user_id}, {file_name}: {e}", exc_info=True)
        finally: conn.close()

def add_active_user(user_id):
    active_users.add(user_id) 
    with DB_LOCK:
        conn = db_connect()
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
            conn.commit()
            logger.info(f"Added/Confirmed active user {user_id} in DB")
        except sqlite3.Error as e: logger.error(f"❌ SQLite error adding active user {user_id}: {e}")
        except Exception as e: logger.error(f"❌ Unexpected error adding active user {user_id}: {e}", exc_info=True)
        finally: conn.close()

def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = db_connect()
        c = conn.cursor()
        try:
            expiry_str = expiry.isoformat()
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)', (user_id, expiry_str))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry}
            logger.info(f"Saved subscription for {user_id}, expiry {expiry_str}")
        except sqlite3.Error as e: logger.error(f"❌ SQLite error saving subscription for {user_id}: {e}")
        except Exception as e: logger.error(f"❌ Unexpected error saving subscription for {user_id}: {e}", exc_info=True)
        finally: conn.close()

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = db_connect()
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_subscriptions: del user_subscriptions[user_id]
            logger.info(f"Removed subscription for {user_id} from DB")
        except sqlite3.Error as e: logger.error(f"❌ SQLite error removing subscription for {user_id}: {e}")
        except Exception as e: logger.error(f"❌ Unexpected error removing subscription for {user_id}: {e}", exc_info=True)
        finally: conn.close()

def add_admin_db(admin_id):
    with DB_LOCK:
        conn = db_connect()
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (admin_id,))
            conn.commit()
            admin_ids.add(admin_id) 
            logger.info(f"Added admin {admin_id} to DB")
        except sqlite3.Error as e: logger.error(f"❌ SQLite error adding admin {admin_id}: {e}")
        except Exception as e: logger.error(f"❌ Unexpected error adding admin {admin_id}: {e}", exc_info=True)
        finally: conn.close()

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID:
        logger.warning("Attempted to remove OWNER_ID from admins.")
        return False 
    with DB_LOCK:
        conn = db_connect()
        c = conn.cursor()
        removed = False
        try:
            c.execute('SELECT 1 FROM admins WHERE user_id = ?', (admin_id,))
            if c.fetchone():
                c.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
                conn.commit()
                removed = c.rowcount > 0 
                if removed: admin_ids.discard(admin_id); logger.info(f"Removed admin {admin_id} from DB")
                else: logger.warning(f"Admin {admin_id} found but delete affected 0 rows.")
            else:
                logger.warning(f"Admin {admin_id} not found in DB.")
                admin_ids.discard(admin_id)
            return removed
        except sqlite3.Error as e: logger.error(f"❌ SQLite error removing admin {admin_id}: {e}"); return False
        except Exception as e: logger.error(f"❌ Unexpected error removing admin {admin_id}: {e}", exc_info=True); return False
        finally: conn.close()

def save_free_user_settings(limit_value, time_value, host_time):
    """Save free user settings to database"""
    with DB_LOCK:
        conn = db_connect()
        c = conn.cursor()
        try:
            c.execute('UPDATE free_user_settings SET limit_value = ?, time_value = ?, host_time = ? WHERE id = 1', 
                      (limit_value, time_value, host_time))
            conn.commit()
            FREE_USER_LIMIT_SETTINGS["limit"] = limit_value
            FREE_USER_LIMIT_SETTINGS["time"] = time_value
            FREE_USER_LIMIT_SETTINGS["host_time"] = host_time
            logger.info(f"Free user settings updated: limit={limit_value}, time={time_value}, host_time={host_time}")
            return True
        except sqlite3.Error as e:
            logger.error(f"❌ SQLite error saving free user settings: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error saving free user settings: {e}", exc_info=True)
            return False
        finally:
            conn.close()
# --- End Database Operations ---

# --- Menu Creation ---
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL),
        types.InlineKeyboardButton('📤 Upload File', callback_data='upload'),
        types.InlineKeyboardButton('📂 Check Files', callback_data='check_files'),
        types.InlineKeyboardButton('⚡ Bot Speed', callback_data='speed'),
        types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}')
    ]

    if user_id in admin_ids:
        admin_buttons = [
            types.InlineKeyboardButton('💳 Subscriptions', callback_data='subscription'),
            types.InlineKeyboardButton('📊 Statistics', callback_data='stats'),
            types.InlineKeyboardButton('🔒 Lock Bot' if not bot_locked else '🔓 Unlock Bot',
                                     callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
            types.InlineKeyboardButton('🟢 Running All Code', callback_data='run_all_scripts'),
            types.InlineKeyboardButton('🔴 Rakib Admin Panel', callback_data='gx_admin_panel')
        ]
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3], admin_buttons[0])
        markup.add(admin_buttons[1], admin_buttons[2])
        markup.add(admin_buttons[3])
        markup.add(admin_buttons[4])
        markup.add(buttons[4])
    else:
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3])
        markup.add(types.InlineKeyboardButton('📊 Statistics', callback_data='stats'))
        markup.add(buttons[4])
    return markup

# --- Colored Reply Keyboard Button Helper ---
# Uses Telegram's native button background styles while keeping button text clean.
COLORED_BUTTON_STYLES = {
    "💎 আপডেট চ্যানেল": "danger", "💎 ফাইল দেখুন": "primary", "💎 আমার প্রোফাইল": "success",
    "💎 সাপোর্ট": "success",
    "UPDATES CHANNEL": "danger", "CHECK FILES": "primary", "STATISTICS": "success", "CONTACT OWNER": "primary",
    "BACK TO MAIN": "primary", "ADMIN LIST": "danger", "BACK TO ADMIN PANEL": "danger", "SHOW ALL ADMINS": "primary",
    "SHOW ALL DEPOSITE REQUEST": "primary", "আমার ডিপোজিট রিকোয়েস্ট": "primary",
    "💎 ফাইল আপলোড করুন": "success", "💎 ডিপোজিট": "danger", "💎 প্রিমিয়াম প্লান 🌟": "primary",
    "UPLOAD FILE": "success", "BOT SPEED": "danger", "SUBSCRIPTIONS": "success", "RUNNING ALL CODE": "danger",
    "SET LIMIT": "success", "FREE BOT LIMIT": "primary", "Set Premium Plan for All User 🌟": "primary",
    "DEPOSITE SYSTEM": "success", "FORCE JOIN": "success", "SET SUPPORT LINK": "primary", "ADD ADMIN": "success",
    "SET DEPOSIT NUMBER AND ID": "success", "Add Your Premium Plan": "success", "Buy Plan": "success", "Deposit": "success",
    "FORCE JOIN ON": "success", "SET FORCE JOIN CHANNEL": "success",
    "LOCK BOT": "primary", "Rakib Admin Panel": "danger", "REMOVE ADMIN": "danger", "TRANSFER OWNERSHIP": "danger",
    "DELETE PAYMENT METHOD": "danger", "Remove Plan": "danger", "Reset All Plans": "danger", "FORCE JOIN OFF": "danger",
}

def create_styled_keyboard_button(text):
    style = COLORED_BUTTON_STYLES.get(text)
    if style:
        try:
            return types.KeyboardButton(text, style=style)
        except TypeError:
            # Compatibility with older pyTelegramBotAPI versions.
            button = types.KeyboardButton(text)
            button.style = style
            return button
    return types.KeyboardButton(text)

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if user_id in admin_ids or user_id in admin_list:
        layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC
    else:
        layout_to_use = COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row_buttons_text in layout_to_use:
        markup.add(*[create_styled_keyboard_button(text) for text in row_buttons_text])
    return markup

def create_otp_reply_keyboard(user_id):
    """Create OTP GURU bot reply keyboard with all buttons"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if user_id in admin_ids or user_id in admin_list:
        for row in OTP_ADMIN_BUTTONS:
            markup.add(*[create_styled_keyboard_button(text) for text in row])
    else:
        for row in OTP_USER_BUTTONS:
            markup.add(*[create_styled_keyboard_button(text) for text in row])
    return markup

def create_otp_admin_list_keyboard():
    """Create OTP admin list sub-menu keyboard"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for row in OTP_ADMIN_LIST_BUTTONS:
        markup.add(*[create_styled_keyboard_button(text) for text in row])
    return markup

def create_otp_deposite_keyboard():
    """Create OTP deposite sub-menu keyboard"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for row in OTP_DEPOSITE_BUTTONS:
        markup.add(*[create_styled_keyboard_button(text) for text in row])
    return markup

def create_premium_admin_keyboard():
    """Create premium plan admin keyboard"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for row in PREMIUM_PLAN_ADMIN_BUTTONS:
        markup.add(*[create_styled_keyboard_button(text) for text in row])
    return markup

def create_premium_user_keyboard():
    """Create premium plan user keyboard"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for row in PREMIUM_PLAN_USER_BUTTONS:
        markup.add(*[create_styled_keyboard_button(text) for text in row])
    return markup

def create_control_buttons(script_owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("📜 View Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    markup.add(types.InlineKeyboardButton("🔙 Back to Files", callback_data='check_files'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Subscription', callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Remove Subscription', callback_data='remove_subscription')
    )
    markup.row(types.InlineKeyboardButton('🔍 Check Subscription', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

# --- File Handling Functions ---
def handle_zip_file(downloaded_file_content, file_name_zip, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    
    if user_id != OWNER_ID:
        is_safe, reason = scan_file_for_malware(downloaded_file_content, file_name_zip, user_id)
        if not is_safe:
            bot.reply_to(message, f"🚨 Security Alert: {reason}\nOnly owner can upload this type of file.")
            return
    
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        logger.info(f"Temp dir for zip: {temp_dir}")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as new_file:
            new_file.write(downloaded_file_content)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            if user_id != OWNER_ID:
                for member in zip_ref.infolist():
                    member_name_lower = member.filename.lower()
                    suspicious_extensions = ['.exe', '.dll', '.bat', '.cmd', '.scr', '.com']
                    if any(member_name_lower.endswith(ext) for ext in suspicious_extensions):
                        bot.reply_to(message, f"🚨 Security Alert: ZIP contains suspicious file: {member.filename}\nOnly owner can upload such files.")
                        return
                    
                    member_path = os.path.abspath(os.path.join(temp_dir, member.filename))
                    if not member_path.startswith(os.path.abspath(temp_dir)):
                        raise zipfile.BadZipFile(f"Zip has unsafe path: {member.filename}")
            
            zip_ref.extractall(temp_dir)
            logger.info(f"Extracted zip to {temp_dir}")

        target_dir = temp_dir
        root_files = os.listdir(target_dir)
        
        if not any(f.endswith(('.py', '.js')) for f in root_files):
            for root, dirs, files in os.walk(temp_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.') and not d.startswith('__')]
                
                if any(f.endswith(('.py', '.js')) for f in files):
                    target_dir = root
                    break
        
        if target_dir != temp_dir:
            logger.info(f"Flattening extracted files from {target_dir} to {temp_dir}")
            for item in os.listdir(target_dir):
                s = os.path.join(target_dir, item)
                d = os.path.join(temp_dir, item)
                if os.path.exists(d):
                    if os.path.isdir(d): shutil.rmtree(d)
                    else: os.remove(d)
                shutil.move(s, d)
            extracted_items = os.listdir(temp_dir)
        else:
            extracted_items = root_files

        py_files = [f for f in extracted_items if f.endswith('.py')]
        js_files = [f for f in extracted_items if f.endswith('.js')]
        req_file = 'requirements.txt' if 'requirements.txt' in extracted_items else None
        pkg_json = 'package.json' if 'package.json' in extracted_items else None

        if req_file:
            req_path = os.path.join(temp_dir, req_file)
            logger.info(f"requirements.txt found, installing: {req_path}")
            bot.reply_to(message, f"🔄 Installing Python deps from `{req_file}`...")
            try:
                command = [sys.executable, '-m', 'pip', 'install', '-r', req_path]
                result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore')
                logger.info(f"pip install from requirements.txt OK. Output:\n{result.stdout}")
                bot.reply_to(message, f"✅ Python deps from `{req_file}` installed.")
            except subprocess.CalledProcessError as e:
                error_msg = f"❌ Failed to install Python deps from `{req_file}`.\nLog:\n```\n{e.stderr or e.stdout}\n```"
                logger.error(error_msg)
                if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (Log truncated)"
                bot.reply_to(message, error_msg, parse_mode='Markdown'); return
            except Exception as e:
                 error_msg = f"❌ Unexpected error installing Python deps: {e}"
                 logger.error(error_msg, exc_info=True); bot.reply_to(message, error_msg); return

        if pkg_json:
            logger.info(f"package.json found, npm install in: {temp_dir}")
            bot.reply_to(message, f"🔄 Installing Node deps from `{pkg_json}`...")
            try:
                command = ['npm', 'install']
                result = subprocess.run(command, capture_output=True, text=True, check=True, cwd=temp_dir, encoding='utf-8', errors='ignore')
                logger.info(f"npm install OK. Output:\n{result.stdout}")
                bot.reply_to(message, f"✅ Node deps from `{pkg_json}` installed.")
            except FileNotFoundError:
                bot.reply_to(message, "❌ 'npm' not found. Cannot install Node deps."); return 
            except subprocess.CalledProcessError as e:
                error_msg = f"❌ Failed to install Node deps from `{pkg_json}`.\nLog:\n```\n{e.stderr or e.stdout}\n```"
                logger.error(error_msg)
                if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (Log truncated)"
                bot.reply_to(message, error_msg, parse_mode='Markdown'); return
            except Exception as e:
                 error_msg = f"❌ Unexpected error installing Node deps: {e}"
                 logger.error(error_msg, exc_info=True); bot.reply_to(message, error_msg); return

        main_script_name = None; file_type = None
        preferred_py = ['main.py', 'bot.py', 'app.py']; preferred_js = ['index.js', 'main.js', 'bot.js', 'app.js']
        for p in preferred_py:
            if p in py_files: main_script_name = p; file_type = 'py'; break
        if not main_script_name:
             for p in preferred_js:
                 if p in js_files: main_script_name = p; file_type = 'js'; break
        if not main_script_name:
            if py_files: main_script_name = py_files[0]; file_type = 'py'
            elif js_files: main_script_name = js_files[0]; file_type = 'js'
        if not main_script_name:
            bot.reply_to(message, "❌ No `.py` or `.js` script found in archive!"); return

        logger.info(f"Moving extracted files from {temp_dir} to {user_folder}")
        moved_count = 0
        for item_name in os.listdir(temp_dir):
            if item_name == file_name_zip: continue
            src_path = os.path.join(temp_dir, item_name)
            dest_path = os.path.join(user_folder, item_name)
            if os.path.isdir(dest_path): shutil.rmtree(dest_path)
            elif os.path.exists(dest_path): os.remove(dest_path)
            shutil.move(src_path, dest_path); moved_count +=1
        logger.info(f"Moved {moved_count} items to {user_folder}")

        save_user_file(user_id, main_script_name, file_type)
        logger.info(f"Saved main script '{main_script_name}' ({file_type}) for {user_id} from zip.")
        main_script_path = os.path.join(user_folder, main_script_name)
        bot.reply_to(message, f"✅ Files extracted. Starting main script: `{main_script_name}`...", parse_mode='Markdown')

        if user_id not in user_upload_times:
            user_upload_times[user_id] = []
        user_upload_times[user_id].append(datetime.now())

        if file_type == 'py':
             threading.Thread(target=run_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()
        elif file_type == 'js':
             threading.Thread(target=run_js_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()

    except zipfile.BadZipFile as e:
        logger.error(f"Bad zip file from {user_id}: {e}")
        bot.reply_to(message, f"❌ Error: Invalid/corrupted ZIP. {e}")
    except Exception as e:
        logger.error(f"❌ Error processing zip for {user_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error processing zip: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir); logger.info(f"Cleaned temp dir: {temp_dir}")
            except Exception as e: logger.error(f"Failed to clean temp dir {temp_dir}: {e}", exc_info=True)

def handle_js_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'js')
        if script_owner_id not in user_upload_times:
            user_upload_times[script_owner_id] = []
        user_upload_times[script_owner_id].append(datetime.now())
        threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        logger.error(f"❌ Error processing JS file {file_name} for {script_owner_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error processing JS file: {str(e)}")

def handle_py_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'py')
        if script_owner_id not in user_upload_times:
            user_upload_times[script_owner_id] = []
        user_upload_times[script_owner_id].append(datetime.now())
        threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        logger.error(f"❌ Error processing Python file {file_name} for {script_owner_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error processing Python file: {str(e)}")

# --- Malware Detection Functions ---
def get_file_type(file_content):
    """Determine file type using magic numbers and mimetypes"""
    signatures = {
        b'\x7fELF': 'application/x-executable',
        b'MZ': 'application/x-dosexec',
        b'\xfe\xed\xfa': 'application/x-mach-binary',
        b'\xce\xfa\xed\xfe': 'application/x-mach-binary',
        b'PK': 'application/zip',
        b'Rar!': 'application/x-rar',
    }
    
    for signature, mime_type in signatures.items():
        if file_content.startswith(signature):
            return mime_type
    
    return 'application/octet-stream'

def is_suspicious_file(file_content, file_name):
    """Check if file contains malware signatures"""
    file_lower = file_name.lower()
    
    suspicious_extensions = ['.exe', '.dll', '.bat', '.cmd', '.scr', '.com', '.pif', '.application', '.gadget',
                            '.msi', '.msp', '.com', '.scr', '.hta', '.cpl', '.msc', '.jar', '.bin', '.deb', '.rpm',
                            '.apk', '.app', '.dmg', '.iso', '.img']
    
    if any(file_lower.endswith(ext) for ext in suspicious_extensions):
        return True, f"Suspicious file extension: {file_name}"
    
    for signature in MALWARE_SIGNATURES:
        if file_content.startswith(signature):
            return True, f"Malware signature detected: {signature}"
    
    sample_size = min(len(file_content), 4096)
    file_sample = file_content[:sample_size]
    
    for indicator in ENCRYPTED_FILE_INDICATORS:
        if indicator in file_sample:
            return True, f"Encrypted file indicator: {indicator.decode('utf-8', errors='ignore')}"
    
    sample_text = file_sample.decode('utf-8', errors='ignore').lower()
    for keyword in SUSPICIOUS_KEYWORDS:
        if keyword.decode('utf-8').lower() in sample_text:
            return True, f"Suspicious keyword found: {keyword.decode('utf-8')}"
    
    try:
        file_type = get_file_type(file_sample)
        if file_type in ['application/x-dosexec', 'application/x-executable', 'application/x-mach-binary']:
            return True, f"Executable file type detected: {file_type}"
    except Exception as e:
        logger.warning(f"Could not determine file type: {e}")
    
    return False, "File appears safe"

def scan_file_for_malware(file_content, file_name, user_id):
    """Comprehensive malware scan for uploaded files"""
    if user_id == OWNER_ID:
        return True, "Owner bypassed security check"
    
    is_suspicious, reason = is_suspicious_file(file_content, file_name)
    
    if is_suspicious:
        logger.warning(f"🚨 Malware detected in {file_name} from user {user_id}: {reason}")
        return False, f"Security violation: {reason}"
    
    return True, "File passed security check"

# ==================== OTP GURU Bot Functions ====================

def is_otp_admin(user_id):
    """Check if user is OTP admin"""
    return user_id in admin_list or user_id == OWNER_ID

def handle_otp_profile(message):
    """Handle OTP profile view with new balance system"""
    user_id = message.from_user.id
    
    user_data = None
    for user in all_users:
        if user["id"] == user_id:
            user_data = user
            break
    
    if not user_data:
        user_name = message.from_user.first_name
        username = message.from_user.username
        add_otp_user(user_id, user_name, username)
        user_data = get_otp_user_data(user_id)
    
    user_files_otp = [f for f in all_files if f["uploader"] == user_id]
    file_count = len(user_files_otp)
    
    user_limit = user_limits.get(user_id, "সীমাহীন")
    
    # Get balance from new system
    balance = get_user_balance_db(user_id)
    
    premium = get_user_premium_plan(user_id)
    if premium and premium["expiry"] > datetime.now():
        user_status = "⭐ প্রিমিয়াম"
        days_left = (premium["expiry"] - datetime.now()).days
        status_text = f"{user_status} (বাকি {days_left} দিন)"
    else:
        user_status = "🆓 ফ্রি"
        status_text = user_status
    
    profile_text = (
        "📋 *আমার প্রোফাইল*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *নাম:* {user_data['name']}\n"
        f"🆔 *ইউজার আইডি:* `{user_data['id']}`\n"
        f"📌 *ইউজারনেম:* {user_data['username']}\n"
        f"📅 *জয়েন তারিখ:* {user_data['joined']}\n"
        f"💰 *ব্যালেন্স:* ৳{balance:.2f}\n"
        f"📁 *মোট ফাইল:* {file_count}\n"
        f"📊 *ফাইল লিমিট:* {user_limit}\n"
        f"⭐ *স্ট্যাটাস:* {status_text}\n"
        f"⏰ *হোস্ট সময়:* {'সীমাহীন' if get_user_host_time(user_id) == float('inf') else str(get_user_host_time(user_id)) + ' ঘন্টা'}"
    )
    
    bot.reply_to(message, profile_text, parse_mode='Markdown')

# ==================== DEPOSIT SYSTEM HANDLERS ====================

def handle_deposit_user(message):
    """Handle deposit for users - NEW SYSTEM"""
    user_id = message.from_user.id
    
    methods = get_payment_methods()
    if not methods:
        bot.reply_to(message, 
            "❌ *কোনো পেমেন্ট মেথড উপলব্ধ নেই!*\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "📌 *অ্যাডমিন পেমেন্ট মেথড সেট করেনি*\n"
            "💡 *দয়া করে পরে আবার চেষ্টা করুন*",
            parse_mode='Markdown'
        )
        return
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for m in methods:
        unit = "USDT" if m['name'].lower() == 'binance' else "BDT"
        btn_text = f"{m['name']} (Min {m['min_deposit']} {unit})"
        keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=f'deposit_method_{m["name"]}'))
    
    keyboard.add(types.InlineKeyboardButton("আমার ডিপোজিট রিকোয়েস্ট", callback_data='my_deposits'))
    keyboard.add(types.InlineKeyboardButton("Cancel", callback_data='cancel_deposit'))
    
    bot.reply_to(message, 
        "💰 *ডিপোজিট*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *আপনার পেমেন্ট মেথড সিলেক্ট করুন:*",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

def handle_deposit_method_selection(call):
    """Handle deposit method selection"""
    user_id = call.from_user.id
    method_name = call.data.split('_')[2]
    
    method = get_payment_method(method_name)
    if not method:
        bot.answer_callback_query(call.id, "❌ মেথড পাওয়া যায়নি!", show_alert=True)
        return
    
    # Store method in user data
    user_deposit_state = getattr(handle_deposit_method_selection, 'user_deposit_state', {})
    user_deposit_state[user_id] = {"method": method_name}
    handle_deposit_method_selection.user_deposit_state = user_deposit_state
    
    unit = "USDT" if method_name.lower() == 'binance' else "BDT"
    
    # Payment instructions
    rate_info = ""
    payment_instruction = ""
    if method_name.lower() in ('bkash', 'nagad'):
        payment_instruction = "\n📌 *Payment Option:* শুধু Send Money"
    elif method_name.lower() == 'binance':
        usdt_rate = get_setting('usdt_rate') or "120"
        rate_info = f"\n💡 *বর্তমান রেট:* 1 USDT = {usdt_rate} BDT"
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_deposit'))
    
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        f"💳 *পেমেন্ট মেথড:* {method_name}\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"📱 *নম্বর/আইডি:* `{method['number']}`{payment_instruction}\n"
        f"💰 *ন্যূনতম:* {method['min_deposit']} {unit}{rate_info}\n\n"
        f"📌 *আপনি কত {unit} ডিপোজিট করতে চান?*\n"
        f"💡 *শুধু সংখ্যা লিখুন:*",
        call.message.chat.id, call.message.message_id,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    
    # Set state for next step
    from telebot.types import ReplyKeyboardMarkup, KeyboardButton
    user_deposit_state[user_id]["step"] = "waiting_amount"
    bot.register_next_step_handler(call.message, process_deposit_amount, method_name)

def process_deposit_amount(message, method_name):
    """Process deposit amount input"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    try:
        amount = float(text)
        if amount <= 0:
            bot.reply_to(message, "❌ *টাকা ০ এর বেশি হতে হবে!*", parse_mode='Markdown')
            return
        
        method = get_payment_method(method_name)
        if not method:
            bot.reply_to(message, "❌ *মেথড পাওয়া যায়নি!*", parse_mode='Markdown')
            return
        
        if amount < method['min_deposit']:
            unit = "USDT" if method_name.lower() == 'binance' else "BDT"
            bot.reply_to(message, 
                f"❌ *ন্যূনতম ডিপোজিট {method['min_deposit']} {unit}!*", 
                parse_mode='Markdown'
            )
            return
        
        # Store amount
        user_deposit_state = getattr(process_deposit_amount, 'user_deposit_state', {})
        if user_id not in user_deposit_state:
            user_deposit_state[user_id] = {}
        user_deposit_state[user_id]["amount"] = amount
        user_deposit_state[user_id]["step"] = "waiting_trxid"
        process_deposit_amount.user_deposit_state = user_deposit_state
        
        unit = "USDT" if method_name.lower() == 'binance' else "BDT"
        
        # For Binance, show calculated BDT
        extra_info = ""
        if method_name.lower() == 'binance':
            usdt_rate = float(get_setting('usdt_rate') or "120")
            calculated_bdt = amount * usdt_rate
            extra_info = f"\n🤑 *পাবেন:* ৳{calculated_bdt:.2f} (রেট: 1$ = {usdt_rate:.2f} BDT)"
        
        bot.reply_to(message, 
            f"💳 *পেমেন্ট মেথড:* {method_name}\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"📱 *নম্বর/আইডি:* `{method['number']}`\n"
            f"💰 *পরিমাণ:* {amount} {unit}{extra_info}\n\n"
            f"📌 *পেমেন্ট শেষে Transaction ID (TrxID) লিখুন:*",
            parse_mode='Markdown'
        )
        
        bot.register_next_step_handler(message, process_deposit_trxid, method_name, amount)
        
    except ValueError:
        bot.reply_to(message, "❌ *শুধু সংখ্যা লিখুন!*", parse_mode='Markdown')

def process_deposit_trxid(message, method_name, amount):
    """Require TrxID, then require a payment screenshot."""
    user_id = message.from_user.id
    if not message.text:
        bot.reply_to(message, "❌ *শুধু TrxID লিখুন!*", parse_mode='Markdown')
        return
    trx_id = message.text.strip()
    if not trx_id:
        bot.reply_to(message, "❌ *Transaction ID লিখুন!*", parse_mode='Markdown')
        return

    # Keep state until screenshot arrives.
    state = getattr(process_deposit_trxid, 'pending_state', {})
    state[user_id] = {"method": method_name, "amount": amount, "trx_id": trx_id}
    process_deposit_trxid.pending_state = state

    bot.reply_to(
        message,
        "📸 *এখন পেমেন্টের Screenshot পাঠান।*\n\n"
        "⚠️ *Screenshot দেওয়া বাধ্যতামূলক।*\n"
        "❌ Screenshot ছাড়া Deposit Request গ্রহণ করা হবে না।",
        parse_mode='Markdown'
    )

@bot.message_handler(content_types=['photo'])
def handle_deposit_screenshot(message):
    """Accept screenshot only when a user has completed the TrxID step."""
    user_id = message.from_user.id
    state = getattr(process_deposit_trxid, 'pending_state', {})
    data = state.get(user_id)
    if not data:
        return

    screenshot_file_id = message.photo[-1].file_id
    method_name = data['method']
    amount = data['amount']
    trx_id = data['trx_id']

    deposit_id, error = create_deposit_request(user_id, amount, method_name, trx_id, screenshot_file_id)
    if error:
        bot.reply_to(message, f"❌ *ডিপোজিট তৈরি করতে ব্যর্থ হয়েছে!*\n\n📌 কারণ: {error}", parse_mode='Markdown')
        return

    # Clear pending state after successful DB insert.
    state.pop(user_id, None)
    process_deposit_trxid.pending_state = state

    unit = 'USDT' if method_name.lower() == 'binance' else 'BDT'
    display_amount = f"{amount:.2f} USDT" if unit == 'USDT' else f"৳{amount:.2f}"
    bot.reply_to(
        message,
        f"✅ *ডিপোজিট রিকোয়েস্ট জমা হয়েছে!*\n━━━━━━━━━━━━━━━━━\n\n"
        f"💰 *পরিমাণ:* {display_amount}\n"
        f"📱 *মেথড:* {method_name}\n"
        f"🧾 *TrxID:* `{trx_id}`\n"
        f"📸 *Screenshot:* ✅ দেওয়া হয়েছে\n"
        f"📌 *স্ট্যাটাস:* ⏳ অপেক্ষমান\n\n"
        f"⏳ *Admin approve করার জন্য অপেক্ষা করুন।*",
        parse_mode='Markdown'
    )

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f'approve_dep_{deposit_id}'),
        types.InlineKeyboardButton("❌ Reject", callback_data=f'reject_dep_{deposit_id}')
    )
    admin_msg = (
        f"📥 *নতুন ডিপোজিট রিকোয়েস্ট!*\n━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *ইউজার:* {message.from_user.first_name}\n"
        f"🆔 *আইডি:* `{user_id}`\n"
        f"💰 *পরিমাণ:* {display_amount}\n"
        f"📱 *মেথড:* {method_name}\n"
        f"🧾 *TrxID:* `{trx_id}`\n"
        f"📸 *Payment Screenshot:* নিচের ছবিতে আছে\n"
        f"📅 *তারিখ:* {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    for admin_id in sorted(set(admin_list) | {OWNER_ID, ADMIN_ID}):
        try:
            bot.send_photo(admin_id, screenshot_file_id, caption=admin_msg, reply_markup=keyboard, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

def handle_my_deposits(call):
    """Show user's deposits"""
    user_id = call.from_user.id
    deposits = get_user_deposits(user_id)
    
    if not deposits:
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "📋 *আমার ডিপোজিট রিকোয়েস্ট*\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "📌 *আপনার কোনো ডিপোজিট রিকোয়েস্ট নেই!*",
            call.message.chat.id, call.message.message_id,
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🔙 Back", callback_data='back_deposit')
            ),
            parse_mode='Markdown'
        )
        return
    
    pending = [d for d in deposits if d[4] == 'pending']
    approved = [d for d in deposits if d[4] == 'approved']
    rejected = [d for d in deposits if d[4] == 'rejected']
    
    deposit_list = ""
    for i, d in enumerate(deposits, 1):
        status_emoji = "🟡" if d[4] == "pending" else "🟢" if d[4] == "approved" else "🔴"
        status_text = "অপেক্ষমান" if d[4] == "pending" else "অ্যাপ্রুভড" if d[4] == "approved" else "বাতিল"
        deposit_list += f"{i}. {status_emoji} *টাকা:* ৳{d[1]:.2f}\n"
        deposit_list += f"   📱 *মেথড:* {d[2]}\n"
        deposit_list += f"   📌 *স্ট্যাটাস:* {status_text}\n"
        deposit_list += f"   📅 *তারিখ:* {d[5]}\n\n"
    
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        f"📋 *আমার ডিপোজিট রিকোয়েস্ট*\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"{deposit_list}"
        f"*মোট রিকোয়েস্ট:* {len(deposits)}\n"
        f"*🟡 অপেক্ষমান:* {len(pending)}",
        call.message.chat.id, call.message.message_id,
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("🔙 Back", callback_data='back_deposit')
        ),
        parse_mode='Markdown'
    )

def handle_admin_deposit_panel(message):
    """Handle admin deposit panel"""
    user_id = message.from_user.id
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    keyboard = create_otp_deposite_keyboard()
    
    bot.reply_to(message, 
        "💳 *DEPOSITE SYSTEM*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *Select an option:*",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

def handle_admin_show_deposits(message):
    """Show pending deposits to owner/admin, including mandatory screenshot."""
    user_id = message.from_user.id
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    pending_deposits = get_pending_deposits()
    if not pending_deposits:
        bot.reply_to(message, "📋 *SHOW ALL DEPOSITE REQUEST*\n━━━━━━━━━━━━━━━━━\n\n📌 *কোনো ডিপোজিট রিকোয়েস্ট নেই!*", parse_mode='Markdown')
        return

    for dep in pending_deposits:
        dep_id, user_id_dep, amount, method, trx_id, created_at, screenshot_file_id = dep
        unit = 'USDT' if str(method).lower() == 'binance' else 'BDT'
        amount_text = f"{amount:.2f} USDT" if unit == 'USDT' else f"৳{amount:.2f}"
        caption = (
            f"📥 *ডিপোজিট #{dep_id}*\n━━━━━━━━━━━━━━━━━\n\n"
            f"👤 *User ID:* `{user_id_dep}`\n"
            f"💰 *Amount:* {amount_text}\n"
            f"📱 *Method:* {method}\n"
            f"🧾 *TrxID:* `{trx_id}`\n"
            f"📅 *Date:* {created_at}\n"
            f"📸 *Screenshot:* {'✅ Attached' if screenshot_file_id else '❌ Missing'}"
        )
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("✅ Approve", callback_data=f'approve_dep_{dep_id}'),
            types.InlineKeyboardButton("❌ Reject", callback_data=f'reject_dep_{dep_id}')
        )
        try:
            if screenshot_file_id:
                bot.send_photo(message.chat.id, screenshot_file_id, caption=caption, reply_markup=keyboard, parse_mode='Markdown')
            else:
                bot.send_message(message.chat.id, caption, reply_markup=keyboard, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to show deposit {dep_id}: {e}")

    back = types.InlineKeyboardMarkup()
    back.add(types.InlineKeyboardButton("🔵 BACK TO ADMIN PANEL", callback_data='back_admin_panel'))
    bot.send_message(message.chat.id, "👇 *উপরের রিকোয়েস্টগুলো Review করুন।*", reply_markup=back, parse_mode='Markdown')

def handle_admin_set_deposit(message):
    """Handle set deposit number and ID"""
    user_id = message.from_user.id
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    msg = bot.reply_to(message, 
        "⚙️ *SET DEPOSIT NUMBER AND ID*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *ফরম্যাট:* `মেথড_নাম: নম্বর/আইডি: ন্যূনতম_পরিমাণ`\n\n"
        "Example:\n"
        "`bKash: 017xxxxxxxx: 10`\n"
        "`Nagad: 017xxxxxxxx: 10`\n"
        "`Binance: binance_pay_id: 0.1`\n\n"
        "💡 *একাধিক মেথড একসাথে দিন*\n"
        "💡 *ন্যূনতম পরিমাণ BDT (Binance এর জন্য USDT)*",
        parse_mode='Markdown'
    )
    register_otp_admin_step_handler(msg, process_admin_set_deposit)

def process_admin_set_deposit(message):
    """Process set deposit number and ID"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    lines = text.split('\n')
    success_count = 0
    
    for line in lines:
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                name = parts[0].strip()
                number = parts[1].strip()
                min_deposit = 10.0
                if len(parts) >= 3:
                    try:
                        min_deposit = float(parts[2].strip())
                    except:
                        pass
                
                if save_payment_method(name, number, min_deposit):
                    success_count += 1
    
    if success_count > 0:
        bot.reply_to(message, 
            f"✅ *{success_count} টি পেমেন্ট মেথড সেট করা হয়েছে!*\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"📌 *সফলভাবে আপডেট করা হয়েছে*",
            parse_mode='Markdown'
        )
    else:
        bot.reply_to(message, 
            "❌ *কোনো মেথড সেট করা হয়নি!*\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "📌 *সঠিক ফরম্যাট ব্যবহার করুন:*\n"
            "`মেথড_নাম: নম্বর/আইডি: ন্যূনতম`",
            parse_mode='Markdown'
        )

# ==================== DELETE PAYMENT METHOD FUNCTIONS ====================

def handle_admin_delete_payment_method(message):
    """Handle delete payment method"""
    user_id = message.from_user.id
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    methods = get_payment_methods()
    if not methods:
        bot.reply_to(message, 
            "❌ *কোনো পেমেন্ট মেথড নেই!*", 
            parse_mode='Markdown'
        )
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for m in methods:
        markup.add(types.InlineKeyboardButton(
            f"🗑️ {m['name']} (Min: {m['min_deposit']})",
            callback_data=f'delete_method_{m["name"]}'
        ))
    markup.add(types.InlineKeyboardButton("🔙 BACK", callback_data='back_deposit_admin'))
    
    bot.reply_to(message, 
        "🗑️ *DELETE PAYMENT METHOD*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *যে মেথড ডিলিট করতে চান সিলেক্ট করুন:*",
        reply_markup=markup,
        parse_mode='Markdown'
    )

def process_delete_payment_method(call):
    """Process delete payment method"""
    user_id = call.from_user.id
    
    if not is_otp_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized!", show_alert=True)
        return
    
    method_name = call.data.split('_')[2]
    
    # কনফার্মেশন চাওয়া
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ হ্যাঁ, ডিলিট করুন", callback_data=f'confirm_delete_method_{method_name}'),
        types.InlineKeyboardButton("❌ না, বাতিল করুন", callback_data='cancel_delete_method')
    )
    
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        f"⚠️ *আপনি কি নিশ্চিত?*\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"📌 *মেথড:* `{method_name}`\n\n"
        f"❌ *এটি ডিলিট করলে আর ফেরত আসবে না!*",
        call.message.chat.id, call.message.message_id,
        reply_markup=markup,
        parse_mode='Markdown'
    )

def process_confirm_delete_method(call):
    """Confirm delete payment method"""
    user_id = call.from_user.id
    
    if not is_otp_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized!", show_alert=True)
        return
    
    method_name = call.data.split('_')[3]
    
    if delete_payment_method(method_name):
        bot.answer_callback_query(call.id, f"✅ {method_name} ডিলিট করা হয়েছে!", show_alert=True)
        bot.edit_message_text(
            f"✅ *পেমেন্ট মেথড ডিলিট করা হয়েছে!*\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"🗑️ *মেথড:* `{method_name}`\n"
            f"✅ *সফলভাবে রিমুভ করা হয়েছে!*",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown'
        )
    else:
        bot.answer_callback_query(call.id, "❌ ডিলিট করতে ব্যর্থ হয়েছে!", show_alert=True)

def process_cancel_delete_method(call):
    """Cancel delete payment method"""
    bot.answer_callback_query(call.id, "❌ ডিলিট বাতিল করা হয়েছে!")
    bot.edit_message_text(
        "❌ *ডিলিট বাতিল করা হয়েছে!*",
        call.message.chat.id, call.message.message_id,
        parse_mode='Markdown'
    )
    # আবার ডিপোজিট প্যানেলে ফেরত যান
    handle_admin_deposit_panel(call.message)

# ==================== END DELETE PAYMENT METHOD FUNCTIONS ====================

def handle_approve_deposit(call):
    """Handle approve deposit from admin"""
    user_id = call.from_user.id
    
    if not is_otp_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized!", show_alert=True)
        return
    
    dep_id = int(call.data.split('_')[2])
    
    success, amount = approve_deposit(dep_id, user_id)
    
    if success:
        bot.answer_callback_query(call.id, f"✅ ডিপোজিট অ্যাপ্রুভ করা হয়েছে! (৳{amount:.2f})", show_alert=True)
        
        # Get deposit details for notification
        conn = db_connect()
        c = conn.cursor()
        c.execute("SELECT user_id, amount, method, trx_id FROM deposits_new WHERE id = ?", (dep_id,))
        dep = c.fetchone()
        conn.close()
        
        if dep:
            target_user = dep[0]
            dep_amount = dep[1]
            method = dep[2]
            trx_id = dep[3]
            
            # Notify user
            try:
                bot.send_message(
                    target_user,
                    f"✅ *আপনার ডিপোজিট অ্যাপ্রুভ করা হয়েছে!*\n"
                    f"━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 *টাকা:* ৳{dep_amount:.2f}\n"
                    f"📱 *মেথড:* {method}\n"
                    f"🧾 *TrxID:* `{trx_id}`\n\n"
                    f"🎉 *আপনার ব্যালেন্স আপডেট করা হয়েছে!*",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify user {target_user}: {e}")
        
        # Update callback message
        try:
            bot.edit_message_text(
                f"✅ *ডিপোজিট অ্যাপ্রুভ করা হয়েছে!*\n"
                f"━━━━━━━━━━━━━━━━━\n\n"
                f"🆔 *আইডি:* `{dep_id}`\n"
                f"💰 *টাকা:* ৳{amount:.2f}\n"
                f"✅ *সফলভাবে অ্যাপ্রুভ করা হয়েছে!*",
                call.message.chat.id, call.message.message_id,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to edit message: {e}")
        
    else:
        bot.answer_callback_query(call.id, "❌ অ্যাপ্রুভ করতে ব্যর্থ হয়েছে!", show_alert=True)

def handle_reject_deposit(call):
    """Handle reject deposit from admin"""
    user_id = call.from_user.id
    
    if not is_otp_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized!", show_alert=True)
        return
    
    dep_id = int(call.data.split('_')[2])
    
    success = reject_deposit(dep_id, user_id)
    
    if success:
        bot.answer_callback_query(call.id, "❌ ডিপোজিট রিজেক্ট করা হয়েছে!", show_alert=True)
        
        # Get deposit details for notification
        conn = db_connect()
        c = conn.cursor()
        c.execute("SELECT user_id, amount, method, trx_id FROM deposits_new WHERE id = ?", (dep_id,))
        dep = c.fetchone()
        conn.close()
        
        if dep:
            target_user = dep[0]
            dep_amount = dep[1]
            method = dep[2]
            
            # Notify user
            try:
                bot.send_message(
                    target_user,
                    f"❌ *আপনার ডিপোজিট রিজেক্ট করা হয়েছে!*\n"
                    f"━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 *টাকা:* ৳{dep_amount:.2f}\n"
                    f"📱 *মেথড:* {method}\n\n"
                    f"😞 *দয়া করে সঠিক তথ্য দিয়ে আবার চেষ্টা করুন*",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify user {target_user}: {e}")
        
        # Update callback message
        try:
            bot.edit_message_text(
                f"❌ *ডিপোজিট রিজেক্ট করা হয়েছে!*\n"
                f"━━━━━━━━━━━━━━━━━\n\n"
                f"🆔 *আইডি:* `{dep_id}`\n"
                f"❌ *সফলভাবে রিজেক্ট করা হয়েছে!*",
                call.message.chat.id, call.message.message_id,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to edit message: {e}")
    else:
        bot.answer_callback_query(call.id, "❌ রিজেক্ট করতে ব্যর্থ হয়েছে!", show_alert=True)

# ==================== END DEPOSIT SYSTEM HANDLERS ====================

# ==================== Premium Plan Functions ====================

def show_all_plans(message):
    """Show all premium plans in a nice list"""
    if not premium_plans:
        bot.reply_to(message, 
            "📋 *প্রিমিয়াম প্লান লিস্ট*\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "📌 *কোনো প্লান যোগ করা নেই!*",
            parse_mode='Markdown'
        )
        return
    
    plan_text = "📋 *প্রিমিয়াম প্লানসমূহ*\n"
    plan_text += "━━━━━━━━━━━━━━━━━\n\n"
    
    for i, plan in enumerate(premium_plans, 1):
        plan_text += f"📌 *প্লান #{i}*\n"
        plan_text += f"   ├ 📁 *ফাইল লিমিট:* {plan['file_limit']}\n"
        plan_text += f"   ├ 📅 *দিন:* {plan['days']}\n"
        plan_text += f"   └ 💰 *মূল্য:* ৳{plan['price']}\n\n"
    
    plan_text += f"📊 *মোট প্লান:* {len(premium_plans)} টি"
    
    bot.reply_to(message, plan_text, parse_mode='Markdown')

def handle_premium_plan_user(message):
    """Handle premium plan for users"""
    user_id = message.from_user.id
    
    if not premium_plans:
        bot.reply_to(message, 
            "❌ *কোনো প্রিমিয়াম প্লান উপলব্ধ নেই!*\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "📌 *অ্যাডমিন প্লান যোগ না করলে কিনতে পারবেন না।*",
            parse_mode='Markdown'
        )
        return
    
    plan_text = "〽️ *প্রিমিয়াম প্লানসমূহ*\n"
    plan_text += "━━━━━━━━━━━━━━━━━\n\n"
    
    for i, plan in enumerate(premium_plans, 1):
        plan_text += f"📌 *প্লান #{i}*\n"
        plan_text += f"   ├ 📁 *ফাইল লিমিট:* {plan['file_limit']}\n"
        plan_text += f"   ├ 📅 *দিন:* {plan['days']}\n"
        plan_text += f"   └ 💰 *মূল্য:* ৳{plan['price']}\n\n"
    
    premium = get_user_premium_plan(user_id)
    if premium and premium["expiry"] > datetime.now():
        plan_text += f"⭐ *আপনার বর্তমান প্লান:*\n"
        plan_text += f"   ├ 📁 লিমিট: {premium['file_limit']} ফাইল\n"
        plan_text += f"   └ 📅 শেষ: {premium['expiry'].strftime('%Y-%m-%d %H:%M')}\n\n"
    
    plan_text += "💡 *প্লান সিলেক্ট করতে নিচের বাটন ব্যবহার করুন:*"
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for plan in premium_plans:
        markup.add(types.InlineKeyboardButton(
            f"📌 প্লান #{plan['id']} - {plan['days']} days - ৳{plan['price']}",
            callback_data=f'buy_plan_{plan["id"]}'
        ))
    markup.add(types.InlineKeyboardButton("🔵 BACK TO MAIN", callback_data='back_to_main'))
    
    bot.reply_to(message, plan_text, reply_markup=markup, parse_mode='Markdown')

def handle_buy_plan(message):
    """Handle buy plan"""
    user_id = message.from_user.id
    
    if not premium_plans:
        bot.reply_to(message, "❌ *কোনো প্লান উপলব্ধ নেই!*", parse_mode='Markdown')
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for plan in premium_plans:
        markup.add(types.InlineKeyboardButton(
            f"📌 প্লান #{plan['id']} - {plan['days']} days - ৳{plan['price']}",
            callback_data=f'buy_plan_{plan["id"]}'
        ))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_premium'))
    
    bot.reply_to(message, 
        "💳 *প্লান সিলেক্ট করুন:*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *আপনি কোন প্লান কিনতে চান?*",
        reply_markup=markup,
        parse_mode='Markdown'
    )

def process_buy_plan(call):
    """Process buy plan with new balance system"""
    user_id = call.from_user.id
    plan_id = int(call.data.split('_')[2])
    
    plan = None
    for p in premium_plans:
        if p["id"] == plan_id:
            plan = p
            break
    
    if not plan:
        bot.answer_callback_query(call.id, "❌ প্লান পাওয়া যায়নি!")
        return
    
    # Check balance from new system
    balance = get_user_balance_db(user_id)
    
    if balance < plan["price"]:
        bot.answer_callback_query(call.id, f"❌ ব্যালেন্স কম! প্রয়োজন: ৳{plan['price']}", show_alert=True)
        return
    
    # Deduct balance
    update_user_balance_db(user_id, -plan["price"])
    
    # Activate premium
    expiry = datetime.now() + timedelta(days=plan["days"])
    save_user_premium_plan(user_id, plan["id"], expiry, plan["file_limit"])
    
    # Update OTP user data balance
    for u in all_users:
        if u["id"] == user_id:
            u["balance"] = get_user_balance_db(user_id)
            break
    
    bot.answer_callback_query(call.id, "✅ প্লান অ্যাক্টিভেটেড!")
    bot.edit_message_text(
        f"🎉 *প্লান সফলভাবে অ্যাক্টিভেটেড!*\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"📁 *ফাইল লিমিট:* {plan['file_limit']} ফাইল\n"
        f"📅 *দিন:* {plan['days']} দিন\n"
        f"💰 *মূল্য:* ৳{plan['price']}\n"
        f"📅 *শেষ তারিখ:* {expiry.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"💰 *বর্তমান ব্যালেন্স:* ৳{get_user_balance_db(user_id):.2f}",
        call.message.chat.id, call.message.message_id,
        parse_mode='Markdown'
    )

def handle_premium_plan_admin(message):
    """Handle premium plan admin"""
    user_id = message.from_user.id
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    bot.reply_to(message, 
        "〽️ *Set Premium Plan for All User* 🌟\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *Select an option:*",
        reply_markup=create_premium_admin_keyboard(),
        parse_mode='Markdown'
    )

def handle_add_premium_plan(message):
    """Handle add premium plan"""
    user_id = message.from_user.id
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    msg = bot.reply_to(message, 
        "➕ *Add Your Premium Plan*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *ফরম্যাট:* `ফাইল_লিমিট দিন মূল্য`\n\n"
        "Example: `100 30 500`\n\n"
        "📁 *ফাইল_লিমিট:* কয়টা ফাইল আপলোড করতে পারবে\n"
        "📅 *দিন:* কত দিন থাকবে\n"
        "💰 *মূল্য:* কত টাকা",
        parse_mode='Markdown'
    )
    register_otp_admin_step_handler(msg, process_add_premium_plan)

def process_add_premium_plan(message):
    """Process add premium plan"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    parts = text.split()
    if len(parts) != 3:
        bot.reply_to(message, 
            "❌ *ভুল ফরম্যাট!*\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "📌 *সঠিক ফরম্যাট:* `ফাইল_লিমিট দিন মূল্য`\n"
            "Example: `100 30 500`\n\n"
            "📁 ফাইল_লিমিট = কয়টা ফাইল আপলোড করতে পারবে\n"
            "📅 দিন = কত দিন থাকবে\n"
            "💰 মূল্য = কত টাকা",
            parse_mode='Markdown'
        )
        return
    
    try:
        file_limit = int(parts[0])
        days = int(parts[1])
        price = int(parts[2])
        
        if file_limit <= 0:
            bot.reply_to(message, "❌ *ফাইল লিমিট ০ এর বেশি হতে হবে!*", parse_mode='Markdown')
            return
        if days <= 0:
            bot.reply_to(message, "❌ *দিন ০ এর বেশি হতে হবে!*", parse_mode='Markdown')
            return
        if price <= 0:
            bot.reply_to(message, "❌ *মূল্য ০ এর বেশি হতে হবে!*", parse_mode='Markdown')
            return
        
        if save_premium_plan(file_limit, days, price):
            show_all_plans(message)
        else:
            bot.reply_to(message, 
                "❌ *প্লান যোগ করতে ব্যর্থ হয়েছে!*\n"
                "━━━━━━━━━━━━━━━━━\n\n"
                "📌 *ডাটাবেজ সংযোগ সমস্যা*\n"
                "💡 *দয়া করে আবার চেষ্টা করুন*",
                parse_mode='Markdown'
            )
            
    except ValueError:
        bot.reply_to(message, 
            "❌ *শুধু সংখ্যা দিন!*\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "📌 *সঠিক ফরম্যাট:* `ফাইল_লিমিট দিন মূল্য`\n"
            "Example: `100 30 500`",
            parse_mode='Markdown'
        )

def handle_remove_premium_plan(message):
    """Handle remove premium plan"""
    user_id = message.from_user.id
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    if not premium_plans:
        bot.reply_to(message, "❌ *কোনো প্লান নেই!*", parse_mode='Markdown')
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for plan in premium_plans:
        markup.add(types.InlineKeyboardButton(
            f"🗑️ প্লান #{plan['id']} - {plan['days']} days - ৳{plan['price']}",
            callback_data=f'remove_plan_{plan["id"]}'
        ))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_premium_admin'))
    
    bot.reply_to(message, 
        "🗑️ *Remove Plan*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *যে প্লান রিমুভ করতে চান সিলেক্ট করুন:*",
        reply_markup=markup,
        parse_mode='Markdown'
    )

def process_remove_plan(call):
    """Process remove plan"""
    user_id = call.from_user.id
    plan_id = int(call.data.split('_')[2])
    
    if not is_otp_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized!", show_alert=True)
        return
    
    if remove_premium_plan(plan_id):
        bot.answer_callback_query(call.id, "✅ প্লান রিমুভ করা হয়েছে!")
        bot.edit_message_text(
            f"✅ *প্লান রিমুভ করা হয়েছে!*\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"🗑️ প্লান আইডি: `{plan_id}`\n\n"
            f"✅ *সফলভাবে রিমুভ করা হয়েছে!*",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown'
        )
        show_all_plans(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ রিমুভ করতে ব্যর্থ হয়েছে!", show_alert=True)

# --- Reset All Plans Functions ---
def handle_reset_all_plans(message):
    """Handle reset all premium plans"""
    user_id = message.from_user.id
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("✅ হ্যাঁ, রিসেট করুন", callback_data='confirm_reset_plans'),
        types.InlineKeyboardButton("❌ না, বাতিল করুন", callback_data='cancel_reset_plans')
    )
    
    bot.reply_to(message, 
        "⚠️ *সব প্রিমিয়াম প্লান রিসেট করতে চান?*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"📊 *বর্তমানে {len(premium_plans)} টি প্লান আছে*\n\n"
        "❌ *রিসেট করলে সব প্লান ডিলিট হয়ে যাবে!*\n"
        "✅ *এরপর নতুন প্লান যোগ করতে পারবেন*\n\n"
        "💡 *আপনি কি নিশ্চিত?*",
        reply_markup=markup,
        parse_mode='Markdown'
    )

def process_reset_plans(call):
    """Process reset all plans"""
    user_id = call.from_user.id
    
    if not is_otp_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized!", show_alert=True)
        return
    
    try:
        if reset_all_plans():
            bot.answer_callback_query(call.id, "✅ সব প্লান রিসেট করা হয়েছে!")
            bot.edit_message_text(
                "✅ *সব প্রিমিয়াম প্লান রিসেট করা হয়েছে!*\n"
                "━━━━━━━━━━━━━━━━━\n\n"
                "📌 *এখন নতুন প্লান যোগ করলে আইডি ১ থেকে শুরু হবে*\n\n"
                "💡 *প্লান যোগ করতে '🟢 Add Your Premium Plan' বাটনে ক্লিক করুন*",
                call.message.chat.id, call.message.message_id,
                parse_mode='Markdown'
            )
            logger.info(f"✅ All plans reset by Admin {user_id}")
        else:
            bot.answer_callback_query(call.id, "❌ রিসেট করতে ব্যর্থ হয়েছে!", show_alert=True)
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ রিসেট করতে ব্যর্থ হয়েছে!", show_alert=True)
        logger.error(f"❌ Error resetting plans: {e}")

def process_cancel_reset(call):
    """Process cancel reset"""
    bot.answer_callback_query(call.id, "❌ রিসেট বাতিল করা হয়েছে!")
    bot.edit_message_text(
        "❌ *রিসেট বাতিল করা হয়েছে!*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *আপনার প্লান নিরাপদ আছে*",
        call.message.chat.id, call.message.message_id,
        parse_mode='Markdown'
    )
    handle_premium_plan_admin(call.message)


# ==================== FORCE JOIN SYSTEM ====================

FORCE_JOIN_DEFAULT_CHANNEL = "@RakibCryptoTech"

def get_force_join_setting(key, default=""):
    try:
        with DB_LOCK:
            conn = db_connect()
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            conn.close()
        return row[0] if row else default
    except Exception as e:
        logger.error(f"Force Join setting read error: {e}")
        return default

def set_force_join_setting(key, value):
    try:
        with DB_LOCK:
            conn = db_connect()
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value))
            )
            conn.commit()
            conn.close()
        return True
    except Exception as e:
        logger.error(f"Force Join setting save error: {e}", exc_info=True)
        return False

def force_join_enabled():
    return get_force_join_setting("force_join_enabled", "0") == "1"

def force_join_channel():
    return get_force_join_setting("force_join_channel", FORCE_JOIN_DEFAULT_CHANNEL) or FORCE_JOIN_DEFAULT_CHANNEL

def normalize_force_join_channel(value):
    value = value.strip()
    if value.startswith("https://t.me/"):
        value = "@" + value.split("https://t.me/", 1)[1].split("/", 1)[0].split("?", 1)[0]
    elif value.startswith("http://t.me/"):
        value = "@" + value.split("http://t.me/", 1)[1].split("/", 1)[0].split("?", 1)[0]
    elif value.startswith("t.me/"):
        value = "@" + value.split("t.me/", 1)[1].split("/", 1)[0].split("?", 1)[0]
    elif not value.startswith("@") and not value.startswith("-100"):
        value = "@" + value
    return value

def check_force_join(user_id):
    if user_id == OWNER_ID or user_id in admin_ids or user_id in admin_list:
        return True, force_join_channel()
    if not force_join_enabled():
        return True, force_join_channel()

    channel = force_join_channel()
    try:
        member = bot.get_chat_member(channel, user_id)
        allowed_statuses = {"member", "administrator", "creator", "restricted"}
        return member.status in allowed_statuses, channel
    except Exception as e:
        logger.warning(f"Force Join membership check failed for {user_id} in {channel}: {e}")
        return False, channel

def force_join_message(chat_id):
    channel = force_join_channel()
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("📢 JOIN CHANNEL", url=f"https://t.me/{channel.lstrip('@')}"))
    markup.add(types.InlineKeyboardButton("✅ VERIFY", callback_data="force_join_verify"))
    bot.send_message(
        chat_id,
        "🔒 *Force Join Required*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📢 আগে আমাদের Channel-এ Join করুন।\n"
        "তারপর নিচের *VERIFY* বাটনে চাপুন।",
        reply_markup=markup,
        parse_mode="Markdown"
    )

def require_force_join(message):
    allowed, _ = check_force_join(message.from_user.id)
    if not allowed:
        force_join_message(message.chat.id)
        return False
    return True

def create_force_join_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        create_styled_keyboard_button("FORCE JOIN ON"),
        create_styled_keyboard_button("FORCE JOIN OFF")
    )
    markup.add(create_styled_keyboard_button("SET FORCE JOIN CHANNEL"))
    markup.add(create_styled_keyboard_button("BACK TO ADMIN PANEL"))
    return markup

def show_force_join_admin(message):
    if not is_otp_admin(message.from_user.id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode="Markdown")
        return
    status = "🟢 ON" if force_join_enabled() else "🔴 OFF"
    channel = force_join_channel()
    bot.reply_to(
        message,
        f"📢 *FORCE JOIN SETTINGS*\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"📌 *Status:* {status}\n"
        f"📢 *Channel:* `{channel}`\n\n"
        f"Select an option:",
        reply_markup=create_force_join_admin_keyboard(),
        parse_mode="Markdown"
    )

def process_force_join_channel(message):
    if not is_otp_admin(message.from_user.id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode="Markdown")
        return
    if not message.text:
        bot.reply_to(message, "❌ Invalid channel.")
        return
    if message.text.strip().lower() == "/cancel":
        show_force_join_admin(message)
        return

    value = normalize_force_join_channel(message.text)
    if not (value.startswith("@") or value.startswith("-100")):
        bot.reply_to(message, "❌ *Invalid channel username/link!*\nExample: `@RakibCryptoTech`", parse_mode="Markdown")
        return

    if set_force_join_setting("force_join_channel", value):
        bot.reply_to(message, f"✅ *Force Join channel saved:* `{value}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Could not save channel.")
    show_force_join_admin(message)

# ==================== END FORCE JOIN SYSTEM ====================

# ==================== OTP Admin Functions ====================

def handle_otp_admin_panel(message):
    """Handle OTP admin panel"""
    user_id = message.from_user.id

    # Always cancel any pending OTP-admin input when opening the panel.
    # This prevents an old next-step handler from capturing menu buttons.
    try:
        bot.clear_step_handler_by_chat_id(message.chat.id)
    except Exception as e:
        logger.debug(f"Could not clear pending step handler: {e}")
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    markup = create_otp_reply_keyboard(user_id)
    bot.reply_to(message, 
        "🔴 *Rakib Admin Panel* 🤡\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "✅ *Welcome Admin!*\n"
        "✅ *You have full access to bot controls.*\n\n"
        "📌 *Select an option:*",
        reply_markup=markup,
        parse_mode='Markdown'
    )

def handle_otp_admin_list(message):
    """Handle admin list menu"""
    user_id = message.from_user.id    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    bot.reply_to(message, 
        "👑 *ADMIN LIST*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *Select an option:*",
        reply_markup=create_otp_admin_list_keyboard(),
        parse_mode='Markdown'
    )

def handle_otp_add_admin(message):
    """Handle add admin input"""
    user_id = message.from_user.id
    
    if user_id != OWNER_ID:
        bot.reply_to(message, "⛔ *Only Owner Can Add Admin!*", parse_mode='Markdown')
        return
    
    msg = bot.reply_to(message, 
        "➕ *Add Admin*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *Send the User ID to add as admin:*",
        parse_mode='Markdown'
    )
    register_otp_admin_step_handler(msg, process_otp_add_admin)

def process_otp_add_admin(message):
    """Process add admin"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    if not text.isdigit():
        bot.reply_to(message, "❌ *Invalid User ID!*", parse_mode='Markdown')
        return
    
    target_user = int(text)
    
    if target_user in admin_list:
        bot.reply_to(message, f"⚠️ *User `{target_user}` is already an admin!*", parse_mode='Markdown')
        return
    
    admin_list.append(target_user)
    bot.reply_to(message, 
        f"✅ *Admin Added!*\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"👤 User ID: `{target_user}`\n"
        f"✅ *সফলভাবে অ্যাডমিন যোগ করা হয়েছে!*",
        parse_mode='Markdown'
    )

def handle_otp_remove_admin(message):
    """Handle remove admin input"""
    user_id = message.from_user.id
    
    if user_id != OWNER_ID:
        bot.reply_to(message, "⛔ *Only Owner Can Remove Admin!*", parse_mode='Markdown')
        return
    
    msg = bot.reply_to(message, 
        "➖ *Remove Admin*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *Send the User ID to remove from admin:*",
        parse_mode='Markdown'
    )
    register_otp_admin_step_handler(msg, process_otp_remove_admin)

def process_otp_remove_admin(message):
    """Process remove admin"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    if not text.isdigit():
        bot.reply_to(message, "❌ *Invalid User ID!*", parse_mode='Markdown')
        return
    
    target_user = int(text)
    
    if target_user == OWNER_ID:
        bot.reply_to(message, "❌ *Cannot remove Owner!*", parse_mode='Markdown')
        return
    
    if target_user not in admin_list:
        bot.reply_to(message, f"⚠️ *User `{target_user}` is not an admin!*", parse_mode='Markdown')
        return
    
    admin_list.remove(target_user)
    bot.reply_to(message, 
        f"✅ *Admin Removed!*\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"👤 User ID: `{target_user}`\n"
        f"✅ *সফলভাবে অ্যাডমিন রিমুভ করা হয়েছে!*",
        parse_mode='Markdown'
    )

def handle_otp_transfer_ownership(message):
    """Handle transfer ownership input"""
    user_id = message.from_user.id
    
    if user_id != OWNER_ID:
        bot.reply_to(message, "⛔ *Only Owner Can Transfer Ownership!*", parse_mode='Markdown')
        return
    
    msg = bot.reply_to(message, 
        "👑 *Transfer Ownership*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *Send the User ID to transfer ownership:*\n\n"
        "⚠️ *Warning: After transfer, you will lose Owner access!*",
        parse_mode='Markdown'
    )
    register_otp_admin_step_handler(msg, process_otp_transfer_ownership)

def process_otp_transfer_ownership(message):
    """Process transfer ownership"""
    global OWNER_ID
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    if not text.isdigit():
        bot.reply_to(message, "❌ *Invalid User ID!*", parse_mode='Markdown')
        return
    
    target_user = int(text)
    
    if target_user == OWNER_ID:
        bot.reply_to(message, "⚠️ *You are already the Owner!*", parse_mode='Markdown')
        return
    
    old_owner = OWNER_ID
    OWNER_ID = target_user
    
    if old_owner not in admin_list:
        admin_list.append(old_owner)
    
    bot.reply_to(message, 
        f"👑 *Ownership Transferred!*\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"✅ New Owner: `{target_user}`\n"
        f"✅ *সফলভাবে ওনারশিপ ট্রান্সফার করা হয়েছে!*",
        parse_mode='Markdown'
    )

def handle_otp_show_all_admins(message):
    """Show all admins"""
    user_id = message.from_user.id
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    if not admin_list:
        bot.reply_to(message, "📌 *কোনো অ্যাডমিন নেই!*", parse_mode='Markdown')
        return
    
    admin_show_list = ""
    for i, uid in enumerate(admin_list, 1):
        user_name = "Unknown"
        username = "@unknown"
        for user in all_users:
            if user["id"] == uid:
                user_name = user["name"]
                username = user["username"]
                break
        
        role = "👑 OWNER" if uid == OWNER_ID else "🔹 ADMIN"
        admin_show_list += f"{i}. *{user_name}*\n"
        admin_show_list += f"   🆔 User ID: `{uid}`\n"
        admin_show_list += f"   📌 {username}\n"
        admin_show_list += f"   👑 {role}\n\n"
    
    bot.reply_to(message, 
        f"📋 *ALL ADMINS*\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"{admin_show_list}"
        f"*Total Admins:* {len(admin_list)}",
        parse_mode='Markdown'
    )

def handle_otp_set_limit(message):
    """Handle set limit input"""
    user_id = message.from_user.id
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    msg = bot.reply_to(message, 
        "⚙️ *SET LIMIT*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *Send the User ID to set limit:*\n\n"
        "Example: `123456789`",
        parse_mode='Markdown'
    )
    register_otp_admin_step_handler(msg, process_otp_set_limit_user)

def process_otp_set_limit_user(message):
    """Process set limit user ID"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    if not text.isdigit():
        bot.reply_to(message, "❌ *Invalid User ID!*", parse_mode='Markdown')
        return
    
    target_user = int(text)
    
    msg = bot.reply_to(message, 
        f"⚙️ *SET LIMIT*\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *User ID:* `{target_user}`\n\n"
        f"📌 *Send the file limit for this user:*\n\n"
        f"Example: `10` (শুধু সংখ্যা)\n"
        f"💡 *0 = সীমাহীন*",
        parse_mode='Markdown'
    )
    register_otp_admin_step_handler(msg, lambda m: process_otp_set_limit_value(m, target_user))

def process_otp_set_limit_value(message, target_user):
    """Process set limit value"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    if not text.isdigit():
        bot.reply_to(message, "❌ *শুধু সংখ্যা লিখুন!*", parse_mode='Markdown')
        return
    
    limit_value = int(text)
    
    if limit_value == 0:
        if target_user in user_limits:
            del user_limits[target_user]
        limit_text = "সীমাহীন"
    else:
        user_limits[target_user] = limit_value
        limit_text = str(limit_value)
    
    bot.reply_to(message, 
        f"✅ *Limit Set Successfully!*\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *User ID:* `{target_user}`\n"
        f"📊 *File Limit:* {limit_text}\n\n"
        f"✅ *সফলভাবে লিমিট সেট করা হয়েছে!*",
        parse_mode='Markdown'
    )

def handle_otp_set_free_user_limit(message):
    """Handle set free user limit input"""
    user_id = message.from_user.id
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    msg = bot.reply_to(message, 
        "⚙️ *SET FREE USER LIMIT*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *সব ফ্রি ইউজারের জন্য সেটিংস সেট করুন*\n\n"
        "📤 *ফরম্যাট:* `লিমিট ঘন্টা হোস্ট_সময়`\n"
        "Example: `10 24 48`\n"
        "`0 0 0` = Unlimited bots + Unlimited host time\n\n"
        "📁 *লিমিট = ফাইল সংখ্যা* (কয়টা ফাইল আপলোড করতে পারবে)\n"
        "⏰ *ঘন্টা = টাইম লিমিট* (কত ঘন্টার মধ্যে আপলোড করতে পারবে)\n"
        "⏳ *হোস্ট_সময় = ফাইল কত ঘন্টা হোস্ট থাকবে*\n\n"
        f"📊 *বর্তমান সেটিংস:*\n"
        f"📁 লিমিট: {'Unlimited' if FREE_USER_LIMIT_SETTINGS['limit'] == 0 else FREE_USER_LIMIT_SETTINGS['limit']} ফাইল\n"
        f"⏰ টাইম: {FREE_USER_LIMIT_SETTINGS['time']} ঘন্টা\n"
        f"⏳ হোস্ট সময়: {'Unlimited' if FREE_USER_LIMIT_SETTINGS['host_time'] == 0 else FREE_USER_LIMIT_SETTINGS['host_time']} ঘন্টা",
        parse_mode='Markdown'
    )
    register_otp_admin_step_handler(msg, process_otp_set_free_user_limit)

def process_otp_set_free_user_limit(message):
    """Process set free user limit"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    parts = text.split()
    if len(parts) != 3:
        bot.reply_to(message, 
            "❌ *ভুল ফরম্যাট!*\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "📌 *সঠিক ফরম্যাট:* `লিমিট ঘন্টা হোস্ট_সময়`\n"
            "Example: `10 24 48`\n"
            "`0 0 0` = Unlimited bots + Unlimited host time",
            parse_mode='Markdown'
        )
        return
    
    if not parts[0].isdigit() or not parts[1].isdigit() or not parts[2].isdigit():
        bot.reply_to(message, 
            "❌ *শুধু সংখ্যা দিন!*\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "📌 *সঠিক ফরম্যাট:* `লিমিট ঘন্টা হোস্ট_সময়`",
            parse_mode='Markdown'
        )
        return
    
    limit_value = int(parts[0])
    time_value = int(parts[1])
    host_time = int(parts[2])
    
    if limit_value < 0 or time_value < 0 or host_time < 0:
        bot.reply_to(message, "❌ *মান ০ এর কম হতে পারে না!*", parse_mode='Markdown')
        return
    
    if save_free_user_settings(limit_value, time_value, host_time):
        bot.reply_to(message, 
            f"✅ *FREE USER LIMIT SET SUCCESSFULLY!*\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"📁 *ফাইল/বট লিমিট:* {'Unlimited' if limit_value == 0 else str(limit_value) + ' ফাইল'}\n"
            f"⏰ *টাইম লিমিট:* {'Unlimited' if time_value == 0 else str(time_value) + ' ঘন্টা'}\n"
            f"⏳ *হোস্ট সময়:* {'Unlimited' if host_time == 0 else str(host_time) + ' ঘন্টা'}\n\n"
            f"✅ *সব ফ্রি ইউজারের জন্য আপডেট করা হয়েছে!*",
            parse_mode='Markdown'
        )
    else:
        bot.reply_to(message, "❌ *সেটিংস সংরক্ষণ করতে ব্যর্থ হয়েছে!*", parse_mode='Markdown')

def register_otp_admin_step_handler(message, callback):
    """Register OTP admin input handler while keeping BACK TO ADMIN PANEL available."""
    def wrapped(next_message):
        if (next_message.text or "").strip() == "BACK TO ADMIN PANEL":
            handle_otp_back_to_admin_panel(next_message)
            return
        callback(next_message)
    bot.register_next_step_handler(message, wrapped)

def handle_otp_back_to_admin_panel(message):
    """Return to the OTP/Rakib Admin Panel from any admin submenu."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return

    # A pending next-step handler can consume the button message before the
    # normal message handlers run. Always cancel it first.
    try:
        bot.clear_step_handler_by_chat_id(chat_id)
    except Exception as e:
        logger.debug(f"Could not clear pending step handler: {e}")

    # BACK TO ADMIN PANEL must return to the original/main Admin menu,
    # not reopen the Rakib Admin Panel submenu.
    go_back_to_main(message)
def go_back_to_main(message):
    """Go back to main menu"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    markup = create_reply_keyboard_main_menu(user_id)
    
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    expiry_info = ""
    if user_id == OWNER_ID: user_status = "👑 Owner"
    elif user_id in admin_ids: user_status = "🛡️ Admin"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            user_status = "⭐ Premium"; days_left = (expiry_date - datetime.now()).days
            expiry_info = f"\n⏳ Subscription expires in: {days_left} days"
        else: user_status = "🆓 Free User (Expired Sub)"
    else: user_status = "🆓 Free User"
    
    balance = get_user_balance_db(user_id)
    
    welcome_msg_text = (f"〽️ Welcome back!\n\n🆔 Your User ID: `{user_id}`\n"
                        f"✳️ Username: `@{message.from_user.username or 'Not set'}`\n"
                        f"🔰 Your Status: {user_status}{expiry_info}\n"
                        f"💰 Balance: ৳{balance:.2f}\n"
                        f"📁 Files Uploaded: {current_files} / {limit_str}\n\n"
                        f"🤖 Host & run Python (`.py`) or JS (`.js`) scripts.\n"
                        f"   Upload single scripts or `.zip` archives.\n\n"
                        f"👇 Use buttons or type commands.")
    
    bot.send_message(chat_id, welcome_msg_text, reply_markup=markup, parse_mode='Markdown')

# --- Running All Code Function (Enhanced) ---
def _logic_run_all_scripts(message_or_call):
    """Show all scripts with status and user info"""
    if isinstance(message_or_call, telebot.types.Message):
        admin_user_id = message_or_call.from_user.id
        admin_chat_id = message_or_call.chat.id
        reply_func = lambda text, **kwargs: bot.reply_to(message_or_call, text, **kwargs)
    elif isinstance(message_or_call, telebot.types.CallbackQuery):
        admin_user_id = message_or_call.from_user.id
        admin_chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
        reply_func = lambda text, **kwargs: bot.send_message(admin_chat_id, text, **kwargs)
    else:
        logger.error("Invalid argument for _logic_run_all_scripts")
        return

    if admin_user_id not in admin_ids:
        reply_func("⚠️ Admin permissions required.")
        return

    reply_func("🟢 *Checking all scripts...*\n━━━━━━━━━━━━━━━━━")
    logger.info(f"Admin {admin_user_id} checked all scripts from chat {admin_chat_id}.")

    total_files = 0
    running_files = 0
    stopped_files = 0
    script_list = ""

    all_user_files_snapshot = dict(user_files)

    for target_user_id, files_for_user in all_user_files_snapshot.items():
        if not files_for_user: continue
        
        username = "Unknown"
        try:
            user_info = bot.get_chat(target_user_id)
            username = user_info.username or user_info.first_name or "Unknown"
        except:
            pass
        
        premium = get_user_premium_plan(target_user_id)
        is_premium = premium and premium["expiry"] > datetime.now()
        
        for file_name, file_type in files_for_user:
            total_files += 1
            is_running = is_bot_running(target_user_id, file_name)
            is_stopped = target_user_id in file_stop_status and file_name in file_stop_status[target_user_id]
            
            if is_stopped:
                status = "⏹️ Stopped"
                stopped_files += 1
            elif is_running:
                status = "🟢 Running"
                running_files += 1
            else:
                status = "🔴 Stopped"
                stopped_files += 1
            
            script_list += f"📄 `{file_name}` ({file_type})\n"
            script_list += f"   👤 User: `{target_user_id}` (@{username})\n"
            script_list += f"   📌 Status: {status}"
            if is_premium:
                script_list += f" ⭐"
            script_list += f"\n\n"

    if total_files == 0:
        script_list = "📌 *No scripts found in the system.*"

    summary_msg = (f"🟢 *ALL SCRIPTS STATUS*\n"
                   f"━━━━━━━━━━━━━━━━━\n\n"
                   f"📊 *Total Scripts:* {total_files}\n"
                   f"🟢 *Running:* {running_files}\n"
                   f"🔴 *Stopped:* {stopped_files}\n\n"
                   f"📋 *Script Details:*\n"
                   f"━━━━━━━━━━━━━━━━━\n\n"
                   f"{script_list}")

    reply_func(summary_msg, parse_mode='Markdown')
    logger.info(f"All scripts checked. Total: {total_files}, Running: {running_files}, Stopped: {stopped_files}")

# --- Logic Functions ---
def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    user_username = message.from_user.username

    logger.info(f"Welcome request from user_id: {user_id}, username: @{user_username}")

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ Bot locked by admin. Try later.")
        return
    
    add_otp_user(user_id, user_name, user_username)

    user_bio = "Could not fetch bio"; photo_file_id = None
    try: user_bio = bot.get_chat(user_id).bio or "No bio"
    except Exception: pass
    try:
        user_profile_photos = bot.get_user_profile_photos(user_id, limit=1)
        if user_profile_photos.photos: photo_file_id = user_profile_photos.photos[0][-1].file_id
    except Exception: pass

    if user_id not in active_users:
        add_active_user(user_id)
        try:
            owner_notification = (f"🎉 New user!\n👤 Name: {user_name}\n✳️ User: @{user_username or 'N/A'}\n"
                                  f"🆔 ID: `{user_id}`\n📝 Bio: {user_bio}")
            bot.send_message(OWNER_ID, owner_notification, parse_mode='Markdown')
            if photo_file_id: bot.send_photo(OWNER_ID, photo_file_id, caption=f"Pic of new user {user_id}")
        except Exception as e: logger.error(f"⚠️ Failed to notify owner about new user {user_id}: {e}")

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    expiry_info = ""
    
    premium = get_user_premium_plan(user_id)
    if premium and premium["expiry"] > datetime.now():
        user_status = "⭐ Premium"
        days_left = (premium["expiry"] - datetime.now()).days
        expiry_info = f"\n⏳ Premium expires in: {days_left} days"
    elif user_id == OWNER_ID:
        user_status = "👑 Owner"
    elif user_id in admin_ids:
        user_status = "🛡️ Admin"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            user_status = "⭐ Premium"; days_left = (expiry_date - datetime.now()).days
            expiry_info = f"\n⏳ Subscription expires in: {days_left} days"
        else: user_status = "🆓 Free User (Expired Sub)"; remove_subscription_db(user_id)
    else: user_status = "🆓 Free User"
    
    balance = get_user_balance_db(user_id)

    welcome_msg_text = (f"〽️ Welcome, {user_name}!\n\n🆔 Your User ID: `{user_id}`\n"
                        f"✳️ Username: `@{user_username or 'Not set'}`\n"
                        f"🔰 Your Status: {user_status}{expiry_info}\n"
                        f"💰 Balance: ৳{balance:.2f}\n"
                        f"📁 Files Uploaded: {current_files} / {limit_str}\n"
                        f"⏰ Host Time: {'Unlimited' if get_user_host_time(user_id) == float('inf') else str(get_user_host_time(user_id)) + ' hours'}\n\n"
                        f"🤖 Host & run Python (`.py`) or JS (`.js`) scripts.\n"
                        f"   Upload single scripts or `.zip` archives.\n\n"
                        f"👇 Use buttons or type commands.")
    
    markup = create_reply_keyboard_main_menu(user_id)
    
    try:
        if photo_file_id: bot.send_photo(chat_id, photo_file_id)
        bot.send_message(chat_id, welcome_msg_text, reply_markup=markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error sending welcome to {user_id}: {e}", exc_info=True)
        try: bot.send_message(chat_id, welcome_msg_text, reply_markup=markup, parse_mode='Markdown')
        except Exception as fallback_e: logger.error(f"Fallback send_message failed for {user_id}: {fallback_e}")

def _logic_updates_channel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL))
    bot.reply_to(message, "Visit our Updates Channel:", reply_markup=markup)

def _logic_support(message):
    support_url = get_setting('support_url').strip()
    if not support_url:
        bot.reply_to(message, "❌ *Support link এখনো অ্যাডমিন সেট করেনি।*", parse_mode='Markdown')
        return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('🆘 Support', url=support_url))
    bot.reply_to(message, "🆘 *Support এ যোগাযোগ করতে নিচের বাটনে ক্লিক করুন:*", reply_markup=markup, parse_mode='Markdown')

def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked by admin, cannot accept files.")
        return

    if user_id not in admin_ids and user_id != OWNER_ID:
        upload_count = get_user_upload_count_in_time(user_id)
        file_limit = get_user_file_limit(user_id)
        
        if file_limit != float("inf") and upload_count >= file_limit:
            bot.reply_to(message, 
                f"❌ *আপনার ফাইল আপলোড লিমিট শেষ হয়েছে!*\n"
                f"━━━━━━━━━━━━━━━━━\n\n"
                f"📁 *আপনি {file_limit} টি ফাইল আপলোড করতে পারবেন*\n"
                f"⏰ *সময়: {FREE_USER_LIMIT_SETTINGS['time']} ঘন্টা*\n\n"
                f"💡 *প্রিমিয়াম কিনতে ডিপোজিট করে প্রিমিয়াম প্লান কিনুন।*\n"
                f"〽️ *প্রিমিয়াম প্লান 🌟* বাটনে ক্লিক করুন।",
                parse_mode='Markdown'
            )
            return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, 
            f"⚠️ *ফাইল লিমিট শেষ!*\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"📁 *আপনি {current_files}/{limit_str} ফাইল আপলোড করেছেন*\n\n"
            f"💡 *প্রিমিয়াম কিনতে ডিপোজিট করে প্রিমিয়াম প্লান কিনুন।*",
            parse_mode='Markdown'
        )
        return
    bot.reply_to(message, "📤 Send your Python (`.py`), JS (`.js`), or ZIP (`.zip`) file.")

def _logic_check_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.reply_to(message, "📂 Your files:\n\n(No files uploaded yet)")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        is_stopped = user_id in file_stop_status and file_name in file_stop_status[user_id]
        
        if is_stopped:
            status_icon = "⏹️ Stopped"
        elif is_running:
            status_icon = "🟢 Running"
        else:
            status_icon = "🔴 Stopped"
            
        btn_text = f"{file_name} ({file_type}) - {status_icon}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))
    bot.reply_to(message, "📂 Your files:\nClick to manage.", reply_markup=markup, parse_mode='Markdown')

def _logic_bot_speed(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    start_time_ping = time.time()
    wait_msg = bot.reply_to(message, "🏃 Testing speed...")
    try:
        bot.send_chat_action(chat_id, 'typing')
        response_time = round((time.time() - start_time_ping) * 1000, 2)
        status = "🔓 Unlocked" if not bot_locked else "🔒 Locked"
        if user_id == OWNER_ID: user_level = "👑 Owner"
        elif user_id in admin_ids: user_level = "🛡️ Admin"
        elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now(): user_level = "⭐ Premium"
        else: user_level = "🆓 Free User"
        speed_msg = (f"⚡ Bot Speed & Status:\n\n⏱️ API Response Time: {response_time} ms\n"
                     f"🚦 Bot Status: {status}\n"
                     f"👤 Your Level: {user_level}")
        bot.edit_message_text(speed_msg, chat_id, wait_msg.message_id)
    except Exception as e:
        logger.error(f"Error during speed test (cmd): {e}", exc_info=True)
        bot.edit_message_text("❌ Error during speed test.", chat_id, wait_msg.message_id)

def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    bot.reply_to(message, "Click to contact Owner:", reply_markup=markup)

def _logic_subscriptions_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    bot.reply_to(message, "💳 Subscription Management\nUse inline buttons from /start or admin command menu.", reply_markup=create_subscription_menu())

def _logic_statistics(message):
    user_id = message.from_user.id
    total_users = len(active_users)
    total_files_records = sum(len(files) for files in user_files.values())

    running_bots_count = 0
    user_running_bots = 0

    for script_key_iter, script_info_iter in list(bot_scripts.items()):
        s_owner_id, _ = script_key_iter.split('_', 1)
        if is_bot_running(int(s_owner_id), script_info_iter['file_name']):
            running_bots_count += 1
            if int(s_owner_id) == user_id:
                user_running_bots +=1

    stats_msg_base = (f"📊 Bot Statistics:\n\n"
                      f"👥 Total Users: {total_users}\n"
                      f"📂 Total File Records: {total_files_records}\n"
                      f"🟢 Total Active Bots: {running_bots_count}\n")

    if user_id in admin_ids:
        stats_msg_admin = (f"🔒 Bot Status: {'🔴 Locked' if bot_locked else '🟢 Unlocked'}\n"
                           f"🤖 Your Running Bots: {user_running_bots}")
        stats_msg = stats_msg_base + stats_msg_admin
    else:
        stats_msg = stats_msg_base + f"🤖 Your Running Bots: {user_running_bots}"

    bot.reply_to(message, stats_msg)

def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    global bot_locked
    bot_locked = not bot_locked
    status = "locked" if bot_locked else "unlocked"
    logger.warning(f"Bot {status} by Admin {message.from_user.id} via command/button.")
    bot.reply_to(message, f"🔒 Bot has been {status}.")


@bot.message_handler(func=lambda message: message.text in [
    "FORCE JOIN ON",
    "FORCE JOIN OFF",
    "SET FORCE JOIN CHANNEL"
])
def handle_force_join_admin_buttons(message):
    user_id = message.from_user.id
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode="Markdown")
        return

    if message.text == "FORCE JOIN ON":
        if set_force_join_setting("force_join_enabled", "1"):
            bot.reply_to(message, f"✅ *Force Join ON*\n📢 Channel: `{force_join_channel()}`", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Could not enable Force Join.")
        show_force_join_admin(message)

    elif message.text == "FORCE JOIN OFF":
        if set_force_join_setting("force_join_enabled", "0"):
            bot.reply_to(message, "✅ *Force Join OFF*", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Could not disable Force Join.")
        show_force_join_admin(message)

    elif message.text == "SET FORCE JOIN CHANNEL":
        msg = bot.reply_to(
            message,
            "📢 *Send Channel username or link*\n\n"
            "Example:\n"
            "`@RakibCryptoTech`\n"
            "or\n"
            "`https://t.me/RakibCryptoTech`\n\n"
            "Cancel: `/cancel`",
            parse_mode="Markdown"
        )
        register_otp_admin_step_handler(msg, process_force_join_channel)

# --- Command Handlers ---
@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message):
    if not require_force_join(message):
        return
    _logic_send_welcome(message)

@bot.message_handler(commands=['status'])
def command_show_status(message): _logic_statistics(message)

BUTTON_TEXT_TO_LOGIC = {
    "UPDATES CHANNEL": _logic_updates_channel,
    "UPLOAD FILE": _logic_upload_file,
    "CHECK FILES": _logic_check_files,
    "BOT SPEED": _logic_bot_speed,
    "CONTACT OWNER": _logic_contact_owner,
    "STATISTICS": _logic_statistics,
    "SUBSCRIPTIONS": _logic_subscriptions_panel,
    "LOCK BOT": _logic_toggle_lock_bot,
    "RUNNING ALL CODE": _logic_run_all_scripts,
}

@bot.message_handler(func=lambda message: message.text in BUTTON_TEXT_TO_LOGIC)
def handle_button_text(message):
    if not require_force_join(message):
        return
    logic_func = BUTTON_TEXT_TO_LOGIC.get(message.text)
    if logic_func: logic_func(message)
    else: logger.warning(f"Button text '{message.text}' matched but no logic func.")

# --- User Bengali Button Handlers ---
@bot.message_handler(func=lambda message: message.text in [
    "💎 আপডেট চ্যানেল",
    "💎 ফাইল আপলোড করুন",
    "💎 ফাইল দেখুন",
    "💎 সাপোর্ট"
])
def handle_user_bengali_buttons(message):
    text = message.text
    
    if text == "💎 আপডেট চ্যানেল":
        _logic_updates_channel(message)
    elif text == "💎 ফাইল আপলোড করুন":
        _logic_upload_file(message)
    elif text == "💎 ফাইল দেখুন":
        _logic_check_files(message)
    elif text == "💎 সাপোর্ট":
        _logic_support(message)

# --- OTP GURU Button Handlers ---
@bot.message_handler(func=lambda message: message.text in [
    "Rakib Admin Panel",
    "BACK TO ADMIN PANEL",
    "আমার প্রোফাইল", "ডিপোজিট", "প্রিমিয়াম প্লান 🌟",
    "💎 আমার প্রোফাইল", "💎 ডিপোজিট", "💎 প্রিমিয়াম প্লান 🌟",
    "BACK TO MAIN"
])
def handle_otp_buttons(message):
    user_id = message.from_user.id
    text = message.text
    
    if text == "Rakib Admin Panel":
        if not (is_otp_admin(user_id)):
            bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
            return
        handle_otp_admin_panel(message)
    elif text == "BACK TO ADMIN PANEL":
        handle_otp_back_to_admin_panel(message)
    elif text in ("আমার প্রোফাইল", "💎 আমার প্রোফাইল"):
        handle_otp_profile(message)
    elif text in ("ডিপোজিট", "💎 ডিপোজিট"):
        handle_deposit_user(message)
    elif text in ("প্রিমিয়াম প্লান 🌟", "💎 প্রিমিয়াম প্লান 🌟"):
        handle_premium_plan_user(message)
    elif text == "BACK TO MAIN":
        go_back_to_main(message)

# --- Premium Plan User Sub-menu Handlers ---
@bot.message_handler(func=lambda message: message.text in [
    "Buy Plan", "Deposit"
])
def handle_premium_user_submenu(message):
    text = message.text
    
    if text == "Buy Plan":
        handle_buy_plan(message)
    elif text == "Deposit":
        handle_deposit_user(message)

# --- Support Link Admin Settings ---
def handle_set_support_link(message):
    if not is_otp_admin(message.from_user.id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode="Markdown")
        return
    current = get_setting('support_url').strip()
    current_text = current if current else "Not set"
    msg = bot.reply_to(
        message,
        "🆘 *SET SUPPORT LINK*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "📌 *Send the support link for the Support button:*\n"
        "Example: `https://t.me/YourSupport`\n\n"
        f"🔗 *Current:* `{current_text}`\n\n"
        "Cancel: `/cancel`",
        parse_mode="Markdown"
    )
    register_otp_admin_step_handler(msg, process_set_support_link)

def process_set_support_link(message):
    if not is_otp_admin(message.from_user.id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode="Markdown")
        return
    text = (message.text or "").strip()
    if text.lower() == '/cancel':
        handle_otp_admin_panel(message)
        return
    if not re.match(r'^https?://\S+$', text):
        bot.reply_to(message, "❌ *Invalid support link!*\nExample: `https://t.me/YourSupport`", parse_mode="Markdown")
        return
    if set_setting('support_url', text):
        bot.reply_to(message, f"✅ *Support link saved successfully!*\n\n🔗 `{text}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ *Support link save করতে ব্যর্থ হয়েছে!*", parse_mode="Markdown")
    handle_otp_admin_panel(message)

# --- OTP Admin Button Handlers (UPDATED - REMOVED BAN/UNBAN, ALL USERS, ALL FILES, STOP & DELETE) ---
@bot.message_handler(func=lambda message: message.text in [
    "ADMIN LIST",
    "SET LIMIT", "FREE BOT LIMIT",
    "Set Premium Plan for All User 🌟",
    "DEPOSITE SYSTEM",
    "FORCE JOIN",
    "SET SUPPORT LINK",
    "BACK TO ADMIN PANEL"
])
def handle_otp_admin_buttons(message):
    user_id = message.from_user.id
    text = message.text
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    if text == "ADMIN LIST":
        handle_otp_admin_list(message)
    elif text == "DEPOSITE SYSTEM":
        handle_admin_deposit_panel(message)
    elif text == "SET LIMIT":
        handle_otp_set_limit(message)
    elif text == "FREE BOT LIMIT":
        handle_otp_set_free_user_limit(message)
    elif text == "Set Premium Plan for All User 🌟":
        handle_premium_plan_admin(message)
    elif text == "FORCE JOIN":
        show_force_join_admin(message)
    elif text == "SET SUPPORT LINK":
        handle_set_support_link(message)
    elif text == "BACK TO ADMIN PANEL":
        handle_otp_back_to_admin_panel(message)

# --- OTP Deposite Sub-menu Handlers ---
@bot.message_handler(func=lambda message: message.text in [
    "SHOW ALL DEPOSITE REQUEST", 
    "SET DEPOSIT NUMBER AND ID",
    "DELETE PAYMENT METHOD"
])
def handle_otp_deposite_submenu(message):
    user_id = message.from_user.id
    text = message.text
    
    if not is_otp_admin(user_id):
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    if text == "SHOW ALL DEPOSITE REQUEST":
        handle_admin_show_deposits(message)
    elif text == "SET DEPOSIT NUMBER AND ID":
        handle_admin_set_deposit(message)
    elif text == "DELETE PAYMENT METHOD":
        handle_admin_delete_payment_method(message)

# --- Premium Plan Admin Sub-menu Handlers ---
@bot.message_handler(func=lambda message: message.text in [
    "Add Your Premium Plan", 
    "Remove Plan",
    "Reset All Plans"
])
def handle_premium_admin_submenu(message):
    text = message.text
    
    if text == "Add Your Premium Plan":
        handle_add_premium_plan(message)
    elif text == "Remove Plan":
        handle_remove_premium_plan(message)
    elif text == "Reset All Plans":
        handle_reset_all_plans(message)

# --- OTP Admin List Sub-menu Handlers ---
@bot.message_handler(func=lambda message: message.text in [
    "ADD ADMIN", "REMOVE ADMIN", "TRANSFER OWNERSHIP", "SHOW ALL ADMINS"
])
def handle_otp_admin_list_submenu(message):
    user_id = message.from_user.id
    text = message.text
    
    if not is_otp_admin(user_id) and text not in ["TRANSFER OWNERSHIP"]:
        bot.reply_to(message, "⛔ *Unauthorized!*", parse_mode='Markdown')
        return
    
    if text == "ADD ADMIN":
        handle_otp_add_admin(message)
    elif text == "REMOVE ADMIN":
        handle_otp_remove_admin(message)
    elif text == "TRANSFER OWNERSHIP":
        handle_otp_transfer_ownership(message)
    elif text == "SHOW ALL ADMINS":
        handle_otp_show_all_admins(message)

# --- Command Handlers ---
@bot.message_handler(commands=['updateschannel'])
def command_updates_channel(message): _logic_updates_channel(message)
@bot.message_handler(commands=['uploadfile'])
def command_upload_file(message): _logic_upload_file(message)
@bot.message_handler(commands=['checkfiles'])
def command_check_files(message): _logic_check_files(message)
@bot.message_handler(commands=['botspeed'])
def command_bot_speed(message): _logic_bot_speed(message)
@bot.message_handler(commands=['contactowner'])
def command_contact_owner(message): _logic_contact_owner(message)
@bot.message_handler(commands=['subscriptions'])
def command_subscriptions(message): _logic_subscriptions_panel(message)
@bot.message_handler(commands=['statistics'])
def command_statistics(message): _logic_statistics(message)
@bot.message_handler(commands=['lockbot']) 
def command_lock_bot(message): _logic_toggle_lock_bot(message)
@bot.message_handler(commands=['runningallcode'])
def command_run_all_code(message): _logic_run_all_scripts(message)

@bot.message_handler(commands=['ping'])
def ping(message):
    start_ping_time = time.time() 
    msg = bot.reply_to(message, "Pong!")
    latency = round((time.time() - start_ping_time) * 1000, 2)
    bot.edit_message_text(f"Pong! Latency: {latency} ms", message.chat.id, msg.message_id)

# --- Document (File) Handler ---
@bot.message_handler(content_types=['document'])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if not require_force_join(message):
        return
    doc = message.document
    logger.info(f"Doc from {user_id}: {doc.file_name} ({doc.mime_type}), Size: {doc.file_size}")

    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked, cannot accept files.")
        return

    if user_id not in admin_ids and user_id != OWNER_ID:
        upload_count = get_user_upload_count_in_time(user_id)
        file_limit = get_user_file_limit(user_id)
        
        if upload_count >= file_limit:
            bot.reply_to(message, 
                f"❌ *আপনার ফাইল আপলোড লিমিট শেষ হয়েছে!*\n"
                f"━━━━━━━━━━━━━━━━━\n\n"
                f"📁 *আপনি {file_limit} টি ফাইল আপলোড করতে পারবেন*\n"
                f"⏰ *সময়: {FREE_USER_LIMIT_SETTINGS['time']} ঘন্টা*\n\n"
                f"💡 *প্রিমিয়াম কিনতে ডিপোজিট করে প্রিমিয়াম প্লান কিনুন।*\n"
                f"〽️ *প্রিমিয়াম প্লান 🌟* বাটনে ক্লিক করুন।",
                parse_mode='Markdown'
            )
            return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, 
            f"⚠️ *ফাইল লিমিট শেষ!*\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"📁 *আপনি {current_files}/{limit_str} ফাইল আপলোড করেছেন*\n\n"
            f"💡 *প্রিমিয়াম কিনতে ডিপোজিট করে প্রিমিয়াম প্লান কিনুন।*",
            parse_mode='Markdown'
        )
        return

    file_name = doc.file_name
    if not file_name: bot.reply_to(message, "⚠️ No file name. Ensure file has a name."); return
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "⚠️ Unsupported type! Only `.py`, `.js`, `.zip` allowed.")
        return
    max_file_size = 20 * 1024 * 1024
    if doc.file_size > max_file_size:
        bot.reply_to(message, f"⚠️ File too large (Max: {max_file_size // 1024 // 1024} MB)."); return

    try:
        try:
            bot.forward_message(OWNER_ID, chat_id, message.message_id)
            bot.send_message(OWNER_ID, f"⬆️ File '{file_name}' from {message.from_user.first_name} (`{user_id}`)", parse_mode='Markdown')
        except Exception as e: logger.error(f"Failed to forward uploaded file to OWNER_ID {OWNER_ID}: {e}")

        download_wait_msg = bot.reply_to(message, f"⏳ Downloading `{file_name}`...")
        file_info_tg_doc = bot.get_file(doc.file_id)
        downloaded_file_content = bot.download_file(file_info_tg_doc.file_path)
        
        if user_id != OWNER_ID:
            is_safe, reason = scan_file_for_malware(downloaded_file_content, file_name, user_id)
            if not is_safe:
                bot.edit_message_text(f"🚨 Security Alert: {reason}", chat_id, download_wait_msg.message_id)
                return
        
        bot.edit_message_text(f"✅ Downloaded `{file_name}`. Processing...", chat_id, download_wait_msg.message_id)
        logger.info(f"Downloaded {file_name} for user {user_id}")
        user_folder = get_user_folder(user_id)

        if user_id not in user_upload_times:
            user_upload_times[user_id] = []
        user_upload_times[user_id].append(datetime.now())

        if file_ext == '.zip':
            handle_zip_file(downloaded_file_content, file_name, message)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f: f.write(downloaded_file_content)
            logger.info(f"Saved single file to {file_path}")
            if file_ext == '.js': handle_js_file(file_path, user_id, user_folder, file_name, message)
            elif file_ext == '.py': handle_py_file(file_path, user_id, user_folder, file_name, message)
    except telebot.apihelper.ApiTelegramException as e:
         logger.error(f"Telegram API Error handling file for {user_id}: {e}", exc_info=True)
         if "file is too big" in str(e).lower():
              bot.reply_to(message, f"❌ Telegram API Error: File too large to download (~20MB limit).")
         else: bot.reply_to(message, f"❌ Telegram API Error: {str(e)}. Try later.")
    except Exception as e:
        logger.error(f"❌ General error handling file for {user_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Unexpected error: {str(e)}")

# --- Callback Query Handlers ---
@bot.callback_query_handler(func=lambda call: True) 
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    logger.info(f"Callback: User={user_id}, Data='{data}'")

    if bot_locked and user_id not in admin_ids and data not in ['back_to_main', 'speed', 'stats']:
        bot.answer_callback_query(call.id, "⚠️ Bot locked by admin.", show_alert=True)
        return
    
    # --- FORCE JOIN VERIFY CALLBACK ---
    if data == 'force_join_verify':
        try:
            allowed, channel = check_force_join(user_id)
            if allowed:
                bot.answer_callback_query(call.id, "✅ Verification successful!")
                bot.send_message(
                    call.message.chat.id,
                    "✅ *Verification successful!*\n\n"
                    "🎉 এখন আপনি Bot ব্যবহার করতে পারবেন।",
                    parse_mode='Markdown'
                )
                _logic_send_welcome(call.message)
            else:
                bot.answer_callback_query(
                    call.id,
                    f"❌ আগে {channel} Channel-এ Join করুন।",
                    show_alert=True
                )
        except Exception as e:
            logger.error(f"Force Join verify error for {user_id}: {e}", exc_info=True)
            bot.answer_callback_query(
                call.id,
                "❌ Verification failed. একটু পরে আবার চেষ্টা করুন।",
                show_alert=True
            )
        return

    # --- New Deposit System Callbacks ---
    if data.startswith('deposit_method_'):
        handle_deposit_method_selection(call)
        return
    
    if data == 'my_deposits':
        handle_my_deposits(call)
        return
    
    if data == 'back_deposit':
        bot.answer_callback_query(call.id)
        handle_deposit_user(call.message)
        return

    if data == 'cancel_deposit':
        # Cancel any pending deposit input first so old next-step handlers
        # cannot consume messages after the user cancels.
        try:
            bot.clear_step_handler_by_chat_id(call.message.chat.id)
        except Exception as e:
            logger.debug(f"Could not clear pending deposit step handler: {e}")

        # Clear all in-memory deposit states for this user.
        for func in (handle_deposit_method_selection, process_deposit_amount):
            state = getattr(func, 'user_deposit_state', {})
            state.pop(user_id, None)
            func.user_deposit_state = state
        pending_state = getattr(process_deposit_trxid, 'pending_state', {})
        pending_state.pop(user_id, None)
        process_deposit_trxid.pending_state = pending_state

        bot.answer_callback_query(call.id, "❌ Deposit cancelled.")

        # Remove the deposit message and return to the normal main menu.
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception as e:
            logger.debug(f"Could not delete cancelled deposit message: {e}")
        go_back_to_main(call.message)
        return
    
    if data.startswith('approve_dep_'):
        handle_approve_deposit(call)
        return
    
    if data.startswith('reject_dep_'):
        handle_reject_deposit(call)
        return
    
    # --- DELETE PAYMENT METHOD CALLBACKS ---
    if data.startswith('delete_method_'):
        process_delete_payment_method(call)
        return
    
    if data.startswith('confirm_delete_method_'):
        process_confirm_delete_method(call)
        return
    
    if data == 'cancel_delete_method':
        process_cancel_delete_method(call)
        return
    
    if data == 'back_deposit_admin':
        bot.answer_callback_query(call.id)
        handle_admin_deposit_panel(call.message)
        return
    
    # --- Premium Plan Callbacks ---
    if data.startswith('buy_plan_'):
        process_buy_plan(call)
        return
    
    if data.startswith('remove_plan_'):
        process_remove_plan(call)
        return
    
    if data == 'confirm_reset_plans':
        process_reset_plans(call)
        return
    
    if data == 'cancel_reset_plans':
        process_cancel_reset(call)
        return
    
    if data == 'back_premium':
        bot.answer_callback_query(call.id)
        handle_premium_plan_user(call.message)
        return
    
    if data == 'back_premium_admin':
        bot.answer_callback_query(call.id)
        handle_premium_plan_admin(call.message)
        return
    
    # --- OTP Admin Callbacks ---
    # Reply-keyboard / inline back button: always return to the Rakib Admin Panel.
    if data == 'otp_back_admin':
        handle_otp_back_admin_callback(call)
        return

    # Deposit request list uses callback_data='back_admin_panel'.
    # This callback was previously missing, so Telegram showed no navigation.
    if data == 'back_admin_panel':
        if not is_otp_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        handle_otp_back_to_admin_panel(call.message)
        return
    
    # --- Main Callbacks ---
    if data == 'upload': upload_callback(call)
    elif data == 'check_files': check_files_callback(call)
    elif data.startswith('file_'): file_control_callback(call)
    elif data.startswith('start_'): start_bot_callback(call)
    elif data.startswith('stop_'): stop_bot_callback(call)
    elif data.startswith('restart_'): restart_bot_callback(call)
    elif data.startswith('delete_'): delete_bot_callback(call)
    elif data.startswith('logs_'): logs_bot_callback(call)
    elif data == 'speed': speed_callback(call)
    elif data == 'back_to_main': back_to_main_callback(call)
    elif data == 'run_all_scripts': admin_required_callback(call, run_all_scripts_callback)
    elif data == 'gx_admin_panel': gx_admin_panel_callback(call)
    elif data == 'subscription': admin_required_callback(call, subscription_management_callback)
    elif data == 'stats': stats_callback(call)
    elif data == 'lock_bot': admin_required_callback(call, lock_bot_callback)
    elif data == 'unlock_bot': admin_required_callback(call, unlock_bot_callback)
    elif data == 'add_subscription': admin_required_callback(call, add_subscription_init_callback) 
    elif data == 'remove_subscription': admin_required_callback(call, remove_subscription_init_callback) 
    elif data == 'check_subscription': admin_required_callback(call, check_subscription_init_callback) 
    else:
        bot.answer_callback_query(call.id, "Unknown action.")
        logger.warning(f"Unhandled callback data: {data} from user {user_id}")

def handle_otp_back_admin_callback(call):
    user_id = call.from_user.id
    
    if not is_otp_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized!", show_alert=True)
        return
    
    bot.answer_callback_query(call.id)
    handle_otp_admin_panel(call.message)

def gx_admin_panel_callback(call):
    user_id = call.from_user.id
    
    if not is_otp_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized!", show_alert=True)
        return
    
    bot.answer_callback_query(call.id)
    markup = create_otp_reply_keyboard(user_id)
    bot.edit_message_text(
        "🔴 *Rakib Admin Panel* 🤡\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "✅ *Welcome Admin!*\n"
        "✅ *You have full access to bot controls.*\n\n"
        "📌 *Select an option:*",
        call.message.chat.id, call.message.message_id,
        reply_markup=markup,
        parse_mode='Markdown'
    )

def run_all_scripts_callback(call):
    _logic_run_all_scripts(call)

# --- Admin Required Callback Wrappers ---
def admin_required_callback(call, func_to_run):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin permissions required.", show_alert=True)
        return
    func_to_run(call)

# --- Main Callback Functions ---
def upload_callback(call):
    user_id = call.from_user.id
    
    if user_id not in admin_ids and user_id != OWNER_ID:
        upload_count = get_user_upload_count_in_time(user_id)
        file_limit = get_user_file_limit(user_id)
        
        if file_limit != float("inf") and upload_count >= file_limit:
            bot.answer_callback_query(call.id, f"⚠️ লিমিট শেষ! {file_limit} ফাইল/{FREE_USER_LIMIT_SETTINGS['time']}ঘন্টা", show_alert=True)
            return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.answer_callback_query(call.id, f"⚠️ File limit ({current_files}/{limit_str}) reached.", show_alert=True)
        return
    bot.answer_callback_query(call.id) 
    bot.send_message(call.message.chat.id, "📤 Send your Python (`.py`), JS (`.js`), or ZIP (`.zip`) file.")

def check_files_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id 
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.answer_callback_query(call.id, "⚠️ No files uploaded.", show_alert=True)
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))
            bot.edit_message_text("📂 Your files:\n\n(No files uploaded)", chat_id, call.message.message_id, reply_markup=markup)
        except Exception as e: logger.error(f"Error editing msg for empty file list: {e}")
        return
    bot.answer_callback_query(call.id) 
    markup = types.InlineKeyboardMarkup(row_width=1) 
    for file_name, file_type in sorted(user_files_list): 
        is_running = is_bot_running(user_id, file_name)
        is_stopped = user_id in file_stop_status and file_name in file_stop_status[user_id]
        
        if is_stopped:
            status_icon = "⏹️ Stopped"
        elif is_running:
            status_icon = "🟢 Running"
        else:
            status_icon = "🔴 Stopped"
            
        btn_text = f"{file_name} ({file_type}) - {status_icon}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))
    try:
        bot.edit_message_text("📂 Your files:\nClick to manage.", chat_id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
    except telebot.apihelper.ApiTelegramException as e:
         if "message is not modified" in str(e): logger.warning("Msg not modified (files).")
         else: logger.error(f"Error editing msg for file list: {e}")
    except Exception as e: logger.error(f"Unexpected error editing msg for file list: {e}", exc_info=True)

def file_control_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            logger.warning(f"User {requesting_user_id} tried to access file '{file_name}' of user {script_owner_id} without permission.")
            bot.answer_callback_query(call.id, "⚠️ You can only manage your own files.", show_alert=True)
            check_files_callback(call)
            return

        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            logger.warning(f"File '{file_name}' not found for user {script_owner_id} during control.")
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True)
            check_files_callback(call) 
            return

        bot.answer_callback_query(call.id) 
        is_running = is_bot_running(script_owner_id, file_name)
        is_stopped = script_owner_id in file_stop_status and file_name in file_stop_status[script_owner_id]
        
        if is_stopped:
            status_text = '⏹️ Stopped'
        elif is_running:
            status_text = '🟢 Running'
        else:
            status_text = '🔴 Stopped'
            
        file_type = next((f[1] for f in user_files_list if f[0] == file_name), '?') 
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nStatus: {status_text}",
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_running and not is_stopped),
                parse_mode='Markdown'
            )
        except telebot.apihelper.ApiTelegramException as e:
             if "message is not modified" in str(e): logger.warning(f"Msg not modified (controls for {file_name})")
             else: raise 
    except (ValueError, IndexError) as ve:
        logger.error(f"Error parsing file control callback: {ve}. Data: '{call.data}'")
        bot.answer_callback_query(call.id, "Error: Invalid action data.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in file_control_callback for data '{call.data}': {e}", exc_info=True)
        bot.answer_callback_query(call.id, "An error occurred.", show_alert=True)

def start_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        logger.info(f"Start request: Requester={requesting_user_id}, Owner={script_owner_id}, File='{file_name}'")

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied to start this script.", show_alert=True); return

        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True); check_files_callback(call); return

        if script_owner_id in file_stop_status and file_name in file_stop_status[script_owner_id]:
            bot.answer_callback_query(call.id, "⏰ এই ফাইলটি স্টপ করা হয়েছে!", show_alert=True)
            return

        file_type = file_info[1]
        user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name)

        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, f"⚠️ Error: File `{file_name}` missing! Re-upload.", show_alert=True)
            remove_user_file_db(script_owner_id, file_name); check_files_callback(call); return

        if is_bot_running(script_owner_id, file_name):
            bot.answer_callback_query(call.id, f"⚠️ Script '{file_name}' already running.", show_alert=True)
            try: bot.edit_message_reply_markup(chat_id_for_reply, call.message.message_id, reply_markup=create_control_buttons(script_owner_id, file_name, True))
            except Exception as e: logger.error(f"Error updating buttons (already running): {e}")
            return

        bot.answer_callback_query(call.id, f"⏳ Attempting to start {file_name} for user {script_owner_id}...")

        if file_type == 'py':
            threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        else:
             bot.send_message(chat_id_for_reply, f"❌ Error: Unknown file type '{file_type}' for '{file_name}'."); return 

        time.sleep(1.5)
        is_now_running = is_bot_running(script_owner_id, file_name) 
        status_text = '🟢 Running' if is_now_running else '🟡 Starting (or failed, check logs/replies)'
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nStatus: {status_text}",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_now_running), parse_mode='Markdown'
            )
        except telebot.apihelper.ApiTelegramException as e:
             if "message is not modified" in str(e): logger.warning(f"Msg not modified after starting {file_name}")
             else: raise
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing start callback '{call.data}': {e}")
        bot.answer_callback_query(call.id, "Error: Invalid start command.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in start_bot_callback for '{call.data}': {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error starting script.", show_alert=True)
        try:
            _, script_owner_id_err_str, file_name_err = call.data.split('_', 2)
            script_owner_id_err = int(script_owner_id_err_str)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_control_buttons(script_owner_id_err, file_name_err, False))
        except Exception as e_btn: logger.error(f"Failed to update buttons after start error: {e_btn}")

def stop_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        logger.info(f"Stop request: Requester={requesting_user_id}, Owner={script_owner_id}, File='{file_name}'")
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return

        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True); check_files_callback(call); return

        file_type = file_info[1] 
        script_key = f"{script_owner_id}_{file_name}"

        if not is_bot_running(script_owner_id, file_name): 
            bot.answer_callback_query(call.id, f"⚠️ Script '{file_name}' already stopped.", show_alert=True)
            try:
                 bot.edit_message_text(
                     f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nStatus: 🔴 Stopped",
                     chat_id_for_reply, call.message.message_id,
                     reply_markup=create_control_buttons(script_owner_id, file_name, False), parse_mode='Markdown')
            except Exception as e: logger.error(f"Error updating buttons (already stopped): {e}")
            return

        bot.answer_callback_query(call.id, f"⏳ Stopping {file_name} for user {script_owner_id}...")
        process_info = bot_scripts.get(script_key)
        if process_info:
            kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]; logger.info(f"Removed {script_key} from running after stop.")
        else: logger.warning(f"Script {script_key} running by psutil but not in bot_scripts dict.")

        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nStatus: 🔴 Stopped",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, False), parse_mode='Markdown'
            )
        except telebot.apihelper.ApiTelegramException as e:
             if "message is not modified" in str(e): logger.warning(f"Msg not modified after stopping {file_name}")
             else: raise
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing stop callback '{call.data}': {e}")
        bot.answer_callback_query(call.id, "Error: Invalid stop command.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in stop_bot_callback for '{call.data}': {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error stopping script.", show_alert=True)

def restart_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        logger.info(f"Restart: Requester={requesting_user_id}, Owner={script_owner_id}, File='{file_name}'")
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return

        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True); check_files_callback(call); return

        if script_owner_id in file_stop_status and file_name in file_stop_status[script_owner_id]:
            bot.answer_callback_query(call.id, "⏰ এই ফাইলটি স্টপ করা হয়েছে!", show_alert=True)
            return

        file_type = file_info[1]; user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name); script_key = f"{script_owner_id}_{file_name}"

        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, f"⚠️ Error: File `{file_name}` missing! Re-upload.", show_alert=True)
            remove_user_file_db(script_owner_id, file_name)
            if script_key in bot_scripts: del bot_scripts[script_key]
            check_files_callback(call); return

        bot.answer_callback_query(call.id, f"⏳ Restarting {file_name} for user {script_owner_id}...")
        if is_bot_running(script_owner_id, file_name):
            logger.info(f"Restart: Stopping existing {script_key}...")
            process_info = bot_scripts.get(script_key)
            if process_info: kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
            time.sleep(1.5) 

        logger.info(f"Restart: Starting script {script_key}...")
        if file_type == 'py':
            threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        else:
             bot.send_message(chat_id_for_reply, f"❌ Unknown type '{file_type}' for '{file_name}'."); return

        time.sleep(1.5) 
        is_now_running = is_bot_running(script_owner_id, file_name) 
        status_text = '🟢 Running' if is_now_running else '🟡 Starting (or failed)'
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nStatus: {status_text}",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_now_running), parse_mode='Markdown'
            )
        except telebot.apihelper.ApiTelegramException as e:
             if "message is not modified" in str(e): logger.warning(f"Msg not modified (restart {file_name})")
             else: raise
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing restart callback '{call.data}': {e}")
        bot.answer_callback_query(call.id, "Error: Invalid restart command.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in restart_bot_callback for '{call.data}': {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error restarting.", show_alert=True)
        try:
            _, script_owner_id_err_str, file_name_err = call.data.split('_', 2)
            script_owner_id_err = int(script_owner_id_err_str)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_control_buttons(script_owner_id_err, file_name_err, False))
        except Exception as e_btn: logger.error(f"Failed to update buttons after restart error: {e_btn}")

def delete_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        logger.info(f"Delete: Requester={requesting_user_id}, Owner={script_owner_id}, File='{file_name}'")
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return

        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True); check_files_callback(call); return

        bot.answer_callback_query(call.id, f"🗑️ Deleting {file_name} for user {script_owner_id}...")
        script_key = f"{script_owner_id}_{file_name}"
        if is_bot_running(script_owner_id, file_name):
            logger.info(f"Delete: Stopping {script_key}...")
            process_info = bot_scripts.get(script_key)
            if process_info: kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
            time.sleep(0.5) 

        user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        deleted_disk = []
        if os.path.exists(file_path):
            try: os.remove(file_path); deleted_disk.append(file_name); logger.info(f"Deleted file: {file_path}")
            except OSError as e: logger.error(f"Error deleting {file_path}: {e}")
        if os.path.exists(log_path):
            try: os.remove(log_path); deleted_disk.append(os.path.basename(log_path)); logger.info(f"Deleted log: {log_path}")
            except OSError as e: logger.error(f"Error deleting log {log_path}: {e}")

        remove_user_file_db(script_owner_id, file_name)
        deleted_str = ", ".join(f"`{f}`" for f in deleted_disk) if deleted_disk else "associated files"
        try:
            bot.edit_message_text(
                f"🗑️ Record `{file_name}` (User `{script_owner_id}`) and {deleted_str} deleted!",
                chat_id_for_reply, call.message.message_id, reply_markup=None, parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error editing msg after delete: {e}")
            bot.send_message(chat_id_for_reply, f"🗑️ Record `{file_name}` deleted.", parse_mode='Markdown')
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing delete callback '{call.data}': {e}")
        bot.answer_callback_query(call.id, "Error: Invalid delete command.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in delete_bot_callback for '{call.data}': {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error deleting.", show_alert=True)

def logs_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        logger.info(f"Logs: Requester={requesting_user_id}, Owner={script_owner_id}, File='{file_name}'")
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return

        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True); check_files_callback(call); return

        user_folder = get_user_folder(script_owner_id)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        if not os.path.exists(log_path):
            bot.answer_callback_query(call.id, f"⚠️ No logs for '{file_name}'.", show_alert=True); return

        bot.answer_callback_query(call.id) 
        try:
            log_content = ""; file_size = os.path.getsize(log_path)
            max_log_kb = 100; max_tg_msg = 4096
            if file_size == 0: log_content = "(Log empty)"
            elif file_size > max_log_kb * 1024:
                 with open(log_path, 'rb') as f: f.seek(-max_log_kb * 1024, os.SEEK_END); log_bytes = f.read()
                 log_content = log_bytes.decode('utf-8', errors='ignore')
                 log_content = f"(Last {max_log_kb} KB)\n...\n" + log_content
            else:
                 with open(log_path, 'r', encoding='utf-8', errors='ignore') as f: log_content = f.read()

            if len(log_content) > max_tg_msg:
                log_content = log_content[-max_tg_msg:]
                first_nl = log_content.find('\n')
                if first_nl != -1: log_content = "...\n" + log_content[first_nl+1:]
                else: log_content = "...\n" + log_content 
            if not log_content.strip(): log_content = "(No visible content)"

            bot.send_message(chat_id_for_reply, f"📜 Logs for `{file_name}` (User `{script_owner_id}`):\n```\n{log_content}\n```", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error reading/sending log {log_path}: {e}", exc_info=True)
            bot.send_message(chat_id_for_reply, f"❌ Error reading log for `{file_name}`.")
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing logs callback '{call.data}': {e}")
        bot.answer_callback_query(call.id, "Error: Invalid logs command.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in logs_bot_callback for '{call.data}': {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error fetching logs.", show_alert=True)

def speed_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    start_cb_ping_time = time.time() 
    try:
        bot.edit_message_text("🏃 Testing speed...", chat_id, call.message.message_id)
        bot.send_chat_action(chat_id, 'typing') 
        response_time = round((time.time() - start_cb_ping_time) * 1000, 2)
        status = "🔓 Unlocked" if not bot_locked else "🔒 Locked"
        if user_id == OWNER_ID: user_level = "👑 Owner"
        elif user_id in admin_ids: user_level = "🛡️ Admin"
        elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now(): user_level = "⭐ Premium"
        else: user_level = "🆓 Free User"
        speed_msg = (f"⚡ Bot Speed & Status:\n\n⏱️ API Response Time: {response_time} ms\n"
                     f"🚦 Bot Status: {status}\n"
                     f"👤 Your Level: {user_level}")
        bot.answer_callback_query(call.id) 
        bot.edit_message_text(speed_msg, chat_id, call.message.message_id, reply_markup=create_main_menu_inline(user_id))
    except Exception as e:
         logger.error(f"Error during speed test (cb): {e}", exc_info=True)
         bot.answer_callback_query(call.id, "Error in speed test.", show_alert=True)
         try: bot.edit_message_text("〽️ Main Menu", chat_id, call.message.message_id, reply_markup=create_main_menu_inline(user_id))
         except Exception: pass

def back_to_main_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    expiry_info = ""
    if user_id == OWNER_ID: user_status = "👑 Owner"
    elif user_id in admin_ids: user_status = "🛡️ Admin"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            user_status = "⭐ Premium"; days_left = (expiry_date - datetime.now()).days
            expiry_info = f"\n⏳ Subscription expires in: {days_left} days"
        else: user_status = "🆓 Free User (Expired Sub)"
    else: user_status = "🆓 Free User"
    
    balance = get_user_balance_db(user_id)
    
    main_menu_text = (f"〽️ Welcome back, {call.from_user.first_name}!\n\n🆔 ID: `{user_id}`\n"
                      f"🔰 Status: {user_status}{expiry_info}\n💰 Balance: ৳{balance:.2f}\n📁 Files: {current_files} / {limit_str}\n\n"
                      f"👇 Use buttons or type commands.")
    try:
        bot.answer_callback_query(call.id)
        bot.edit_message_text(main_menu_text, chat_id, call.message.message_id,
                              reply_markup=create_main_menu_inline(user_id), parse_mode='Markdown')
    except telebot.apihelper.ApiTelegramException as e:
         if "message is not modified" in str(e): logger.warning("Msg not modified (back_to_main).")
         else: logger.error(f"API error on back_to_main: {e}")
    except Exception as e: logger.error(f"Error handling back_to_main: {e}", exc_info=True)

# --- Admin Callback Implementations ---
def subscription_management_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("💳 Subscription Management\nSelect action:",
                              call.message.chat.id, call.message.message_id, reply_markup=create_subscription_menu())
    except Exception as e: logger.error(f"Error showing sub menu: {e}")

def stats_callback(call):
    bot.answer_callback_query(call.id)
    _logic_statistics(call.message)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                      reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception as e:
        logger.error(f"Error updating menu after stats_callback: {e}")

def lock_bot_callback(call):
    global bot_locked; bot_locked = True
    logger.warning(f"Bot locked by Admin {call.from_user.id}")
    bot.answer_callback_query(call.id, "🔒 Bot locked.")
    try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception as e: logger.error(f"Error updating menu (lock): {e}")

def unlock_bot_callback(call):
    global bot_locked; bot_locked = False
    logger.warning(f"Bot unlocked by Admin {call.from_user.id}")
    bot.answer_callback_query(call.id, "🔓 Bot unlocked.")
    try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception as e: logger.error(f"Error updating menu (unlock): {e}")

def add_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter User ID & days (e.g., `12345678 30`).\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_add_subscription_details)

def process_add_subscription_details(message):
    admin_id_check = message.from_user.id 
    if admin_id_check not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Sub add cancelled."); return
    try:
        parts = message.text.split();
        if len(parts) != 2: raise ValueError("Incorrect format")
        sub_user_id = int(parts[0].strip()); days = int(parts[1].strip())
        if sub_user_id <= 0 or days <= 0: raise ValueError("User ID/days must be positive")

        current_expiry = user_subscriptions.get(sub_user_id, {}).get('expiry')
        start_date_new_sub = datetime.now()
        if current_expiry and current_expiry > start_date_new_sub: start_date_new_sub = current_expiry
        new_expiry = start_date_new_sub + timedelta(days=days)
        save_subscription(sub_user_id, new_expiry)

        logger.info(f"Sub for {sub_user_id} by admin {admin_id_check}. Expiry: {new_expiry:%Y-%m-%d}")
        bot.reply_to(message, f"✅ Sub for `{sub_user_id}` by {days} days.\nNew expiry: {new_expiry:%Y-%m-%d}")
        try: bot.send_message(sub_user_id, f"🎉 Sub activated/extended by {days} days! Expires: {new_expiry:%Y-%m-%d}.")
        except Exception as e: logger.error(f"Failed to notify {sub_user_id} of new sub: {e}")
    except ValueError as e:
        bot.reply_to(message, f"⚠️ Invalid: {e}. Format: `ID days` or /cancel.")
        msg = bot.send_message(message.chat.id, "💳 Enter User ID & days, or /cancel.")
        bot.register_next_step_handler(msg, process_add_subscription_details)
    except Exception as e: logger.error(f"Error processing add sub: {e}", exc_info=True); bot.reply_to(message, "Error.")

def remove_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter User ID to remove sub.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_subscription_id)

def process_remove_subscription_id(message):
    admin_id_check = message.from_user.id
    if admin_id_check not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Sub removal cancelled."); return
    try:
        sub_user_id_remove = int(message.text.strip())
        if sub_user_id_remove <= 0: raise ValueError("ID must be positive")
        if sub_user_id_remove not in user_subscriptions:
            bot.reply_to(message, f"⚠️ User `{sub_user_id_remove}` no active sub in memory."); return
        remove_subscription_db(sub_user_id_remove) 
        logger.warning(f"Sub removed for {sub_user_id_remove} by admin {admin_id_check}.")
        bot.reply_to(message, f"✅ Sub for `{sub_user_id_remove}` removed.")
        try: bot.send_message(sub_user_id_remove, "ℹ️ Your subscription removed by admin.")
        except Exception as e: logger.error(f"Failed to notify {sub_user_id_remove} of sub removal: {e}")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID. Send numerical ID or /cancel.")
        msg = bot.send_message(message.chat.id, "💳 Enter User ID to remove sub from, or /cancel.")
        bot.register_next_step_handler(msg, process_remove_subscription_id)
    except Exception as e: logger.error(f"Error processing remove sub: {e}", exc_info=True); bot.reply_to(message, "Error.")

def check_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter User ID to check sub.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_check_subscription_id)

def process_check_subscription_id(message):
    admin_id_check = message.from_user.id
    if admin_id_check not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Sub check cancelled."); return
    try:
        sub_user_id_check = int(message.text.strip())
        if sub_user_id_check <= 0: raise ValueError("ID must be positive")
        if sub_user_id_check in user_subscriptions:
            expiry_dt = user_subscriptions[sub_user_id_check].get('expiry')
            if expiry_dt:
                if expiry_dt > datetime.now():
                    days_left = (expiry_dt - datetime.now()).days
                    bot.reply_to(message, f"✅ User `{sub_user_id_check}` active sub.\nExpires: {expiry_dt:%Y-%m-%d %H:%M:%S} ({days_left} days left).")
                else:
                    bot.reply_to(message, f"⚠️ User `{sub_user_id_check}` expired sub (On: {expiry_dt:%Y-%m-%d %H:%M:%S}).")
                    remove_subscription_db(sub_user_id_check)
            else: bot.reply_to(message, f"⚠️ User `{sub_user_id_check}` in sub list, but expiry missing. Re-add if needed.")
        else: bot.reply_to(message, f"ℹ️ User `{sub_user_id_check}` no active sub record.")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID. Send numerical ID or /cancel.")
        msg = bot.send_message(message.chat.id, "💳 Enter User ID to check, or /cancel.")
        bot.register_next_step_handler(msg, process_check_subscription_id)
    except Exception as e: logger.error(f"Error processing check sub: {e}", exc_info=True); bot.reply_to(message, "Error.")

# --- Cleanup Function ---
def cleanup():
    logger.warning("Shutdown. Cleaning up processes...")
    script_keys_to_stop = list(bot_scripts.keys()) 
    if not script_keys_to_stop: logger.info("No scripts running. Exiting."); return
    logger.info(f"Stopping {len(script_keys_to_stop)} scripts...")
    for key in script_keys_to_stop:
        if key in bot_scripts: logger.info(f"Stopping: {key}"); kill_process_tree(bot_scripts[key])
        else: logger.info(f"Script {key} already removed.")
    logger.warning("Cleanup finished.")
atexit.register(cleanup)

# --- Main Execution ---
if __name__ == '__main__':
    logger.info("="*40)
    logger.info("🤖 Bot Starting Up...")
    logger.info(f"🐍 Python: {sys.version.split()[0]}")
    logger.info(f"🔧 Base Dir: {BASE_DIR}")
    logger.info(f"📁 Upload Dir: {UPLOAD_BOTS_DIR}")
    logger.info(f"📊 Data Dir: {IROTECH_DIR}")
    logger.info(f"🔑 Owner ID: {OWNER_ID}")
    logger.info(f"🛡️ Admins: {admin_ids}")
    logger.info(f"👑 OTP Admin List: {admin_list}")
    logger.info("="*40)
    
    keep_alive()
    
    logger.info("🚀 Starting polling...")
    while True:
        try:
            bot.infinity_polling(logger_level=logging.INFO, timeout=60, long_polling_timeout=30)
        except requests.exceptions.ReadTimeout:
            logger.warning("Polling ReadTimeout. Restarting in 5s...")
            time.sleep(5)
        except requests.exceptions.ConnectionError as ce:
            logger.error(f"Polling ConnectionError: {ce}. Retrying in 15s...")
            time.sleep(15)
        except Exception as e:
            logger.critical(f"💥 Unrecoverable polling error: {e}", exc_info=True)
            logger.info("Restarting polling in 30s due to critical error...")
            time.sleep(30)
        finally:
            logger.warning("Polling attempt finished. Will restart if in loop.")
            time.sleep(1)
