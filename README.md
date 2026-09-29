# Telegram 2FA Authenticator Bot (TOTP/HOTP)

[![Author](https://img.shields.io/badge/Author-mhdhfzz-blue.svg?logo=github)](https://github.com/mhdhfzz)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Telegram Bot API](https://img.shields.io/badge/Telegram_Bot_API-v20+-2CA5E0.svg?logo=telegram&logoColor=white)](https://python-telegram-bot.org/)
[![Security](https://img.shields.io/badge/Security-AES--256--GCM%20%7C%20Argon2id-green.svg)](https://cryptography.io/)
[![Tests](https://img.shields.io/badge/Tests-96%20Passed-brightgreen.svg)](#pengujian-otomatis-testing)
[![Demo Bot](https://img.shields.io/badge/Demo_Bot-@VexAuthKey__bot-26A5E4.svg?logo=telegram&logoColor=white)](https://t.me/VexAuthKey_bot)

Bot Telegram yang berfungsi sebagai aplikasi *two-factor authenticator* mandiri (seperti Google Authenticator / Authy), dihosting di VPS menggunakan Python. Bot mendukung multi-tenant dengan data antar-pengguna terisolasi penuh dan dienkripsi kuat menggunakan PIN pribadi masing-masing user.

Seluruh navigasi berbasis **inline button** dan **inline numeric keypad**, sehingga PIN tidak pernah diketik secara terbuka di chat Telegram.

> 🛡️ **PENTING: Privasi Data & Jaminan Nol Penyimpanan di Telegram (Zero Telegram Storage)**:  
> Bot ini **SAMA SEKALI TIDAK MENYIMPAN** data akun, secret key, PIN, maupun recovery phrase Anda di server atau cloud Telegram. Seluruh data disimpan secara lokal pada database server mandiri (Self-Hosted VPS), dan dienkripsi kuat dengan standar **AES-256-GCM** menggunakan kunci yang diturunkan langsung dari PIN pribadi Anda (**Zero Master Key**). Telegram hanya berfungsi sebagai antarmuka transport pesan sementara, di mana pesan sensitif (OTP, secret, QR, passphrase) otomatis langsung dihapus dari chat.

> 🤖 **Live Demo Bot**: Coba langsung di Telegram: [@VexAuthKey_bot](https://t.me/VexAuthKey_bot)

---

## ✨ Fitur Utama

- 🔒 **Zero Master Key**: Server tidak memiliki master key. Kunci enkripsi diturunkan langsung dari PIN user + salt unik menggunakan **Argon2id**.
- 🛡️ **Zero Cloud / Telegram Storage**: Server Telegram **sama sekali tidak menyimpan** data akun atau rahasia Anda. Semua database akun berada di VPS lokal milik host, dan seluruh rahasia dienkripsi sehingga bahkan pemilik VPS atau Telegram tidak dapat membaca kode OTP tanpa PIN Anda.
- 🛡️ **Enkripsi AES-256-GCM**: Setiap secret akun dienkripsi secara independen dengan nonce 12-byte unik dan verifikasi authentication tag anti-tampering.
- 🔢 **Inline Numeric Keypad**: Input PIN dilakukan melalui grid tombol inline interaktif (`0-9`, `⌫`, `✅`, `❌`) dengan display tersamar (`PIN: • • • • _ _`).
- 📏 **Panjang PIN Dinamis**: Panjang PIN dapat dikonfigurasi fleksibel (`PIN_LENGTH=4` hingga `PIN_LENGTH=8`, default: 6 digit) melalui environment variable.
- 📋 **Tap-to-Copy Monospace OTP**: Kode OTP diformat dalam tag monospace tanpa spasi (`<code>123456</code>`), memudahkan pengguna menyalin kode cukup dengan satu sentuhan.
- 👁️ **Lihat Semua Kode OTP Sekaligus**: Buka seluruh kode OTP akun hanya dengan 1x input PIN. Tampilan ringkas (1 akun per baris dengan tap-to-copy), pagination responsif (hingga 10 akun per halaman), auto-refresh serentak tiap 5 detik, auto-delete pesan dalam 90 detik, dan zero persistence disk (secret hanya di memori sementara).
- ⏳ **Visual Countdown Bar & Dynamic Auto-Refresh**: Progres bar visual sisa waktu kode TOTP (`⏳ [■■■■■■□□□□] 18 detik lagi`) otomatis memperbarui kode saat window waktu berganti, serta dilengkapi tombol refresh manual (mendukung HOTP increment counter & TOTP) tanpa bentrok sesi PIN.
- ⏱️ **Auto-Delete Pesan Sensitif & Pembersihan Otomatis Obrolan**:
  - Pesan berisi kode OTP, recovery phrase, atau dokumen cadangan dihapus otomatis setelah 90 detik (`AUTO_DELETE_SECONDS`).
  - Pesan input pengguna (Secret Key manual, nama label, upload QR, passphrase backup, search query) beserta pesan prompt instruksi bot **otomatis dihapus langsung** setelah direspons, menjaga chat history tetap bersih dan aman dari kebocoran teks plaintext rahasia.
- 🔄 **Auto-Restore Menu Utama Pasca Auto-Delete**: Ketika pesan kode OTP atau recovery phrase selesai ditampilkan dan terhapus otomatis oleh timer, bot **secara otomatis menampilkan kembali Menu Utama** ke obrolan pengguna tanpa perlu mengetik ulang command `/start`.
- ⚡ **SQLite Concurrency & WAL Hardening**: Menggunakan mode SQLite WAL (`PRAGMA journal_mode=WAL`) dan `PRAGMA busy_timeout=5000` untuk operasi database concurrent yang cepat tanpa risiko *database locked*.
- 🛡️ **Sanitasi Data & Defensive Input**: Validasi panjang label (maks. 64 karakter), penataan spasi, sanitasi URI OTP (`digits`, `period`, `counter`), dan escaping Markdown menyeluruh untuk mencegah error parsing Telegram.
- 🚫 **Exponential Lockout**: Mencegah serangan brute-force PIN (salah 5x berturut-turut mengunci akun selama 5 menit; berlanjut ke 15 menit, lalu maksimum 60 menit) dengan countdown timer dan indikator sisa percobaan.
- 📷 **Scan QR Code & Input Manual**: Tambah akun dengan mengirim foto/tangkapan layar QR code (`otpauth://`) atau memasukkan Secret Key Base32 secara manual.
- 🗂️ **Cadangan Terenkripsi (Export/Import)**: Cadangkan seluruh akun ke file JSON yang dienkripsi menggunakan passphrase mandiri (terpisah dari PIN login).
- 🔑 **Recovery Phrase 12 Kata (Dwi-Bahasa)**: Pemulihan akun menggunakan 12 kata acak (mendukung BIP-39 English standar atau daftar kata bahasa Indonesia).
- 📜 **Audit Log Transparan**: Riwayat aktivitas akses tanpa mencatat data rahasia (PIN, secret, dan OTP tidak pernah ditulis ke log).

---

## 🔒 Arsitektur Keamanan & Privasi Data

| Aspek Keamanan | Mekanisme & Implementasi |
| :--- | :--- |
| **Penyimpanan Telegram** | **NOL (Zero Storage)**. Server/cloud Telegram tidak pernah menyimpan database, secret key, atau PIN Anda. |
| **Lokasi Database** | Tersimpan secara lokal pada server mandiri Anda (`SQLite`) dan tidak diunggah ke pihak ketiga mana pun. |
| **Enkripsi Data Akun** | Setiap secret key dienkripsi menggunakan **AES-256-GCM** dengan tag autentikasi 16-byte dan nonce 12-byte acak unik. |
| **Zero Master Key** | Server tidak memiliki master key. Kunci enkripsi diturunkan langsung via **Argon2id KDF** dari PIN Anda saat sesi aktif. |
| **Pembersihan Chat History** | Pesan input pengguna (Secret Key Base32, label, dokumen backup, kata kunci pencarian) dan prompt bot langsung dihapus seketika. |
| **Auto-Restore Menu** | Setelah timer auto-delete OTP (default: 90 detik) habis dan pesan dihapus, Menu Utama otomatis dimunculkan kembali agar obrolan tidak kosong. |

---

## 🏗️ Struktur Direktori

```text
├── bot.py                     # Entry point & inisialisasi ApplicationBuilder
├── config.py                  # Pydantic Settings & environment loader
├── .env.example               # Template environment variables
├── requirements.txt           # Dependensi Python
├── db/
│   ├── models.py              # Model SQLAlchemy 2.0 (User, Account, AccessLog)
│   └── session.py             # Engine & async_sessionmaker (aiosqlite)
├── crypto/
│   ├── kdf.py                 # Argon2id: verifikasi PIN & derive key enkripsi
│   ├── cipher.py              # AES-256-GCM (encrypt, decrypt dengan nonce 12-byte)
│   └── recovery.py            # Generator 12 kata Recovery Phrase (BIP-39 & ID)
├── services/
│   ├── otp_service.py         # Generator TOTP / HOTP (pyotp) & visual countdown
│   ├── qr_service.py          # Decoder QR code (pyzbar + fallback OpenCV) & encoder
│   ├── icon_service.py        # Pemetaan otomatis issuer ke emoji
│   ├── lockout_service.py     # Exponential lockout & counter percobaan gagal
│   ├── log_service.py         # Pencatatan audit log & pagination
│   └── backup_service.py      # Ekspor/impor cadangan JSON terenkripsi
├── handlers/
│   ├── keypad.py              # Reusable inline numeric keypad handler
│   ├── start.py               # /start & alur registrasi PIN awal
│   ├── menu.py                # Menu navigasi dashboard
│   ├── add_account.py         # Alur scan QR & input manual secret
│   ├── view_code.py           # Tampilan OTP monospace, timer, & dynamic countdown refresh
│   ├── view_all_codes.py      # Tampilan semua kode OTP, pagination & periodic refresh
│   ├── manage_account.py      # Kelola label, status favorit, & hapus akun
│   └── settings.py            # Ganti PIN, ekspor/impor, & lihat log akses
├── deploy/
│   ├── telegram-2fa-bot.service # Unit file systemd untuk Linux VPS
│   └── README-deploy.md       # Panduan deployment lengkap di VPS
└── tests/                     # 83 Automated unit & integration tests (pytest)
```

---

## 🚀 Panduan Memulai Cepat (Local Development)

### 1. Kloning Repositori
```bash
git clone https://github.com/mhdhfzz/telegram-2fa-bot.git
cd telegram-2fa-bot
```

### 2. Buat Virtual Environment & Pasang Dependensi
```bash
python -m venv venv
# Linux / macOS:
source venv/bin/activate
# Windows PowerShell:
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 3. Konfigurasi Environment
Salin file `.env.example` menjadi `.env`:
```bash
cp .env.example .env
```
Edit file `.env`:
```ini
BOT_TOKEN=token_telegram_anda_disini
DB_PATH=2fa_bot.db
LOG_LEVEL=INFO
PIN_LENGTH=6
AUTO_DELETE_SECONDS=90
```

### 4. Jalankan Bot
```bash
python bot.py
```
Buka Telegram, cari bot Anda atau uji melalui bot demo [@VexAuthKey_bot](https://t.me/VexAuthKey_bot), lalu kirim perintah `/start`.

---

## 🧪 Pengujian Otomatis (Testing)

Proyek ini memiliki **84 unit dan integration test** yang mencakup seluruh lapisan sistem:

```bash
pytest -v
```

Hasil pengujian:
```text
tests/test_add_account.py .....                            [  5%]
tests/test_backup.py .....                                 [ 10%]
tests/test_bot_smoke.py ...                                [ 13%]
tests/test_config.py ...                                   [ 16%]
tests/test_crypto.py ......                                [ 23%]
tests/test_db.py ...                                       [ 26%]
tests/test_keypad.py ......                                [ 32%]
tests/test_lockout.py ..                                   [ 34%]
tests/test_lockout_handlers.py .....                       [ 39%]
tests/test_menu_handlers.py ...........                    [ 50%]
tests/test_otp.py ..........                               [ 61%]
tests/test_settings.py .......                             [ 68%]
tests/test_start_handler.py .....                          [ 73%]
tests/test_view_all_codes.py ...............               [ 89%]
tests/test_view_code.py ..........                         [100%]

============================= 96 passed in 26.37s =============================
```

---

## 🌐 Panduan Deployment di VPS (Production)

Panduan detail konfigurasi Linux VPS (Ubuntu/Debian) dengan user non-root, instalasi pustaka sistem `libzbar0`, systemd service, firewall, dan cron backup harian tersedia di:
📖 **[deploy/README-deploy.md](deploy/README-deploy.md)**

---

## 👤 Author

- GitHub: [@mhdhfzz](https://github.com/mhdhfzz)

## 📜 Lisensi

Proyek ini dilisensikan di bawah lisensi MIT. Bebas digunakan dan dimodifikasi untuk kebutuhan pribadi maupun organisasi.
