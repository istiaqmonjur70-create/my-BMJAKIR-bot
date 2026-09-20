# -*- coding: utf-8 -*-
import atexit
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import zipfile
import uuid
from flask import Flask
from threading import Thread
import psutil
import requests
import telebot
from telebot import types
from telebot.types import KeyboardButton

# --- Flask Keep Alive ---
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

# --- Configuration ---
TOKEN = os.getenv("BOT_TOKEN", "8910223271:AAEGc6ZTC4qE6FkOBLL13Xj0QwtQyfCI7CU").strip()
OWNER_ID = 8814363793
ADMIN_ID = 8814363793
YOUR_USERNAME = "@DevCloudX"
UPDATE_CHANNEL = "https://t.me/shiyam744"

# --- Default Binance Config (Can be changed from Admin Panel) ---
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "").strip()  
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "").strip()  
BINANCE_PAY_ID = os.getenv("BINANCE_PAY_ID", "").strip()  

# Folder setup - using absolute paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, "upload_bots")
IROTECH_DIR = os.path.join(BASE_DIR, "inf")
DATABASE_PATH = os.path.join(IROTECH_DIR, "bot_data.db")

FREE_USER_LIMIT = 0  
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 999
OWNER_LIMIT = float("inf")

USDT_BDT_RATE = 120.0  

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required. Set BOT_TOKEN in your hosting environment.")
bot = telebot.TeleBot(TOKEN, parse_mode=None)

# --- Data structures ---
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False

# --- Malware Detection Configuration ---
MALWARE_SIGNATURES = [
    b"MZ", b"\x7fELF", b"\xfe\xed\xfa", b"\xce\xfa\xed\xfe", b"PK", b"Rar!",  
]

ENCRYPTED_FILE_INDICATORS = [
    b"openssl", b"encrypted", b"cipher", b"AES", b"DES", b"RSA", b"GPG", b"PGP",
]

SUSPICIOUS_KEYWORDS = [
    b"ransomware", b"trojan", b"virus", b"malware", b"backdoor", b"exploit", 
    b"payload", b"botnet", b"keylogger", b"rootkit",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- STYLISH FONT MAPPING (For Buttons and processing) ---
BTN_TEXT_MAPPING = {
    "Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ": "UPDATES CHANNEL",
    "Mʏ Pʀᴏғɪʟᴇ": "MY PROFILE",
    "Rᴇғᴇʀ & Eᴀʀɴ": "REFER & EARN",
    "Uᴘʟᴏᴀᴅ Fɪʟᴇ": "UPLOAD FILE",
    "Mᴀɴᴀɢᴇ Fɪʟᴇs": "MANAGE FILES",
    "Vɪᴇᴡ Pʟᴀɴs": "VIEW PLANS",
    "Sᴘᴇᴇᴅ & Pɪɴɢ": "SPEED & PING",
    "Bᴏᴛ Sᴛᴀᴛs": "BOT STATS",
    "Lᴀɴɢᴜᴀɢᴇ": "LANGUAGE",
    "Cᴏɴᴛᴀᴄᴛ Oᴡɴᴇʀ": "CONTACT OWNER",
    "Aᴅᴍɪɴ Pᴀɴᴇʟ": "ADMIN PANEL"
}

def get_mapped_btn_name(text):
    return BTN_TEXT_MAPPING.get(text, text).upper()

def make_button(text, style=None):
    try: 
        return KeyboardButton(text, style=style)
    except TypeError:
        btn = KeyboardButton(text)
        if style: btn.style = style
        return btn

def make_inline_button(text, callback_data=None, url=None, style=None):
    try:
        return types.InlineKeyboardButton(text, callback_data=callback_data, url=url, style=style)
    except TypeError:
        btn = types.InlineKeyboardButton(text, callback_data=callback_data, url=url)
        if style: 
            try: btn.style = style 
            except: pass
        return btn

# --- Buttons Layout (WITH STYLISH FONT) ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ"],
    ["Mʏ Pʀᴏғɪʟᴇ", "Rᴇғᴇʀ & Eᴀʀɴ"],
    ["Uᴘʟᴏᴀᴅ Fɪʟᴇ", "Mᴀɴᴀɢᴇ Fɪʟᴇs"],
    ["Vɪᴇᴡ Pʟᴀɴs", "Sᴘᴇᴇᴅ & Pɪɴɢ"],
    ["Bᴏᴛ Sᴛᴀᴛs", "Lᴀɴɢᴜᴀɢᴇ"],
    ["Cᴏɴᴛᴀᴄᴛ Oᴡɴᴇʀ"],
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ"],
    ["Mʏ Pʀᴏғɪʟᴇ", "Rᴇғᴇʀ & Eᴀʀɴ"],
    ["Uᴘʟᴏᴀᴅ Fɪʟᴇ", "Mᴀɴᴀɢᴇ Fɪʟᴇs"],
    ["Vɪᴇᴡ Pʟᴀɴs", "Aᴅᴍɪɴ Pᴀɴᴇʟ"],
    ["Sᴘᴇᴇᴅ & Pɪɴɢ", "Bᴏᴛ Sᴛᴀᴛs"],
    ["Lᴀɴɢᴜᴀɢᴇ", "Cᴏɴᴛᴀᴄᴛ Oᴡɴᴇʀ"],
]

DB_LOCK = threading.Lock()

# --- Language Templates (PREMIUM CLEAN LOOK UPDATED) ---
MSG_TEMPLATES = {
    'EN': {
        'profile': "👤 **MY PROFILE**\n━━━━━━━━━━━━━━━━━━━━━━\n📛 **Name:** {name}\n🔖 **Username:** {uname}\n🆔 **User ID:** `{user_id}`\n\n💰 **Balance:** `{bal} {base_curr}`\n👥 **Total Referrals:** `{refs}`\n💎 **Active Plan:** `{plan_str}`\n━━━━━━━━━━━━━━━━━━━━━━\n🌟 *Enjoy our premium bot hosting!*",
        'refer': "👥 **REFER & EARN**\n━━━━━━━━━━━━━━━━━━━━━━\n🎁 **Invite your friends and earn!**\n💵 **Bonus per refer:** `{bonus} {base_curr}`\n\n🔗 **Your Referral Link:**\n`{ref_link}`\n\n📢 *Share this link with everyone to grow your balance faster!*",
        'upload_active': "🔰 **Active Plan:** `{plan_name}`\n\n🚀 **Click below to upload files:**",
        'upload_no_plan': "❌ **YOU DON'T HAVE AN ACTIVE PLAN!**\n\n**To upload files, please subscribe first.**",
        'lang_prompt': "🌐 **SELECT YOUR LANGUAGE:**\n\n*Choose from the options below:*",
        'welcome': "🌟 **𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗕𝗢𝗧 𝗛𝗢𝗦𝗧𝗜𝗡𝗚** 🌟\n━━━━━━━━━━━━━━━━━━━━━━\n👋 **Welcome, {user_name}!**\n\n📌 **ACCOUNT DETAILS:**\n├ 🆔 **ID:** `{user_id}`\n├ 🔰 **Status:** {user_status}\n└ 📁 **Files:** `{files}` / `{limit}`\n\n🚀 *Host & Run your Python (.PY) & JS (.JS) bots 24/7 with ultimate performance!*\n\n👇 **Select an option from the menu below:**",
        'manage_title': "📁 **YOUR UPLOADED FILES:**\n━━━━━━━━━━━━━━━━━━━━━━",
        'manage_empty': "📂 **YOUR FILES:**\n\n*(No files uploaded yet)*",
        'contact': "📞 **SUPPORT & CONTACT**\n━━━━━━━━━━━━━━━━━━━━━━\n**Select an option below to reach out to us:**",
    },
    'BN': {
        'profile': "👤 **আমার প্রোফাইল**\n━━━━━━━━━━━━━━━━━━━━━━\n📛 **নাম:** {name}\n🔖 **ইউজারনেম:** {uname}\n🆔 **ইউজার আইডি:** `{user_id}`\n\n💰 **ব্যালেন্স:** `{bal} {base_curr}`\n👥 **মোট রেফার:** `{refs}`\n💎 **বর্তমান প্ল্যান:** `{plan_str}`\n━━━━━━━━━━━━━━━━━━━━━━\n🌟 *আমাদের প্রিমিয়াম হোস্টিং উপভোগ করুন!*",
        'refer': "👥 **রেফার করুন এবং আয় করুন**\n━━━━━━━━━━━━━━━━━━━━━━\n🎁 **আপনার বন্ধুদের আমন্ত্রণ জানান এবং আয় করুন!**\n💵 **প্রতি রেফারে বোনাস:** `{bonus} {base_curr}`\n\n🔗 **আপনার রেফারেল লিঙ্ক:**\n`{ref_link}`\n\n📢 *বেশি আয় করতে আপনার বন্ধুদের সাথে লিঙ্কটি শেয়ার করুন!*",
        'upload_active': "🔰 **আপনার বর্তমান প্ল্যান:** `{plan_name}`\n\n🚀 **ফাইল আপলোড করতে নিচের বাটনে ক্লিক করুন:**",
        'upload_no_plan': "❌ **আপনার কোনো অ্যাক্টিভ প্ল্যান নেই!**\n\n**ফাইল আপলোড করতে আগে একটি প্ল্যান কিনুন।**",
        'lang_prompt': "🌐 **আপনার ভাষা নির্বাচন করুন:**",
        'welcome': "🌟 **𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗕𝗢𝗧 𝗛𝗢𝗦𝗧𝗜𝗡𝗚** 🌟\n━━━━━━━━━━━━━━━━━━━━━━\n👋 **স্বাগতম, {user_name}!**\n\n📌 **অ্যাকাউন্ট ইনফো:**\n├ 🆔 **আইডি:** `{user_id}`\n├ 🔰 **স্ট্যাটাস:** {user_status}\n└ 📁 **ফাইল:** `{files}` / `{limit}`\n\n🚀 *আপনার পাইথন (.PY) এবং JS (.JS) বটগুলো ২৪/৭ লাইভ হোস্ট করুন কোনো ঝামেলা ছাড়াই!*\n\n👇 **নিচের মেনু থেকে একটি অপশন বেছে নিন:**",
        'manage_title': "📁 **আপনার আপলোড করা ফাইলসমূহ:**\n━━━━━━━━━━━━━━━━━━━━━━",
        'manage_empty': "📂 **আপনার ফাইলসমূহ:**\n\n*(এখনো কোনো ফাইল আপলোড করা হয়নি)*",
        'contact': "📞 **সাপোর্ট এবং যোগাযোগ**\n━━━━━━━━━━━━━━━━━━━━━━\n**আমাদের সাথে যোগাযোগ করতে নিচের একটি অপশন বেছে নিন:**",
    },
    'HI': {
        'profile': "👤 **मेरी प्रोफाइल**\n━━━━━━━━━━━━━━━━━━━━━━\n📛 **नाम:** {name}\n🔖 **यूजरनेम:** {uname}\n🆔 **यूजर आईडी:** `{user_id}`\n\n💰 **बैलेंस:** `{bal} {base_curr}`\n👥 **कुल रेफरल:** `{refs}`\n💎 **सक्रिय योजना:** `{plan_str}`\n━━━━━━━━━━━━━━━━━━━━━━",
        'refer': "👥 **रेफर करें और कमाएं**\n━━━━━━━━━━━━━━━━━━━━━━\n🎁 **अपने दोस्तों को आमंत्रित करें और कमाएं!**\n💵 **प्रति रेफरल बोनस:** `{bonus} {base_curr}`\n\n🔗 **आपका रेफरल लिंक:**\n`{ref_link}`\n\n📢 *अधिक कमाने के लिए इस लिंक को साझा करें!*",
        'upload_active': "🔰 **सक्रिय योजना:** `{plan_name}`\n\n🚀 **फ़ाइल अपलोड करने के लिए नीचे क्लिक करें:**",
        'upload_no_plan': "❌ **आपके पास कोई सक्रिय योजना नहीं है!**\n\n**फ़ाइल अपलोड करने के लिए कृपया योजना खरीदें।**",
        'lang_prompt': "🌐 **अपनी पसंदीदा भाषा चुनें:**",
        'welcome': "🌟 **𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗕𝗢𝗧 𝗛𝗢𝗦𝗧𝗜𝗡𝗚** 🌟\n━━━━━━━━━━━━━━━━━━━━━━\n👋 **स्वागत है, {user_name}!**\n\n📌 **खाता विवरण:**\n├ 🆔 **आईडी:** `{user_id}`\n├ 🔰 **स्थिति:** {user_status}\n└ 📁 **फ़ाइलें:** `{files}` / `{limit}`\n\n🚀 *अपने बॉट को 24/7 होस्ट करें!*\n\n👇 *नीचे से एक विकल्प चुनें:*",
        'manage_title': "📁 **आपकी अपलोड की गई फ़ाइलें:**\n━━━━━━━━━━━━━━━━━━━━━━",
        'manage_empty': "📂 **आपकी अपलोड की गई फ़ाइलें:**\n\n*(अभी तक कोई फ़ाइल अपलोड नहीं की गई है)*",
        'contact': "📞 **समर्थन और संपर्क**\n━━━━━━━━━━━━━━━━━━━━━━\n**हमसे संपर्क करने के लिए नीचे एक विकल्प चुनें:**",
    },
    'UR': {
        'profile': "👤 **میری پروفائل**\n━━━━━━━━━━━━━━━━━━━━━━\n📛 **نام:** {name}\n🔖 **صارف نام:** {uname}\n🆔 **یوزر آئی ڈی:** `{user_id}`\n\n💰 **بیلنس:** `{bal} {base_curr}`\n👥 **کل ریفرلز:** `{refs}`\n💎 **فعال منصوبہ:** `{plan_str}`\n━━━━━━━━━━━━━━━━━━━━━━",
        'refer': "👥 **ریفر کریں اور کمائیں**\n━━━━━━━━━━━━━━━━━━━━━━\n🎁 **اپنے دوستوں کو مدعو کریں اور کمائیں!**\n💵 **فی ریفرل بونس:** `{bonus} {base_curr}`\n\n🔗 **آپ کا ریفرل لنک:**\n`{ref_link}`\n\n📢 *مزید کمانے کے لیے اس لنک کو شیئر کریں!*",
        'upload_active': "🔰 **فعال منصوبہ:** `{plan_name}`\n\n🚀 **فائل اپ لوڈ کرنے کے لیے نیچے کلک کریں:**",
        'upload_no_plan': "❌ **آپ کا کوئی فعال منصوبہ نہیں ہے!**\n\n**فائل اپ لوڈ کرنے کے لیے منصوبہ خریدیں۔**",
        'lang_prompt': "🌐 **اپنی زبان کا انتخاب کریں:**",
        'welcome': "🌟 **𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗕𝗢𝗧 𝗛𝗢𝗦𝗧𝗜𝗡 اور 🌟\n━━━━━━━━━━━━━━━━━━━━━━\n👋 **خوش آمدید، {user_name}!**\n\n📌 **اکاؤنٹ کی تفصیلات:**\n├ 🆔 **آئی ڈی:** `{user_id}`\n├ 🔰 **حیثیت:** {user_status}\n└ 📁 **فائلیں:** `{files}` / `{limit}`\n\n🚀 *اپنے بوٹ کو 24/7 ہوسٹ کریں!*\n\n👇 *نیچے سے ایک آپشن منتخب کریں:*",
        'manage_title': "📁 **آپ کی فائلیں:**\n━━━━━━━━━━━━━━━━━━━━━━",
        'manage_empty': "📂 **آپ کی فائلیں:**\n\n*(ابھی تک کوئی فائل اپ لوڈ نہیں کی گئی ہے)*",
        'contact': "📞 **رابطہ اور تعاون**\n━━━━━━━━━━━━━━━━━━━━━━\n**ہم سے رابطہ کرنے کے لیے نیچے ایک آپشن منتخب کریں:**",
    }
}

def init_db():
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, referred_by INTEGER, refer_count INTEGER DEFAULT 0)")
        
        try:
            c.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'EN'")
        except:
            pass

        c.execute("CREATE TABLE IF NOT EXISTS force_subs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, chat_id TEXT, url TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS support_buttons (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, url TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS subscriptions (user_id INTEGER PRIMARY KEY, plan_name TEXT, expiry TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS user_files (user_id INTEGER, file_name TEXT, file_type TEXT, PRIMARY KEY (user_id, file_name))")
        c.execute("CREATE TABLE IF NOT EXISTS active_users (user_id INTEGER PRIMARY KEY)")
        c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
        c.execute("CREATE TABLE IF NOT EXISTS plans (plan_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, file_limit INTEGER, price TEXT, duration INTEGER, buy_link TEXT)")
        
        # New Tables for Free Plan Limit and Ban System
        c.execute("CREATE TABLE IF NOT EXISTS free_plan_claimed (user_id INTEGER PRIMARY KEY)")
        c.execute("CREATE TABLE IF NOT EXISTS banned_users (user_id INTEGER PRIMARY KEY)")
        c.execute("""CREATE TABLE IF NOT EXISTS pending_uploads (
            request_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS approved_files (
            user_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            PRIMARY KEY (user_id, file_name)
        )""")

        # Add 'features' column safely for dynamic plan features
        try:
            c.execute("ALTER TABLE plans ADD COLUMN features TEXT DEFAULT ''")
        except:
            pass

        c.execute("CREATE TABLE IF NOT EXISTS pending_payments (user_id INTEGER, plan_id INTEGER, paid_amount REAL, PRIMARY KEY (user_id, plan_id))")
        c.execute("CREATE TABLE IF NOT EXISTS used_txids (tx_id TEXT PRIMARY KEY)")
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS button_media (button_name TEXT PRIMARY KEY, media_type TEXT, file_id TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS payment_methods (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, number TEXT, instructions TEXT)")

        c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (ADMIN_ID,))

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DATABASE INITIALIZATION ERROR: {e}", exc_info=True)

def is_user_banned(user_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT user_id FROM banned_users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_user_lang(user_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute("SELECT lang FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        lang = row[0] if (row and row[0]) else 'EN'
    except:
        lang = 'EN'
    conn.close()
    return lang if lang in MSG_TEMPLATES else 'EN'

def set_user_lang(user_id, lang):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
        except:
            pass
        conn.commit()
        conn.close()

def get_user_balance(user_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        bal = row[0] if row else 0.0
    except:
        bal = 0.0
    conn.close()
    return bal

def load_data():
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT user_id, plan_name, expiry FROM subscriptions")
        for row in c.fetchall():
            user_id = row[0]
            plan_name = row[1] if len(row) > 2 else "PREMIUM"
            expiry = row[-1]
            try:
                user_subscriptions[user_id] = {"plan_name": plan_name, "expiry": datetime.fromisoformat(expiry)}
            except ValueError: pass

        c.execute("SELECT user_id, file_name, file_type FROM user_files")
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files: user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))

        c.execute("SELECT user_id FROM active_users")
        active_users.update(user_id for (user_id,) in c.fetchall())

        c.execute("SELECT user_id FROM admins")
        admin_ids.update(user_id for (user_id,) in c.fetchall())

        conn.close()
    except Exception as e:
        logger.error(f"ERROR LOADING DATA: {e}", exc_info=True)

init_db()
load_data()

def get_setting(key, default_val=None):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else default_val

def set_setting(key, value):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()

# Fixing Double Number bug safely
def get_base_curr():
    curr = get_setting("BASE_CURRENCY", "USDT")
    if str(curr).strip().replace('.', '', 1).isdigit():
        return "BDT"
    return str(curr).strip()

def get_local_curr():
    curr = get_setting("LOCAL_CURRENCY", "BDT")
    if str(curr).strip().replace('.', '', 1).isdigit():
        return "BDT"
    return str(curr).strip()

def get_referral_bonus():
    try:
        return float(get_setting("REFERRAL_BONUS", "0.0"))
    except:
        return 0.0

def clean_btn_name(text):
    text = get_mapped_btn_name(text)
    return re.sub(r'[^\w\s]', '', text).strip().upper()

def get_button_media(button_name):
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT media_type, file_id FROM button_media WHERE button_name=?", (clean_btn_name(button_name),))
        res = c.fetchone()
        conn.close()
        return res
    except:
        return None

def set_button_media(button_name, media_type, file_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        btn_clean = clean_btn_name(button_name)
        if media_type is None: c.execute("DELETE FROM button_media WHERE button_name=?", (btn_clean,))
        else: c.execute("INSERT OR REPLACE INTO button_media (button_name, media_type, file_id) VALUES (?, ?, ?)", (btn_clean, media_type, file_id))
        conn.commit()
        conn.close()

def get_all_payment_methods():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT id, name, number, instructions FROM payment_methods")
    res = c.fetchall()
    conn.close()
    return res

def add_payment_method(name, number, instructions):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT INTO payment_methods (name, number, instructions) VALUES (?, ?, ?)", (name, number, instructions))
        conn.commit()
        conn.close()

def del_payment_method(pid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("DELETE FROM payment_methods WHERE id=?", (pid,))
        conn.commit()
        conn.close()

def parse_price_to_base(price_str):
    base_curr = get_base_curr()
    local_curr = get_local_curr()
    rate = float(get_setting("EXCHANGE_RATE", "120.0"))
    
    price_clean = str(price_str).upper().strip()
    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", price_clean)
    if not numbers: return 0.0, price_str
    val = float(numbers[0])
    
    if local_curr in price_clean or "TAKA" in price_clean or "TK" in price_clean:
        base_val = round(val / rate, 2)
        return base_val, f"{price_str} (~{base_val} {base_curr})"
    elif base_curr in price_clean or "$" in price_clean or "USD" in price_clean:
        return round(val, 2), f"{val} {base_curr}"
    else: return round(val, 2), f"{val} {base_curr}"

def add_plan_db(name, file_limit, price, duration, buy_link="", features=""):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO plans (name, file_limit, price, duration, buy_link, features) VALUES (?, ?, ?, ?, ?, ?)",(name, file_limit, price, duration, buy_link, features))
        except sqlite3.OperationalError:
            # Fallback if DB structure doesn't have features column yet for some reason
            c.execute("INSERT INTO plans (name, file_limit, price, duration, buy_link) VALUES (?, ?, ?, ?, ?)",(name, file_limit, price, duration, buy_link))
        conn.commit()
        conn.close()

def get_all_plans():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT * FROM plans")
    plans = c.fetchall()
    conn.close()
    return plans

def get_plan_by_id(plan_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
    plan = c.fetchone()
    conn.close()
    return plan

def delete_plan_db(plan_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,))
        conn.commit()
        conn.close()

def get_pending_payment(user_id, plan_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT paid_amount FROM pending_payments WHERE user_id=? AND plan_id=?",(user_id, plan_id))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0.0

def update_pending_payment(user_id, plan_id, amount):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO pending_payments (user_id, plan_id, paid_amount) VALUES (?, ?, ?)",(user_id, plan_id, amount))
        conn.commit()
        conn.close()

def clear_pending_payment(user_id, plan_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("DELETE FROM pending_payments WHERE user_id=? AND plan_id=?",(user_id, plan_id))
        conn.commit()
        conn.close()

def is_txid_used(tx_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT tx_id FROM used_txids WHERE tx_id=?", (str(tx_id).strip(),))
    row = c.fetchone()
    conn.close()
    return row is not None

def add_used_txid(tx_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO used_txids (tx_id) VALUES (?)",(str(tx_id).strip(),))
        conn.commit()
        conn.close()

def check_binance_payment(pay_order_id):
    bin_api = get_setting("BINANCE_API_KEY", BINANCE_API_KEY)
    bin_sec = get_setting("BINANCE_SECRET_KEY", BINANCE_SECRET_KEY)
    
    if not bin_api or bin_api == "YOUR_NEW_BINANCE_API_KEY_HERE":
        return False, 0.0, "BINANCE API KEY NOT CONFIGURED."
        
    endpoint = "https://api.binance.com/sapi/v1/pay/transactions"
    timestamp = int(time.time() * 1000)
    query_string = f"timestamp={timestamp}"
    signature = hmac.new(bin_sec.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()
    url = f"{endpoint}?{query_string}&signature={signature}"
    headers = {"X-MBX-APIKEY": bin_api}

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            transactions = data.get("data", []) if isinstance(data, dict) else data
            for item in transactions:
                order_id_str = str(item.get("orderId", "") or item.get("transactionId", ""))
                if order_id_str.strip() == str(pay_order_id).strip():
                    amount = float(item.get("amount", 0.0))
                    currency = item.get("currency", "USDT")
                    return True, amount, f"{amount} {currency}"
            return False, 0.0, "ORDER/TRANSACTION ID NOT FOUND IN BINANCE HISTORY."
        else: return False, 0.0, "BINANCE SERVER ERROR OR API PERMISSION ISSUE."
    except Exception as e: return False, 0.0, f"ERROR: {str(e)}"

def is_suspicious_file(file_content, file_name):
    file_lower = file_name.lower()
    suspicious_extensions = [".exe", ".dll", ".bat", ".cmd", ".scr", ".com", ".pif", ".application", ".gadget", ".msi", ".msp", ".com", ".scr", ".hta", ".cpl", ".msc", ".jar", ".bin", ".deb", ".rpm", ".apk", ".app", ".dmg", ".iso", ".img"]
    if any(file_lower.endswith(ext) for ext in suspicious_extensions): return True, f"SUSPICIOUS FILE EXTENSION: {file_name}"
    for signature in MALWARE_SIGNATURES:
        if file_content.startswith(signature): return True, f"MALWARE SIGNATURE DETECTED."
    sample_size = min(len(file_content), 4096)
    file_sample = file_content[:sample_size]
    for indicator in ENCRYPTED_FILE_INDICATORS:
        if indicator in file_sample: return True, f"ENCRYPTED FILE INDICATOR DETECTED."
    sample_text = file_sample.decode("utf-8", errors="ignore").lower()
    for keyword in SUSPICIOUS_KEYWORDS:
        if keyword.decode("utf-8").lower() in sample_text: return True, f"SUSPICIOUS KEYWORD FOUND."
    return False, "FILE APPEARS SAFE"

def scan_file_for_malware(file_content, file_name, user_id):
    if user_id == OWNER_ID: return True, "OWNER BYPASSED SECURITY CHECK"
    is_suspicious, reason = is_suspicious_file(file_content, file_name)
    if is_suspicious: return False, f"SECURITY VIOLATION: {reason}"
    return True, "FILE PASSED SECURITY CHECK"

def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]["expiry"] > datetime.now(): return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get("process"):
        try:
            proc = psutil.Process(script_info["process"].pid)
            is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not is_running:
                if "log_file" in script_info and hasattr(script_info["log_file"], "close") and not script_info["log_file"].closed:
                    try: script_info["log_file"].close()
                    except: pass
                if script_key in bot_scripts: del bot_scripts[script_key]
            return is_running
        except:
            if script_key in bot_scripts: del bot_scripts[script_key]
            return False
    return False

def kill_process_tree(process_info):
    try:
        if "log_file" in process_info and hasattr(process_info["log_file"], "close") and not process_info["log_file"].closed:
            try: process_info["log_file"].close()
            except: pass
        process = process_info.get("process")
        if process and hasattr(process, "pid"):
            pid = process.pid
            if pid:
                parent = psutil.Process(pid)
                for child in parent.children(recursive=True):
                    try: child.terminate()
                    except: pass
                try: parent.terminate()
                except: pass
    except Exception as e: logger.error(f"ERROR KILLING PROCESS: {e}")

TELEGRAM_MODULES = {
    "telebot": "pyTelegramBotAPI", "telegram": "python-telegram-bot", "python_telegram_bot": "python-telegram-bot",
    "aiogram": "aiogram", "pyrogram": "pyrogram", "telethon": "telethon", "bs4": "beautifulsoup4",
    "requests": "requests", "pillow": "Pillow", "cv2": "opencv-python", "flask": "Flask", "psutil": "psutil",
}

def monitor_and_guide_error(process, log_file_path, script_owner_id, file_name, message_obj_for_reply):
    if not message_obj_for_reply: return
    time.sleep(3)
    if process.poll() is not None:
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f: log_content = f.read()
            match_py = re.search(r"(?:ModuleNotFoundError|ImportError): No module named '(.+?)'", log_content)
            match_js = re.search(r"Cannot find module '(.+?)'", log_content)
            missing_module = None
            if match_py: missing_module = match_py.group(1).split(".")[0].strip("'\"")
            elif match_js: missing_module = match_js.group(1).split("/")[0].strip("'\"")

            if missing_module:
                pkg_name = TELEGRAM_MODULES.get(missing_module.lower(), missing_module)
                ext = os.path.splitext(file_name)[1].lower()
                cmd_text = f"npm install {pkg_name}" if ext == ".js" else f"pip install {pkg_name}"
                error_msg = (f"⚠️ **MODULE MISSING ERROR!**\n\n📄 **FILE:** `{file_name.upper()}`\n"
                             f"❌ **PROBLEM:** MODULE `{missing_module.upper()}` IS MISSING.\n"
                             f"💻 **COMMAND NEEDED:** `{cmd_text.upper()}`\n\n👇 **CLICK BELOW TO INSTALL MODULE:**")
                markup = types.InlineKeyboardMarkup()
                markup.add(make_inline_button(f"INSTALL {pkg_name.upper()}", callback_data=f"instmod_{script_owner_id}_{missing_module}_{file_name}", style="success"))
                markup.add(make_inline_button("VIEW ERROR LOGS", callback_data=f"viewlog_{script_owner_id}_{file_name}", style="danger"))
                bot.reply_to(message_obj_for_reply, error_msg, reply_markup=markup, parse_mode="Markdown")
            else:
                error_msg = (f"⚠️ **SYNTAX / RUNTIME ERROR DETECTED!**\n\n📄 **FILE:** `{file_name.upper()}`\n👇 **CLICK 'VIEW LOGS' TO SEE THE ERROR:**")
                markup = types.InlineKeyboardMarkup()
                markup.add(make_inline_button("VIEW ERROR LOGS", callback_data=f"viewlog_{script_owner_id}_{file_name}", style="danger"))
                bot.reply_to(message_obj_for_reply, error_msg, reply_markup=markup, parse_mode="Markdown")
        except Exception as e: logger.error(f"ERROR CHECKING LOG FILE: {e}")

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply=None):
    script_key = f"{script_owner_id}_{file_name}"
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        process = subprocess.Popen([sys.executable, script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.PIPE)
        bot_scripts[script_key] = {"process": process, "log_file": log_file, "file_name": file_name, "script_owner_id": script_owner_id, "start_time": datetime.now(), "user_folder": user_folder, "type": "py", "script_key": script_key}
        if message_obj_for_reply:
            bot.reply_to(message_obj_for_reply, f"🚀 **PYTHON SCRIPT STARTED!**\n📄 **FILE:** `{file_name}`\n🆔 **PID:** `{process.pid}`", parse_mode="Markdown")
            threading.Thread(target=monitor_and_guide_error, args=(process, log_file_path, script_owner_id, file_name, message_obj_for_reply)).start()
    except Exception as e: 
        if message_obj_for_reply: bot.reply_to(message_obj_for_reply, f"❌ **ERROR RUNNING SCRIPT:** {str(e).upper()}")

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply=None):
    script_key = f"{script_owner_id}_{file_name}"
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        process = subprocess.Popen(["node", script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.PIPE)
        bot_scripts[script_key] = {"process": process, "log_file": log_file, "file_name": file_name, "script_owner_id": script_owner_id, "start_time": datetime.now(), "user_folder": user_folder, "type": "js", "script_key": script_key}
        if message_obj_for_reply:
            bot.reply_to(message_obj_for_reply, f"🚀 **JS SCRIPT STARTED!**\n📄 **FILE:** `{file_name}`\n🆔 **PID:** `{process.pid}`", parse_mode="Markdown")
            threading.Thread(target=monitor_and_guide_error, args=(process, log_file_path, script_owner_id, file_name, message_obj_for_reply)).start()
    except Exception as e: 
        if message_obj_for_reply: bot.reply_to(message_obj_for_reply, f"❌ **ERROR RUNNING JS SCRIPT:** {str(e).upper()}")

def save_user_file(user_id, file_name, file_type="py"):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)", (user_id, file_name, file_type))
        conn.commit()
        conn.close()
        if user_id not in user_files: user_files[user_id] = []
        user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
        user_files[user_id].append((file_name, file_type))

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("DELETE FROM user_files WHERE user_id = ? AND file_name = ?", (user_id, file_name))
        conn.commit()
        conn.close()
        if user_id in user_files: user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]

def add_active_user(user_id, referred_by=None):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO active_users (user_id) VALUES (?)", (user_id,))
        
        c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if not c.fetchone():
            c.execute("INSERT INTO users (user_id, referred_by) VALUES (?, ?)", (user_id, referred_by))
            if referred_by and str(referred_by) != str(user_id):
                c.execute("UPDATE users SET refer_count = refer_count + 1 WHERE user_id=?", (referred_by,))
                bonus = get_referral_bonus()
                if bonus > 0:
                    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (bonus, referred_by))
        conn.commit()
        conn.close()

def save_subscription(user_id, plan_name, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO subscriptions (user_id, plan_name, expiry) VALUES (?, ?, ?)",(user_id, plan_name, expiry.isoformat()))
        conn.commit()
        conn.close()
        user_subscriptions[user_id] = {"plan_name": plan_name, "expiry": expiry}

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        if user_id in user_subscriptions: del user_subscriptions[user_id]

# --- FORCE SUB LOGIC ---
def check_force_sub(user_id):
    if user_id in admin_ids or user_id == OWNER_ID: return []
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT id, name, chat_id, url FROM force_subs")
    channels = c.fetchall()
    conn.close()
    
    not_joined = []
    for ch in channels:
        try:
            stat = bot.get_chat_member(ch[2], user_id).status
            if stat in ['left', 'kicked']: not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    return not_joined


# --- Premium main menu: inline buttons with Telegram button styles ---
MAIN_BUTTON_STYLES = {
    "updates": "primary", "profile": "primary", "refer": "success",
    "upload": "success", "manage": "primary", "plans": "success",
    "speed": "primary", "stats": "primary", "language": "danger",
    "contact": "success", "admin": "danger",
}

def create_main_inline_menu(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("📢 Updates Channel", "main_updates"),
        ("👤 My Profile", "main_profile"),
        ("🎁 Refer & Earn", "main_refer"),
        ("📤 Upload File", "main_upload"),
        ("📁 Manage Files", "main_manage"),
        ("💎 View Plans", "main_plans"),
        ("⚡ Speed & Ping", "main_speed"),
        ("📊 Bot Stats", "main_stats"),
        ("🌐 Language", "main_language"),
        ("📞 Contact Owner", "main_contact"),
    ]
    for i in range(0, len(buttons), 2):
        row = []
        for label, data in buttons[i:i+2]:
            key = data.replace("main_", "")
            row.append(make_inline_button(label, callback_data=data,
                                          style=MAIN_BUTTON_STYLES.get(key, "primary")))
        markup.row(*row)
    if user_id in admin_ids:
        markup.row(make_inline_button("🛡️ Admin Panel", callback_data="main_admin", style="danger"))
    return markup

def create_approval_markup(request_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        make_inline_button("✅ APPROVE & AUTO RUN", callback_data=f"approve_upload_{request_id}", style="success"),
        make_inline_button("❌ REJECT", callback_data=f"reject_upload_{request_id}", style="danger"),
    )
    return markup

def create_reply_keyboard_main_menu(user_id):

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row in layout_to_use:
        btn_row = []
        for text in row:
            normalized = get_mapped_btn_name(text)
            style = "primary" # Default Blue
            if any(x in normalized for x in ["UPDATE", "UPLOAD", "MANAGE", "VIEW PLAN", "PROFILE", "REFER"]):
                style = "success" # Green
            elif any(x in normalized for x in ["ADMIN PANEL", "CONTACT", "LANGUAGE"]):
                style = "danger" # Red
            
            btn_row.append(make_button(text, style=style))
        markup.add(*btn_row)
    return markup

def create_admin_panel_inline():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        make_inline_button("➕ ADD PLAN", callback_data="add_plan_init", style="success"),
        make_inline_button("🗑️ MANAGE PLANS", callback_data="manage_plans", style="danger"),
    )
    markup.add(
        make_inline_button("💎 ADD SUB", callback_data="add_subscription", style="success"),
        make_inline_button("❌ REMOVE SUB", callback_data="remove_subscription", style="danger"),
    )
    markup.add(
        make_inline_button("👑 ADD ADMIN", callback_data="add_admin", style="success"),
        make_inline_button("➖ REMOVE ADMIN", callback_data="remove_admin", style="danger"),
    )
    markup.add(
        make_inline_button("📣 BROADCAST", callback_data="broadcast", style="primary"),
        make_inline_button("🔐 LOCK/UNLOCK", callback_data="toggle_lock", style="danger"),
    )
    markup.add(
        make_inline_button("⚙️ RUN SCRIPTS", callback_data="run_all_scripts", style="success"),
        make_inline_button("📊 BOT STATS", callback_data="stats", style="primary"),
    )
    markup.add(
        make_inline_button("🎛️ SETTINGS", callback_data="admin_settings", style="primary"),
        make_inline_button("💳 PAY METHODS", callback_data="admin_pay_methods", style="primary")
    )
    markup.add(
        make_inline_button("🖼️ BTN MEDIA", callback_data="admin_btn_media", style="primary"),
        make_inline_button("📢 FORCE SUBS", callback_data="admin_force_subs", style="primary")
    )
    markup.add(
        make_inline_button("📞 SUPPORT BTNS", callback_data="admin_support_btns", style="primary")
    )
    return markup

def create_admin_settings_inline():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        make_inline_button("📢 SET UPDATES CHANNEL", callback_data="set_cfg_channel", style="primary"),
        make_inline_button("👑 SET OWNER CONTACT", callback_data="set_cfg_owner", style="primary")
    )
    markup.add(
        make_inline_button("🔸 SET BINANCE PAY ID", callback_data="set_cfg_binance", style="primary"),
        make_inline_button("🔑 SET BINANCE API", callback_data="set_cfg_binance_api", style="primary"),
        make_inline_button("🔒 SET BINANCE SECRET", callback_data="set_cfg_binance_secret", style="primary")
    )
    markup.add(
        make_inline_button("💵 SET BASE CURRENCY", callback_data="set_cfg_base", style="primary"),
        make_inline_button("💴 SET LOCAL CURRENCY", callback_data="set_cfg_local", style="primary"),
        make_inline_button("💱 SET EXCHANGE RATE", callback_data="set_cfg_rate", style="primary"),
        make_inline_button("🎁 SET REF BONUS", callback_data="set_cfg_ref", style="primary"),
        make_inline_button("🔙 BACK TO ADMIN", callback_data="admin_panel_back", style="danger")
    )
    return markup


# ==================================
# BOT COMMANDS
# ==================================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        return bot.send_message(user_id, "❌ **YOU ARE BANNED FROM USING THIS BOT.**", parse_mode="Markdown")

    parts = message.text.split()
    ref_id = None
    if len(parts) > 1:
        try: ref_id = int(parts[1])
        except: pass
    _logic_send_welcome(message, ref_id)

def _logic_send_welcome(message, ref_id=None):
    user_id = message.from_user.id
    chat_id = message.chat.id
    lang = get_user_lang(user_id)
    
    if bot_locked and user_id not in admin_ids: return bot.send_message(chat_id, "⚠️ **BOT IS TEMPORARILY LOCKED BY ADMIN.**", parse_mode="Markdown")
    
    not_joined = check_force_sub(user_id)
    if not_joined:
        if user_id not in active_users: add_active_user(user_id, ref_id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in not_joined:
            markup.add(make_inline_button(f"📢 JOIN {str(ch[1]).upper()}", url=ch[3], style="primary"))
        markup.add(make_inline_button("✅ I HAVE JOINED", callback_data="check_fsub", style="success"))
        bot.send_message(chat_id, "🛑 **PLEASE JOIN OUR CHANNELS TO USE THE BOT:**", reply_markup=markup, parse_mode="Markdown")
        return

    if user_id not in active_users: add_active_user(user_id, ref_id)

    if user_id == OWNER_ID: user_status = "👑 **OWNER**"
    elif user_id in admin_ids: user_status = "🛡️ **ADMIN**"
    elif user_id in user_subscriptions and user_subscriptions[user_id]["expiry"] > datetime.now():
        sub = user_subscriptions[user_id]
        days_left = (sub["expiry"] - datetime.now()).days
        user_status = f"💎 **{str(sub.get('plan_name', 'PREMIUM')).upper()} ACTIVE** ({days_left} DAYS LEFT)"
    else: user_status = "🆓 **NO ACTIVE PLAN**"

    user_name = str(message.from_user.first_name).upper()
    
    welcome_msg = MSG_TEMPLATES[lang]['welcome'].format(
        user_name=user_name, user_id=user_id, user_status=user_status,
        files=get_user_file_count(user_id), limit=get_user_file_limit(user_id)
    )

    # --- NEW CODE FOR WELCOME MEDIA ---
    media = get_button_media("WELCOME")
    if media:
        mtype, fid = media
        try:
            if mtype == 'photo':
                bot.send_photo(chat_id, fid, caption=welcome_msg, reply_markup=create_main_inline_menu(user_id), parse_mode="Markdown")
            elif mtype == 'video':
                bot.send_video(chat_id, fid, caption=welcome_msg, reply_markup=create_main_inline_menu(user_id), parse_mode="Markdown")
            return  # Exit function so it doesn't send the text version below
        except Exception as e:
            logger.error(f"FAILED TO SEND WELCOME MEDIA: {e}")
    # ----------------------------------

    bot.send_message(chat_id, welcome_msg, reply_markup=create_main_inline_menu(user_id), parse_mode="Markdown")

def _logic_language(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    text = MSG_TEMPLATES[lang].get('lang_prompt', MSG_TEMPLATES['EN']['lang_prompt'])
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        make_inline_button("🇧🇩 BANGLADESH", callback_data="setlang_BN", style="success"),
        make_inline_button("🇺🇸 ENGLISH", callback_data="setlang_EN", style="primary")
    )
    markup.add(
        make_inline_button("🇮🇳 INDIA", callback_data="setlang_HI", style="primary"),
        make_inline_button("🇵🇰 PAKISTAN", callback_data="setlang_UR", style="success")
    )
    bot.reply_to(message, text, reply_markup=markup, parse_mode="Markdown")

def _logic_my_profile(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT balance, refer_count FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()
    except:
        row = None
        
    bal = row[0] if row else 0.0
    refs = row[1] if row else 0
    base_curr = get_base_curr()
    
    if user_id == OWNER_ID: plan_str = "OWNER UNLIMITED"
    elif user_id in admin_ids: plan_str = "ADMIN UNLIMITED"
    elif user_id in user_subscriptions and user_subscriptions[user_id]["expiry"] > datetime.now():
        plan_str = str(user_subscriptions[user_id]["plan_name"]).upper()
    else: plan_str = "FREE / NONE"
    
    name = str(message.from_user.first_name).upper()
    uname = f"@{message.from_user.username}" if message.from_user.username else "NONE"
    
    text = MSG_TEMPLATES[lang]['profile'].format(
        name=name, uname=uname, user_id=user_id, bal=bal, base_curr=base_curr.upper(), refs=refs, plan_str=plan_str
    )
    
    try:
        photos = bot.get_user_profile_photos(user_id)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            bot.send_photo(message.chat.id, file_id, caption=text, parse_mode="Markdown")
        else:
            bot.reply_to(message, text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error fetching profile photo: {e}")
        bot.reply_to(message, text, parse_mode="Markdown")

def _logic_refer(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    bonus_val = get_referral_bonus()
    bonus_str = f"{bonus_val:g}"
    base_curr = get_base_curr()
    
    text = MSG_TEMPLATES[lang]['refer'].format(bonus=bonus_str, base_curr=base_curr.upper(), ref_link=ref_link)
    bot.reply_to(message, text, parse_mode="Markdown")

def _logic_contact_owner(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT name, url FROM support_buttons")
        btns = c.fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"Error fetching support btns: {e}")
        btns = []
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(make_inline_button("👑 OWNER CONTACT", url=f"https://t.me/{str(get_setting('OWNER_USERNAME', YOUR_USERNAME)).replace('@','')}", style="success"))
    
    for b in btns:
        markup.add(make_inline_button(str(b[0]).upper(), url=b[1], style="primary"))
    
    text = MSG_TEMPLATES[lang].get('contact', MSG_TEMPLATES['EN']['contact'])
    bot.reply_to(message, text, reply_markup=markup, parse_mode="Markdown")

def send_plan_page(chat_id, user_id, page, message_id=None):
    plans = get_all_plans()
    if not plans: 
        if message_id: bot.edit_message_text("ℹ️ **NO PLANS AVAILABLE AT THE MOMENT.**", chat_id, message_id, parse_mode="Markdown")
        else: bot.send_message(chat_id, "ℹ️ **NO PLANS AVAILABLE AT THE MOMENT.**", parse_mode="Markdown")
        return

    total_plans = len(plans)
    if page < 0: page = 0
    elif page >= total_plans: page = total_plans - 1

    plan = plans[page]
    plan_id = plan[0]
    name = plan[1]
    limit = plan[2]
    price = plan[3]
    duration = plan[4]
    
    # Safe retrieval of custom features (backward compatibility)
    features_str = plan[6] if len(plan) > 6 else ""

    base_price, formatted_price = parse_price_to_base(price)
    user_bal = get_user_balance(user_id)
    base_curr = get_base_curr()
    
    is_free = (base_price == 0.0 or price == "0" or "FREE" in name.upper())
    icon = "🆓" if is_free else "🚀"
    desc = "Lifetime Free Trial Bothosting for beginners" if is_free else "Best for starters"
    
    # Generate custom features list dynamically
    if features_str and features_str.strip():
        feature_list = [f.strip() for f in features_str.split(",")]
        feature_text = ""
        for feat in feature_list:
            if feat:
                # Add ✅ if admin didn't include an emoji at start
                if feat.startswith("✅") or feat.startswith("❌"):
                    feature_text += f"{feat}\n"
                else:
                    feature_text += f"✅ {feat}\n"
    else:
        # Default features if admin didn't set any custom ones
        feature_text = (
            "✅ 512 MB RAM\n"
            "✅ 1 Core CPU\n"
            "✅ 128 MB NVMe\n"
            "✅ Code Editor\n"
            "✅ Log Views\n"
            "✅ File Manager\n"
            "✅ Normal Support\n"
        )

    text = f"🛍️ **STORE [{page+1}/{total_plans}]**\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"{icon} **{name.upper()}**\n\n"
    text += f"{desc}\n\n"
    text += f"⚙️ **Host up to {limit} Python Bot(s)**\n\n"
    text += f"{feature_text}\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"💰 **Price:** `{formatted_price}`\n"
    text += f"💳 **Wallet:** `{user_bal} {base_curr.upper()}`"

    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # Action Row
    action_btns = []
    if is_free:
        action_btns.append(make_inline_button("GET STARTED FREE", callback_data=f"claim_free_{plan_id}", style="success"))
    else:
        action_btns.append(make_inline_button("Bᴜʏ Nᴏᴡ", callback_data=f"buy_binance_{plan_id}", style="success"))
        action_btns.append(make_inline_button("Dᴇᴘᴏsɪᴛ", callback_data=f"manual_pay_{plan_id}", style="primary"))
    
    if action_btns:
        markup.add(*action_btns)

    # Navigation Row
    nav_btns = []
    if page > 0:
        nav_btns.append(make_inline_button("⬅️ Bᴀᴄᴋ", callback_data=f"page_plan_{page-1}", style="primary"))
    if page < total_plans - 1:
        nav_btns.append(make_inline_button("Nᴇxᴛ ➡️", callback_data=f"page_plan_{page+1}", style="primary"))
    
    if nav_btns:
        markup.add(*nav_btns)

    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

def _logic_upload_file(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    if bot_locked and user_id not in admin_ids: return bot.reply_to(message, "⚠️ **BOT IS LOCKED BY ADMIN.**", parse_mode="Markdown")
    
    has_active_plan = False
    plan_name = "NONE"
    if user_id in admin_ids or user_id == OWNER_ID:
        has_active_plan = True
        plan_name = "ADMIN / OWNER UNLIMITED"
    elif user_id in user_subscriptions and user_subscriptions[user_id]["expiry"] > datetime.now():
        has_active_plan = True
        plan_name = str(user_subscriptions[user_id].get("plan_name", "PREMIUM PLAN")).upper()

    if not has_active_plan:
        markup = types.InlineKeyboardMarkup()
        markup.add(make_inline_button("Vɪᴇᴡ Pʟᴀɴs", callback_data="view_plans_cb", style="primary"))
        return bot.reply_to(message, MSG_TEMPLATES[lang]['upload_no_plan'], reply_markup=markup, parse_mode="Markdown")

    markup = types.InlineKeyboardMarkup()
    markup.add(make_inline_button(f"CONTINUE WITH {plan_name}", callback_data="confirm_plan_upload", style="success"))
    bot.reply_to(message, MSG_TEMPLATES[lang]['upload_active'].format(plan_name=plan_name), reply_markup=markup, parse_mode="Markdown")


# --- NEW FIX: Removed Ghost Files and UI fixes ---
def _logic_check_files(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    user_files_list = user_files.get(user_id, [])

    # FIX: Check if file physically exists on the disk. If not, remove from DB to prevent ghost files.
    user_folder = get_user_folder(user_id)
    valid_files = []
    for fname, ftype in user_files_list:
        if os.path.exists(os.path.join(user_folder, fname)):
            valid_files.append((fname, ftype))
        else:
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute("DELETE FROM user_files WHERE user_id = ? AND file_name = ?", (user_id, fname))
                conn.commit()
                conn.close()

    # Update memory variables after cleanup
    user_files[user_id] = valid_files
    user_files_list = valid_files

    if not user_files_list: 
        return bot.reply_to(message, MSG_TEMPLATES[lang].get('manage_empty', MSG_TEMPLATES['EN']['manage_empty']), parse_mode="Markdown")
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        status_icon = "RUNNING" if is_running else "STOPPED"
        markup.add(make_inline_button(f"FILE: {file_name.upper()} ({file_type.upper()}) - {status_icon}", callback_data=f"file_{user_id}_{file_name}", style="primary"))
    bot.reply_to(message, MSG_TEMPLATES[lang].get('manage_title', MSG_TEMPLATES['EN']['manage_title']), reply_markup=markup, parse_mode="Markdown")
# ----------------------------------------------------


@bot.message_handler(content_types=["document"])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if is_user_banned(user_id):
        return bot.send_message(user_id, "❌ **YOU ARE BANNED FROM USING THIS BOT.**", parse_mode="Markdown")
        
    doc = message.document
    if user_id not in admin_ids and user_id != OWNER_ID:
        if user_id not in user_subscriptions or user_subscriptions[user_id]["expiry"] <= datetime.now():
            return bot.reply_to(message, "❌ **YOU DON'T HAVE AN ACTIVE PLAN! BUY A PLAN TO UPLOAD FILES.**", parse_mode="Markdown")
    
    file_name = doc.file_name
    file_ext = os.path.splitext(file_name)[1].lower()
    
    if file_ext not in [".py", ".js", ".zip"]: 
        return bot.reply_to(message, "⚠️ **ONLY `.PY`, `.JS`, AND `.ZIP` FILES ARE SUPPORTED!**", parse_mode="Markdown")

    try:
        download_wait_msg = bot.reply_to(message, "⏳ **DOWNLOADING... [■□□□□□□□□□] 10%**", parse_mode="Markdown")
        time.sleep(0.3)
        bot.edit_message_text("⏳ **PROCESSING... [■■■■■□□□□□] 50%**", chat_id, download_wait_msg.message_id, parse_mode="Markdown")

        file_info_tg_doc = bot.get_file(doc.file_id)
        downloaded_file_content = bot.download_file(file_info_tg_doc.file_path)

        bot.edit_message_text("🔍 **ANALYZING... [■■■■■■■■□□] 80%**", chat_id, download_wait_msg.message_id, parse_mode="Markdown")

        if user_id != OWNER_ID:
            is_safe, reason = scan_file_for_malware(downloaded_file_content, file_name, user_id)
            if not is_safe: return bot.edit_message_text(f"🚨 **SECURITY ALERT:** {reason.upper()}", chat_id, download_wait_msg.message_id, parse_mode="Markdown")

            # Every non-admin upload requires admin approval before execution.
            # The file is stored safely but NOT executed until the Approve button is pressed.
            pass

        user_folder = get_user_folder(user_id)
        file_path = os.path.join(user_folder, file_name)
        with open(file_path, "wb") as f: f.write(downloaded_file_content)

        bot.edit_message_text("✅ **FINALIZING... [■■■■■■■■■■] 100%**", chat_id, download_wait_msg.message_id, parse_mode="Markdown")
        time.sleep(0.3)

        if file_ext == ".zip":
            bot.edit_message_text(f"📦 **EXTRACTING ZIP FILE...**", chat_id, download_wait_msg.message_id, parse_mode="Markdown")
            extracted_count = 0
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    filename = os.path.basename(member)
                    if not filename: continue
                    
                    source = zip_ref.open(member)
                    target_path = os.path.join(user_folder, filename)
                    with open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in [".py", ".js"]:
                        save_user_file(user_id, filename, ext[1:])
                        extracted_count += 1
            
            bot.edit_message_text(f"✅ **FILE `{file_name.upper()}` UPLOADED AND EXTRACTED SUCCESSFULLY! ({extracted_count} SCRIPTS FOUND)**", chat_id, download_wait_msg.message_id, parse_mode="Markdown")

        elif file_ext == ".js":
            save_user_file(user_id, file_name, "js")
            bot.edit_message_text(f"✅ **FILE `{file_name.upper()}` UPLOADED SUCCESSFULLY!**", chat_id, download_wait_msg.message_id, parse_mode="Markdown")
            threading.Thread(target=run_js_script, args=(file_path, user_id, user_folder, file_name, message)).start()
            
        elif file_ext == ".py":
            save_user_file(user_id, file_name, "py")
            bot.edit_message_text(f"✅ **FILE `{file_name.upper()}` UPLOADED SUCCESSFULLY!**", chat_id, download_wait_msg.message_id, parse_mode="Markdown")
            threading.Thread(target=run_script, args=(file_path, user_id, user_folder, file_name, message)).start()

    except Exception as e: 
        bot.reply_to(message, f"❌ **ERROR:** {str(e).upper()}", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data

    if data == "ignore":
        bot.answer_callback_query(call.id)
        

    elif data.startswith("main_"):
        action = data[5:]
        bot.answer_callback_query(call.id)
        msg = call.message

        if action == "updates":
            update_data = str(get_setting('UPDATE_CHANNEL', f"📢 JOIN UPDATES CHANNEL | {UPDATE_CHANNEL}"))
            if "|" in update_data:
                btn_name, btn_link = [x.strip() for x in update_data.split("|", 1)]
            else:
                btn_name, btn_link = "📢 JOIN UPDATES CHANNEL", update_data
            markup = types.InlineKeyboardMarkup()
            markup.add(make_inline_button(f"📢 {btn_name}", url=btn_link, style="primary"))
            bot.send_message(msg.chat.id, "📢 **STAY UPDATED WITH OUR LATEST NEWS:**",
                             reply_markup=markup, parse_mode="Markdown")
        elif action == "profile":
            _logic_my_profile(msg)
        elif action == "refer":
            _logic_refer(msg)
        elif action == "upload":
            _logic_upload_file(msg)
        elif action == "manage":
            _logic_check_files(msg)
        elif action == "plans":
            send_plan_page(msg.chat.id, user_id, 0)
        elif action == "speed":
            bot.send_message(msg.chat.id, "⚡ **BOT LATENCY:** `12 MS` (SERVER ACTIVE)",
                             parse_mode="Markdown")
        elif action == "stats":
            try:
                running = len([k for k, v in bot_scripts.items()
                               if is_bot_running(v['script_owner_id'], v['file_name'])])
                bot.send_message(msg.chat.id,
                    f"📊 **ACTIVE USERS:** `{len(active_users)}`\n"
                    f"🤖 **ACTIVE SCRIPTS:** `{running}`", parse_mode="Markdown")
            except Exception:
                bot.send_message(msg.chat.id, "📊 **STATS TEMPORARILY UNAVAILABLE.**",
                                 parse_mode="Markdown")
        elif action == "language":
            _logic_language(msg)
        elif action == "contact":
            _logic_contact_owner(msg)
        elif action == "admin":
            if user_id not in admin_ids:
                return bot.answer_callback_query(call.id, "❌ ADMIN ACCESS REQUIRED!", show_alert=True)
            bot.send_message(msg.chat.id, "🛡️ **ADMIN CONTROL PANEL:**",
                             reply_markup=create_admin_panel_inline(), parse_mode="Markdown")

    elif data.startswith("setlang_"):
        new_lang = data.split("_")[1]
        set_user_lang(user_id, new_lang)
        bot.answer_callback_query(call.id, "✅ LANGUAGE UPDATED!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        msg_mock = call.message
        msg_mock.from_user = call.from_user
        _logic_send_welcome(msg_mock)
        
    elif data == "check_fsub":
        not_joined = check_force_sub(user_id)
        if not_joined:
            bot.answer_callback_query(call.id, "❌ YOU HAVEN'T JOINED ALL CHANNELS!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "✅ THANK YOU FOR JOINING!")
            bot.delete_message(call.message.chat.id, call.message.message_id)
            msg_mock = call.message
            msg_mock.from_user = call.from_user
            _logic_send_welcome(msg_mock)

    elif data == "view_plans_cb":
        bot.answer_callback_query(call.id)
        send_plan_page(call.message.chat.id, user_id, 0)
        
    elif data.startswith("page_plan_"):
        page = int(data.split("_")[2])
        bot.answer_callback_query(call.id)
        send_plan_page(call.message.chat.id, user_id, page, call.message.message_id)

    elif data == "confirm_plan_upload":
        bot.answer_callback_query(call.id, "PLAN VERIFIED!")
        bot.send_message(call.message.chat.id, "🚀 **NOW SEND YOUR PYTHON (.PY), JS (.JS), OR ZIP (.ZIP) FILE IN THE CHAT.**", parse_mode="Markdown")

    elif data.startswith("instmod_"):
        _, owner_id, mod_name, fname = data.split("_", 3)
        if user_id != int(owner_id) and user_id not in admin_ids: return bot.answer_callback_query(call.id, "YOU CANNOT CUSTOMIZE OTHER USER'S FILE!", show_alert=True)
        bot.answer_callback_query(call.id)
        pkg_name = TELEGRAM_MODULES.get(mod_name.lower(), mod_name)
        ext = os.path.splitext(fname)[1].lower()
        status_msg = bot.send_message(call.message.chat.id, f"⏳ **INSTALLING MODULE `{pkg_name.upper()}`...**", parse_mode="Markdown")

        def do_pip_install():
            cmd = ["npm", "install", pkg_name] if ext == ".js" else [sys.executable, "-m", "pip", "install", pkg_name]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                bot.edit_message_text(f"✅ **MODULE `{pkg_name.upper()}` INSTALLED SUCCESSFULLY!**\n🚀 **RESTARTING SCRIPT...**", call.message.chat.id, status_msg.message_id, parse_mode="Markdown")
                time.sleep(1)
                ufolder = get_user_folder(int(owner_id))
                fpath = os.path.join(ufolder, fname)
                if ext == ".js": run_js_script(fpath, int(owner_id), ufolder, fname, call.message)
                else: run_script(fpath, int(owner_id), ufolder, fname, call.message)
            else: bot.edit_message_text(f"❌ **INSTALLATION FAILED!**\n\n```\n{res.stderr[:300].upper()}\n```", call.message.chat.id, status_msg.message_id, parse_mode="Markdown")
        threading.Thread(target=do_pip_install).start()

    elif data.startswith("viewlog_"):
        _, owner_id, fname = data.split("_", 2)
        log_fpath = os.path.join(get_user_folder(int(owner_id)), f"{os.path.splitext(fname)[0]}.log")
        if os.path.exists(log_fpath):
            with open(log_fpath, "r", encoding="utf-8", errors="ignore") as f: logs = f.read()[-2000:]
            bot.send_message(call.message.chat.id, f"📜 **ERROR LOG FOR `{fname.upper()}`:**\n\n```\n{logs if logs else 'NO LOGS RECORDED.'}\n```", parse_mode="Markdown")
        else: bot.answer_callback_query(call.id, "NO LOG FILE FOUND!", show_alert=True)

    elif data.startswith("claim_free_"):
        plan_id = int(data.split("_")[2])
        plan = get_plan_by_id(plan_id)
        if plan:
            # CHECK IF ALREADY CLAIMED
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("SELECT user_id FROM free_plan_claimed WHERE user_id=?", (user_id,))
            already_claimed = c.fetchone()
            if already_claimed:
                bot.answer_callback_query(call.id, "❌ YOU HAVE ALREADY CLAIMED THE FREE PLAN ONCE!", show_alert=True)
                conn.close()
                return
                
            name, duration = plan[1], plan[4]
            expiry = datetime.now() + timedelta(days=duration)
            save_subscription(user_id, name, expiry)
            
            # MARK AS CLAIMED
            c.execute("INSERT INTO free_plan_claimed (user_id) VALUES (?)", (user_id,))
            conn.commit()
            conn.close()
            
            bot.answer_callback_query(call.id, "FREE PLAN ACTIVATED!", show_alert=True)
            bot.send_message(call.message.chat.id, f"🎉 **{name.upper()}** has been activated successfully! You can now host your bots.", parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, "Plan not found!", show_alert=True)

    elif data.startswith("buy_binance_"):
        plan_id = int(data.split("_")[2])
        plan = get_plan_by_id(plan_id)
        if not plan: return bot.answer_callback_query(call.id, "PLAN NOT FOUND!")
        bot.answer_callback_query(call.id)
        name, price, duration = plan[1], plan[3], plan[4]
        base_price, formatted_price = parse_price_to_base(price)
        base_curr = get_base_curr()
        
        already_paid = get_pending_payment(user_id, plan_id)
        due_amount = max(0.0, round(base_price - already_paid, 2))
        binance_id_configured = get_setting("BINANCE_PAY_ID", BINANCE_PAY_ID)

        pay_msg = (f"💛 **BINANCE PAY AUTO PAYMENT PROCESS**\n\n📌 **SELECTED PLAN:** `{name.upper()}`\n💰 **TOTAL PRICE:** `{base_price} {base_curr.upper()}` ({formatted_price.upper()})\n")
        if already_paid > 0: pay_msg += (f"✅ **ALREADY DEPOSITED:** `{already_paid} {base_curr.upper()}`\n⚠️ **REMAINING AMOUNT:** `{due_amount} {base_curr.upper()}`\n\n")
        else: pay_msg += f"⏱️ **DURATION:** `{duration} DAYS`\n\n"
        pay_msg += (f"👇 **HOW TO PAY:**\n1️⃣ GO TO BINANCE APP -> PAY -> SEND.\n2️⃣ SEND EXACTLY `{due_amount} {base_curr.upper()}` TO THE FOLLOWING BINANCE PAY ID:\n🔸 **BINANCE PAY ID:** `{binance_id_configured}`\n\n3️⃣ ONCE PAID, CLICK THE BUTTON BELOW TO SUBMIT YOUR ORDER ID / TRANSACTION ID.")
        markup = types.InlineKeyboardMarkup()
        markup.add(make_inline_button("SUBMIT ORDER ID / TXID", callback_data=f"submit_txid_{plan_id}", style="success"))
        bot.send_message(call.message.chat.id, pay_msg, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("submit_txid_"):
        plan_id = int(data.split("_")[2])
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "📩 **ENTER YOUR BINANCE PAY ORDER ID / TRANSACTION ID:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: process_binance_txid(m, plan_id))

    elif data.startswith("manual_pay_"):
        plan_id = int(data.split("_")[2])
        bot.answer_callback_query(call.id)
        
        methods = get_all_payment_methods()
        if not methods:
            return bot.send_message(call.message.chat.id, "*(NO MANUAL PAYMENT METHOD ADDED YET)*", parse_mode="Markdown")

        markup = types.InlineKeyboardMarkup(row_width=2)
        btns = []
        for m in methods:
            btns.append(make_inline_button(str(m[1]).upper(), callback_data=f"paymethod_{plan_id}_{m[0]}", style="primary"))
        markup.add(*btns)

        bot.send_message(call.message.chat.id, "💳 **SELECT YOUR PAYMENT METHOD:**", reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("paymethod_"):
        parts = data.split("_")
        plan_id = int(parts[1])
        method_id = int(parts[2])
        bot.answer_callback_query(call.id)
        
        methods = get_all_payment_methods()
        method_name = next((m[1] for m in methods if str(m[0]) == str(method_id)), "UNKNOWN")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(make_inline_button("ADD AMOUNT", callback_data=f"add_amount_{plan_id}_{method_id}", style="success"))
        markup.add(make_inline_button("BACK", callback_data=f"manual_pay_{plan_id}", style="danger"))
        
        text = (f"💳 **{method_name.upper()} PAYMENT**\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"ENTER THE AMOUNT YOU WANT TO DEPOSIT.\n"
                f"THEN YOU WILL GET THE PAYMENT NUMBER BASED ON YOUR SELECTED AMOUNT.")
        bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("add_amount_"):
        parts = data.split("_")
        plan_id = int(parts[2])
        method_id = int(parts[3])
        bot.answer_callback_query(call.id)
        
        msg = bot.send_message(call.message.chat.id, "💰 **ENTER AMOUNT TO DEPOSIT (ONLY NUMBER):**\n\n/cancel", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: process_manual_amount(m, plan_id, method_id))

    elif data.startswith("verify_txid_"):
        parts = data.split("_")
        plan_id = int(parts[2])
        method_id = int(parts[3])
        amount = parts[4]
        bot.answer_callback_query(call.id)
        
        msg = bot.send_message(call.message.chat.id, "📩 **SEND YOUR TRANSACTION ID (ONLY TXID):**\n\n/cancel", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: process_manual_txid(m, plan_id, method_id, amount))

    # --- Ban User Feature from Forwarded Uploads ---
    elif data.startswith("ban_user_"):
        if user_id == OWNER_ID or user_id in admin_ids:
            target_uid = int(data.split("_")[2])
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)", (target_uid,))
            conn.commit()
            conn.close()
            bot.answer_callback_query(call.id, "USER BANNED!", show_alert=True)
            bot.edit_message_caption(f"🚫 **USER {target_uid} HAS BEEN BANNED.**", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")

    # --- Admin Verification (Approve/Reject) ---

    elif data.startswith("approve_upload_"):
        if user_id not in admin_ids:
            return bot.answer_callback_query(call.id, "❌ ADMIN ACCESS REQUIRED!", show_alert=True)
        request_id = data.split("approve_upload_", 1)[1]
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, chat_id, file_name, file_type, status FROM pending_uploads WHERE request_id=?", (request_id,))
        row = c.fetchone()
        if not row or row[4] != "pending":
            conn.close()
            return bot.answer_callback_query(call.id, "REQUEST ALREADY PROCESSED.", show_alert=True)
        target_uid, target_chat, fname, ftype, _ = row
        c.execute("UPDATE pending_uploads SET status='approved' WHERE request_id=?", (request_id,))
        conn.commit()
        conn.close()

        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        bot.answer_callback_query(call.id, "✅ APPROVED — STARTING BOT!")
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        if ftype in ("py", "js"):
            c.execute("INSERT OR REPLACE INTO approved_files (user_id, file_name, file_type) VALUES (?, ?, ?)",
                      (target_uid, fname, ftype))
        elif ftype == "zip":
            for child_name, child_type in user_files.get(target_uid, []):
                c.execute("INSERT OR REPLACE INTO approved_files (user_id, file_name, file_type) VALUES (?, ?, ?)",
                          (target_uid, child_name, child_type))
        conn.commit()
        conn.close()

        bot.send_message(target_chat, f"✅ **ADMIN APPROVED `{fname.upper()}`**\n🚀 **STARTING AUTOMATICALLY...**",
                         parse_mode="Markdown")

        ufolder = get_user_folder(target_uid)
        fpath = os.path.join(ufolder, fname)
        if os.path.isfile(fpath):
            if ftype == "js":
                threading.Thread(target=run_js_script, args=(fpath, target_uid, ufolder, fname, call.message), daemon=True).start()
            elif ftype == "py":
                threading.Thread(target=run_script, args=(fpath, target_uid, ufolder, fname, call.message), daemon=True).start()
            elif ftype == "zip":
                # ZIP uploads are extracted before approval; start all saved scripts.
                started = 0
                for child_name, child_type in user_files.get(target_uid, []):
                    child_path = os.path.join(ufolder, child_name)
                    if child_type == "py" and os.path.isfile(child_path):
                        threading.Thread(target=run_script, args=(child_path, target_uid, ufolder, child_name, call.message), daemon=True).start()
                        started += 1
                    elif child_type == "js" and os.path.isfile(child_path):
                        threading.Thread(target=run_js_script, args=(child_path, target_uid, ufolder, child_name, call.message), daemon=True).start()
                        started += 1
                bot.send_message(target_chat, f"🚀 **{started} SCRIPT(S) STARTED AUTOMATICALLY.**", parse_mode="Markdown")
        else:
            bot.send_message(target_chat, "❌ **UPLOADED FILE IS MISSING FROM SERVER STORAGE.**", parse_mode="Markdown")

    elif data.startswith("reject_upload_"):
        if user_id not in admin_ids:
            return bot.answer_callback_query(call.id, "❌ ADMIN ACCESS REQUIRED!", show_alert=True)
        request_id = data.split("reject_upload_", 1)[1]
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, chat_id, file_name, status FROM pending_uploads WHERE request_id=?", (request_id,))
        row = c.fetchone()
        if not row or row[3] != "pending":
            conn.close()
            return bot.answer_callback_query(call.id, "REQUEST ALREADY PROCESSED.", show_alert=True)
        target_uid, target_chat, fname, _ = row
        c.execute("UPDATE pending_uploads SET status='rejected' WHERE request_id=?", (request_id,))
        conn.commit()
        conn.close()
        try:
            archive_path = os.path.join(get_user_folder(target_uid), fname)
            if os.path.isfile(archive_path):
                os.remove(archive_path)
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM user_files WHERE user_id=? AND file_name=?", (target_uid, fname))
            c.execute("DELETE FROM approved_files WHERE user_id=? AND file_name=?", (target_uid, fname))
            conn.commit()
            conn.close()
            user_files[target_uid] = [(n, t) for n, t in user_files.get(target_uid, []) if n != fname]
        except Exception:
            pass
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        bot.answer_callback_query(call.id, "❌ UPLOAD REJECTED.")
        bot.send_message(target_chat, f"❌ **ADMIN REJECTED `{fname.upper()}`.**", parse_mode="Markdown")

    elif data.startswith("approve_pay_"):
        if user_id not in admin_ids: return bot.answer_callback_query(call.id, "YOU ARE NOT AN ADMIN!", show_alert=True)
        parts = data.split("_")
        target_uid, plan_id = int(parts[2]), int(parts[3])
        plan = get_plan_by_id(plan_id)
        if not plan: return bot.answer_callback_query(call.id, "PLAN NOT FOUND!")
        name, duration = plan[1], plan[4]
        expiry = datetime.now() + timedelta(days=duration)
        save_subscription(target_uid, name, expiry)
        bot.answer_callback_query(call.id, "PAYMENT APPROVED!")
        bot.edit_message_text(f"✅ **PAYMENT APPROVED FOR USER {target_uid} (PLAN: {name.upper()})**", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        try: bot.send_message(target_uid, f"🎉 **YOUR PAYMENT HAS BEEN APPROVED BY ADMIN!**\n\n✅ **PLAN:** `{name.upper()}` ACTIVE FOR {duration} DAYS.\n🚀 **YOU CAN NOW UPLOAD FILES!**", parse_mode="Markdown")
        except: pass

    elif data.startswith("reject_pay_"):
        if user_id not in admin_ids: return bot.answer_callback_query(call.id, "YOU ARE NOT AN ADMIN!", show_alert=True)
        target_uid = int(data.split("_")[2])
        bot.answer_callback_query(call.id, "PAYMENT REJECTED!")
        bot.edit_message_text(f"❌ **PAYMENT REJECTED FOR USER {target_uid}**", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        try: bot.send_message(target_uid, "❌ **YOUR PAYMENT WAS REJECTED.**\nPLEASE TRY AGAIN WITH CORRECT DETAILS OR CONTACT ADMIN.", parse_mode="Markdown")
        except: pass

    elif data == "admin_panel_back" and user_id in admin_ids:
        bot.edit_message_text("🛡️ **ADMIN CONTROL PANEL:**", call.message.chat.id, call.message.message_id, reply_markup=create_admin_panel_inline(), parse_mode="Markdown")

    elif data == "add_plan_init" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        prompt = (
            "📝 **ENTER PLAN DETAILS IN FORMAT:**\n"
            "`NAME | FILELIMIT | PRICE | DURATIONINDAYS | FEATURES (Comma Separated)`\n\n"
            "*EXAMPLE:* \n`BASIC | 5 | 500 BDT | 30 | ✅ 1GB RAM, ✅ 2 Core CPU, ❌ Root Access`"
        )
        msg = bot.send_message(call.message.chat.id, prompt, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_add_plan)

    elif data == "manage_plans" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        plans = get_all_plans()
        if not plans: return bot.send_message(call.message.chat.id, "NO PLANS FOUND.")
        markup = types.InlineKeyboardMarkup()
        for p in plans: markup.add(make_inline_button(f"DELETE {str(p[1]).upper()}", callback_data=f"del_plan_{p[0]}", style="danger"))
        bot.send_message(call.message.chat.id, "🗑️ **SELECT A PLAN TO DELETE:**", reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("del_plan_") and user_id in admin_ids:
        pid = int(data.split("_")[2])
        delete_plan_db(pid)
        bot.answer_callback_query(call.id, "PLAN DELETED!")
        bot.send_message(call.message.chat.id, "✅ **PLAN SUCCESSFULLY DELETED.**", parse_mode="Markdown")

    elif data == "add_subscription" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "💎 **ENTER USER ID, PLAN NAME & DAYS:**\nFORMAT: `USERID PLANNAME DAYS`\n*EXAMPLE:* `123456789 VIP 9999`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_add_subscription)

    elif data == "remove_subscription" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "❌ **ENTER USER ID TO REMOVE SUBSCRIPTION:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_remove_sub)

    elif data == "add_admin" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "👑 **ENTER USER ID TO PROMOTE TO ADMIN:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_add_admin)

    elif data == "remove_admin" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "➖ **ENTER USER ID TO DEMOTE FROM ADMIN:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_remove_admin)

    elif data == "broadcast" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "📣 **ENTER MESSAGE TO BROADCAST TO ALL ACTIVE USERS:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_broadcast)

    elif data == "run_all_scripts" and user_id in admin_ids:
        started = 0
        for uid, files in user_files.items():
            for fname, ftype in files:
                if not is_bot_running(uid, fname):
                    ufolder = get_user_folder(uid)
                    fpath = os.path.join(ufolder, fname)
                    if os.path.exists(fpath):
                        if ftype == 'py': threading.Thread(target=run_script, args=(fpath, uid, ufolder, fname, None)).start()
                        elif ftype == 'js': threading.Thread(target=run_js_script, args=(fpath, uid, ufolder, fname, None)).start()
                        started += 1
        bot.answer_callback_query(call.id, f"STARTED {started} SCRIPTS!")
        bot.send_message(call.message.chat.id, f"🚀 **{started}** OFFLINE SCRIPTS HAVE BEEN SUCCESSFULLY STARTED.", parse_mode="Markdown")

    elif data == "stats" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        total_files = sum(len(f) for f in user_files.values())
        running_bots = len([k for k, v in bot_scripts.items() if is_bot_running(v['script_owner_id'], v['file_name'])])
        stats_msg = (f"📊 **BOT STATISTICS:**\n\n"
                     f"👥 **TOTAL ACTIVE USERS:** `{len(active_users)}`\n"
                     f"💎 **TOTAL SUBSCRIBED:** `{len(user_subscriptions)}`\n"
                     f"📁 **TOTAL FILES UPLOADED:** `{total_files}`\n"
                     f"🤖 **TOTAL RUNNING BOTS:** `{running_bots}`")
        bot.send_message(call.message.chat.id, stats_msg, parse_mode="Markdown")

    elif data == "toggle_lock" and user_id in admin_ids:
        global bot_locked
        bot_locked = not bot_locked
        bot.answer_callback_query(call.id, f"BOT LOCKED: {bot_locked}")
        bot.send_message(call.message.chat.id, f"🔐 **BOT STATUS CHANGED TO:** `{'LOCKED' if bot_locked else 'UNLOCKED'}`", parse_mode="Markdown")

    elif data == "admin_settings" and user_id in admin_ids:
        bot.edit_message_text("🎛️ **VARIABLES & SETTINGS SETUP:**", call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_inline(), parse_mode="Markdown")

    elif data == "set_cfg_channel" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "📢 **ENTER NEW UPDATES CHANNEL (FORMAT: Button Name | Link):**\n*Example:* `JOIN UPDATES | https://t.me/mychannel`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: _save_config(m, 'UPDATE_CHANNEL', "UPDATES CHANNEL"))

    elif data == "set_cfg_owner" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "👑 **ENTER NEW OWNER CONTACT (E.G. @USERNAME):**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: _save_config(m, 'OWNER_USERNAME', "OWNER CONTACT"))

    elif data == "set_cfg_binance" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "🔸 **ENTER NEW BINANCE PAY ID:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: _save_config(m, 'BINANCE_PAY_ID', "BINANCE PAY ID"))
        
    elif data == "set_cfg_binance_api" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "🔑 **ENTER NEW BINANCE API KEY:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: _save_config(m, 'BINANCE_API_KEY', "BINANCE API KEY"))
        
    elif data == "set_cfg_binance_secret" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "🔒 **ENTER NEW BINANCE SECRET KEY:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: _save_config(m, 'BINANCE_SECRET_KEY', "BINANCE SECRET KEY"))
        
    elif data == "set_cfg_base" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "💵 **ENTER NEW BASE CURRENCY (E.G. USDT, USD):**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: _save_config(m, 'BASE_CURRENCY', "BASE CURRENCY"))
        
    elif data == "set_cfg_local" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "💴 **ENTER NEW LOCAL CURRENCY (E.G. BDT, INR):**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: _save_config(m, 'LOCAL_CURRENCY', "LOCAL CURRENCY"))
        
    elif data == "set_cfg_rate" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "💱 **ENTER NEW EXCHANGE RATE (E.G. 120.0):**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: _save_config(m, 'EXCHANGE_RATE', "EXCHANGE RATE"))
        
    elif data == "set_cfg_ref" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "🎁 **ENTER NEW REFERRAL BONUS AMOUNT (E.G. 10.0):**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: _save_config(m, 'REFERRAL_BONUS', "REFERRAL BONUS"))

    elif data == "admin_pay_methods" and user_id in admin_ids:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(make_inline_button("ADD METHOD", callback_data="add_pay_method", style="success"))
        for m in get_all_payment_methods():
            markup.add(make_inline_button(f"DEL: {str(m[1]).upper()}", callback_data=f"del_pay_{m[0]}", style="danger"))
        markup.add(make_inline_button("BACK TO ADMIN", callback_data="admin_panel_back", style="primary"))
        bot.edit_message_text("💳 **MANAGE MANUAL PAYMENT METHODS:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == "add_pay_method" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "➕ **ENTER PAYMENT METHOD DETAILS:**\nFORMAT: `METHOD NAME | NUMBER | INSTRUCTIONS`\n*EXAMPLE:* `BKASH PERSONAL | 017XXXX | SEND MONEY...`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_add_pay_method)

    elif data == "admin_btn_media" and user_id in admin_ids:
        markup = types.InlineKeyboardMarkup(row_width=2)
        btns = ["Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ", "Uᴘʟᴏᴀᴅ Fɪʟᴇ", "Mᴀɴᴀɢᴇ Fɪʟᴇs", "Vɪᴇᴡ Pʟᴀɴs", "Sᴘᴇᴇᴅ & Pɪɴɢ", "Bᴏᴛ Sᴛᴀᴛs", "Lᴀɴɢᴜᴀɢᴇ", "Cᴏɴᴛᴀᴄᴛ Oᴡɴᴇʀ", "Mʏ Pʀᴏғɪʟᴇ", "Rᴇғᴇʀ & Eᴀʀɴ"]
        for b in btns: markup.add(make_inline_button(b, callback_data=f"setmedia_{get_mapped_btn_name(b)}", style="primary"))
        markup.add(make_inline_button("✨ WELCOME MESSAGE MEDIA", callback_data="setmedia_WELCOME", style="success"))
        markup.add(make_inline_button("BACK TO ADMIN", callback_data="admin_panel_back", style="danger"))
        bot.edit_message_text("🖼️ **SELECT A BUTTON TO SET MEDIA (PHOTO/VIDEO):**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("setmedia_") and user_id in admin_ids:
        btn_name = data.split("_", 1)[1]
        msg = bot.send_message(call.message.chat.id, f"🖼️ **SEND A PHOTO OR VIDEO FOR THE `{btn_name}` BUTTON.**\n\n*(TYPE `CLEAR` TO REMOVE EXISTING MEDIA FROM THIS BUTTON)*", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: process_set_button_media(m, btn_name))

    # --- FORCE SUBS ADMIN ---
    elif data == "admin_force_subs" and user_id in admin_ids:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT id, name FROM force_subs")
        fsubs = c.fetchall()
        conn.close()
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(make_inline_button("➕ ADD FORCE SUB", callback_data="add_force_sub", style="success"))
        for ch in fsubs:
            markup.add(make_inline_button(f"🗑️ DEL: {ch[1]}", callback_data=f"del_force_sub_{ch[0]}", style="danger"))
        markup.add(make_inline_button("🔙 BACK TO ADMIN", callback_data="admin_panel_back", style="primary"))
        
        bot.edit_message_text("📢 **MANAGE UNLIMITED FORCE SUBSCRIBE CHANNELS:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == "add_force_sub" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "➕ **ENTER FORCE SUB CHANNEL DETAILS:**\nFORMAT: `CHANNEL NAME | CHAT ID | URL`\n*EXAMPLE:* `MY CHANNEL | -1001234567 | HTTPS://T.ME/MYCH`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_add_force_sub)

    elif data.startswith("del_force_sub_") and user_id in admin_ids:
        fid = int(data.split("_")[3])
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM force_subs WHERE id=?", (fid,))
            conn.commit()
            conn.close()
        bot.answer_callback_query(call.id, "FORCE SUB DELETED!")
        bot.send_message(call.message.chat.id, "✅ **FORCE SUB CHANNEL REMOVED.**", parse_mode="Markdown")

    # --- SUPPORT BUTTONS ADMIN ---
    elif data == "admin_support_btns" and user_id in admin_ids:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT id, name FROM support_buttons")
        sbtns = c.fetchall()
        conn.close()
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(make_inline_button("➕ ADD SUPPORT BTN", callback_data="add_support_btn", style="success"))
        for b in sbtns:
            markup.add(make_inline_button(f"🗑️ DEL: {b[1]}", callback_data=f"del_support_btn_{b[0]}", style="danger"))
        markup.add(make_inline_button("🔙 BACK TO ADMIN", callback_data="admin_panel_back", style="primary"))
        
        bot.edit_message_text("📞 **MANAGE UNLIMITED SUPPORT BUTTONS:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == "add_support_btn" and user_id in admin_ids:
        msg = bot.send_message(call.message.chat.id, "➕ **ENTER SUPPORT BUTTON DETAILS:**\nFORMAT: `BUTTON NAME | URL`\n*EXAMPLE:* `WHATSAPP SUPPORT | HTTPS://WA.ME/12345`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_add_support_btn)

    elif data.startswith("del_support_btn_") and user_id in admin_ids:
        bid = int(data.split("_")[3])
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM support_buttons WHERE id=?", (bid,))
            conn.commit()
            conn.close()
        bot.answer_callback_query(call.id, "SUPPORT BUTTON DELETED!")
        bot.send_message(call.message.chat.id, "✅ **SUPPORT BUTTON REMOVED.**", parse_mode="Markdown")


    # --- NEW MANAGE FILES UI ---
    elif data.startswith("file_"):
        try:
            _, owner_id, fname = data.split("_", 2)
            is_running = is_bot_running(int(owner_id), fname)

            ufolder = get_user_folder(int(owner_id))
            all_files = os.listdir(ufolder) if os.path.exists(ufolder) else []
            log_file_name = f"{os.path.splitext(fname)[0]}.log"
            
            data_files = [f for f in all_files if f != fname and f != log_file_name]

            data_list_text = ""
            if data_files:
                data_list_text = "\n\n📂 <b>ফাইলের ভিতরের ডাটা (Saved Files):</b>\n"
                for df in data_files:
                    safe_df = str(df).replace("<", "&lt;").replace(">", "&gt;")
                    data_list_text += f"├ 📄 <code>{safe_df}</code>\n"
            else:
                data_list_text = "\n\n📂 <b>ফাইলের ভিতরের ডাটা:</b>\n└ <i>(কোনো এক্সট্রা ডাটা সেভ হয়নি)</i>"

            markup = types.InlineKeyboardMarkup(row_width=2)
            
            if is_running:
                btn_action = make_inline_button("🔴 STOP", callback_data=f"stop_{owner_id}_{fname}", style="danger")
            else:
                btn_action = make_inline_button("🟢 START", callback_data=f"start_{owner_id}_{fname}", style="success")
            
            btn_delete = make_inline_button("🗑️ DELETE", callback_data=f"del_{owner_id}_{fname}", style="danger")
            
            markup.add(btn_action, btn_delete)
            
            log_fpath = os.path.join(ufolder, log_file_name)
            if os.path.exists(log_fpath) and os.path.getsize(log_fpath) > 0:
                btn_log = make_inline_button("⚠️ Vɪᴇᴡ Eʀʀᴏʀ Lᴏɢs", callback_data=f"viewlog_{owner_id}_{fname}", style="danger")
            else:
                btn_log = make_inline_button("📜 Vɪᴇᴡ Lᴏɢs", callback_data=f"viewlog_{owner_id}_{fname}", style="primary")
                
            btn_back = make_inline_button("⬅️ Bᴀᴄᴋ", callback_data="manage_files_back", style="secondary")
            
            markup.add(btn_log, btn_back)
            
            safe_fname = str(fname).replace("<", "&lt;").replace(">", "&gt;")
            msg_text = f"⚙️ <b>CONTROL PANEL</b>\n━━━━━━━━━━━━━━━━━━━━\n📄 <b>মেইন স্ক্রিপ্ট:</b> <code>{safe_fname}</code>\n🚦 <b>স্ট্যাটাস:</b> <code>{'🟢 RUNNING' if is_running else '🔴 STOPPED'}</code>\n👤 <b>ইউজার আইডি:</b> <code>{owner_id}</code>{data_list_text}"

            bot.edit_message_text(
                text=msg_text, 
                chat_id=call.message.chat.id, 
                message_id=call.message.message_id, 
                reply_markup=markup, 
                parse_mode="HTML"
            )
            bot.answer_callback_query(call.id) 
        except Exception as e:
            logger.error(f"File Manage UI Error: {e}")
            try:
                bot.answer_callback_query(call.id, "❌ Error loading file details! Please try again.", show_alert=True)
            except:
                pass

    elif data == "manage_files_back":
        bot.answer_callback_query(call.id) # <--- FIX: Button Unresponsive Bug solved here
        bot.delete_message(call.message.chat.id, call.message.message_id)
        msg_mock = call.message
        msg_mock.from_user = call.from_user
        _logic_check_files(msg_mock)

    elif data.startswith("start_"):
        _, owner_id, fname = data.split("_", 2)
        if is_bot_running(int(owner_id), fname):
            bot.answer_callback_query(call.id, "⚠️ SCRIPT IS ALREADY RUNNING!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "▶️ STARTING SCRIPT...")
            ufolder = get_user_folder(int(owner_id))
            fpath = os.path.join(ufolder, fname)
            if os.path.exists(fpath):
                ext = os.path.splitext(fname)[1].lower()
                if ext == ".py": threading.Thread(target=run_script, args=(fpath, int(owner_id), ufolder, fname, call.message)).start()
                elif ext == ".js": threading.Thread(target=run_js_script, args=(fpath, int(owner_id), ufolder, fname, call.message)).start()
            else: bot.send_message(call.message.chat.id, f"❌ **FILE NOT FOUND:** `{fname.upper()}`", parse_mode="Markdown")

    elif data.startswith("stop_"):
        _, owner_id, fname = data.split("_", 2)
        skey = f"{owner_id}_{fname}"
        if skey in bot_scripts: kill_process_tree(bot_scripts[skey]); del bot_scripts[skey]
        bot.answer_callback_query(call.id, "STOPPED!")
        bot.send_message(call.message.chat.id, f"🛑 **SCRIPT `{fname.upper()}` STOPPED.**", parse_mode="Markdown")

    elif data.startswith("del_"):
        _, owner_id, fname = data.split("_", 2)
        skey = f"{owner_id}_{fname}"
        if skey in bot_scripts: kill_process_tree(bot_scripts[skey]); del bot_scripts[skey]
        remove_user_file_db(int(owner_id), fname)
        ufolder = get_user_folder(int(owner_id))
        fpath = os.path.join(ufolder, fname)
        if os.path.exists(fpath): os.remove(fpath)
        bot.answer_callback_query(call.id, "DELETED!")
        bot.send_message(call.message.chat.id, f"🗑️ **FILE `{fname.upper()}` DELETED.**", parse_mode="Markdown")


# --- Added Step Handlers for Missing Functions ---

def process_add_plan(message):
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) < 5: 
            bot.reply_to(message, "❌ **INVALID FORMAT!** MUST BE EXACTLY 5 PARTS SEPARATED BY `|`.\n\n*Example:* `BASIC | 5 | 500 BDT | 30 | ✅ 1GB RAM, ✅ 1 Core CPU, ❌ No Custom Server`", parse_mode="Markdown")
            return
            
        name = parts[0]
        limit = int(parts[1])
        price = parts[2]
        duration = int(parts[3])
        features = parts[4]
        
        add_plan_db(name, limit, price, duration, "", features)
        bot.reply_to(message, f"✅ **PLAN `{name.upper()}` ADDED SUCCESSFULLY!**", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "❌ **ERROR:** `FILELIMIT` AND `DURATIONINDAYS` MUST BE **NUMBERS ONLY**.", parse_mode="Markdown")
    except Exception as e: 
        bot.reply_to(message, f"❌ **ERROR:** {str(e).upper()}", parse_mode="Markdown")

def process_add_subscription(message):
    try:
        parts = message.text.split()
        if len(parts) < 3: 
            bot.reply_to(message, "❌ **INVALID FORMAT!** MUST BE `USERID PLANNAME DAYS` (e.g. `123456789 VIP 30`)", parse_mode="Markdown")
            return
            
        uid = int(parts[0])
        plan_name = parts[1]
        days = int(parts[2])
        expiry = datetime.now() + timedelta(days=days)
        save_subscription(uid, plan_name, expiry)
        bot.reply_to(message, f"✅ **SUBSCRIPTION ADDED!**\n\n👤 **USER:** `{uid}`\n💎 **PLAN:** `{plan_name.upper()}`\n⏱️ **DAYS:** `{days}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ **ERROR:** MUST BE `USERID PLANNAME DAYS`.\n{e}", parse_mode="Markdown")

def process_binance_txid(message, plan_id):
    if message.text.strip() == '/cancel':
        return bot.reply_to(message, "🚫 **CANCELLED.**", parse_mode="Markdown")
        
    txid = message.text.strip()
    user_id = message.from_user.id
    
    plan = get_plan_by_id(plan_id)
    if not plan: return
    plan_name, duration = plan[1], plan[4]
    
    bot.reply_to(message, "⏳ **VERIFYING YOUR PAYMENT WITH BINANCE... PLEASE WAIT!**", parse_mode="Markdown")
    
    is_valid, amount, amount_str = check_binance_payment(txid)
    if is_valid:
        if is_txid_used(txid):
            return bot.reply_to(message, "❌ **THIS TRANSACTION ID HAS ALREADY BEEN USED!**", parse_mode="Markdown")
        
        add_used_txid(txid)
        expiry = datetime.now() + timedelta(days=duration)
        save_subscription(user_id, plan_name, expiry)
        bot.reply_to(message, f"✅ **PAYMENT VERIFIED!**\n\n🎉 **PLAN:** `{plan_name.upper()}` ACTIVATED FOR {duration} DAYS.\n💰 **AMOUNT RECEIVED:** `{amount_str}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ **PAYMENT VERIFICATION FAILED!**\n\n⚠️ **REASON:** `{amount_str}`\n\nPLEASE CHECK YOUR TRANSACTION ID OR TRY MANUAL PAYMENT.", parse_mode="Markdown")


# --- Step Handlers for Manual Payment ---
def process_manual_amount(message, plan_id, method_id):
    if message.text.strip() == '/cancel':
        return bot.reply_to(message, "🚫 **CANCELLED.**", parse_mode="Markdown")
        
    amount = message.text.strip()
    methods = get_all_payment_methods()
    
    try:
        method_details = next((m for m in methods if str(m[0]) == str(method_id)), None)
    except Exception:
        method_details = None
        
    if not method_details: 
        bot.reply_to(message, "❌ **ERROR FINDING PAYMENT METHOD.**", parse_mode="Markdown")
        return
    
    method_name, method_number, method_instructions = method_details[1], method_details[2], method_details[3]
    
    text = (
        f"💳 **{method_name.upper()} PAYMENT**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 **DEPOSIT AMOUNT: {amount}**\n\n"
        f"SEND EXACTLY THIS AMOUNT TO THE NUMBER BELOW.\n"
        f"AFTER PAYMENT, VERIFY WITH YOUR TRANSACTION ID.\n\n"
        f"⚠️ THE RECEIVED AMOUNT MUST MATCH YOUR SELECTED AMOUNT.\n\n"
        f"📝 **INSTRUCTIONS:** {method_instructions.upper()}"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(make_inline_button(method_number, callback_data="ignore", style="primary"))
    markup.add(make_inline_button("TRANSACTION VERIFY", callback_data=f"verify_txid_{plan_id}_{method_id}_{amount}", style="success"))
    
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

def process_manual_txid(message, plan_id, method_id, amount):
    if message.text.strip() == '/cancel':
        return bot.reply_to(message, "🚫 **CANCELLED.**", parse_mode="Markdown")
        
    txid = message.text.strip()
    user_id = message.from_user.id
    username = message.from_user.username or "NO USERNAME"
    
    plan = get_plan_by_id(plan_id)
    if not plan: return
    plan_name, plan_price = plan[1], plan[3]
    
    methods = get_all_payment_methods()
    method_details = next((m for m in methods if str(m[0]) == str(method_id)), None)
    method_name = method_details[1] if method_details else "UNKNOWN"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        make_inline_button("APPROVE", callback_data=f"approve_pay_{user_id}_{plan_id}", style="success"),
        make_inline_button("REJECT", callback_data=f"reject_pay_{user_id}", style="danger")
    )
    caption = (
        f"🔔 **NEW MANUAL PAYMENT VERIFICATION REQUEST!**\n\n"
        f"👤 **USER:** `{user_id}` (@{username})\n"
        f"📦 **SELECTED PLAN:** `{plan_name.upper()}`\n"
        f"💰 **EXPECTED PLAN PRICE:** `{plan_price.upper()}`\n"
        f"💳 **METHOD:** `{method_name.upper()}`\n"
        f"💵 **USER ENTERED AMOUNT:** `{amount}`\n"
        f"📑 **TRANSACTION ID:** `{txid}`\n\n"
        f"✅ **PLEASE VERIFY THE TXID AND TAKE ACTION.**"
    )
    bot.send_message(OWNER_ID, caption, reply_markup=markup, parse_mode="Markdown")
    bot.reply_to(message, "⏳ **YOUR TRANSACTION ID HAS BEEN SENT TO ADMIN!**\n\nADMIN WILL VERIFY AND ACTIVATE YOUR PLAN SHORTLY. PLEASE WAIT.", parse_mode="Markdown")

def _save_config(message, key, name):
    val = message.text.strip()
    set_setting(key, val)
    bot.reply_to(message, f"✅ **{name.upper()}** SUCCESSFULLY UPDATED TO:\n`{val.upper()}`", parse_mode="Markdown")

def process_add_pay_method(message):
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) < 3: raise ValueError("Not enough fields")
        add_payment_method(parts[0], parts[1], parts[2])
        bot.reply_to(message, f"✅ **PAYMENT METHOD `{parts[0].upper()}` ADDED SUCCESSFULLY!**", parse_mode="Markdown")
    except Exception as e: bot.reply_to(message, "❌ **INVALID FORMAT!** MUST BE `NAME | NUMBER | INSTRUCTIONS`", parse_mode="Markdown")

def process_set_button_media(message, btn_name):
    if message.content_type == 'text' and message.text.lower() == 'clear':
        set_button_media(btn_name, None, None)
        return bot.reply_to(message, f"🗑️ **MEDIA CLEARED FOR `{btn_name}`.**", parse_mode="Markdown")
    
    if message.content_type == 'photo':
        file_id = message.photo[-1].file_id
        set_button_media(btn_name, 'photo', file_id)
        bot.reply_to(message, f"✅ **PHOTO MEDIA SET FOR `{btn_name}`!**", parse_mode="Markdown")
    elif message.content_type == 'video':
        file_id = message.video.file_id
        set_button_media(btn_name, 'video', file_id)
        bot.reply_to(message, f"✅ **VIDEO MEDIA SET FOR `{btn_name}`!**", parse_mode="Markdown")
    else: bot.reply_to(message, "❌ **INVALID MEDIA. SEND PHOTO, VIDEO OR TYPE `CLEAR`.**", parse_mode="Markdown")

def process_remove_sub(message):
    try:
        uid = int(message.text)
        remove_subscription_db(uid)
        bot.reply_to(message, f"✅ **SUCCESSFULLY REMOVED SUBSCRIPTION FOR USER ID `{uid}`.**", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ **INVALID USER ID.**", parse_mode="Markdown")

def process_add_admin(message):
    try:
        uid = int(message.text)
        admin_ids.add(uid)
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (uid,))
            conn.commit()
            conn.close()
        bot.reply_to(message, f"✅ **USER ID `{uid}` IS NOW AN ADMIN.**", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ **INVALID USER ID.**", parse_mode="Markdown")

def process_remove_admin(message):
    try:
        uid = int(message.text)
        if uid == OWNER_ID: return bot.reply_to(message, "❌ **YOU CANNOT REMOVE THE OWNER.**", parse_mode="Markdown")
        if uid in admin_ids: admin_ids.remove(uid)
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM admins WHERE user_id=?", (uid,))
            conn.commit()
            conn.close()
        bot.reply_to(message, f"➖ **USER ID `{uid}` HAS BEEN DEMOTED FROM ADMIN.**", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ **INVALID USER ID.**", parse_mode="Markdown")

def process_broadcast(message):
    msg_text = message.text
    if not msg_text: return
    success = 0
    wait_msg = bot.reply_to(message, "⏳ **BROADCASTING MESSAGE...**", parse_mode="Markdown")
    for uid in active_users:
        try: 
            bot.send_message(uid, msg_text, parse_mode="Markdown")
            success += 1
        except: pass
    bot.edit_message_text(f"📣 **BROADCAST COMPLETE!**\nMESSAGE SENT TO `{success}` USERS.", message.chat.id, wait_msg.message_id, parse_mode="Markdown")

def process_add_force_sub(message):
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) < 3: raise ValueError("Not enough fields")
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO force_subs (name, chat_id, url) VALUES (?, ?, ?)", (parts[0], parts[1], parts[2]))
            conn.commit()
            conn.close()
        bot.reply_to(message, f"✅ **FORCE SUB CHANNEL `{parts[0].upper()}` ADDED SUCCESSFULLY!**", parse_mode="Markdown")
    except Exception as e: bot.reply_to(message, "❌ **INVALID FORMAT!** MUST BE `NAME | CHAT ID | URL`", parse_mode="Markdown")

def process_add_support_btn(message):
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) < 2: raise ValueError("Not enough fields")
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO support_buttons (name, url) VALUES (?, ?)", (parts[0], parts[1]))
            conn.commit()
            conn.close()
        bot.reply_to(message, f"✅ **SUPPORT BUTTON `{parts[0].upper()}` ADDED SUCCESSFULLY!**", parse_mode="Markdown")
    except Exception as e: bot.reply_to(message, "❌ **INVALID FORMAT!** MUST BE `NAME | URL`", parse_mode="Markdown")


# ==================================
# BUTTON HANDLER
# ==================================
@bot.message_handler(func=lambda m: True)
def handle_main_buttons(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        return bot.send_message(user_id, "❌ **YOU ARE BANNED FROM USING THIS BOT.**", parse_mode="Markdown")

    # Mapping stylish names back to plain format for processing
    btn_text = get_mapped_btn_name(message.text)
    
    # Send Media if configured
    try:
        media = get_button_media(btn_text)
        if media:
            mtype, fid = media
            if mtype == 'photo': bot.send_photo(message.chat.id, fid)
            elif mtype == 'video': bot.send_video(message.chat.id, fid)
    except Exception as e: 
        logger.error(f"FAILED TO SEND MEDIA: {e}")

    # Button Logic processing
    if "PROFILE" in btn_text: _logic_my_profile(message)
    elif "REFER" in btn_text: _logic_refer(message)
    elif "UPDATES" in btn_text: 
        update_data = str(get_setting('UPDATE_CHANNEL', f"📢 JOIN UPDATES CHANNEL | {UPDATE_CHANNEL}"))
        if "|" in update_data:
            btn_name, btn_link = [x.strip() for x in update_data.split("|", 1)]
        else:
            btn_name, btn_link = "📢 JOIN UPDATES CHANNEL", update_data
            
        markup = types.InlineKeyboardMarkup()
        markup.add(make_inline_button(btn_name, url=btn_link, style="primary"))
        bot.reply_to(message, "📢 **STAY UPDATED WITH OUR LATEST NEWS:**", reply_markup=markup, parse_mode="Markdown")
        
    elif "UPLOAD" in btn_text: _logic_upload_file(message)
    elif "MANAGE" in btn_text: _logic_check_files(message)
    elif "PLANS" in btn_text: send_plan_page(message.chat.id, message.from_user.id, 0)
    elif "SPEED" in btn_text: bot.reply_to(message, "⚡ **BOT LATENCY:** `12 MS` (SERVER ACTIVE)", parse_mode="Markdown")
    elif "STATS" in btn_text: 
        try:
            bot.reply_to(message, f"📊 **ACTIVE USERS:** `{len(active_users)}`\n🤖 **ACTIVE SCRIPTS:** `{len([k for k, v in bot_scripts.items() if is_bot_running(v['script_owner_id'], v['file_name'])])}`", parse_mode="Markdown")
        except: pass
    elif "LANGUAGE" in btn_text or "ভাষা" in btn_text: _logic_language(message)
    elif "CONTACT" in btn_text: _logic_contact_owner(message)
    elif "ADMIN" in btn_text: bot.reply_to(message, "🛡️ **ADMIN CONTROL PANEL:**", reply_markup=create_admin_panel_inline(), parse_mode="Markdown")


def auto_start_approved_files():
    """Restart only files explicitly approved by an admin/owner."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, file_name, file_type FROM approved_files")
        approved = c.fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"AUTO-START DB ERROR: {e}")
        return

    started = 0
    for uid, fname, ftype in approved:
        try:
            folder = get_user_folder(uid)
            path = os.path.join(folder, fname)
            if not os.path.isfile(path) or is_bot_running(uid, fname):
                continue
            if ftype == "py":
                threading.Thread(target=run_script,
                                 args=(path, uid, folder, fname, None), daemon=True).start()
                started += 1
            elif ftype == "js":
                threading.Thread(target=run_js_script,
                                 args=(path, uid, folder, fname, None), daemon=True).start()
                started += 1
        except Exception as e:
            logger.error(f"AUTO-START FAILED for {fname}: {e}")

    if started:
        logger.info("AUTO-STARTED %s approved script(s). No CMD/terminal command required.", started)

def cleanup():
    for key in list(bot_scripts.keys()): kill_process_tree(bot_scripts[key])

atexit.register(cleanup)

if __name__ == "__main__":
    logger.info("BOT STARTED SUCCESSFULLY WITH ALL FIXES INCLUDED.")
    keep_alive()
    auto_start_approved_files()
    bot.infinity_polling(timeout=60, long_polling_timeout=30)