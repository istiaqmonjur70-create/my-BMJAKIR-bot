
import os
import re
import time
import asyncio
import logging
import sqlite3
import tempfile
import shutil
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==================================================
# CONFIG
# ==================================================

BOT_TOKEN = "8994105336:AAE7RnOhA_w8wstj-FxmxdR286RDpcAnJdc"
ADMIN_ID = 8814363793
SUPPORT_USERNAME = "@DevCloudX"

MAX_FILE_SIZE_MB = 45
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
DOWNLOAD_TIMEOUT = 240
DB_FILE = "downloader.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("MediaDownloader")


# ==================================================
# DATABASE
# ==================================================

def db():
    conn = sqlite3.connect(DB_FILE, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                blocked INTEGER DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel TEXT PRIMARY KEY
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                url TEXT,
                media_type TEXT,
                created_at INTEGER,
                status TEXT,
                reason TEXT
            )
        """)

        # Upgrade an older database if needed.
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(history)"
            ).fetchall()
        }

        if "reason" not in columns:
            conn.execute(
                "ALTER TABLE history ADD COLUMN reason TEXT DEFAULT ''"
            )

        conn.execute("""
            INSERT OR IGNORE INTO channels(channel)
            VALUES('@JAKIRLABS')
        """)


def save_user(user):
    with db() as conn:
        conn.execute("""
            INSERT INTO users(user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
        """, (
            user.id,
            user.username or "",
            user.first_name or "",
        ))


def is_blocked(user_id):
    with db() as conn:
        row = conn.execute(
            "SELECT blocked FROM users WHERE user_id=?",
            (user_id,),
        ).fetchone()

    return bool(row and row["blocked"])


def get_channels():
    with db() as conn:
        rows = conn.execute(
            "SELECT channel FROM channels ORDER BY channel"
        ).fetchall()

    return [row["channel"] for row in rows]


def record_history(user_id, url, media_type, status, reason=""):
    with db() as conn:
        conn.execute("""
            INSERT INTO history(
                user_id, url, media_type, created_at, status, reason
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            url[:1500],
            media_type,
            int(time.time()),
            status,
            reason[:1000],
        ))


# ==================================================
# KEYBOARDS
# ==================================================

def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("⬇️ Download Video"),
                KeyboardButton("🖼️ Download Photo"),
            ],
            [
                KeyboardButton("📚 My History"),
                KeyboardButton("🎧 Support"),
            ],
            [KeyboardButton("❓ Help")],
        ],
        resize_keyboard=True,
    )


def join_keyboard():
    rows = []

    for channel in get_channels():
        name = channel.lstrip("@")
        rows.append([
            InlineKeyboardButton(
                f"📢 Join {name}",
                url=f"https://t.me/{name}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            "✅ I Joined",
            callback_data="check_join",
        )
    ])

    return InlineKeyboardMarkup(rows)


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📊 Statistics",
                callback_data="admin_stats",
            ),
            InlineKeyboardButton(
                "📢 Channels",
                callback_data="admin_channels",
            ),
        ],
        [
            InlineKeyboardButton(
                "➕ Add Channel",
                callback_data="admin_add",
            ),
            InlineKeyboardButton(
                "➖ Remove Channel",
                callback_data="admin_remove",
            ),
        ],
        [
            InlineKeyboardButton(
                "🚫 Block User",
                callback_data="admin_block",
            ),
            InlineKeyboardButton(
                "✅ Unblock User",
                callback_data="admin_unblock",
            ),
        ],
        [
            InlineKeyboardButton(
                "📨 Broadcast",
                callback_data="admin_broadcast",
            )
        ],
    ])


# ==================================================
# URL VALIDATION
# ==================================================

def validate_url(url):
    try:
        parsed = urlparse(url.strip())

        if parsed.scheme not in ("https", "http"):
            return False, "শুধু HTTP/HTTPS লিংক গ্রহণ করা হয়।"

        if not parsed.hostname:
            return False, "লিংকের ডোমেইন পাওয়া যায়নি।"

        if parsed.username or parsed.password:
            return False, "লিংকের মধ্যে login credentials দেওয়া যাবে না।"

        host = parsed.hostname.lower().rstrip(".")

        if host == "localhost" or host.endswith(".localhost"):
            return False, "Localhost URL অনুমোদিত নয়।"

        if host.endswith(".local"):
            return False, "Local network URL অনুমোদিত নয়।"

        try:
            address = ipaddress.ip_address(host)
            if not address.is_global:
                return False, "Private বা internal IP URL অনুমোদিত নয়।"
        except ValueError:
            pass

        # Reject common internal hostnames.
        if "." not in host and host != "youtube.com":
            return False, "এই hostname গ্রহণযোগ্য নয়।"

        return True, ""

    except Exception:
        return False, "লিংকটি সঠিক নয়।"


# ==================================================
# FORCE JOIN
# ==================================================

async def joined_all(user_id, context):
    for channel in get_channels():
        try:
            member = await context.bot.get_chat_member(
                chat_id=channel,
                user_id=user_id,
            )

            if member.status in ("left", "kicked"):
                return False

            if (
                member.status == "restricted"
                and not getattr(member, "is_member", False)
            ):
                return False

        except TelegramError:
            logger.exception("Force-join verification failed")
            return False

    return True


async def check_access(update, context):
    user = update.effective_user

    if not user:
        return False

    if is_blocked(user.id):
        target = update.effective_message
        if target:
            await target.reply_text(
                "🚫 আপনাকে এই বট ব্যবহার থেকে Block করা হয়েছে।"
            )
        return False

    if await joined_all(user.id, context):
        return True

    target = update.effective_message

    if update.callback_query:
        await update.callback_query.answer(
            "আগে সব চ্যানেলে Join করুন।",
            show_alert=True,
        )
        target = update.callback_query.message

    if target:
        await target.reply_text(
            "🔒 <b>Force Join Required</b>\n\n"
            "প্রথমে নিচের সব চ্যানেলে Join করুন। "
            "তারপর I Joined চাপুন।",
            parse_mode="HTML",
            reply_markup=join_keyboard(),
        )

    return False


# ==================================================
# ERROR CLASSIFIER
# ==================================================

def classify_error(error):
    """
    Convert yt-dlp/network errors into understandable messages.
    This does not bypass platform restrictions.
    """
    raw = str(error)
    text = raw.lower()

    if (
        "sign in to confirm" in text
        or "confirm you're not a bot" in text
        or "confirm you’re not a bot" in text
        or "login required" in text
        or "cookies are needed" in text
    ):
        return (
            "YOUTUBE_VERIFICATION",
            "YouTube অতিরিক্ত যাচাই চাইছে।",
            "সার্ভার থেকে এই ভিডিওর অ্যাক্সেস পাওয়া যায়নি। "
            "yt-dlp আপডেট করেও সমস্যা থাকতে পারে। "
            "কিছুক্ষণ পরে আবার চেষ্টা করুন অথবা অন্য "
            "অনুমতিপ্রাপ্ত পাবলিক লিংক পরীক্ষা করুন।",
        )

    if (
        "private video" in text
        or "private" in text and "video" in text
        or "sign in to view" in text
        or "members-only" in text
        or "members only" in text
    ):
        return (
            "PRIVATE_MEDIA",
            "ভিডিওটি Private বা সীমাবদ্ধ।",
            "বটের বর্তমান অ্যাক্সেস দিয়ে এই মিডিয়া পাওয়া যাচ্ছে না। "
            "একটি অনুমতিপ্রাপ্ত পাবলিক লিংক ব্যবহার করুন।",
        )

    if (
        "unsupported url" in text
        or "no suitable extractor" in text
        or "not a valid url" in text
    ):
        return (
            "UNSUPPORTED_URL",
            "এই লিংকটি সমর্থিত নয়।",
            "এই প্ল্যাটফর্ম বা লিংকের ধরন yt-dlp শনাক্ত করতে পারেনি। "
            "লিংকটি পরীক্ষা করুন এবং yt-dlp আপডেট করুন।",
        )

    if (
        "max-filesize" in text
        or "file is larger" in text
        or "file size exceeds" in text
    ):
        return (
            "FILE_TOO_LARGE",
            "ফাইলের সাইজ অনেক বড়।",
            f"এই বটের সর্বোচ্চ ফাইল সাইজ {MAX_FILE_SIZE_MB} MB।",
        )

    if (
        "timed out" in text
        or "timeout" in text
        or "read operation timed out" in text
    ):
        return (
            "TIMEOUT",
            "ডাউনলোডের সময় শেষ হয়ে গেছে।",
            "ইন্টারনেট বা প্ল্যাটফর্ম ধীর হতে পারে। "
            "ছোট ফাইল দিয়ে আবার চেষ্টা করুন।",
        )

    if (
        "name or service not known" in text
        or "temporary failure in name resolution" in text
        or "connection refused" in text
        or "network is unreachable" in text
        or "connection reset" in text
        or "unable to download webpage" in text
    ):
        return (
            "NETWORK_ERROR",
            "নেটওয়ার্ক সমস্যা হয়েছে।",
            "বটের সার্ভার প্ল্যাটফর্মে সংযোগ করতে পারেনি। "
            "হোস্টিংয়ের ইন্টারনেট সংযোগ পরীক্ষা করে আবার চেষ্টা করুন।",
        )

    if (
        "requested format is not available" in text
        or "no video formats found" in text
        or "format is not available" in text
    ):
        return (
            "FORMAT_UNAVAILABLE",
            "কোনো সমর্থিত ভিডিও ফরম্যাট পাওয়া যায়নি।",
            "প্ল্যাটফর্মের উপলব্ধ ফরম্যাট বটের সঙ্গে সামঞ্জস্যপূর্ণ নয়।",
        )

    if (
        "age-restricted" in text
        or "age restricted" in text
    ):
        return (
            "AGE_RESTRICTED",
            "ভিডিওটি বয়স-সীমাবদ্ধ।",
            "এই বটের বর্তমান অ্যাক্সেস দিয়ে ভিডিওটি পাওয়া যাচ্ছে না।",
        )

    if (
        "429" in text
        or "too many requests" in text
    ):
        return (
            "RATE_LIMITED",
            "প্ল্যাটফর্ম সাময়িকভাবে অনুরোধ সীমিত করেছে।",
            "কিছুক্ষণ অপেক্ষা করে আবার চেষ্টা করুন।",
        )

    if (
        "ffmpeg" in text
        or "postprocessing" in text
    ):
        return (
            "PROCESSING_ERROR",
            "ফাইল কনভার্ট করতে সমস্যা হয়েছে।",
            "সার্ভারে FFmpeg ইনস্টল আছে কি না পরীক্ষা করুন।",
        )

    if (
        "no such file" in text
        or "permission denied" in text
        or "no space left on device" in text
    ):
        return (
            "HOSTING_ERROR",
            "হোস্টিংয়ের স্টোরেজ বা ফাইল সিস্টেমে সমস্যা হয়েছে।",
            "ডিস্ক স্পেস এবং ফোল্ডারের Permission পরীক্ষা করুন।",
        )

    return (
        "UNKNOWN_ERROR",
        "ডাউনলোড ব্যর্থ হয়েছে।",
        "প্ল্যাটফর্ম একটি অজানা Error দিয়েছে। "
        "Admin Log-এ বিস্তারিত তথ্য পরীক্ষা করুন।",
    )


# ==================================================
# DOWNLOAD ENGINE
# ==================================================

def download_media(url, media_type, folder):
    output = str(
        Path(folder) / "%(title).60s_%(id)s.%(ext)s"
    )

    options = {
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 25,
        "retries": 2,
        "fragment_retries": 2,
        "max_filesize": MAX_FILE_SIZE,
        "restrictfilenames": True,
        "overwrites": True,
    }

    if media_type == "audio":
        options["format"] = "bestaudio/best"
        options["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "128",
        }]
    elif media_type == "photo":
        options["format"] = "best"
    else:
        options["format"] = (
            "best[ext=mp4][filesize<45M]/"
            "best[filesize<45M]/best"
        )
        options["merge_output_format"] = "mp4"

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

    if info and info.get("entries"):
        info = next(
            (entry for entry in info["entries"] if entry),
            None,
        )

    if not info:
        raise RuntimeError("No downloadable media was returned.")

    files = [
        p for p in Path(folder).iterdir()
        if p.is_file()
        and not p.name.endswith((".part", ".ytdl"))
    ]

    if not files:
        raise RuntimeError("No media file was created.")

    files.sort(
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    path = files[0]

    if path.stat().st_size > MAX_FILE_SIZE:
        raise RuntimeError("File exceeds max-filesize.")

    return str(path), info.get("title", "Media")


# ==================================================
# DOWNLOAD HANDLER
# ==================================================

async def send_download(update, context, url, media_type):
    message = update.effective_message
    user_id = update.effective_user.id

    valid, reason = validate_url(url)

    if not valid:
        await message.reply_text("⚠️ " + reason)
        return

    status = await message.reply_text(
        "⏳ <b>লিংক পরীক্ষা করা হচ্ছে...</b>",
        parse_mode="HTML",
    )

    folder = tempfile.mkdtemp(prefix="media_bot_")

    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.UPLOAD_DOCUMENT,
        )

        path, title = await asyncio.wait_for(
            asyncio.to_thread(
                download_media,
                url,
                media_type,
                folder,
            ),
            timeout=DOWNLOAD_TIMEOUT,
        )

        caption = (
            "✅ <b>Download Successful</b>\n\n"
            f"<b>Title:</b> {title[:400]}"
        )

        with open(path, "rb") as file:
            if media_type == "photo":
                await message.reply_photo(
                    photo=file,
                    caption=caption,
                    parse_mode="HTML",
                    read_timeout=120,
                    write_timeout=120,
                )
            elif media_type == "audio":
                await message.reply_audio(
                    audio=file,
                    caption=caption,
                    parse_mode="HTML",
                    read_timeout=120,
                    write_timeout=120,
                )
            else:
                await message.reply_document(
                    document=file,
                    caption=caption,
                    parse_mode="HTML",
                    read_timeout=120,
                    write_timeout=120,
                )

        record_history(
            user_id, url, media_type, "success"
        )

        await status.edit_text(
            "✅ ডাউনলোড সম্পন্ন হয়েছে!"
        )

    except asyncio.TimeoutError as exc:
        code, title, explanation = classify_error(
            "download timed out"
        )

        record_history(
            user_id, url, media_type, "failed", code
        )

        await status.edit_text(
            f"❌ <b>{title}</b>\n\n{explanation}",
            parse_mode="HTML",
        )

    except Exception as exc:
        code, title, explanation = classify_error(exc)

        logger.error(
            "Download failure | user=%s | type=%s | "
            "code=%s | url=%s | error=%s",
            user_id,
            media_type,
            code,
            url,
            str(exc)[:1500],
        )

        record_history(
            user_id, url, media_type, "failed", code
        )

        await status.edit_text(
            f"❌ <b>{title}</b>\n\n"
            f"{explanation}\n\n"
            f"<b>Error Code:</b> <code>{code}</code>",
            parse_mode="HTML",
        )

    finally:
        shutil.rmtree(folder, ignore_errors=True)

    context.user_data.pop("mode", None)
    context.user_data.pop("pending_url", None)

    await message.reply_text(
        "🏠 Main Menu",
        reply_markup=main_keyboard(),
    )


# ==================================================
# USER COMMANDS
# ==================================================

async def start(update, context):
    save_user(update.effective_user)

    if not await check_access(update, context):
        return

    await update.effective_message.reply_text(
        "✨ <b>MEDIA DOWNLOADER</b>\n\n"
        "ভিডিও, অডিও বা ছবি ডাউনলোড করতে নিচের বাটন ব্যবহার করুন।",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


async def help_command(update, context):
    await update.effective_message.reply_text(
        "❓ <b>Help</b>\n\n"
        "1. Download Video অথবা Download Photo চাপুন।\n"
        "2. পাবলিক মিডিয়া লিংক পাঠান।\n"
        "3. ভিডিওর ক্ষেত্রে Video বা Audio বেছে নিন।\n"
        "4. ব্যর্থ হলে বট Error Code দেখাবে।\n\n"
        "Private বা protected কনটেন্ট এবং কিছু প্ল্যাটফর্ম "
        "সমর্থিত নাও হতে পারে।",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


async def history_command(update, context):
    with db() as conn:
        rows = conn.execute("""
            SELECT url, media_type, created_at, status, reason
            FROM history
            WHERE user_id=?
            ORDER BY id DESC LIMIT 10
        """, (update.effective_user.id,)).fetchall()

    if not rows:
        await update.effective_message.reply_text(
            "📚 এখনো কোনো ডাউনলোড হিস্টোরি নেই।",
            reply_markup=main_keyboard(),
        )
        return

    lines = ["📚 <b>My History</b>\n"]

    for row in rows:
        date = time.strftime(
            "%Y-%m-%d %H:%M",
            time.localtime(row["created_at"]),
        )

        lines.append(
            f"• {row['media_type']} | {row['status']}\n"
            f"সময়: {date}\n"
            f"কারণ: {row['reason'] or 'N/A'}\n"
            f"{row['url'][:130]}"
        )

    await update.effective_message.reply_text(
        "\n\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=main_keyboard(),
    )


async def cancel_command(update, context):
    context.user_data.clear()

    await update.effective_message.reply_text(
        "❌ বাতিল করা হয়েছে।",
        reply_markup=main_keyboard(),
    )


# ==================================================
# ADMIN
# ==================================================

async def admin_command(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text(
            "⛔ Access Denied"
        )
        return

    await update.effective_message.reply_text(
        "🛠️ <b>Admin Panel</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


async def addchannel_command(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.effective_message.reply_text(
            "ব্যবহার: /addchannel @MyChannel"
        )
        return

    channel = context.args[0]

    if not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", channel):
        await update.effective_message.reply_text(
            "সঠিক Public Channel Username দিন।"
        )
        return

    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO channels(channel) VALUES(?)",
            (channel,),
        )

    await update.effective_message.reply_text(
        f"✅ Added: {channel}\n"
        "বটকে চ্যানেলের Administrator করতে হবে।"
    )


async def delchannel_command(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.effective_message.reply_text(
            "ব্যবহার: /delchannel @MyChannel"
        )
        return

    with db() as conn:
        conn.execute(
            "DELETE FROM channels WHERE channel=?",
            (context.args[0],),
        )

    await update.effective_message.reply_text(
        "✅ Channel removed."
    )


async def admin_callback(update, context):
    query = update.callback_query

    if query.from_user.id != ADMIN_ID:
        await query.answer("Access denied.", show_alert=True)
        return

    await query.answer()
    action = query.data

    if action == "admin_stats":
        with db() as conn:
            users = conn.execute(
                "SELECT COUNT(*) n FROM users"
            ).fetchone()["n"]

            total = conn.execute(
                "SELECT COUNT(*) n FROM history"
            ).fetchone()["n"]

            failed = conn.execute(
                "SELECT COUNT(*) n FROM history WHERE status='failed'"
            ).fetchone()["n"]

        await query.message.reply_text(
            f"📊 Users: {users}\n"
            f"📥 Total Requests: {total}\n"
            f"❌ Failed: {failed}"
        )

    elif action == "admin_channels":
        await query.message.reply_text(
            "📢 Channels:\n"
            + ("\n".join(get_channels()) or "None")
            + "\n\n/addchannel @MyChannel"
            + "\n/delchannel @MyChannel"
        )

    elif action in ("admin_add", "admin_remove"):
        context.user_data["admin_action"] = (
            "add_channel"
            if action == "admin_add"
            else "remove_channel"
        )

        await query.message.reply_text(
            "চ্যানেলের Username পাঠান।"
        )

    elif action in ("admin_block", "admin_unblock"):
        context.user_data["admin_action"] = (
            "block_user"
            if action == "admin_block"
            else "unblock_user"
        )

        await query.message.reply_text(
            "ইউজারের Numeric Telegram ID পাঠান।"
        )

    elif action == "admin_broadcast":
        context.user_data["admin_action"] = "broadcast"

        await query.message.reply_text(
            "Broadcast-এর টেক্সট পাঠান। বাতিল করতে /cancel"
        )


async def process_admin_action(update, context, text):
    action = context.user_data.get("admin_action")

    if not action or update.effective_user.id != ADMIN_ID:
        return False

    context.user_data.pop("admin_action", None)

    if action in ("add_channel", "remove_channel"):
        if not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", text):
            await update.effective_message.reply_text(
                "সঠিক Public Channel Username দিন।"
            )
            return True

        with db() as conn:
            if action == "add_channel":
                conn.execute(
                    "INSERT OR IGNORE INTO channels(channel) VALUES(?)",
                    (text,),
                )
            else:
                conn.execute(
                    "DELETE FROM channels WHERE channel=?",
                    (text,),
                )

        await update.effective_message.reply_text(
            "✅ সম্পন্ন হয়েছে।"
        )
        return True

    if action in ("block_user", "unblock_user"):
        try:
            target = int(text)
        except ValueError:
            await update.effective_message.reply_text(
                "Numeric User ID দিন।"
            )
            return True

        with db() as conn:
            exists = conn.execute(
                "SELECT user_id FROM users WHERE user_id=?",
                (target,),
            ).fetchone()

            if not exists:
                await update.effective_message.reply_text(
                    "ইউজার ডাটাবেসে নেই।"
                )
                return True

            value = 1 if action == "block_user" else 0

            conn.execute(
                "UPDATE users SET blocked=? WHERE user_id=?",
                (value, target),
            )

        await update.effective_message.reply_text(
            "✅ Block status updated."
        )
        return True

    if action == "broadcast":
        with db() as conn:
            users = conn.execute(
                "SELECT user_id FROM users WHERE blocked=0"
            ).fetchall()

        sent = 0
        failed = 0

        for row in users:
            try:
                await context.bot.send_message(
                    chat_id=row["user_id"],
                    text=text[:4096],
                )
                sent += 1
            except TelegramError:
                failed += 1

            await asyncio.sleep(0.05)

        await update.effective_message.reply_text(
            f"📨 Broadcast Finished\n"
            f"Sent: {sent}\nFailed: {failed}"
        )
        return True

    return False


# ==================================================
# MESSAGE ROUTER
# ==================================================

async def handle_message(update, context):
    message = update.effective_message
    user = update.effective_user

    if not message or not user or not message.text:
        return

    save_user(user)
    text = message.text.strip()

    if text == "❌ Cancel":
        await cancel_command(update, context)
        return

    if is_blocked(user.id):
        await message.reply_text("🚫 আপনি Blocked।")
        return

    if user.id == ADMIN_ID:
        if await process_admin_action(update, context, text):
            return

    if not await check_access(update, context):
        return

    if text == "⬇️ Download Video":
        context.user_data["mode"] = "video"

        await message.reply_text(
            "⬇️ ভিডিও লিংক পাঠান।",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("❌ Cancel")]],
                resize_keyboard=True,
            ),
        )
        return

    if text == "🖼️ Download Photo":
        context.user_data["mode"] = "photo"

        await message.reply_text(
            "🖼️ ফটো বা পোস্টের পাবলিক লিংক পাঠান।",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("❌ Cancel")]],
                resize_keyboard=True,
            ),
        )
        return

    if text == "📚 My History":
        await history_command(update, context)
        return

    if text == "❓ Help":
        await help_command(update, context)
        return

    if text == "🎧 Support":
        await message.reply_text(
            f"🎧 Support: {SUPPORT_USERNAME}",
            reply_markup=main_keyboard(),
        )
        return

    mode = context.user_data.get("mode")

    # IMPORTANT: Check format selection BEFORE URL input.
    if mode == "choose_format":
        url = context.user_data.get("pending_url")

        if text == "🎬 Download Video":
            await send_download(update, context, url, "video")
            return

        if text == "🎵 Download Audio":
            await send_download(update, context, url, "audio")
            return

        await message.reply_text(
            "Video অথবা Audio বেছে নিন।"
        )
        return

    if mode in ("video", "photo"):
        valid, reason = validate_url(text)

        if not valid:
            await message.reply_text("⚠️ " + reason)
            return

        if mode == "photo":
            await send_download(update, context, text, "photo")
            return

        context.user_data["pending_url"] = text
        context.user_data["mode"] = "choose_format"

        await message.reply_text(
            "🎬 কোন ফরম্যাট ডাউনলোড করবেন?",
            reply_markup=ReplyKeyboardMarkup(
                [
                    [
                        KeyboardButton("🎬 Download Video"),
                        KeyboardButton("🎵 Download Audio"),
                    ],
                    [KeyboardButton("❌ Cancel")],
                ],
                resize_keyboard=True,
            ),
        )
        return

    await message.reply_text(
        "মেনু থেকে একটি অপশন বেছে নিন।",
        reply_markup=main_keyboard(),
    )


# ==================================================
# JOIN CALLBACK
# ==================================================

async def check_join_callback(update, context):
    query = update.callback_query

    if is_blocked(query.from_user.id):
        await query.answer("আপনি Blocked।", show_alert=True)
        return

    if await joined_all(query.from_user.id, context):
        save_user(query.from_user)

        await query.answer("Membership verified!")

        await query.message.reply_text(
            "✅ Verification Successful!",
            reply_markup=main_keyboard(),
        )
    else:
        await query.answer(
            "সব চ্যানেলে Join করে আবার চেষ্টা করুন।",
            show_alert=True,
        )


# ==================================================
# START APPLICATION
# ==================================================

def main():
    if BOT_TOKEN == "PASTE_BOT_TOKEN_HERE":
        raise RuntimeError(
            "main.py-তে BOT_TOKEN সেট করুন।"
        )

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("addchannel", addchannel_command))
    app.add_handler(CommandHandler("delchannel", delchannel_command))

    app.add_handler(
        CallbackQueryHandler(
            check_join_callback,
            pattern=r"^check_join$",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            admin_callback,
            pattern=r"^admin_",
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    logger.info("Media Downloader is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
