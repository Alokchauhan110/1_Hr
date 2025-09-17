# Telegram Auto-Forwarder & Management Bot

This project is a sophisticated Telegram bot designed to automate content forwarding between channels. It is controlled entirely through a separate Telegram bot, allowing for dynamic management of forwarding tasks without ever needing to access the server directly after initial setup.

The system uses a powerful combination of a **user bot** (via Telethon) to read from any channel and a **control bot** (via `python-telegram-bot`) to receive your commands.

---

## Features

-   **Full Control via Telegram**: Add, view, and delete forwarding tasks using simple bot commands.
-   **Secure**: Only the specified Admin User ID can access the bot's commands.
-   **Multiple Simultaneous Tasks**: Run an unlimited number of forwarding jobs from different sources to different destinations.
-   **Custom Posting Intervals**: Set a unique posting schedule (e.g., every 1 hour, every 24 hours) for each task.
-   **Smart Posting Logic**: The bot keeps track of posted messages and will not repeat a post within a 30-day window, ensuring fresh content.
-   **Selective Link Conversion**: Automatically finds and converts any `teraboxapp.com` or `terabox.com` links into `tinyurl.com` links to prevent download issues, while leaving all other links unchanged.
-   **Preserves Post Integrity**: Forwards messages with their original media, buttons, and formatting, but without the "forwarded from" tag.
-   **Persistent Storage**: Tasks are saved to a `tasks.json` file, so they automatically resume even if the server is rebooted.
-   **Channel Discovery**: Includes a `/channels` command to list all channels your user account is a part of, making it easy to find the correct IDs for setup.

---

## Prerequisites

Before you begin, you will need the following:

1.  **A VPS (Virtual Private Server)**: A small, cheap server is sufficient. **Ubuntu 22.04 LTS** is recommended.
2.  **Telegram API Credentials**:
    -   **API ID** and **API Hash**: Get these from [my.telegram.org](https://my.telegram.org).
3.  **Telegram Bot Token**:
    -   **Bot Token**: Create a bot by talking to `@BotFather` on Telegram and save the token he gives you.
4.  **Your Telegram User ID**:
    -   **Admin User ID**: Talk to `@userinfobot` on Telegram to get your numerical user ID.

---

## Deployment Guide (Using `nano`)

Follow these steps on your fresh Ubuntu 22.04 VPS.

### 1. Connect to Your Server
Connect to your server's terminal via SSH.
```bash
ssh root@your_vps_ip
```

### 2. Prepare the Server Environment
Run these commands one by one to install the necessary software.
```bash
# Update system packages
apt update && apt upgrade -y

# Install Python, Pip, and the virtual environment tool
apt install python3 python3-pip python3-venv -y

# Create a directory for our files (recommended)
mkdir /home/bot-project
cd /home/bot-project

# Create a Python virtual environment
python3 -m venv bot_env

# Activate the virtual environment
source bot_env/bin/activate

# Install required Python libraries
pip install telethon python-telegram-bot requests --upgrade```

### 3. Create the Bot Script
We will use the `nano` text editor to create our Python file.

```bash
# Open a new blank file called master_bot.py
nano master_bot.py```
Copy the entire code from the `master_bot.py` file and paste it into the `nano` editor.

**Crucially, edit the configuration variables at the top of the file with your own credentials.**

```python
# --- CONFIGURE YOUR BOT HERE ---
API_ID = 1234567                   # Replace with your API ID
API_HASH = "YOUR_API_HASH"         # Replace with your API Hash
BOT_TOKEN = "YOUR_BOT_TOKEN"       # Replace with your Bot Token
ADMIN_USER_ID = 987654321          # Replace with your numerical User ID
# -----------------------------
```
Save the file and exit `nano` by pressing `Ctrl + X`, then `Y`, then `Enter`.

### 4. First-Time Login
You must run the bot once manually to log in to your Telegram account.

```bash
# Run the script from inside the activated environment
python3 master_bot.py
```
The script will prompt you for your phone number, the login code Telegram sends you, and your 2FA password (if you have one). After you see the "Control bot started" message, you can stop the script by pressing `Ctrl + C`. A `telegram_user.session` file will be created, saving your login.

### 5. Set Up the 24/7 Service (`systemd`)
This will ensure your bot runs forever and restarts automatically.

First, deactivate the virtual environment.
```bash
deactivate
```
Now, create a service file with `nano`.
```bash
nano /etc/systemd/system/telegram-bot.service
```
Paste the following configuration into the `nano` editor. This configuration points to the project directory we created.

```ini
[Unit]
Description=Telegram Master Bot
After=network.target

[Service]
User=root
WorkingDirectory=/home/bot-project
ExecStart=/home/bot-project/bot_env/bin/python3 /home/bot-project/master_bot.py
Restart=always
RestartSec=10
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
```
Save and exit (`Ctrl + X`, `Y`, `Enter`).

Finally, enable and start the service by running these three commands one by one.
```bash
systemctl daemon-reload
systemctl enable telegram-bot.service
systemctl start telegram-bot.service
```

### 6. Verify the Bot is Running
Check the status of your new service.
```bash
systemctl status telegram-bot.service
```
If you see a green `active (running)` message, your bot is successfully deployed!

---

## How to Use the Bot

Talk to your bot on Telegram. Only you (the Admin) can use these commands.

-   `/start` - Shows a welcome message.
-   `/channels` - Lists all channels your user account has joined, with their IDs.
-   `/addtask` - Starts a guided conversation to add a new forwarding task.
-   `/tasks` - Displays all currently active tasks.
-   `/deletetask` - Shows a menu of tasks to delete.

---

## How to Update the Code

If you need to deploy a new version of the `master_bot.py` script:

1.  **Stop the service:**
    ```bash
    systemctl stop telegram-bot.service
    ```
2.  **Update the file:** You can either use `nano /home/bot-project/master_bot.py` to paste the new code, or use `scp` to transfer the file from your computer.
3.  **Start the service again:**
    ```bash
    systemctl start telegram-bot.service
    ```
4.  **Check the logs for any errors:**
    ```bash
    journalctl -u telegram-bot.service -f -n 50
    ```