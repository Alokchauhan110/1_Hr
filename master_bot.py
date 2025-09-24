import asyncio
import json
import logging
import os
import random
import re
import time
from collections import defaultdict
from dotenv import load_dotenv

import requests
from telethon.sync import TelegramClient, events
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# --- Load Environment Variables ---
load_dotenv()

# ==============================================================================
# --- CONFIGURATION (Loaded from .env file) ---
# ==============================================================================
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))
# ==============================================================================

# --- Global File Paths & Constants ---
SESSION_FILE = 'telegram_user.session'
TASKS_FILE = 'tasks.json'
POSTED_MESSAGES_FILE = 'posted_messages.json'
MESSAGE_FETCH_LIMIT = 5000

# --- Logging Setup ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Global Clients & Task Variables ---
telethon_client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
running_tasks = {}

# --- Data Persistence ---
def load_data(filename):
    try:
        with open(filename, 'r') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {}

def save_data(filename, data):
    with open(filename, 'w') as f: json.dump(data, f, indent=4)

# --- Link Processing ---
def process_terabox_links(text):
    if not text: return text
    try:
        urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
        for url in urls:
            if 'terabox' in url.lower():
                response = requests.get(f'http://tinyurl.com/api-create.php?url={url}')
                if response.status_code == 200:
                    text = text.replace(url, response.text)
    except Exception as e:
        logger.error(f"Error shortening URL: {e}")
    return text

# ==============================================================================
# --- CORE FORWARDING LOGIC ---
# ==============================================================================
async def send_post(destinations, messages):
    if not isinstance(destinations, list): destinations = [destinations]
    messages.sort(key=lambda m: m.id)
    media_to_send = [msg.media for msg in messages if msg.media]
    caption = next((msg.text for msg in messages if msg.text), None)
    buttons = next((msg.buttons for msg in messages if msg.buttons), None)
    processed_caption = process_terabox_links(caption)
    for dest_id in destinations:
        try:
            await telethon_client.send_file(dest_id, file=media_to_send, caption=processed_caption, buttons=buttons)
            logger.info(f"Post successfully sent to {dest_id}.")
        except Exception as e:
            logger.error(f"Failed to send post to destination {dest_id}: {e}")

async def scheduled_post_task(task_id, task_info):
    logger.info(f"Starting SCHEDULED task '{task_id}'.")
    while task_id in running_tasks:
        try:
            all_posts = defaultdict(list)
            sources = task_info.get('source', [])
            if not isinstance(sources, list): sources = [sources]
            for source_id in sources:
                try:
                    messages = await telethon_client.get_messages(source_id, limit=MESSAGE_FETCH_LIMIT)
                    for msg in reversed(messages):
                        key = msg.grouped_id or msg.id
                        if key: all_posts[key].append(msg)
                except Exception as e:
                    logger.error(f"Could not fetch from source {source_id} for task {task_id}: {e}")
            posted_data = load_data(POSTED_MESSAGES_FILE)
            posted_ids = set(map(int, posted_data.get(task_id, [])))
            unposted_ids = list(set(all_posts.keys()) - posted_ids)
            if not unposted_ids and all_posts:
                logger.info(f"Task '{task_id}': All posts sent. Resetting cycle.")
                posted_ids.clear()
                unposted_ids = list(all_posts.keys())
            if unposted_ids:
                post_id = random.choice(unposted_ids)
                await send_post(task_info['destination'], all_posts[post_id])
                posted_ids.add(post_id)
                posted_data[task_id] = list(posted_ids)
                save_data(POSTED_MESSAGES_FILE, posted_data)
        except Exception as e:
            logger.error(f"Error in SCHEDULED task '{task_id}': {e}", exc_info=True)
        await asyncio.sleep(int(task_info.get('gap_minutes', 60) * 60))

@telethon_client.on(events.NewMessage())
async def live_copy_handler(event):
    message = event.message
    tasks = load_data(TASKS_FILE)
    for task_id, info in tasks.items():
        sources = info.get('source', [])
        if not isinstance(sources, list): sources = [sources]
        if info.get('task_type') == 'live_copy' and message.chat_id in sources:
            if message.grouped_id:
                if running_tasks.get(f"album_{message.grouped_id}"): continue
                running_tasks[f"album_{message.grouped_id}"] = True
                await asyncio.sleep(2)
                album_messages = [msg async for msg in telethon_client.iter_messages(message.chat_id, limit=20) if msg and msg.grouped_id == message.grouped_id]
                await send_post(info['destination'], album_messages)
                del running_tasks[f"album_{message.grouped_id}"]
            else:
                await send_post(info['destination'], [message])

# ==============================================================================
# --- TELEGRAM BOT CONTROL INTERFACE ---
# ==============================================================================
admin_filter = filters.User(user_id=ADMIN_USER_ID)
(SELECT_TASK_TYPE, GET_SOURCE, GET_DEST, GET_GAP, EDIT_SELECT_TASK, EDIT_SELECT_FIELD, EDIT_GET_NEW_VALUE) = range(7)
cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_conv")]])

def parse_ids(text: str) -> list[int]:
    return [int(id_str.strip()) for id_str in text.split(',') if id_str.strip()]

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome!\n/addtask, /edittask, /tasks, /deletetask, /channels")

async def list_channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching your chats...")
    dialogs = await telethon_client.get_dialogs()
    dialog_list = [f"• **{d.name}**\n  `ID: {d.id}`" for d in dialogs]
    message = "Available Chats and IDs:\n\n" + "\n".join(dialog_list)
    for x in range(0, len(message), 4096): await update.message.reply_text(message[x:x+4096], parse_mode='Markdown')

async def add_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton("📅 Scheduled Post", callback_data="scheduled")], [InlineKeyboardButton("⚡ Live Copy", callback_data="live_copy")]]
    await update.message.reply_text("➕ **Add New Task**\n\nSelect task type:", reply_markup=InlineKeyboardMarkup(buttons))
    return SELECT_TASK_TYPE

async def select_task_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['task_type'] = query.data
    await query.edit_message_text(f"Selected: {query.data}.\nPlease send Source Chat ID(s), separated by commas.", reply_markup=cancel_markup)
    return GET_SOURCE

async def get_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['source'] = parse_ids(update.message.text)
    await update.message.reply_text("Got it. Now, send Destination Chat ID(s), separated by commas.", reply_markup=cancel_markup)
    return GET_DEST

async def get_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['destination'] = parse_ids(update.message.text)
    if context.user_data['task_type'] == 'scheduled':
        await update.message.reply_text("How many MINUTES between posts?", reply_markup=cancel_markup)
        return GET_GAP
    else:
        await finalize_task_creation(update.message, context.user_data)
        return ConversationHandler.END

async def get_gap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gap_minutes'] = float(update.message.text)
    await finalize_task_creation(update.message, context.user_data)
    return ConversationHandler.END

async def finalize_task_creation(message, user_data):
    tasks = load_data(TASKS_FILE)
    task_id = f"task_{int(time.time())}"
    tasks[task_id] = user_data
    save_data(TASKS_FILE, tasks)
    if user_data.get('task_type') == 'scheduled':
        running_tasks[task_id] = asyncio.create_task(scheduled_post_task(task_id, tasks[task_id]))
    await message.reply_text(f"✅ Task `{task_id}` created!", parse_mode='Markdown')

async def edit_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = load_data(TASKS_FILE)
    if not tasks: await update.message.reply_text("No tasks to edit."); return ConversationHandler.END
    buttons = [[InlineKeyboardButton(f"✏️ {task_id}", callback_data=task_id)] for task_id in tasks]
    await update.message.reply_text("✏️ **Edit Task**\n\nSelect a task to modify:", reply_markup=InlineKeyboardMarkup(buttons))
    return EDIT_SELECT_TASK

async def edit_select_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['edit_task_id'] = query.data
    task_info = load_data(TASKS_FILE).get(query.data, {})
    buttons = [
        [InlineKeyboardButton("🔄 Edit Sources", callback_data="edit_source")],
        [InlineKeyboardButton("🔄 Edit Destinations", callback_data="edit_destination")]
    ]
    if task_info.get('task_type') == 'scheduled':
        buttons.append([InlineKeyboardButton("⏰ Edit Gap (Minutes)", callback_data="edit_gap")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_conv")])
    await query.edit_message_text(f"Editing `{query.data}`. What to change?", reply_markup=InlineKeyboardMarkup(buttons), parse_mode='Markdown')
    return EDIT_SELECT_FIELD

async def edit_select_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['edit_field'] = query.data.replace('edit_', '')
    await query.edit_message_text(f"Please send the new value for **{context.user_data['edit_field']}**.", reply_markup=cancel_markup, parse_mode='Markdown')
    return EDIT_GET_NEW_VALUE

async def edit_get_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = load_data(TASKS_FILE)
    task_id = context.user_data['edit_task_id']
    field = context.user_data['edit_field']
    try:
        if field in ['source', 'destination']: new_value = parse_ids(update.message.text)
        else: new_value = float(update.message.text)
        tasks[task_id][field] = new_value
        save_data(TASKS_FILE, tasks)
        if task_id in running_tasks:
            running_tasks[task_id].cancel()
        if tasks[task_id].get('task_type') == 'scheduled':
            running_tasks[task_id] = asyncio.create_task(scheduled_post_task(task_id, tasks[task_id]))
            logger.info(f"Restarted task {task_id} with new settings.")
        await update.message.reply_text(f"✅ Task `{task_id}` updated!", parse_mode='Markdown')
    except (ValueError, KeyError):
        await update.message.reply_text("Invalid format. Please try again.", reply_markup=cancel_markup)
        return EDIT_GET_NEW_VALUE
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    message = query.message if query else update.message
    await message.reply_text("Operation cancelled.")
    if query: await query.edit_message_text("Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = load_data(TASKS_FILE)
    if not tasks: await update.message.reply_text("No active tasks."); return
    message = "📑 **Current Forwarding Tasks:**\n\n"
    for task_id, info in tasks.items():
        source_str = ', '.join(map(str, info.get('source', [])))
        dest_str = ', '.join(map(str, info.get('destination', [])))
        task_type_str = info.get('task_type', 'N/A').replace('_', ' ').title()
        message += f"**ID**: `{task_id}`\n  **Type**: {task_type_str}\n"
        message += f"  **Source(s)**: `{source_str}`\n  **Destination(s)**: `{dest_str}`\n"
        if info.get('task_type') == 'scheduled':
            message += f"  **Gap**: {info.get('gap_minutes', 'N/A')} minutes\n\n"
        else:
            message += "\n"
    await update.message.reply_text(message, parse_mode='Markdown')

async def delete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = load_data(TASKS_FILE)
    if not tasks: await update.message.reply_text("No tasks to delete."); return
    buttons = [[InlineKeyboardButton(f"🗑️ {task_id}", callback_data=f"delete_{task_id}")] for task_id in tasks]
    await update.message.reply_text("🗑️ **Delete Task**\n\nSelect a task to permanently delete:", reply_markup=InlineKeyboardMarkup(buttons))

async def delete_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = query.data.replace('delete_', '')
    tasks = load_data(TASKS_FILE)
    if task_id in tasks:
        del tasks[task_id]
        save_data(TASKS_FILE, tasks)
        if task_id in running_tasks:
            running_tasks[task_id].cancel()
            del running_tasks[task_id]
        await query.edit_message_text(f"✅ Task `{task_id}` has been deleted.", parse_mode='Markdown')
    else:
        await query.edit_message_text(f"Task '{task_id}' not found.")

async def main():
    if not all([API_ID, API_HASH, BOT_TOKEN, ADMIN_USER_ID]):
        logger.error("FATAL: One or more environment variables are missing. Please check your .env file.")
        return
        
    await telethon_client.start()
    logger.info("Telethon client started successfully.")
    tasks = load_data(TASKS_FILE)
    for task_id, info in tasks.items():
        if info.get('task_type') == 'scheduled':
            running_tasks[task_id] = asyncio.create_task(scheduled_post_task(task_id, info))
            
    application = Application.builder().token(BOT_TOKEN).build()
    cancel_handler = CallbackQueryHandler(cancel_conversation, pattern='^cancel_conv$')
    add_task_handler = ConversationHandler(
        entry_points=[CommandHandler('addtask', add_task_start, filters=admin_filter)],
        states={
            SELECT_TASK_TYPE: [CallbackQueryHandler(select_task_type)],
            GET_SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_source)],
            GET_DEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_destination)],
            GET_GAP: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gap)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation), cancel_handler], per_message=False
    )
    edit_task_handler = ConversationHandler(
        entry_points=[CommandHandler('edittask', edit_task_start, filters=admin_filter)],
        states={
            EDIT_SELECT_TASK: [CallbackQueryHandler(edit_select_task)],
            EDIT_SELECT_FIELD: [CallbackQueryHandler(edit_select_field)],
            EDIT_GET_NEW_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_get_new_value)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation), cancel_handler], per_message=False
    )
    application.add_handler(CommandHandler('start', start_command, filters=admin_filter))
    application.add_handler(CommandHandler('channels', list_channels_command, filters=admin_filter))
    application.add_handler(CommandHandler('tasks', list_tasks_command, filters=admin_filter))
    application.add_handler(CommandHandler('deletetask', delete_task_command, filters=admin_filter))
    application.add_handler(CallbackQueryHandler(delete_task_callback, pattern='^delete_'))
    application.add_handler(add_task_handler)
    application.add_handler(edit_task_handler)
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        logger.info("Control bot started and is now polling for commands.")
        await telethon_client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped manually.")