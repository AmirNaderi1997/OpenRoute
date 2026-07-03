# OpenRoute 🌍


<p align="center">
  <b>Your Path to the Open Internet.</b><br>
  A comprehensive, automated VPN provisioning platform featuring a Telegram Bot, Web App, Crypto & Fiat payments, and intelligent routing.
</p>

<p align="center">
  <a href="README_FA.md">🇮🇷 برای مطالعه توضیحات به زبان فارسی اینجا کلیک کنید 🇮🇷</a>
</p>

---

## 🚀 Features

- **Multi-Protocol Support:** Fully automated provisioning for Direct SSH and V2Ray (VLESS Reality / PasarGuard) protocols.
- **Telegram Bot Integration:** A feature-rich Telegram Bot built with `aiogram` for seamless user interaction, plan purchasing, and subscription management.
- **Integrated Mini App:** A modern Telegram WebApp for a sleek UI/UX, allowing users to manage their services without leaving Telegram.
- **Automated Payment Pipeline:**
  - **Crypto Payments:** Fully automated crypto checkouts using the **NOWPayments API**.
  - **Fiat (Card-to-Card):** Built-in workflow for manual receipt verification via an exclusive Admin Management Group.
- **Advanced Admin Dashboard:** Real-time metrics, user management, and instant payment approval workflows.
- **Smart Routing & Censorship Bypass:** Designed specifically for high-censorship environments to ensure a stable and secure connection.
- **Dockerized Infrastructure:** Ready-to-deploy containers for PostgreSQL, Redis, FastAPI, and the SSH Daemon.

## 🏗 Architecture

The project is divided into several robust components:

- **FastAPI Backend (`/app/api/`)**: Handles WebApp routing, NOWPayments webhooks, and REST APIs.
- **Telegram Bot (`/app/bot/`)**: Handles all Telegram commands, inline keyboards, and the receipt-approval workflow.
- **Services (`/app/services/`)**: The core business logic including SSH user management, V2Ray panel communication, and the payment pipeline.
- **Database (`/app/db/`)**: Asynchronous PostgreSQL with SQLAlchemy ORM.
- **Landing Page (`/var/www/openroute_website/`)**: The static HTML/CSS front-end for `openroute.ir` with integrated Crypto and Fiat payment forms.

## ⚙️ Prerequisites

To run OpenRoute, you will need:
- Docker and Docker Compose
- A Telegram Bot Token from [@BotFather](https://t.me/botfather)
- A PostgreSQL & Redis instance (handled via Docker Compose)
- (Optional) A [NOWPayments](https://nowpayments.io/) API Key for crypto payments

## 🛠 Installation & Deployment

1. **Clone the repository:**
   ```bash
   git clone https://github.com/AmirNaderi1997/OpenRoute.git
   cd OpenRoute/home/openroute/selling_vpn_bot
   ```

2. **Configure the Environment:**
   Open the `.env` file and replace the placeholder values with your actual secrets (Bot Token, DB Passwords, API Keys, etc.).
   ```env
   BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE
   POSTGRES_PASSWORD=YOUR_DB_PASSWORD
   NOWPAYMENTS_API_KEY=YOUR_NOWPAYMENTS_API_KEY
   # ... update all other YOUR_ placeholders
   ```

3. **Deploy with Docker Compose:**
   ```bash
   docker compose up -d --build
   ```

4. **Initialize the Bot:**
   - Open your bot in Telegram (e.g., `@getopenroutebot`).
   - Send `/start`.
   - To access the admin panel, send `/admin_login` and provide your configured `SUPERADMIN_PASSWORD`.
   - Run `/setup_topics` inside your designated Admin Management Group to map the bot's notification channels.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/AmirNaderi1997/OpenRoute/issues).

## 📄 License

This project is licensed under the MIT License.
