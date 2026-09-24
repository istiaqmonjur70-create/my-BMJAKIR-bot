# -*- coding: utf-8 -*-

import os
import json
import time
import shutil
import socket
import asyncio
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from html import escape

from aiohttp import web, ClientSession
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8640062161:AAHOKHWzo0naxUpZRmNWdqGUKlYI3wjeXo0").strip()

ADMIN_ID = int(
    os.getenv("ADMIN_ID", "8814363793")
)

PORT = int(
    os.getenv("PORT", "10000")
)

BASE_URL = os.getenv(
    "BASE_URL",
    "https://my-bmjakir-bot-1.onrender.com"
).rstrip("/")

DATA_DIR = Path(
    os.getenv(
        "DATA_DIR",
        "/app/data"
    )
)

PROJECTS_DIR = DATA_DIR / "projects"
DB_FILE = DATA_DIR / "database.json"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True
)

PROJECTS_DIR.mkdir(
    parents=True,
    exist_ok=True
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("PHP-HOST")


# ============================================================
# DATABASE
# ============================================================

DB = {
    "users": {},
    "projects": {}
}

db_lock = asyncio.Lock()


def load_db():
    global DB

    if not DB_FILE.exists():
        save_db_sync()
        return

    try:
        data = json.loads(
            DB_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, dict):
            DB = data

        DB.setdefault("users", {})
        DB.setdefault("projects", {})

    except Exception:
        logger.exception(
            "Database load error"
        )


def save_db_sync():
    try:
        DB_FILE.write_text(
            json.dumps(
                DB,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )
    except Exception:
        logger.exception(
            "Database save error"
        )


async def save_db():
    async with db_lock:
        save_db_sync()


load_db()


# ============================================================
# PROCESS STORAGE
# ============================================================

processes = {}

# pending uploaded files
pending_uploads = {}


def project_key(user_id, project):
    return f"{user_id}:{project}"


def project_dir(user_id, project):
    return (
        PROJECTS_DIR
        / str(user_id)
        / project
    )


def get_free_port():
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    sock.bind(
        ("127.0.0.1", 0)
    )

    port = sock.getsockname()[1]

    sock.close()

    return port


def valid_project_name(name):
    if not name:
        return False

    if len(name) > 40:
        return False

    allowed = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789-_"
    )

    return all(
        char in allowed
        for char in name
    )


# ============================================================
# URL
# ============================================================

def website_url(
    user_id,
    project
):
    return (
        f"{BASE_URL}/site/"
        f"{user_id}/"
        f"{project}/"
    )


# ============================================================
# START WEBSITE
# ============================================================

async def start_website(
    user_id,
    project
):
    key = project_key(
        user_id,
        project
    )

    old = processes.get(key)

    if old:
        proc = old.get("process")

        if (
            proc
            and proc.poll() is None
            and old.get("type") == "website"
        ):
            return old["port"]

    await stop_project(
        user_id,
        project
    )

    folder = project_dir(
        user_id,
        project
    )

    folder.mkdir(
        parents=True,
        exist_ok=True
    )

    port = get_free_port()

    log_path = (
        folder / ".server.log"
    )

    log_handle = open(
        log_path,
        "a",
        encoding="utf-8"
    )

    command = [
        "php",
        "-S",
        f"127.0.0.1:{port}",
        "-t",
        str(folder)
    ]

    logger.info(
        "Starting PHP website: %s",
        key
    )

    proc = subprocess.Popen(
        command,
        cwd=str(folder),
        stdout=log_handle,
        stderr=subprocess.STDOUT
    )

    processes[key] = {
        "process": proc,
        "port": port,
        "type": "website",
        "log_handle": log_handle,
        "started_at": time.time()
    }

    DB["projects"].setdefault(
        key,
        {}
    )

    DB["projects"][key].update({
        "user_id": int(user_id),
        "name": project,
        "type": "website",
        "port": port,
        "status": "running"
    })

    await save_db()

    await asyncio.sleep(1)

    if proc.poll() is not None:
        processes.pop(
            key,
            None
        )

        try:
            log_handle.close()
        except Exception:
            pass

        DB["projects"][key][
            "status"
        ] = "stopped"

        await save_db()

        raise RuntimeError(
            "PHP website failed to start."
        )

    return port


# ============================================================
# START TELEGRAM PHP BOT
# ============================================================

async def start_php_bot(
    user_id,
    project
):
    key = project_key(
        user_id,
        project
    )

    await stop_project(
        user_id,
        project
    )

    folder = project_dir(
        user_id,
        project
    )

    folder.mkdir(
        parents=True,
        exist_ok=True
    )

    bot_file = DB["projects"].get(
        key,
        {}
    ).get(
        "bot_file"
    )

    if not bot_file:
        # automatic detection
        candidates = [
            "bot.php",
            "main.php",
            "index.php"
        ]

        for name in candidates:
            if (
                folder / name
            ).exists():
                bot_file = name
                break

    if not bot_file:
        php_files = list(
            folder.glob("*.php")
        )

        if php_files:
            bot_file = php_files[0].name

    if not bot_file:
        raise RuntimeError(
            "No PHP file found."
        )

    bot_path = folder / bot_file

    if not bot_path.exists():
        raise RuntimeError(
            f"{bot_file} not found."
        )

    log_path = (
        folder / ".bot.log"
    )

    log_handle = open(
        log_path,
        "a",
        encoding="utf-8"
    )

    command = [
        "php",
        bot_file
    ]

    logger.info(
        "Starting PHP Telegram bot: %s",
        key
    )

    proc = subprocess.Popen(
        command,
        cwd=str(folder),
        stdout=log_handle,
        stderr=subprocess.STDOUT
    )

    processes[key] = {
        "process": proc,
        "port": None,
        "type": "telegram_bot",
        "bot_file": bot_file,
        "log_handle": log_handle,
        "started_at": time.time()
    }

    DB["projects"].setdefault(
        key,
        {}
    )

    DB["projects"][key].update({
        "user_id": int(user_id),
        "name": project,
        "type": "telegram_bot",
        "bot_file": bot_file,
        "port": None,
        "status": "running"
    })

    await save_db()

    await asyncio.sleep(1)

    if proc.poll() is not None:
        processes.pop(
            key,
            None
        )

        try:
            log_handle.close()
        except Exception:
            pass

        DB["projects"][key][
            "status"
        ] = "error"

        await save_db()

        raise RuntimeError(
            "PHP Telegram bot stopped immediately. "
            "Open Logs to see the error."
        )

    return bot_file


# ============================================================
# STOP
# ============================================================

async def stop_project(
    user_id,
    project
):
    key = project_key(
        user_id,
        project
    )

    item = processes.get(key)

    if item:
        proc = item.get("process")

        try:
            if (
                proc
                and proc.poll() is None
            ):
                proc.terminate()

                try:
                    proc.wait(
                        timeout=5
                    )
                except subprocess.TimeoutExpired:
                    proc.kill()

        except Exception:
            logger.exception(
                "Process stop error"
            )

        try:
            item[
                "log_handle"
            ].close()
        except Exception:
            pass

        processes.pop(
            key,
            None
        )

    if key in DB["projects"]:
        DB["projects"][key][
            "status"
        ] = "stopped"

        await save_db()

    return True


# ============================================================
# RESTART
# ============================================================

async def restart_project(
    user_id,
    project
):
    info = DB["projects"].get(
        project_key(
            user_id,
            project
        ),
        {}
    )

    ptype = info.get(
        "type",
        "website"
    )

    if ptype == "telegram_bot":
        return await start_php_bot(
            user_id,
            project
        )

    return await start_website(
        user_id,
        project
    )


# ============================================================
# ZIP EXTRACTION
# ============================================================

def safe_extract(
    zip_path,
    destination
):
    destination = destination.resolve()

    import zipfile

    with zipfile.ZipFile(
        zip_path,
        "r"
    ) as archive:

        for member in archive.infolist():

            target = (
                destination
                / member.filename
            ).resolve()

            if not str(target).startswith(
                str(destination)
            ):
                raise ValueError(
                    "Unsafe ZIP file."
                )

            if member.is_dir():
                target.mkdir(
                    parents=True,
                    exist_ok=True
                )
            else:
                target.parent.mkdir(
                    parents=True,
                    exist_ok=True
                )

                with archive.open(
                    member
                ) as src:

                    with open(
                        target,
                        "wb"
                    ) as dst:

                        shutil.copyfileobj(
                            src,
                            dst
                        )


# ============================================================
# UPLOAD
# ============================================================

async def document_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    # IMPORTANT FIX:
    # Some Telegram updates don't have message/document.
    if not update:
        return

    if not update.message:
        return

    document = update.message.document

    if not document:
        return

    user = update.effective_user

    if not user:
        return

    filename = (
        document.file_name
        or "upload"
    )

    lower = filename.lower()

    if not (
        lower.endswith(".zip")
        or lower.endswith(".php")
        or lower.endswith(".html")
    ):
        await update.message.reply_text(
            "❌ শুধু ZIP, PHP অথবা HTML file upload করুন।"
        )
        return

    project_name = Path(
        filename
    ).stem

    project_name = "".join(
        c for c in project_name
        if (
            c.isalnum()
            or c in "-_"
        )
    )

    if not project_name:
        project_name = (
            f"project_{int(time.time())}"
        )

    if len(project_name) > 35:
        project_name = project_name[:35]

    user_folder = (
        PROJECTS_DIR
        / str(user.id)
    )

    user_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    final_folder = (
        user_folder
        / project_name
    )

    if final_folder.exists():
        project_name = (
            f"{project_name}_"
            f"{int(time.time())}"
        )

        final_folder = (
            user_folder
            / project_name
        )

    final_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    await update.message.reply_text(
        "⏳ File download হচ্ছে..."
    )

    try:
        tg_file = await context.bot.get_file(
            document.file_id
        )

        temp = (
            user_folder
            / (
                f".upload_"
                f"{int(time.time())}_"
                f"{filename}"
            )
        )

        await tg_file.download_to_drive(
            custom_path=str(temp)
        )

        if lower.endswith(".zip"):

            await update.message.reply_text(
                "📦 ZIP extract হচ্ছে..."
            )

            safe_extract(
                temp,
                final_folder
            )

            temp.unlink(
                missing_ok=True
            )

        else:

            target = (
                final_folder
                / filename
            )

            shutil.move(
                str(temp),
                str(target)
            )

        key = project_key(
            user.id,
            project_name
        )

        DB["projects"][key] = {
            "user_id": user.id,
            "name": project_name,
            "type": "pending",
            "status": "stopped",
            "bot_file": None,
            "created_at": datetime.utcnow().isoformat()
        }

        await save_db()

        # Ask mode
        await update.message.reply_text(
            "✅ <b>File uploaded!</b>\n\n"
            "আপনি এই project-টি কী হিসেবে চালাতে চান?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🌐 PHP Website",
                        callback_data=(
                            f"mode_web:"
                            f"{user.id}:"
                            f"{project_name}"
                        )
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🤖 PHP Telegram Bot",
                        callback_data=(
                            f"mode_bot:"
                            f"{user.id}:"
                            f"{project_name}"
                        )
                    )
                ]
            ])
        )

    except Exception as e:

        logger.exception(
            "Upload failed"
        )

        shutil.rmtree(
            final_folder,
            ignore_errors=True
        )

        await update.message.reply_text(
            "❌ Upload failed.\n\n"
            f"<code>{escape(str(e))}</code>",
            parse_mode="HTML"
        )


# ============================================================
# PROJECT KEYBOARD
# ============================================================

def project_keyboard(
    user_id,
    project
):
    key = project_key(
        user_id,
        project
    )

    info = DB["projects"].get(
        key,
        {}
    )

    ptype = info.get(
        "type",
        "website"
    )

    buttons = []

    if ptype == "website":

        buttons.append([
            InlineKeyboardButton(
                "🌐 Open Website",
                url=website_url(
                    user_id,
                    project
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "▶️ Start",
            callback_data=(
                f"start:"
                f"{user_id}:"
                f"{project}"
            )
        ),
        InlineKeyboardButton(
            "⏹ Stop",
            callback_data=(
                f"stop:"
                f"{user_id}:"
                f"{project}"
            )
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            "🔄 Restart",
            callback_data=(
                f"restart:"
                f"{user_id}:"
                f"{project}"
            )
        ),
        InlineKeyboardButton(
            "📄 Logs",
            callback_data=(
                f"logs:"
                f"{user_id}:"
                f"{project}"
            )
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            "🗑 Delete",
            callback_data=(
                f"delete:"
                f"{user_id}:"
                f"{project}"
            )
        )
    ])

    return InlineKeyboardMarkup(
        buttons
    )


# ============================================================
# PROJECT MENU
# ============================================================

async def show_project(
    query,
    user_id,
    project
):
    key = project_key(
        user_id,
        project
    )

    info = DB["projects"].get(
        key,
        {}
    )

    if not info:
        await query.edit_message_text(
            "❌ Project not found."
        )
        return

    ptype = info.get(
        "type",
        "website"
    )

    status = info.get(
        "status",
        "stopped"
    )

    if ptype == "telegram_bot":
        type_text = "Telegram PHP Bot"
    elif ptype == "website":
        type_text = "PHP Website"
    else:
        type_text = "Not selected"

    text = (
        f"📦 <b>{escape(project)}</b>\n\n"
        f"Type: <b>{type_text}</b>\n"
        f"Status: <b>{escape(status.upper())}</b>\n"
    )

    if ptype == "website":
        text += (
            "\n🌐 <b>Website URL:</b>\n"
            f"{escape(website_url(user_id, project))}\n"
        )

    if ptype == "telegram_bot":
        bot_file = info.get(
            "bot_file",
            "Unknown"
        )

        text += (
            f"\n🤖 Bot File: "
            f"<code>{escape(bot_file)}</code>\n"
        )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=project_keyboard(
            user_id,
            project
        )
    )


# ============================================================
# MY PROJECTS
# ============================================================

async def my_projects(
    update,
    context
):
    user = update.effective_user

    projects = []

    for info in DB[
        "projects"
    ].values():

        if int(
            info.get(
                "user_id",
                0
            )
        ) == user.id:

            projects.append(info)

    buttons = []

    for info in projects:

        name = info.get(
            "name",
            "Unknown"
        )

        status = info.get(
            "status",
            "stopped"
        )

        buttons.append([
            InlineKeyboardButton(
                f"📦 {name} [{status}]",
                callback_data=(
                    f"project:"
                    f"{user.id}:"
                    f"{name}"
                )
            )
        ])

    text = (
        "📂 <b>My Projects</b>\n\n"
        "আপনার project নির্বাচন করুন।"
    )

    if not buttons:
        text = (
            "📂 <b>My Projects</b>\n\n"
            "কোনো project নেই।"
        )

    markup = InlineKeyboardMarkup(
        buttons
    ) if buttons else None

    if update.callback_query:

        await update.callback_query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=markup
        )

    else:

        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=markup
        )


# ============================================================
# START COMMAND
# ============================================================

async def start_command(
    update,
    context
):
    # Important safety check
    if not update.message:
        return

    user = update.effective_user

    if not user:
        return

    uid = str(
        user.id
    )

    DB["users"].setdefault(
        uid,
        {
            "id": user.id,
            "name": user.full_name,
            "username": user.username or ""
        }
    )

    await save_db()

    buttons = [
        [
            InlineKeyboardButton(
                "📤 Upload PHP",
                callback_data="upload"
            )
        ],
        [
            InlineKeyboardButton(
                "📂 My Projects",
                callback_data="my_projects"
            )
        ],
        [
            InlineKeyboardButton(
                "ℹ️ Help",
                callback_data="help"
            )
        ]
    ]

    if user.id == ADMIN_ID:
        buttons.append([
            InlineKeyboardButton(
                "⚙️ Admin",
                callback_data="admin"
            )
        ])

    await update.message.reply_text(
        "🚀 <b>PHP HOSTING BOT</b>\n\n"
        "PHP Website অথবা PHP Telegram Bot host করুন।\n\n"
        "📤 ZIP/PHP/HTML upload করুন।\n"
        "তারপর Website অথবা Telegram Bot mode নির্বাচন করুন।",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            buttons
        )
    )


# ============================================================
# CALLBACK HANDLER
# ============================================================

async def callback_handler(
    update,
    context
):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data or ""

    user = update.effective_user

    if not user:
        return

    # --------------------------------------------------------
    # UPLOAD
    # --------------------------------------------------------

    if data == "upload":

        await query.edit_message_text(
            "📤 <b>PHP File Upload</b>\n\n"
            "একটি ZIP, PHP অথবা HTML file এই chat-এ পাঠান।\n\n"
            "Upload-এর পর Website অথবা Telegram Bot নির্বাচন করতে পারবেন।",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # HELP
    # --------------------------------------------------------

    if data == "help":

        await query.edit_message_text(
            "ℹ️ <b>PHP Hosting</b>\n\n"
            "🌐 Website mode:\n"
            "PHP website live URL পাবেন।\n\n"
            "🤖 Telegram Bot mode:\n"
            "PHP file background process হিসেবে চলবে।\n\n"
            "▶️ Start\n"
            "⏹ Stop\n"
            "🔄 Restart\n"
            "📄 Logs",
            parse_mode="HTML"
        )

        return

    # --------------------------------------------------------
    # MY PROJECTS
    # --------------------------------------------------------

    if data == "my_projects":

        await my_projects(
            update,
            context
        )

        return

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    if data == "admin":

        if user.id != ADMIN_ID:
            return

        total_users = len(
            DB["users"]
        )

        total_projects = len(
            DB["projects"]
        )

        running = sum(
            1
            for p in DB["projects"].values()
            if p.get("status") == "running"
        )

        await query.edit_message_text(
            "⚙️ <b>ADMIN PANEL</b>\n\n"
            f"👤 Users: {total_users}\n"
            f"📦 Projects: {total_projects}\n"
            f"🟢 Running: {running}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔄 Refresh",
                        callback_data="admin"
                    )
                ]
            ])
        )

        return

    # --------------------------------------------------------
    # MODE WEBSITE
    # --------------------------------------------------------

    if data.startswith(
        "mode_web:"
    ):

        parts = data.split(
            ":",
            2
        )

        if len(parts) != 3:
            return

        user_id = int(
            parts[1]
        )

        project = parts[2]

        if user_id != user.id:
            return

        key = project_key(
            user_id,
            project
        )

        if key not in DB["projects"]:
            return

        DB["projects"][key][
            "type"
        ] = "website"

        await save_db()

        await query.edit_message_text(
            "⏳ PHP Website start হচ্ছে..."
        )

        try:

            await start_website(
                user_id,
                project
            )

            await show_project(
                query,
                user_id,
                project
            )

        except Exception as e:

            await query.edit_message_text(
                "❌ Website start failed:\n\n"
                f"<code>{escape(str(e))}</code>",
                parse_mode="HTML"
            )

        return

    # --------------------------------------------------------
    # MODE BOT
    # --------------------------------------------------------

    if data.startswith(
        "mode_bot:"
    ):

        parts = data.split(
            ":",
            2
        )

        if len(parts) != 3:
            return

        user_id = int(
            parts[1]
        )

        project = parts[2]

        if user_id != user.id:
            return

        key = project_key(
            user_id,
            project
        )

        if key not in DB["projects"]:
            return

        DB["projects"][key][
            "type"
        ] = "telegram_bot"

        # Find bot file
        folder = project_dir(
            user_id,
            project
        )

        bot_file = None

        for name in [
            "bot.php",
            "main.php"
        ]:

            if (
                folder / name
            ).exists():

                bot_file = name
                break

        if not bot_file:

            php_files = list(
                folder.glob(
                    "*.php"
                )
            )

            if php_files:
                bot_file = (
                    php_files[0].name
                )

        DB["projects"][key][
            "bot_file"
        ] = bot_file

        await save_db()

        if not bot_file:

            await query.edit_message_text(
                "❌ কোনো PHP file পাওয়া যায়নি।"
            )

            return

        await query.edit_message_text(
            "🤖 <b>PHP Telegram Bot</b>\n\n"
            f"File: <code>{escape(bot_file)}</code>\n\n"
            "⏳ Bot start হচ্ছে...",
            parse_mode="HTML"
        )

        try:

            await start_php_bot(
                user_id,
                project
            )

            await show_project(
                query,
                user_id,
                project
            )

        except Exception as e:

            await query.edit_message_text(
                "❌ PHP Bot start failed.\n\n"
                f"<code>{escape(str(e))}</code>\n\n"
                "📄 Logs থেকে বিস্তারিত error দেখুন।",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📄 Logs",
                            callback_data=(
                                f"logs:"
                                f"{user_id}:"
                                f"{project}"
                            )
                        )
                    ]
                ])
            )

        return

    # --------------------------------------------------------
    # PROJECT
    # --------------------------------------------------------

    if data.startswith(
        "project:"
    ):

        parts = data.split(
            ":",
            2
        )

        if len(parts) != 3:
            return

        user_id = int(
            parts[1]
        )

        project = parts[2]

        if user_id != user.id:
            return

        await show_project(
            query,
            user_id,
            project
        )

        return

    # --------------------------------------------------------
    # START / STOP / RESTART / LOGS / DELETE
    # --------------------------------------------------------

    parts = data.split(
        ":",
        2
    )

    if len(parts) != 3:
        return

    action = parts[0]

    if action not in {
        "start",
        "stop",
        "restart",
        "logs",
        "delete"
    }:
        return

    user_id = int(
        parts[1]
    )

    project = parts[2]

    if user_id != user.id:
        return

    key = project_key(
        user_id,
        project
    )

    if key not in DB["projects"]:
        await query.edit_message_text(
            "❌ Project not found."
        )
        return

    if action == "start":

        info = DB["projects"][key]

        if info.get(
            "type"
        ) == "telegram_bot":

            await start_php_bot(
                user_id,
                project
            )

        else:

            await start_website(
                user_id,
                project
            )

        await show_project(
            query,
            user_id,
            project
        )

    elif action == "stop":

        await stop_project(
            user_id,
            project
        )

        await show_project(
            query,
            user_id,
            project
        )

    elif action == "restart":

        await restart_project(
            user_id,
            project
        )

        await show_project(
            query,
            user_id,
            project
        )

    elif action == "logs":

        folder = project_dir(
            user_id,
            project
        )

        info = DB["projects"].get(
            key,
            {}
        )

        if info.get(
            "type"
        ) == "telegram_bot":

            log_file = (
                folder / ".bot.log"
            )

        else:

            log_file = (
                folder / ".server.log"
            )

        if not log_file.exists():

            text = (
                "📄 কোনো log পাওয়া যায়নি।"
            )

        else:

            content = log_file.read_text(
                encoding="utf-8",
                errors="ignore"
            )

            if len(content) > 3800:
                content = content[-3800:]

            text = (
                f"📄 <b>{escape(project)} Logs</b>\n\n"
                f"<pre>{escape(content)}</pre>"
            )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data=(
                            f"project:"
                            f"{user_id}:"
                            f"{project}"
                        )
                    )
                ]
            ])
        )

    elif action == "delete":

        await stop_project(
            user_id,
            project
        )

        shutil.rmtree(
            project_dir(
                user_id,
                project
            ),
            ignore_errors=True
        )

        DB["projects"].pop(
            key,
            None
        )

        await save_db()

        await query.edit_message_text(
            "✅ Project deleted successfully."
        )


# ============================================================
# PUBLIC WEB SERVER
# ============================================================

async def home(request):
    return web.Response(
        text=(
            "<!doctype html>"
            "<html>"
            "<head>"
            "<meta charset='utf-8'>"
            "<meta name='viewport' "
            "content='width=device-width,initial-scale=1'>"
            "<title>PHP Hosting</title>"
            "</head>"
            "<body style='margin:0;"
            "background:#080b14;color:white;"
            "font-family:Arial;text-align:center;"
            "padding-top:70px'>"
            "<h1>PHP Hosting Server</h1>"
            "<p>ONLINE</p>"
            "<p>PHP Website + PHP Telegram Bot Hosting</p>"
            "</body>"
            "</html>"
        ),
        content_type="text/html"
    )


async def health(request):
    return web.json_response({
        "status": "ok",
        "service": "php-hosting",
        "time": datetime.utcnow().isoformat()
    })


async def proxy_site(request):
    user_id = request.match_info[
        "user_id"
    ]

    project = request.match_info[
        "project"
    ]

    path = request.match_info.get(
        "path",
        ""
    )

    key = project_key(
        user_id,
        project
    )

    info = DB["projects"].get(
        key
    )

    if not info:
        return web.Response(
            status=404,
            text="Project not found."
        )

    if info.get(
        "type"
    ) != "website":
        return web.Response(
            status=400,
            text="This project is a Telegram bot."
        )

    folder = project_dir(
        user_id,
        project
    )

    if not folder.exists():
        return web.Response(
            status=404,
            text="Project files not found."
        )

    item = processes.get(key)

    if (
        not item
        or not item.get("process")
        or item["process"].poll() is not None
    ):

        try:
            port = await start_website(
                int(user_id),
                project
            )

        except Exception as e:

            return web.Response(
                status=500,
                text=f"PHP server failed: {e}"
            )

    else:

        port = item["port"]

    target_path = "/" + path

    target_url = (
        f"http://127.0.0.1:"
        f"{port}"
        f"{target_path}"
    )

    if request.query_string:
        target_url += (
            "?"
            + request.query_string
        )

    headers = {}

    for name, value in request.headers.items():

        if name.lower() in {
            "host",
            "content-length",
            "connection"
        }:
            continue

        headers[name] = value

    body = await request.read()

    try:

        async with ClientSession() as session:

            async with session.request(
                request.method,
                target_url,
                headers=headers,
                data=body,
                allow_redirects=False
            ) as response:

                response_body = await response.read()

                response_headers = {}

                for name, value in response.headers.items():

                    if name.lower() in {
                        "content-length",
                        "transfer-encoding",
                        "connection"
                    }:
                        continue

                    response_headers[name] = value

                return web.Response(
                    status=response.status,
                    body=response_body,
                    headers=response_headers
                )

    except Exception as e:

        logger.exception(
            "Proxy error"
        )

        return web.Response(
            status=502,
            text=f"Bad Gateway: {e}"
        )


# ============================================================
# WEB SERVER
# ============================================================

async def start_web():
    app = web.Application(
        client_max_size=100 * 1024 * 1024
    )

    app.router.add_get(
        "/",
        home
    )

    app.router.add_get(
        "/health",
        health
    )

    app.router.add_route(
        "*",
        "/site/{user_id}/{project}/{path:.*}",
        proxy_site
    )

    runner = web.AppRunner(
        app
    )

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT
    )

    await site.start()

    logger.info(
        "======================================"
    )

    logger.info(
        "WEB SERVER LISTENING ON 0.0.0.0:%s",
        PORT
    )

    logger.info(
        "BASE URL: %s",
        BASE_URL
    )

    logger.info(
        "======================================"
    )

    return runner


# ============================================================
# CLEANUP
# ============================================================

async def cleanup():
    for key, item in list(
        processes.items()
    ):

        try:

            proc = item.get(
                "process"
            )

            if (
                proc
                and proc.poll() is None
            ):
                proc.terminate()

                try:
                    proc.wait(
                        timeout=3
                    )
                except Exception:
                    proc.kill()

            item[
                "log_handle"
            ].close()

        except Exception:
            pass

    processes.clear()


# ============================================================
# MAIN
# ============================================================

async def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    logger.info(
        "Starting PHP Hosting..."
    )

    # Web server FIRST
    # Render will detect this port.
    web_runner = await start_web()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    app.add_handler(
        CommandHandler(
            "upload",
            lambda update, context:
            upload_command(
                update,
                context
            )
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            document_handler
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    await app.initialize()

    await app.start()

    await app.updater.start_polling(
        drop_pending_updates=True
    )

    logger.info(
        "Telegram bot polling started."
    )

    try:

        await asyncio.Event().wait()

    finally:

        await cleanup()

        try:
            await app.updater.stop()
        except Exception:
            pass

        try:
            await app.stop()
        except Exception:
            pass

        try:
            await app.shutdown()
        except Exception:
            pass

        await web_runner.cleanup()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        pass

    except Exception:

        logger.exception(
            "FATAL ERROR"
        )

        raise