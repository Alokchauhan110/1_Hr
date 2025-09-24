# Telegram Auto-Forwarder & Management Bot (Professional Edition)

This is the definitive, stable version of the Telegram automation bot, featuring a professional deployment workflow using **Git** and a secure **`.env` file** for configuration.

This version resolves all known bugs related to task management and provides a stable foundation for both **Scheduled Random Posting** and **Live Copy (Mirroring)**.

---

## Core Features

-   **Professional Workflow**:
    -   **`.env` File Support**: Securely manage your API keys and tokens in an environment file. No more editing the Python script.
    -   **Git-Based Deployment**: After initial setup, update your bot simply by running `git push` from your local computer.
-   **Stable Task Management**:
    -   All commands, including `/tasks` and `/deletetask`, are now fully functional and stable.
    -   Core "Scheduled Post" and "Live Copy" features have been fixed and tested.
-   **Redesigned UI**:
    -   Emoji-driven menus (📅, ⚡, ✏️, 🗑️, ❌) for a clean, intuitive user experience.
-   **Dual Task Modes**:
    1.  **Scheduled Random Post**: Posts unique, random content from source channels on a schedule set in **minutes**.
    2.  **Live Copy (Mirror)**: Instantly mirrors new messages from any source to any destination.
-   **Universal Features**: Multi-channel support, album handling, and `terabox` link conversion are all included.

---

## **Part 1: Initial Setup on Your VPS**

Follow these steps **one time only** to set up the new project structure.

### 1. Clean Up the Old Project
Connect to your VPS and run these commands to remove the old bot and its files.```bash
# Stop and disable the old service
sudo systemctl stop telegram-bot.service
sudo systemctl disable telegram-bot.service

# Remove the old service file
sudo rm /etc/systemd/system/telegram-bot.service

# Go to your home directory and delete the old project
cd ~
rm -rf /home/bot-project # Or the name of your old project folder
```

### 2. Install Git and Prepare the Environment
```bash
# Install Git
sudo apt update && sudo apt install git -y

# Create a new, clean project directory
mkdir telegram-bot
cd telegram-bot

# Install Python tools (if not already installed)
sudo apt install python3-pip python3-venv -y

# Create and activate a Python virtual environment
python3 -m venv bot_env
source bot_env/bin/activate

# Install required Python libraries
pip install telethon python-telegram-bot requests python-dotenv
```

### 3. Create the Project Files
You will now create three essential files.

#### A. The `.env` File (Your Secrets)
This file will hold your credentials.
```bash
# Open a new file named .env with nano
nano .env
```
Copy the following block, paste it into `nano`, and **replace the placeholders with your new, secure credentials.**
```env
# Telegram API Credentials
API_ID=12345678
API_HASH="YOUR_NEW_API_HASH"

# Telegram Bot Token
BOT_TOKEN="YOUR_NEW_BOT_TOKEN"

# Your User ID for Admin Access
ADMIN_USER_ID=5277583773
```
Save and exit (`Ctrl+X`, `Y`, `Enter`).

#### B. The Python Script (`master_bot.py`)
```bash
# Open a new file for the bot code
nano master_bot.py
```
Copy the **entire** `master_bot.py` code from the final code block below and paste it into `nano`. **You do not need to edit this file.** Save and exit.

#### C. The Deployment Script (`deploy.sh`)
This script will automate updates.
```bash
# Open a new file for the deployment script
nano deploy.sh
```
Copy and paste the following script into `nano`.
```bash
#!/bin/bash
# A simple script to pull the latest code and restart the bot.

# Pull the latest changes from the main branch
git pull origin main

# Install any new dependencies
source bot_env/bin/activate
pip install -r requirements.txt
deactivate

# Restart the bot service
sudo systemctl restart telegram-bot.service

echo "✅ Deployment successful!"
```
Save and exit. Now, make this script executable:
```bash
chmod +x deploy.sh
```

### 4. Set Up the 24/7 Service (`systemd`)
```bash
# Create the service file
sudo nano /etc/systemd/system/telegram-bot.service
```
Paste the following configuration. **Make sure the paths match your new project folder (`/home/YOUR_USERNAME/telegram-bot`).**
```ini
[Unit]
Description=Telegram Master Bot
After=network.target

[Service]
# Replace 'root' with your username if you are not using the root user
User=root
WorkingDirectory=/root/telegram-bot
ExecStart=/root/telegram-bot/bot_env/bin/python3 /root/telegram-bot/master_bot.py
Restart=always
RestartSec=10
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
```
Save and exit.

### 5. First-Time Login and Start
```bash
# Run the bot once MANUALLY to log in
source bot_env/bin/activate
python3 master_bot.py
```
Log in with your phone, code, and 2FA password. Once it says "Control bot started", stop it with `Ctrl+C`.

Now, enable and start the service to run it 24/7.
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot.service
sudo systemctl start telegram-bot.service

# Verify it is running
sudo systemctl status telegram-bot.service
```

---

## **Part 2: Setting Up Git (The `git push` Workflow)**

This part connects your VPS to a Git repository (like GitHub).

### 1. On Your Local Computer
1.  Create a new folder for your project.
2.  Inside that folder, create the `master_bot.py` and `.env` files with the same content as on the server.
3.  **Create a new, empty, private repository on [GitHub](https://github.com).**
4.  Follow GitHub's instructions to "push an existing repository from the command line". It will look like this:
    ```bash
    git init
    git add .
    git commit -m "First commit"
    git branch -M main
    git remote add origin https://github.com/YourUsername/YourRepoName.git
    git push -u origin main
    ```

### 2. On Your VPS
Now, link your VPS's project folder to the repository you just created.
```bash
# Go to your project directory
cd ~/telegram-bot

# Initialize Git and link it to your GitHub repo
git init
git remote add origin https://github.com/YourUsername/YourRepoName.git
git fetch origin
git reset --hard origin/main # This syncs your VPS with the code on GitHub
```

## **Part 3: The New Update Workflow (Easy Updates)**

From now on, updating your bot is incredibly simple.

1.  **On your Local Computer**: Make changes to your `master_bot.py` file.
2.  **On your Local Computer**: Open a terminal in your project folder and run:
    ```bash
    git add master_bot.py
    git commit -m "Describe your update here"
    git push origin main
    ```
3.  **On your VPS**: Connect via SSH, go to your project folder, and run the deployment script:
    ```bash
    cd ~/telegram-bot
    ./deploy.sh
    ```

Your bot is now updated and restarted automatically. **No more copy-pasting code!**