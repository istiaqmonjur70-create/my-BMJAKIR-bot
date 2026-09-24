import os
import re
import json
import time
import signal
import socket
import shutil
import threading
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from aiohttp import web, ClientSession
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8640062161:AAHOKHWzo0naxUpZRmNWdqGUKlYI3wjeXo0").strip()

ADMIN_ID = int(os.getenv("ADMIN_ID", "8814363793"))

BASE_URL = os.getenv(
    "BASE_URL",
    "https://my-bmjakir-bot-1.onrender.com"
).rstrip("/")

PORT = int(os.getenv("PORT", "10000"))

DATA_DIR = Path(
    os.getenv("DATA_DIR", "/app/data")
)

PROJECTS_DIR = DATA_DIR / "projects"
USERS_FILE = DATA_DIR / "users.json"

MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB

PROJECT_NAME_RE = re.compile(
    r"^[A-Za-z0-9_-]{1,40}$"
)

ALLOWED_PHP_EXTENSIONS = {
    ".php"
}


# ============================================================
# DIRECTORIES
# ============================================================

DATA_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

DATA_LOCK = threading.RLock()
PROCESS_LOCK = threading.RLock()

PROCESSES = {}


# ============================================================
# DATABASE
# ============================================================

def load_users():
    with DATA_LOCK:
        if not USERS_FILE.exists():
            USERS_FILE.write_text(
                json.dumps(
                    {"users": {}},
                    indent=2
                ),
                encoding="utf-8"
            )

        try:
            return json.loads(
                USERS_FILE.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            return {"users": {}}


def save_users(data):
    with DATA_LOCK:
        tmp = USERS_FILE.with_suffix(".tmp")

        tmp.write_text(
            json.dumps(
                data,
                indent=2
            ),
            encoding="utf-8"
        )

        tmp.replace(USERS_FILE)


def ensure_user(user_id):
    data = load_users()

    uid = str(user_id)

    if uid not in data["users"]:
        data["users"][uid] = {
            "created_at": int(time.time()),
            "projects": {}
        }

        save_users(data)

    return data


def get_projects(user_id):
    data = load_users()

    return data["users"].get(
        str(user_id),
        {}
    ).get(
        "projects",
        {}
    )


# ============================================================
# PATH HELPERS
# ============================================================

def user_root(user_id):
    path = PROJECTS_DIR / str(user_id)
    path.mkdir(
        parents=True,
        exist_ok=True
    )
    return path


def project_path(user_id, project):
    return user_root(user_id) / project


def safe_filename(filename):
    filename = os.path.basename(
        filename or ""
    )

    filename = re.sub(
        r"[^A-Za-z0-9._-]",
        "_",
        filename
    )

    if not filename:
        filename = "index.php"

    return filename[:120]


def valid_project_name(name):
    return bool(
        PROJECT_NAME_RE.fullmatch(name)
    )


# ============================================================
# PORT
# ============================================================

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


# ============================================================
# PROJECT PROCESS
# ============================================================

def pid_path(path):
    return path / ".php.pid"


def meta_path(path):
    return path / ".project.json"


def log_path(path):
    return path / "php.log"


def get_project_meta(path):
    file = meta_path(path)

    if not file.exists():
        return {}

    try:
        return json.loads(
            file.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def save_project_meta(path, data):
    meta_path(path).write_text(
        json.dumps(
            data,
            indent=2
        ),
        encoding="utf-8"
    )


def get_pid(path):
    with PROCESS_LOCK:

        process = PROCESSES.get(
            str(path)
        )

        if process:
            if process.poll() is None:
                return process.pid

            PROCESSES.pop(
                str(path),
                None
            )

        pid_file = pid_path(path)

        if not pid_file.exists():
            return None

        try:
            pid = int(
                pid_file.read_text().strip()
            )

            os.kill(pid, 0)

            return pid

        except Exception:

            try:
                pid_file.unlink()
            except Exception:
                pass

            return None


def is_running(path):
    return get_pid(path) is not None


def start_php_server(
    user_id,
    project
):
    path = project_path(
        user_id,
        project
    )

    if not path.exists():
        return False, "Project does not exist."

    index = path / "index.php"

    php_files = list(
        path.glob("*.php")
    )

    if not index.exists():

        if not php_files:
            return False, "No PHP file found."

        shutil.copy2(
            php_files[0],
            index
        )

    if is_running(path):
        return True, "already_running"

    port = get_free_port()

    logfile = open(
        log_path(path),
        "a",
        encoding="utf-8",
        buffering=1
    )

    command = [
        "php",
        "-S",
        f"127.0.0.1:{port}",
        "-t",
        str(path)
    ]

    try:

        process = subprocess.Popen(
            command,
            stdout=logfile,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True
        )

        with PROCESS_LOCK:
            PROCESSES[str(path)] = process

        pid_path(path).write_text(
            str(process.pid),
            encoding="utf-8"
        )

        save_project_meta(
            path,
            {
                "port": port,
                "pid": process.pid,
                "started_at": int(time.time())
            }
        )

        return True, port

    except Exception as e:

        try:
            logfile.close()
        except Exception:
            pass

        return False, str(e)


def stop_php_server(
    user_id,
    project
):
    path = project_path(
        user_id,
        project
    )

    process = None

    with PROCESS_LOCK:
        process = PROCESSES.get(
            str(path)
        )

    if process:

        try:
            process.terminate()

            try:
                process.wait(
                    timeout=5
                )
            except subprocess.TimeoutExpired:
                process.kill()

        except Exception:
            pass

        with PROCESS_LOCK:
            PROCESSES.pop(
                str(path),
                None
            )

    else:

        pid = get_pid(path)

        if pid:

            try:
                os.kill(
                    pid,
                    signal.SIGTERM
                )
            except Exception:
                pass

    try:
        pid_path(path).unlink()
    except Exception:
        pass

    return True


def restart_php_server(
    user_id,
    project
):
    stop_php_server(
        user_id,
        project
    )

    time.sleep(0.5)

    return start_php_server(
        user_id,
        project
    )


# ============================================================
# URL
# ============================================================

def project_url(
    user_id,
    project
):
    return (
        f"{BASE_URL}"
        f"/site/{user_id}/{project}/"
    )


# ============================================================
# LOGS
# ============================================================

def get_logs(
    user_id,
    project
):
    path = project_path(
        user_id,
        project
    )

    file = log_path(path)

    if not file.exists():
        return "No logs yet."

    try:
        text = file.read_text(
            encoding="utf-8",
            errors="replace"
        )

        if len(text) > 6000:
            text = text[-6000:]

        return text or "No logs yet."

    except Exception as e:
        return f"Log error: {e}"


# ============================================================
# PROJECT DELETE
# ============================================================

def delete_project(
    user_id,
    project
):
    stop_php_server(
        user_id,
        project
    )

    path = project_path(
        user_id,
        project
    )

    if path.exists():
        shutil.rmtree(path)

    data = load_users()

    uid = str(user_id)

    if (
        uid in data["users"]
        and project in data["users"][uid]["projects"]
    ):
        del data["users"][uid]["projects"][project]

        save_users(data)


# ============================================================
# TELEGRAM UI
# ============================================================

def home_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Upload PHP",
                callback_data="upload"
            ),
            InlineKeyboardButton(
                "📂 My Projects",
                callback_data="projects"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Status",
                callback_data="status"
            ),
            InlineKeyboardButton(
                "📜 Logs",
                callback_data="logs"
            )
        ],
        [
            InlineKeyboardButton(
                "ℹ️ Help",
                callback_data="help"
            )
        ]
    ])


def project_keyboard(
    user_id,
    project
):
    path = project_path(
        user_id,
        project
    )

    running = is_running(path)

    status = (
        "🟢 Running"
        if running
        else
        "🔴 Stopped"
    )

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                status,
                callback_data="noop"
            )
        ],
        [
            InlineKeyboardButton(
                "▶️ Start",
                callback_data=f"start:{project}"
            ),
            InlineKeyboardButton(
                "⏹ Stop",
                callback_data=f"stop:{project}"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Restart",
                callback_data=f"restart:{project}"
            ),
            InlineKeyboardButton(
                "📜 Logs",
                callback_data=f"plogs:{project}"
            )
        ],
        [
            InlineKeyboardButton(
                "🌐 Open",
                url=project_url(
                    user_id,
                    project
                )
            ),
            InlineKeyboardButton(
                "🗑 Delete",
                callback_data=f"delete:{project}"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data="projects"
            )
        ]
    ])


# ============================================================
# /START
# ============================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    ensure_user(user.id)

    context.user_data[
        "waiting_upload"
    ] = False

    text = (
        "╔══════════════════════════╗\n"
        "        PHP HOSTING\n"
        "╚══════════════════════════╝\n\n"
        f"👤 {user.first_name}\n"
        f"🆔 `{user.id}`\n\n"
        "Host your PHP projects directly "
        "from Telegram.\n\n"
        "• Upload PHP files\n"
        "• Start / Stop / Restart\n"
        "• Public PHP URL\n"
        "• Logs\n"
        "• Project management\n\n"
        "Choose an option:"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=home_keyboard()
    )


# ============================================================
# UPLOAD COMMAND
# ============================================================

async def upload_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data[
        "waiting_upload"
    ] = True

    await update.message.reply_text(
        "📤 **Send your PHP file now.**\n\n"
        "Example:\n"
        "`index.php`\n\n"
        "Maximum file size: 25 MB",
        parse_mode="Markdown"
    )


# ============================================================
# DOCUMENT UPLOAD
# ============================================================

async def document_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    document = update.message.document

    if not document:
        return

    filename = safe_filename(
        document.file_name
    )

    extension = Path(
        filename
    ).suffix.lower()

    if extension not in ALLOWED_PHP_EXTENSIONS:

        await update.message.reply_text(
            "❌ Only `.php` files are allowed."
        )

        return

    if (
        document.file_size
        and
        document.file_size > MAX_UPLOAD_SIZE
    ):

        await update.message.reply_text(
            "❌ File too large.\n\n"
            "Maximum: 25 MB."
        )

        return

    user = update.effective_user

    await update.message.reply_text(
        "⏳ Uploading PHP file..."
    )

    try:

        ensure_user(
            user.id
        )

        tg_file = await document.get_file()

        original_project = Path(
            filename
        ).stem

        original_project = re.sub(
            r"[^A-Za-z0-9_-]",
            "_",
            original_project
        )

        if not original_project:
            original_project = "project"

        original_project = original_project[:30]

        project = original_project

        counter = 1

        while project_path(
            user.id,
            project
        ).exists():

            project = (
                f"{original_project}_{counter}"
            )

            counter += 1

        path = project_path(
            user.id,
            project
        )

        path.mkdir(
            parents=True,
            exist_ok=True
        )

        destination = path / filename

        await tg_file.download_to_drive(
            custom_path=str(destination)
        )

        if filename.lower() != "index.php":

            shutil.copy2(
                destination,
                path / "index.php"
            )

        data = load_users()

        uid = str(user.id)

        data["users"][uid][
            "projects"
        ][project] = {
            "filename": filename,
            "created_at": int(time.time())
        }

        save_users(data)

        ok, result = start_php_server(
            user.id,
            project
        )

        if not ok:

            await update.message.reply_text(
                "⚠️ File uploaded, but PHP "
                "server could not start.\n\n"
                f"Error:\n`{result}`",
                parse_mode="Markdown"
            )

            return

        url = project_url(
            user.id,
            project
        )

        text = (
            "╔══════════════════════════╗\n"
            "       PHP UPLOADED\n"
            "╚══════════════════════════╝\n\n"
            f"📁 Project: `{project}`\n"
            f"📄 File: `{filename}`\n"
            "🟢 Status: Running\n\n"
            f"🌐 URL:\n{url}\n\n"
            "Your PHP project is ready."
        )

        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=project_keyboard(
                user.id,
                project
            )
        )

        context.user_data[
            "waiting_upload"
        ] = False

    except Exception as e:

        await update.message.reply_text(
            "❌ Upload failed.\n\n"
            f"`{e}`",
            parse_mode="Markdown"
        )


# ============================================================
# PROJECT LIST
# ============================================================

async def projects_page(
    query,
    user_id
):
    projects = get_projects(
        user_id
    )

    keyboard = []

    for project in projects:

        running = is_running(
            project_path(
                user_id,
                project
            )
        )

        icon = (
            "🟢"
            if running
            else
            "🔴"
        )

        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {project}",
                callback_data=f"project:{project}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "➕ Upload",
            callback_data="upload"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Home",
            callback_data="home"
        )
    ])

    text = (
        "╔══════════════════════════╗\n"
        "         MY PROJECTS\n"
        "╚══════════════════════════╝\n\n"
    )

    if not projects:
        text += (
            "No projects yet.\n\n"
            "Upload a PHP file to create one."
        )
    else:
        text += (
            f"Total: {len(projects)}\n\n"
            "Select a project:"
        )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# PROJECT PAGE
# ============================================================

async def project_page(
    query,
    user_id,
    project
):
    projects = get_projects(
        user_id
    )

    if project not in projects:

        await query.answer(
            "Project not found.",
            show_alert=True
        )

        return

    path = project_path(
        user_id,
        project
    )

    running = is_running(path)

    meta = get_project_meta(
        path
    )

    port = meta.get(
        "port",
        "N/A"
    )

    status = (
        "🟢 Running"
        if running
        else
        "🔴 Stopped"
    )

    text = (
        "╔══════════════════════════╗\n"
        "        PROJECT PANEL\n"
        "╚══════════════════════════╝\n\n"
        f"📁 Project: `{project}`\n"
        f"📄 File: `{projects[project].get('filename', 'index.php')}`\n"
        f"📡 Status: {status}\n"
        f"🔌 Internal Port: `{port}`\n\n"
        f"🌐 URL:\n"
        f"{project_url(user_id, project)}"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=project_keyboard(
            user_id,
            project
        )
    )


# ============================================================
# CALLBACK
# ============================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    await query.answer()

    user = update.effective_user

    data = query.data

    if data == "noop":
        return

    if data == "home":

        await query.edit_message_text(
            "╔══════════════════════════╗\n"
            "        PHP HOSTING\n"
            "╚══════════════════════════╝\n\n"
            "Choose an option:",
            reply_markup=home_keyboard()
        )

        return

    if data == "upload":

        context.user_data[
            "waiting_upload"
        ] = True

        await query.edit_message_text(
            "📤 **UPLOAD PHP FILE**\n\n"
            "Send your `.php` file now.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="home"
                    )
                ]
            ])
        )

        return

    if data == "projects":

        await projects_page(
            query,
            user.id
        )

        return

    if data == "status":

        projects = get_projects(
            user.id
        )

        lines = [
            "╔══════════════════════════╗",
            "         PROJECT STATUS",
            "╚══════════════════════════╝",
            ""
        ]

        if not projects:

            lines.append(
                "No projects."
            )

        else:

            for project in projects:

                running = is_running(
                    project_path(
                        user.id,
                        project
                    )
                )

                status = (
                    "🟢 RUNNING"
                    if running
                    else
                    "🔴 STOPPED"
                )

                lines.append(
                    f"📁 `{project}` — {status}"
                )

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Home",
                        callback_data="home"
                    )
                ]
            ])
        )

        return

    if data == "logs":

        projects = get_projects(
            user.id
        )

        keyboard = []

        for project in projects:

            keyboard.append([
                InlineKeyboardButton(
                    f"📜 {project}",
                    callback_data=f"plogs:{project}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "⬅️ Home",
                callback_data="home"
            )
        ])

        await query.edit_message_text(
            "📜 **SELECT PROJECT LOGS**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

        return

    if data == "help":

        await query.edit_message_text(
            "╔══════════════════════════╗\n"
            "            HELP\n"
            "╚══════════════════════════╝\n\n"
            "1. Upload a `.php` file.\n"
            "2. Bot creates a separate project.\n"
            "3. PHP server starts automatically.\n"
            "4. You receive a public URL.\n"
            "5. Manage it from Project Panel.\n\n"
            "Controls:\n"
            "▶️ Start\n"
            "⏹ Stop\n"
            "🔄 Restart\n"
            "📜 Logs\n"
            "🌐 Open\n"
            "🗑 Delete",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Home",
                        callback_data="home"
                    )
                ]
            ])
        )

        return

    if ":" not in data:
        return

    action, project = data.split(
        ":",
        1
    )

    projects = get_projects(
        user.id
    )

    if project not in projects:

        await query.answer(
            "Project not found.",
            show_alert=True
        )

        return

    # --------------------------------------------------------
    # PROJECT
    # --------------------------------------------------------

    if action == "project":

        await project_page(
            query,
            user.id,
            project
        )

        return

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    if action == "start":

        ok, result = start_php_server(
            user.id,
            project
        )

        if ok:

            await query.answer(
                "Project started."
            )

        else:

            await query.answer(
                f"Error: {result}",
                show_alert=True
            )

        await project_page(
            query,
            user.id,
            project
        )

        return

    # --------------------------------------------------------
    # STOP
    # --------------------------------------------------------

    if action == "stop":

        stop_php_server(
            user.id,
            project
        )

        await query.answer(
            "Project stopped."
        )

        await project_page(
            query,
            user.id,
            project
        )

        return

    # --------------------------------------------------------
    # RESTART
    # --------------------------------------------------------

    if action == "restart":

        ok, result = restart_php_server(
            user.id,
            project
        )

        if ok:

            await query.answer(
                "Project restarted."
            )

        else:

            await query.answer(
                f"Error: {result}",
                show_alert=True
            )

        await project_page(
            query,
            user.id,
            project
        )

        return

    # --------------------------------------------------------
    # LOGS
    # --------------------------------------------------------

    if action == "plogs":

        logs = get_logs(
            user.id,
            project
        )

        safe_logs = logs.replace(
            "```",
            "'''"
        )

        text = (
            f"📜 **LOGS — {project}**\n\n"
            f"```text\n"
            f"{safe_logs}\n"
            f"```"
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Project",
                        callback_data=f"project:{project}"
                    )
                ]
            ])
        )

        return

    # --------------------------------------------------------
    # DELETE CONFIRM
    # --------------------------------------------------------

    if action == "delete":

        await query.edit_message_text(
            "⚠️ **DELETE PROJECT?**\n\n"
            f"Project: `{project}`\n\n"
            "All uploaded PHP files and logs "
            "will be deleted.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "❌ Yes, Delete",
                        callback_data=f"confirmdelete:{project}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Cancel",
                        callback_data=f"project:{project}"
                    )
                ]
            ])
        )

        return

    # --------------------------------------------------------
    # CONFIRM DELETE
    # --------------------------------------------------------

    if action == "confirmdelete":

        delete_project(
            user.id,
            project
        )

        await query.edit_message_text(
            f"🗑 `{project}` deleted successfully.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📂 My Projects",
                        callback_data="projects"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 Home",
                        callback_data="home"
                    )
                ]
            ])
        )

        return


# ============================================================
# ADMIN
# ============================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Admin only."
        )

        return

    data = load_users()

    users = len(
        data.get(
            "users",
            {}
        )
    )

    projects = 0

    for item in data.get(
        "users",
        {}
    ).values():

        projects += len(
            item.get(
                "projects",
                {}
            )
        )

    running = 0

    for item in data.get(
        "users",
        {}
    ).items():

        uid, user_data = item

        for project in user_data.get(
            "projects",
            {}
        ):

            if is_running(
                project_path(
                    uid,
                    project
                )
            ):
                running += 1

    text = (
        "╔══════════════════════════╗\n"
        "          ADMIN PANEL\n"
        "╚══════════════════════════╝\n\n"
        f"👥 Users: {users}\n"
        f"📦 Projects: {projects}\n"
        f"🟢 Running: {running}\n"
        f"🌐 URL: {BASE_URL}\n"
        f"🔌 Port: {PORT}"
    )

    await update.message.reply_text(
        text
    )


# ============================================================
# TEXT
# ============================================================

async def text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if context.user_data.get(
        "waiting_upload"
    ):

        await update.message.reply_text(
            "📤 Send the PHP file as a document.\n\n"
            "Example: `index.php`",
            parse_mode="Markdown"
        )

        return

    await update.message.reply_text(
        "Use /start to open the PHP Hosting panel."
    )


# ============================================================
# PUBLIC WEB SERVER
# ============================================================

async def health(request):
    return web.json_response({
        "status": "ok",
        "service": "PHP Hosting",
        "time": int(time.time())
    })


async def root(request):
    return web.Response(
        text=(
            "PHP Hosting Server is online.\n\n"
            "Use Telegram bot to manage projects."
        ),
        content_type="text/plain"
    )


async def project_proxy(
    request
):
    """
    Public URL:

    /site/{user_id}/{project}/...

    Example:

    /site/123456/index/

    is proxied to the user's local PHP server.
    """

    user_id = request.match_info[
        "user_id"
    ]

    project = request.match_info[
        "project"
    ]

    remaining = request.match_info.get(
        "path",
        ""
    )

    if not user_id.isdigit():
        raise web.HTTPNotFound()

    if not valid_project_name(project):
        raise web.HTTPNotFound()

    path = project_path(
        user_id,
        project
    )

    if not path.exists():
        raise web.HTTPNotFound(
            text="Project not found."
        )

    if not is_running(path):

        # Automatically start stopped project.
        ok, result = start_php_server(
            int(user_id),
            project
        )

        if not ok:
            raise web.HTTPServiceUnavailable(
                text="PHP server is not running."
            )

    meta = get_project_meta(
        path
    )

    port = meta.get(
        "port"
    )

    if not port:
        raise web.HTTPServiceUnavailable(
            text="PHP server port unavailable."
        )

    if remaining:
        upstream_path = "/" + remaining
    else:
        upstream_path = "/"

    query = request.query_string

    if query:
        upstream_path += "?" + query

    upstream_url = (
        f"http://127.0.0.1:"
        f"{port}"
        f"{upstream_path}"
    )

    body = await request.read()

    headers = {}

    skip_headers = {
        "host",
        "content-length",
        "connection",
        "transfer-encoding",
        "upgrade",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer"
    }

    for key, value in request.headers.items():

        if key.lower() in skip_headers:
            continue

        headers[key] = value

    headers["Host"] = (
        f"127.0.0.1:{port}"
    )

    timeout = 60

    try:

        async with ClientSession() as session:

            async with session.request(
                request.method,
                upstream_url,
                headers=headers,
                data=body,
                allow_redirects=False,
                timeout=timeout
            ) as response:

                response_body = await response.read()

                response_headers = {}

                for key, value in response.headers.items():

                    if key.lower() in {
                        "content-length",
                        "transfer-encoding",
                        "connection"
                    }:
                        continue

                    response_headers[
                        key
                    ] = value

                return web.Response(
                    status=response.status,
                    body=response_body,
                    headers=response_headers
                )

    except Exception as e:

        return web.Response(
            status=502,
            text=(
                "PHP upstream error.\n\n"
                f"{e}"
            )
        )


# ============================================================
# WEB SERVER THREAD
# ============================================================

def run_web_server():
    app = web.Application(
        client_max_size=MAX_UPLOAD_SIZE
    )

    app.router.add_get(
        "/",
        root
    )

    app.router.add_get(
        "/health",
        health
    )

    app.router.add_route(
        "*",
        "/site/{user_id}/{project}/{path:.*}",
        project_proxy
    )

    print(
        f"Web server listening on "
        f"0.0.0.0:{PORT}"
    )

    web.run_app(
        app,
        host="0.0.0.0",
        port=PORT,
        print=None
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    print(
        "================================"
    )

    print(
        "PHP HOSTING BOT"
    )

    print(
        f"BASE_URL: {BASE_URL}"
    )

    print(
        f"PORT: {PORT}"
    )

    print(
        "================================"
    )

    web_thread = threading.Thread(
        target=run_web_server,
        daemon=True
    )

    web_thread.start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    application.add_handler(
        CommandHandler(
            "upload",
            upload_command
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Document.ALL,
            document_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            text_handler
        )
    )

    print(
        "Telegram bot starting..."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
