import asyncio
import json
import logging
import random
import re
import time
from datetime import datetime, timedelta

import requests
from telethon.sync import TelegramClient
from telethon.tl.types import Dialog
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

# ==============================================================================
# --- CONFIGURE YOUR BOT HERE ---
# ==============================================================================
API_ID = 1234567                   # Replace with your API ID from my.telegram.org
API_HASH = "YOUR_API_HASH"         # Replace with your API Hash
BOT_TOKEN = "YOUR_BOT_TOKEN"       # Replace with your Bot Token from BotFather
ADMIN_USER_ID = 987654321          # Replace with your numerical Telegram User ID
# ==============================================================================

# --- Global File Paths ---
SESSION_FILE = 'telegram_user.session'
TASKS_FILE = 'tasks.json'
POSTED_MESSAGES_FILE = 'posted_messages.json'

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Global Client and Task Variables ---
telethon_client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
running_tasks = {}  # Dictionary to hold the running asyncio task objects

# --- Data Persistence Functions ---
def load_data(filename):
    """Loads JSON data from a file."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_data(filename, data):
    """Saves Python dictionary to a JSON file."""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

# --- Link Processing Logic ---
def shorten_url(url):
    """Converts a given URL to a TinyURL."""
    try:
        api_url = f'http://tinyurl.com/api-create.php?url={url}'
        response = requests.get(api_url)
        return response.text if response.status_code == 200 else url
    except Exception:
        return url

def process_links_in_text(text):
    """Finds all Terabox links in text and replaces them with TinyURLs."""
    if not text:
        return text
    # Regex to find all URLs
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
    for url in urls:
        if 'terabox' in url.lower():
            text = text.replace(url, shorten_url(url))
    return text

# --- Core Forwarding Logic (Telethon) ---
async def forwarder_task(task_id, task_info):
    """The main asynchronous function that runs for each forwarding task."""
    logger.info(f"Starting forwarder task '{task_id}'.")
    while task_id in running_tasks:
        try:
            posted_data = load_data(POSTED_MESSAGES_FILE)
            task_posts = posted_data.get(task_id, {})
            
            # Identify message IDs that have been posted in the last 30 days
            thirty_days_ago = datetime.now() - timedelta(days=30)
            recently_posted_ids = {
                int(k) for k, v in task_posts.items() 
                if datetime.fromisoformat(v) > thirty_days_ago
            }
            
            # Fetch a list of recent messages from the source channel
            all_messages = await telethon_client.get_messages(task_info['source'], limit=3000)
            
            # Filter out messages that were posted recently
            unposted_messages = [
                msg for msg in all_messages if msg and msg.id not in recently_posted_ids
            ]

            if not unposted_messages:
                logger.warning(f"Task '{task_id}': No new (unposted in last 30 days) messages found. Will try again later.")
            else:
                # Select a random message from the valid list
                message_to_post = random.choice(unposted_messages)
                
                # Process text for Terabox links
                processed_text = process_links_in_text(message_to_post.text)
                
                # Send a new message to the destination (avoids "forwarded from" tag)
                await telethon_client.send_message(
                    task_info['destination'],
                    message=processed_text,
                    file=message_to_post.media,
                    buttons=message_to_post.buttons
                )
                logger.info(f"Task '{task_id}': Posted message {message_to_post.id} to destination {task_info['destination']}.")
                
                # Log this message as posted
                task_posts[str(message_to_post.id)] = datetime.now().isoformat()
                posted_data[task_id] = task_posts
                save_data(POSTED_MESSAGES_FILE, posted_data)

        except Exception as e:
            logger.error(f"Error in task '{task_id}': {e}", exc_info=True)
        
        # Wait for the specified interval before the next post
        sleep_duration = int(task_info['gap_hours'] * 3600)
        await asyncio.sleep(sleep_duration)

# --- Control Bot Command Handlers (python-telegram-bot) ---
admin_filter = filters.User(user_id=ADMIN_USER_ID)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /start command."""
    await update.message.reply_text(
        "Welcome! I am your personal forwarding bot.\n"
        "Use the following commands to manage your tasks:\n\n"
        "/addtask - Create a new forwarding task.\n"
        "/tasks - View all active tasks.\n"
        "/deletetask - Remove a task.\n"
        "/channels - List all channels I can access."
    )

async def list_channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all channels the user account is a member of."""
    await update.message.reply_text("Fetching your channels, this may take a moment...")
    dialogs = await telethon_client.get_dialogs()
    channel_list = [f"• **{d.name}**\n  `ID: {d.id}`" for d in dialogs if d.is_channel]
    
    if not channel_list:
        await update.message.reply_text("I couldn't find any channels in your account.")
        return

    message = "Here are your available channels and their IDs:\n\n" + "\n".join(channel_list)
    # Split the message into chunks if it's too long for a single Telegram message
    for x in range(0, len(message), 4096):
        await update.message.reply_text(message[x:x+4096], parse_mode='Markdown')

# --- Add Task Conversation States ---
GET_SOURCE, GET_DEST, GET_GAP = range(3)

async def add_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the conversation to add a new task."""
    await update.message.reply_text("Let's add a new task.\n\nFirst, send me the Source Channel ID.\nYou can get this from the /channels command.")
    return GET_SOURCE

async def get_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles receiving the source channel ID."""
    try:
        context.user_data['source'] = int(update.message.text)
        await update.message.reply_text("Got it. Now, send me the Destination Channel ID.")
        return GET_DEST
    except ValueError:
        await update.message.reply_text("Invalid ID. Please send a valid numerical ID.")
        return GET_SOURCE

async def get_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles receiving the destination channel ID."""
    try:
        context.user_data['destination'] = int(update.message.text)
        await update.message.reply_text("Perfect. Finally, how many hours should I wait between posts? (e.g., 1, 6, 24)")
        return GET_GAP
    except ValueError:
        await update.message.reply_text("Invalid ID. Please send a valid numerical ID.")
        return GET_DEST

async def get_gap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles receiving the posting interval and finalizes the task."""
    try:
        gap_hours = float(update.message.text)
        if gap_hours <= 0:
            await update.message.reply_text("Please enter a positive number for the hours.")
            return GET_GAP
            
        tasks = load_data(TASKS_FILE)
        task_id = f"task_{int(time.time())}"
        tasks[task_id] = {
            "source": context.user_data['source'],
            "destination": context.user_data['destination'],
            "gap_hours": gap_hours
        }
        save_data(TASKS_FILE, tasks)
        
        # Start the new task in the background
        task = asyncio.create_task(forwarder_task(task_id, tasks[task_id]))
        running_tasks[task_id] = task
        
        await update.message.reply_text(f"✅ Task '{task_id}' has been created and started successfully!")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Invalid number. Please enter a number for the hours (e.g., 1.5).")
        return GET_GAP

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the add task conversation."""
    await update.message.reply_text("Task creation cancelled.")
    return ConversationHandler.END

# --- View and Delete Task Handlers ---
async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays all currently configured tasks."""
    tasks = load_data(TASKS_FILE)
    if not tasks:
        await update.message.reply_text("There are no active tasks.")
        return
    
    message = "Current forwarding tasks:\n\n"
    for task_id, info in tasks.items():
        message += (f"**ID**: `{task_id}`\n"
                    f"  **Source**: `{info['source']}`\n"
                    f"  **Destination**: `{info['destination']}`\n"
                    f"  **Gap**: {info['gap_hours']} hours\n\n")
    await update.message.reply_text(message, parse_mode='Markdown')

async def delete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows a button menu of tasks to delete."""
    tasks = load_data(TASKS_FILE)
    if not tasks:
        await update.message.reply_text("There are no tasks to delete.")
        return
    
    buttons = [[InlineKeyboardButton(f"❌ {task_id}", callback_data=f"delete_{task_id}")] for task_id in tasks]
    await update.message.reply_text("Select a task to delete:", reply_markup=InlineKeyboardMarkup(buttons))

async def delete_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the callback from the delete task button menu."""
    query = update.callback_query
    await query.answer()
    task_id = query.data.split('_')

    tasks = load_data(TASKS_FILE)
    if task_id in tasks:
        # Remove task from saved data
        del tasks[task_id]
        save_data(TASKS_FILE, tasks)
        
        # Stop the running asyncio task
        if task_id in running_tasks:
            running_tasks[task_id].cancel()
            del running_tasks[task_id]
        
        await query.edit_message_text(f"🗑️ Task '{task_id}' has been deleted.")
    else:
        await query.edit_message_text(f"Task '{task_id}' not found (might have already been deleted).")

# --- Main Application Logic ---
async def main():
    """The main function that connects clients and starts the bot."""
    # Connect the Telethon client (user account)
    await telethon_client.start()
    logger.info("Telethon client started successfully.")
    
    # Load saved tasks and start them
    tasks = load_data(TASKS_FILE)
    for task_id, info in tasks.items():
        task = asyncio.create_task(forwarder_task(task_id, info))
        running_tasks[task_id] = task
        
    # Set up the control bot application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handler for adding a new task
    add_task_handler = ConversationHandler(
        entry_points=[CommandHandler('addtask', add_task_start, filters=admin_filter)],
        states={
            GET_SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_source)],
            GET_DEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_destination)],
            GET_GAP: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gap)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )

    # Register all command and callback handlers
    application.add_handler(CommandHandler('start', start_command, filters=admin_filter))
    application.add_handler(CommandHandler('channels', list_channels_command, filters=admin_filter))
    application.add_handler(CommandHandler('tasks', list_tasks_command, filters=admin_filter))
    application.add_handler(CommandHandler('deletetask', delete_task_command, filters=admin_filter))
    application.add_handler(CallbackQueryHandler(delete_task_callback, pattern='^delete_'))
    application.add_handler(add_task_handler)
    
    # Run the bot and client concurrently
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        logger.info("Control bot started and is now polling for commands.")
        
        # Keep the script alive until it's manually stopped
        await telethon_client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped manually.")
