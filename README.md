# Telegram Bot Hosting Web Panel

A complete self-hosted web application for running Telegram bots in the cloud. Users can upload bot files, start/stop bots, view real-time console logs, and manage resources. Includes admin panel, multi-bot support, plan limits, and Android WebView app.

## Features

### Core
- User authentication (signup/login/logout)
- Upload `requirements.txt` and `bot.py`
- Start/Stop/Restart bot
- Live console output with timestamps
- Resource monitoring (CPU/RAM)
- 24-hour auto-stop and restart limits
- Session isolation per user

### Advanced
- Multi-bot support (per plan)
- Plan system: FREE, PRO, ULTRA
- Admin panel: manage users, bots, force stop
- Account management: change password, delete account
- Command panel: send stdin to running bot
- Download logs as .txt
- Android WebView app

### Security
- Password hashing (werkzeug)
- Session-based auth
- File upload validation (only .txt/.py, max 1MB)
- Rate limiting on start/stop
- Input sanitization
- SQLite with prepared statements

## Local Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/telegram-bot-web.git
cd telegram-bot-web/backend