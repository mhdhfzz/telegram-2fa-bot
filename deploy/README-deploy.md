# Panduan Deployment VPS: Telegram 2FA Authenticator Bot

Dokumen ini menjelaskan langkah-langkah men-deploy Bot Telegram 2FA Authenticator ke Virtual Private Server (VPS) berbasis Linux (Ubuntu / Debian).

---

## 1. Persiapan Server & Dependensi Sistem

Perbarui paket sistem dan pasang dependensi yang diperlukan:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv libzbar0 git
```

> **Penting**: Paket `libzbar0` wajib dipasang agar fitur decode QR code dari foto via `pyzbar` dapat berjalan optimal di Linux VPS.

---

## 2. Membuat User Non-Root

Demi keamanan, jalankan bot dengan user sistem khusus:

```bash
sudo useradd -r -s /bin/false -d /opt/telegram-2fa-bot bot2fa
```

---

## 3. Clone Repository & Setup Virtual Environment

```bash
sudo mkdir -p /opt/telegram-2fa-bot
sudo chown -R $USER:$USER /opt/telegram-2fa-bot
git clone https://github.com/mhdhfzz/telegram-2fa-bot.git /opt/telegram-2fa-bot
cd /opt/telegram-2fa-bot

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Konfigurasi Environment Variables

Salin file template `.env.example` ke `.env`:

```bash
cp .env.example .env
nano .env
```

Isi dengan token bot Telegram Anda:
```ini
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
DB_PATH=/opt/telegram-2fa-bot/2fa_bot.db
LOG_LEVEL=INFO
PIN_LENGTH=6
```

Atur permission ketat:
```bash
chmod 600 .env
sudo chown -R bot2fa:bot2fa /opt/telegram-2fa-bot
```

---

## 5. Menjalankan via systemd Service

```bash
sudo cp deploy/telegram-2fa-bot.service /etc/systemd/system/telegram-2fa-bot.service
sudo systemctl daemon-reload
sudo systemctl enable telegram-2fa-bot
sudo systemctl start telegram-2fa-bot
```

### Memeriksa Status & Log Bot:

```bash
sudo systemctl status telegram-2fa-bot
sudo journalctl -u telegram-2fa-bot -f
```

---

## 6. Backup Rutin Database

Tambahkan cron job untuk mencadangkan database SQLite setiap hari:

```bash
sudo crontab -e
```

Contoh jadwal backup harian pukul 02:00:
```cron
0 2 * * * cp /opt/telegram-2fa-bot/2fa_bot.db /backup/2fa_bot_$(date +\%Y\%m\%d).db
```

---

## 7. Firewall

Karena bot menggunakan **Long Polling**, server tidak membutuhkan port inbound terbuka:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw enable
```
