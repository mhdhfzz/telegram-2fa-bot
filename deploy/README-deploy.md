# Panduan Deployment VPS: Telegram 2FA Authenticator Bot & Mini App

Dokumen ini menjelaskan langkah-langkah men-deploy Bot Telegram 2FA Authenticator dan Telegram Mini App (Web App) ke Virtual Private Server (VPS) berbasis Linux (Ubuntu / Debian).

---

## 1. Persiapan Server & Dependensi Sistem

Perbarui paket sistem dan pasang dependensi yang diperlukan:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv libzbar0 git nginx certbot python3-certbot-nginx
```

> **Penting**: Paket `libzbar0` wajib dipasang agar fitur decode QR code dari foto via `pyzbar` dapat berjalan optimal di Linux VPS.
> 
> 🛡️ **Privasi & Keamanan Data (Zero Telegram Storage)**: Seluruh database pengguna (`2fa_bot.db`) tersimpan secara lokal pada server VPS Anda. Bot sama sekali tidak menyimpan data akun ke server atau cloud Telegram. Semua secret akun dienkripsi menggunakan AES-256-GCM dengan kunci yang diturunkan dari PIN masing-masing pengguna (Zero Master Key).

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

Contoh konfigurasi `.env`:
```ini
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
DB_PATH=/opt/telegram-2fa-bot/2fa_bot.db
LOG_LEVEL=INFO
PIN_LENGTH=6
AUTO_DELETE_SECONDS=90

# Konfigurasi Telegram Mini App
MINI_APP_ENABLED=true
MINI_APP_HOST=127.0.0.1
MINI_APP_PORT=8080
MINI_APP_URL=https://mfa.domainanda.com
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

## 6. Konfigurasi HTTPS Nginx Reverse Proxy (Untuk Mini App)

Telegram Mini App mewajibkan koneksi HTTPS dengan SSL valid.

1. Buat file konfigurasi Nginx:
   ```bash
   sudo nano /etc/nginx/sites-available/mfa-bot
   ```

2. Masukkan konfigurasi reverse proxy:
   ```nginx
   server {
       server_name mfa.domainanda.com;

       location / {
           proxy_pass http://127.0.0.1:8080;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_cache_bypass $http_upgrade;
       }
   }
   ```

3. Aktifkan konfigurasi dan pasang sertifikat SSL gratis:
   ```bash
   sudo ln -s /etc/nginx/sites-available/mfa-bot /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   sudo certbot --nginx -d mfa.domainanda.com
   ```

*(Alternatif tanpa domain/Nginx: Anda dapat menggunakan Cloudflare Tunnel gratis `cloudflared tunnel --url http://localhost:8080`)*

---

## 7. Konfigurasi Menu Button di @BotFather

1. Buka [@BotFather](https://t.me/BotFather) di Telegram.
2. Kirim `/setmenubutton` -> Pilih bot Anda.
3. Masukkan URL: `https://mfa.domainanda.com`
4. Masukkan nama tombol: `📱 Buka MFA`

Panduan lengkap mengenai pendaftaran BotFather tersedia di [docs/BOTFATHER_MINI_APP_GUIDE.md](docs/BOTFATHER_MINI_APP_GUIDE.md).

---

## 8. Backup Rutin Database

Tambahkan cron job untuk mencadangkan database SQLite setiap hari:

```bash
sudo crontab -e
```

Contoh jadwal backup harian pukul 02:00:
```cron
0 2 * * * cp /opt/telegram-2fa-bot/2fa_bot.db /backup/2fa_bot_$(date +\%Y\%m\%d).db
```

---

## 9. Firewall (UFW)

Atur firewall VPS dengan aman:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Port internal bot `8080` tetap tertutup dari publik karena hanya diakses oleh Nginx secara lokal (`127.0.0.1`).
