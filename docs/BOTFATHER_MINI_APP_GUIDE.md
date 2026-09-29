# 📱 Panduan Konfigurasi Telegram Mini App & BotFather

Panduan ini menjelaskan cara mengaktifkan, mengekspos, dan mengonfigurasi **Telegram Mini App (Web App)** untuk bot 2FA Anda di **@BotFather**, lengkap dengan integrasi logo resmi **Simple Icons (simpleicons.org)**.

---

## 🌟 Fitur Utama Mini App

1. **Dashboard Interaktif 2FA**: Tampilan visual modern layaknya Google Authenticator / Authy langsung di dalam aplikasi Telegram (Mobile & Desktop).
2. **Logo Resmi Simple Icons**: Menggunakan SVG vector ringan dari [Simple Icons](https://simpleicons.org) untuk 200+ platform populer (Google, GitHub, Discord, Steam, AWS, Tokopedia, Binance, dll.) dengan fallback emoji cerdas.
3. **Countdown Ticker Real-Time**: Timer lingkaran beranimasi per detik yang berubah warna saat kode hampir kedaluwarsa (< 5 detik).
4. **1-Tap Quick Copy**: Salin kode OTP instan ke clipboard dengan getaran Haptic Feedback Telegram.
5. **Kamera QR Telegram**: Scan QR Code langsung menggunakan kamera bawaan Telegram (`showScanQrPopup`).
6. **Keamanan Berlapis**: Terenkripsi dengan Master PIN Anda menggunakan **AES-256-GCM** dan derivasi **Argon2id**.

---

## 📋 Langkah 1: Persiapan HTTPS (Persyaratan Wajib Telegram)

Telegram mewajibkan semua Web App / Mini App menggunakan protokol **HTTPS** dengan sertifikat SSL valid.

Pilih salah satu metode berikut sesuai preferensi infrastruktur Anda:

### Pilihan A: Menggunakan Cloudflare Tunnel (Gratis, Paling Praktis & Aman)
Tidak perlu buka port firewall, tidak perlu beli IP publik:

1. Unduh dan install `cloudflared` di VPS atau komputer lokal:
   ```bash
   # Di Ubuntu/Debian:
   curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared.deb
   ```
2. Jalankan quick tunnel langsung ke port Mini App (default `8080`):
   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```
3. Salin URL HTTPS yang muncul di terminal, contoh:
   `https://random-subdomain.trycloudflare.com`

---

### Pilihan B: Menggunakan Domain Sendiri + Nginx + Let's Encrypt (Untuk Produksi)

1. Pasang konfigurasi virtual host Nginx (misal `/etc/nginx/sites-available/mfa-bot`):
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
2. Pasang sertifikat SSL gratis via Certbot:
   ```bash
   sudo certbot --nginx -d mfa.domainanda.com
   ```
3. URL Mini App Anda adalah: `https://mfa.domainanda.com`

---

### Pilihan C: Menggunakan ngrok (Untuk Uji Coba Cepat di PC Lokal)

```bash
ngrok http 8080
```
Salin URL forwarding HTTPS yang disediakan oleh ngrok.

---

## 🤖 Langkah 2: Konfigurasi di @BotFather

Buka obrolan dengan [@BotFather](https://t.me/BotFather) di Telegram.

### Metode 1: Mengatur Menu Button Chat (Sangat Direkomendasikan)
Tombol ini akan selalu muncul di sudut kiri bawah kolom input pesan chat pengguna:

1. Ketik perintah:
   ```text
   /setmenubutton
   ```
2. Pilih bot Anda dari daftar.
3. BotFather akan meminta URL Mini App. Masukkan URL HTTPS Anda:
   ```text
   https://mfa.domainanda.com
   ```
4. Masukkan nama/teks tombol yang ingin ditampilkan:
   ```text
   📱 Buka 2FA
   ```
5. Selesai! Pengguna Anda kini dapat membuka Mini App kapan saja dengan 1 klik pada tombol di samping kolom ketik chat.

---

### Metode 2: Membuat Dedicated Mini App (`/newapp`)
Jika Anda ingin memiliki direct link seperti `t.me/UsernameBot/app` atau tombol attachment:

1. Kirim perintah:
   ```text
   /newapp
   ```
2. Pilih bot Anda.
3. Masukkan **Title** aplikasi:
   ```text
   2FA Authenticator
   ```
4. Masukkan **Description** singkat:
   ```text
   Aplikasi 2FA Authenticator aman & modern dengan integrasi Simple Icons.
   ```
5. Kirim foto / logo untuk thumbnail (ukuran yang disarankan: 640 x 360 pixel).
6. (Opsional) Kirim animasi GIF pendek demonstrasi (atau kirim `/empty` untuk melewatinya).
7. Masukkan URL HTTPS Mini App Anda:
   ```text
   https://mfa.domainanda.com
   ```
8. Tentukan **Short Name** (hanya huruf kecil dan angka, tanpa spasi), misalnya:
   ```text
   app
   ```
9. BotFather akan memberikan link direct Mini App Anda:
   `t.me/NamaBotAnda/app`

---

### Metode 3: Pengaturan Profil & Informasi Lengkap Bot

Agar bot Anda memiliki tampilan yang menarik dan profesional, atur perintah berikut di BotFather:

1. **Deskripsi Awal Chat (`/setdescription`)**:
   - Kirim `/setdescription` -> Pilih bot Anda.
   - Kirim teks:
     ```text
     🛡️ Telegram 2FA Authenticator Bot mandiri dengan enkripsi tingkat tinggi (AES-256-GCM + Argon2id).

     ✨ Fitur Utama:
     • 📱 Mini App interaktif (Liquid Glass & Neumorphism)
     • 🎨 200+ logo resmi Simple Icons (Google, GitHub, Discord, Steam, AWS, dll.)
     • 🔐 Zero Master Key & Zero Telegram Cloud Storage
     • 🔢 Keypad inline interaktif (PIN aman tersamar)
     • ⏱️ Auto-delete pesan sensitif 90 detik

     Ketik /start untuk mulai mengamankan akun Anda!
     ```

2. **Tentang Bot / Info Profil (`/setabouttext`)**:
   - Kirim `/setabouttext` -> Pilih bot Anda.
   - Kirim teks:
     ```text
     Aplikasi 2FA Authenticator mandiri (TOTP/HOTP) terenkripsi AES-256-GCM dengan Mini App modern & integrasi Simple Icons.
     ```

3. **Foto Profil Bot (`/setuserpic`)**:
   - Kirim `/setuserpic` -> Pilih bot Anda.
   - Unggah gambar logo persegi (disarankan resolusi 512x512 pixel).

4. **Daftar Menu Command (`/setcommands`)**:
   - Kirim `/setcommands` -> Pilih bot Anda.
   - Kirim list berikut:
     ```text
     start - 🚀 Buka Menu Utama & Registrasi PIN
     menu - 📋 Tampilkan Menu Navigasi Dashboard
     miniapp - 📱 Buka Telegram Mini App
     help - ℹ️ Bantuan & Panduan Penggunaan
     cancel - ❌ Batalkan operasi aktif
     ```

---

## ⚙️ Langkah 3: Konfigurasi File `.env` Bot

Buka file `.env` di folder bot Anda dan sesuaikan konfigurasi berikut:

```dotenv
# Port server web internal bot (default: 8080)
MINI_APP_ENABLED=true
MINI_APP_HOST=0.0.0.0
MINI_APP_PORT=8080

# Masukkan URL HTTPS publik yang sudah Anda siapkan
MINI_APP_URL=https://mfa.domainanda.com
```

Setelah mengubah `.env`, jalankan atau restart bot Anda:
```bash
python bot.py
```

Saat bot menyala, server aiohttp otomatis aktif berdampingan dengan bot Telegram dalam satu event loop:
```text
INFO - Mini App web server running on 0.0.0.0:8080
INFO - Starting Telegram 2FA Authenticator Bot in polling mode...
```

---

## 🎨 Integrasi Simple Icons (simpleicons.org)

Bot & Mini App ini telah terintegrasi penuh dengan pustaka **Simple Icons**:
- Di dalam Mini App, ketika Anda memasukkan issuer seperti `Google`, `GitHub`, `Discord`, `Steam`, `AWS`, `Binance`, dll., aplikasi secara otomatis mengambil ikon vektor resmi SVG langsung dari CDN Simple Icons (`https://cdn.simpleicons.org/<slug>/white`).
- Jika platform belum terdaftar di Simple Icons atau dalam kondisi offline, sistem secara cerdas beralih ke badge emoji presisi tinggi yang serasi dengan identitas brand.
- Di chat Telegram standar, bot tetap menampilkan emoji brand yang akurat dan rapi.

---

## ❓ FAQ & Troubleshooting

### Kenapa muncul pesan "Aplikasi ini didesain untuk dijalankan di dalam Telegram Mini App"?
Mini App membutuhkan verifikasi otentikasi kriptografis `Telegram.WebApp.initData` yang hanya di-generate oleh aplikasi resmi Telegram. Buka tautan lewat chat bot atau tombol menu di Telegram, bukan lewat browser biasa.

### Kenapa scanner kamera tidak terbuka?
Fitur scanner kamera menggunakan API `Telegram.WebApp.showScanQrPopup` yang didukung penuh pada aplikasi Telegram versi terbaru (Android, iOS, dan Telegram Desktop). Pastikan aplikasi Telegram Anda sudah diperbarui.

### Bagaimana jika Master PIN salah?
Mini App memiliki sistem perlindungan brute-force lockout yang sama dengan bot chat: setelah beberapa kali percobaan gagal, akun akan terkunci secara sementara dengan countdown detik.
