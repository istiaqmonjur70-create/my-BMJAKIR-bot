import os
import sys
import json
import time
import signal
import shutil
import asyncio
import subprocess
from pathlib import Path
from threading import Lock

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============================================================
# PHP HOSTING TELEGRAM BOT
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8857119494:AAGYkDTV_PryJXECYPiRwbrEuOU3vDP6dhU")

# Example:
# https://your-domain.com
BASE_URL = os.getenv("BASE_URL", "https://my-bmjakir-bot-1.onrender.com")

ADMIN_ID = int(os.getenv("ADMIN_ID", "8814363793"))

HOST_DIR = Path(os.getenv("HOST_DIR", "php_projects"))
DATA_FILE = HOST_DIR / "users.json"

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

HOST_DIR.mkdir(parents=True, exist_ok=True)

data_lock = Lock()


# ============================================================
# DATA
# ============================================================

def load_data():
    with data_lock:
        if not DATA_FILE.exists():
            DATA_FILE.write_text(
                json.dumps({"users": {}}, indent=2),
                encoding="utf-8"
            )

        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"users": {}}


def save_data(data):
    with data_lock:
        DATA_FILE.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8"
        )


def user_dir(user_id):
    path = HOST_DIR / str(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_dir(user_id, project):
    path = user_dir(user_id) / project
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_name(name):
    name = os.path.basename(name)
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    name = "".join(c if c in allowed else "_" for c in name)

    if not name:
        name = "index.php"

    return name[:100]


def get_user_projects(user_id):
    data = load_data()
    return data["users"].get(str(user_id), {}).get("projects", {})


def ensure_user(user_id):
    data = load_data()

    uid = str(user_id)

    if uid not in data["users"]:
        data["users"][uid] = {
            "projects": {}
        }
        save_data(data)

    return data


# ============================================================
# PROCESS HELPERS
# ============================================================

def pid_file(project_path):
    return project_path / ".pid"


def log_file(project_path):
    return project_path / "php.log"


def get_pid(project_path):
    p = pid_file(project_path)

    if not p.exists():
        return None

    try:
        pid = int(p.read_text().strip())

        os.kill(pid, 0)

        return pid
    except Exception:
        try:
            p.unlink()
        except Exception:
            pass

        return None


def is_running(project_path):
    return get_pid(project_path) is not None


def stop_process(project_path):
    pid = get_pid(project_path)

    if not pid:
        return True

    try:
        os.kill(pid, signal.SIGTERM)

        for _ in range(20):
            time.sleep(0.1)

            try:
                os.kill(pid, 0)
            except OSError:
                break

        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    except Exception:
        pass

    try:
        pid_file(project_path).unlink()
    except Exception:
        pass

    return True


def find_free_port():
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    return port


def start_project(project_path, project_name):
    index_file = project_path / "index.php"

    if not index_file.exists():
        php_files = list(project_path.glob("*.php"))

        if php_files:
            shutil.copy2(
                php_files[0],
                index_file
            )
        else:
            return False, "PHP file not found."

    if is_running(project_path):
        return True, "already_running"

    port = find_free_port()

    log = open(
        log_file(project_path),
        "a",
        encoding="utf-8"
    )

    command = [
        "php",
        "-S",
        f"127.0.0.1:{port}",
        "-t",
        str(project_path)
    ]

    try:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True
        )

        pid_file(project_path).write_text(
            str(process.pid),
            encoding="utf-8"
        )

        meta = project_path / ".meta.json"

        meta.write_text(
            json.dumps({
                "port": port,
                "project": project_name,
                "started_at": int(time.time())
            }, indent=2),
            encoding="utf-8"
        )

        return True, port

    except Exception as e:
        return False, str(e)


def get_project_port(project_path):
    meta = project_path / ".meta.json"

    if not meta.exists():
        return None

    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        return data.get("port")
    except Exception:
        return None


def project_url(project_name):
    return f"{BASE_URL.rstrip('/')}/site/{project_name}/"


def read_logs(project_path):
    log = log_file(project_path)

    if not log.exists():
        return "No logs available."

    try:
        text = log.read_text(
            encoding="utf-8",
            errors="replace"
        )

        if not text.strip():
            return "No logs available."

        return text[-6000:]

    except Exception as e:
        return f"Log error: {e}"


# ============================================================
# UI
# ============================================================

def main_menu():
    keyboard = [
        [
            InlineKeyboardButton("➕ Upload PHP", callback_data="upload"),
            InlineKeyboardButton("📂 My Projects", callback_data="projects")
        ],
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
            InlineKeyboardButton("📜 Logs", callback_data="logs")
        ],
        [
            InlineKeyboardButton("ℹ️ Help", callback_data="help"),
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


def project_buttons(project_name, running):
    status = "🟢 Running" if running else "🔴 Stopped"

    keyboard = [
        [
            InlineKeyboardButton(
                status,
                callback_data=f"none:{project_name}"
            )
        ],
        [
            InlineKeyboardButton(
                "▶️ Start",
                callback_data=f"start:{project_name}"
            ),
            InlineKeyboardButton(
                "⏹ Stop",
                callback_data=f"stop:{project_name}"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Restart",
                callback_data=f"restart:{project_name}"
            ),
            InlineKeyboardButton(
                "📜 Logs",
                callback_data=f"plogs:{project_name}"
            )
        ],
        [
            InlineKeyboardButton(
                "🌐 Open",
                callback_data=f"open:{project_name}"
            ),
            InlineKeyboardButton(
                "🗑 Delete",
                callback_data=f"delete:{project_name}"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data="projects"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    ensure_user(user.id)

    text = (
        "╔══════════════════════╗\n"
        "      PHP HOSTING\n"
        "╚══════════════════════╝\n\n"
        f"👤 User: {user.first_name}\n"
        f"🆔 ID: {user.id}\n\n"
        "🚀 Host your PHP projects directly from Telegram.\n\n"
        "📁 Upload .php files\n"
        "▶️ Start / Stop / Restart\n"
        "📜 View logs\n"
        "🌐 Open hosted project\n\n"
        "Choose an option below:"
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu()
    )


# ============================================================
# UPLOAD
# ============================================================

async def upload_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_php"] = True

    await update.message.reply_text(
        "📤 Send your PHP file now.\n\n"
        "Example:\n"
        "`index.php`\n\n"
        "Only .php files are accepted.",
        parse_mode="Markdown"
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    user = update.effective_user

    if not document:
        return

    filename = safe_name(document.file_name or "index.php")

    if not filename.lower().endswith(".php"):
        await update.message.reply_text(
            "❌ Only `.php` files are allowed.",
            parse_mode="Markdown"
        )
        return

    if document.file_size and document.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            "❌ File is too large.\n"
            "Maximum size: 20 MB."
        )
        return

    await update.message.reply_text(
        "⏳ Uploading PHP file..."
    )

    try:
        tg_file = await document.get_file()

        uid = str(user.id)

        project_name = Path(filename).stem
        project_name = safe_name(project_name)

        if not project_name:
            project_name = f"project_{int(time.time())}"

        # Avoid duplicate project names
        original_name = project_name
        counter = 1

        while (HOST_DIR / uid / project_name).exists():
            project_name = f"{original_name}_{counter}"
            counter += 1

        path = project_dir(user.id, project_name)

        destination = path / filename

        await tg_file.download_to_drive(
            custom_path=str(destination)
        )

        # If the uploaded file isn't index.php,
        # make it the index file as well.
        if filename.lower() != "index.php":
            shutil.copy2(
                destination,
                path / "index.php"
            )

        data = ensure_user(user.id)

        data["users"][uid]["projects"][project_name] = {
            "filename": filename,
            "created_at": int(time.time()),
            "running": False
        }

        save_data(data)

        ok, result = start_project(
            path,
            project_name
        )

        if ok:
            if result == "already_running":
                status = "🟢 Already running"
            else:
                status = "🟢 Started automatically"

            url = project_url(project_name)

            await update.message.reply_text(
                "╔══════════════════════╗\n"
                "       PHP UPLOADED\n"
                "╚══════════════════════╝\n\n"
                f"📁 Project: `{project_name}`\n"
                f"📄 File: `{filename}`\n"
                f"⚡ Status: {status}\n\n"
                f"🌐 URL:\n{url}\n\n"
                "Manage your project below:",
                parse_mode="Markdown",
                reply_markup=project_buttons(
                    project_name,
                    True
                )
            )

        else:
            await update.message.reply_text(
                f"⚠️ File uploaded, but PHP server could not start.\n\n"
                f"Error:\n`{result}`",
                parse_mode="Markdown",
                reply_markup=project_buttons(
                    project_name,
                    False
                )
            )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Upload failed:\n\n`{e}`",
            parse_mode="Markdown"
        )


# ============================================================
# PROJECT LIST
# ============================================================

async def show_projects(update, context):
    user = update.effective_user

    projects = get_user_projects(user.id)

    if not projects:
        text = (
            "📂 **My Projects**\n\n"
            "You don't have any PHP projects yet.\n\n"
            "Upload a `.php` file to create your first project."
        )

        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "➕ Upload PHP",
                    callback_data="upload"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Back",
                    callback_data="home"
                )
            ]
        ])

        if update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            await update.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=markup
            )

        return

    keyboard = []

    for project in projects:
        path = project_dir(user.id, project)

        running = is_running(path)

        icon = "🟢" if running else "🔴"

        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {project}",
                callback_data=f"project:{project}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "➕ Upload PHP",
            callback_data="upload"
        ),
        InlineKeyboardButton(
            "⬅️ Back",
            callback_data="home"
        )
    ])

    text = (
        "╔══════════════════════╗\n"
        "       MY PROJECTS\n"
        "╚══════════════════════╝\n\n"
        f"📦 Total projects: {len(projects)}\n\n"
        "Select a project:"
    )

    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=markup
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=markup
        )


# ============================================================
# PROJECT DETAILS
# ============================================================

async def show_project(query, user_id, project):
    projects = get_user_projects(user_id)

    if project not in projects:
        await query.answer(
            "Project not found.",
            show_alert=True
        )
        return

    path = project_dir(user_id, project)

    running = is_running(path)

    port = get_project_port(path)

    status = "🟢 Running" if running else "🔴 Stopped"

    url = project_url(project)

    text = (
        "╔══════════════════════╗\n"
        "      PROJECT PANEL\n"
        "╚══════════════════════╝\n\n"
        f"📁 Project: `{project}`\n"
        f"📄 File: `{projects[project].get('filename', 'index.php')}`\n"
        f"📡 Status: {status}\n"
        f"🔌 Port: `{port or 'N/A'}`\n\n"
        f"🌐 URL:\n{url}"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=project_buttons(
            project,
            running
        )
    )


# ============================================================
# CALLBACKS
# ============================================================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    user = update.effective_user
    data = query.data

    if data == "none":
        return

    if data == "home":
        text = (
            "╔══════════════════════╗\n"
            "        PHP HOSTING\n"
            "╚══════════════════════╝\n\n"
            "🚀 Manage your PHP hosting from Telegram.\n\n"
            "Choose an option:"
        )

        await query.edit_message_text(
            text,
            reply_markup=main_menu()
        )

        return

    if data == "refresh":
        text = (
            "╔══════════════════════╗\n"
            "        PHP HOSTING\n"
            "╚══════════════════════╝\n\n"
            "🔄 Panel refreshed.\n\n"
            "Choose an option:"
        )

        await query.edit_message_text(
            text,
            reply_markup=main_menu()
        )

        return

    if data == "upload":
        context.user_data["waiting_php"] = True

        await query.edit_message_text(
            "📤 **UPLOAD PHP FILE**\n\n"
            "Send your `.php` file here.\n\n"
            "Example:\n"
            "`index.php`",
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
        await show_projects(update, context)
        return

    if data == "status":
        projects = get_user_projects(user.id)

        if not projects:
            await query.edit_message_text(
                "📊 You don't have any projects.",
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

        lines = [
            "╔══════════════════════╗",
            "        PROJECT STATUS",
            "╚══════════════════════╝",
            ""
        ]

        for project in projects:
            path = project_dir(user.id, project)
            status = "🟢 RUNNING" if is_running(path) else "🔴 STOPPED"

            lines.append(
                f"📁 `{project}` — {status}"
            )

        await query.edit_message_text(
            "\n".join(lines),
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

    if data == "logs":
        projects = get_user_projects(user.id)

        if not projects:
            await query.edit_message_text(
                "📜 No projects/logs found.",
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
                "⬅️ Back",
                callback_data="home"
            )
        ])

        await query.edit_message_text(
            "📜 **SELECT PROJECT LOGS**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return

    if data == "help":
        await query.edit_message_text(
            "╔══════════════════════╗\n"
            "           HELP\n"
            "╚══════════════════════╝\n\n"
            "1️⃣ Tap **Upload PHP**\n"
            "2️⃣ Send your `.php` file\n"
            "3️⃣ Bot creates your project\n"
            "4️⃣ PHP server starts automatically\n"
            "5️⃣ Use the generated URL\n\n"
            "Available controls:\n"
            "▶️ Start\n"
            "⏹ Stop\n"
            "🔄 Restart\n"
            "📜 Logs\n"
            "🗑 Delete",
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

    if data.startswith("project:"):
        project = data.split(":", 1)[1]
        await show_project(
            query,
            user.id,
            project
        )
        return

    if ":" not in data:
        return

    action, project = data.split(":", 1)

    projects = get_user_projects(user.id)

    if project not in projects:
        await query.answer(
            "Project not found.",
            show_alert=True
        )
        return

    path = project_dir(user.id, project)

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    if action == "start":
        ok, result = start_project(
            path,
            project
        )

        if ok:
            await query.answer(
                "Project started."
            )
        else:
            await query.answer(
                f"Start failed: {result}",
                show_alert=True
            )

        await show_project(
            query,
            user.id,
            project
        )

        return

    # --------------------------------------------------------
    # STOP
    # --------------------------------------------------------

    if action == "stop":
        stop_process(path)

        await query.answer(
            "Project stopped."
        )

        await show_project(
            query,
            user.id,
            project
        )

        return

    # --------------------------------------------------------
    # RESTART
    # --------------------------------------------------------

    if action == "restart":
        stop_process(path)

        await asyncio.sleep(1)

        ok, result = start_project(
            path,
            project
        )

        if ok:
            await query.answer(
                "Project restarted."
            )
        else:
            await query.answer(
                f"Restart failed: {result}",
                show_alert=True
            )

        await show_project(
            query,
            user.id,
            project
        )

        return

    # --------------------------------------------------------
    # LOGS
    # --------------------------------------------------------

    if action == "plogs":
        logs = read_logs(path)

        if len(logs) > 6000:
            logs = logs[-6000:]

        text = (
            f"📜 **LOGS — {project}**\n\n"
            f"```text\n{logs}\n```"
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
    # OPEN
    # --------------------------------------------------------

    if action == "open":
        url = project_url(project)

        await query.edit_message_text(
            f"🌐 **{project}**\n\n"
            f"{url}\n\n"
            "Open the URL in your browser.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🌐 Open Website",
                        url=url
                    )
                ],
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
    # DELETE
    # --------------------------------------------------------

    if action == "delete":
        keyboard = [
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
        ]

        await query.edit_message_text(
            f"⚠️ **Delete Project?**\n\n"
            f"Project: `{project}`\n\n"
            "All PHP files and logs will be permanently deleted.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return

    # --------------------------------------------------------
    # CONFIRM DELETE
    # --------------------------------------------------------

    if action == "confirmdelete":
        stop_process(path)

        try:
            shutil.rmtree(path)
        except Exception as e:
            await query.answer(
                f"Delete failed: {e}",
                show_alert=True
            )
            return

        data_store = load_data()

        try:
            del data_store["users"][str(user.id)]["projects"][project]
        except Exception:
            pass

        save_data(data_store)

        await query.edit_message_text(
            f"🗑 Project `{project}` deleted successfully.",
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

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Admin only."
        )
        return

    data = load_data()

    users = len(data.get("users", {}))

    projects = 0

    for user_data in data.get("users", {}).values():
        projects += len(
            user_data.get("projects", {})
        )

    text = (
        "╔══════════════════════╗\n"
        "         ADMIN PANEL\n"
        "╚══════════════════════╝\n\n"
        f"👥 Users: {users}\n"
        f"📦 Projects: {projects}\n"
        f"💻 Host Directory: `{HOST_DIR}`"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown"
    )


# ============================================================
# TEXT HANDLER
# ============================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_php"):
        await update.message.reply_text(
            "📤 Please send a `.php` document.\n\n"
            "Do not send PHP code as normal text."
        )
        return

    await update.message.reply_text(
        "Use /start to open the PHP Hosting panel.",
        reply_markup=main_menu()
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update, context):
    print(
        "BOT ERROR:",
        repr(context.error)
    )


# ============================================================
# MAIN
# ============================================================

def main():
    if not BOT_TOKEN or BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        print(
            "ERROR: Please set BOT_TOKEN environment variable."
        )
        sys.exit(1)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "admin",
            admin
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_document
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler
        )
    )

    app.add_error_handler(
        error_handler
    )

    print("PHP Hosting Bot is running...")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
