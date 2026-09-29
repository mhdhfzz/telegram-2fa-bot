# Design Specification: Fitur "Lihat Semua Kode OTP"

## 1. Ringkasan Eksekutif (Overview)
Fitur **Lihat Semua Kode OTP** memungkinkan pengguna melihat seluruh kode autentikasi 2FA (TOTP/HOTP) dari semua akun yang tersimpan secara simultan dalam satu tampilan pesan. Fitur ini dirancang untuk kenyamanan akses cepat tanpa harus membuka akun satu per satu, dengan tetap menjaga standar keamanan tinggi (otentikasi PIN tunggal, zero plaintext storage, auto-delete pesan rahasia, dan auto-restore menu).

---

## 2. Titik Akses (Entry Points)
Fitur dapat diakses dari 2 lokasi:
1. **Menu Utama (Main Menu):**
   - Menambahkan tombol `👁️ Semua Kode` di baris atas menu navigasi utama.
   - Callback data: `menu:view_all_codes`
2. **Menu "🔑 Lihat Kode":**
   - Menambahkan tombol `👁️ Lihat Semua Kode Sekaligus` di bagian atas daftar pilihan akun tunggal.
   - Callback data: `menu:view_all_codes`

---

## 3. Alur Autentikasi & Pengelolaan Sesi (Authentication & Session State)

### 3.1. Alur Masuk PIN
1. Saat pengguna menekan tombol `menu:view_all_codes`:
   - Bot memeriksa apakah akun pengguna sedang terkena pembatasan lockout. Jika terkunci, tampilkan pesan waktu tunggu.
   - Bot memeriksa apakah pengguna memiliki akun yang tersimpan. Jika belum ada, tampilkan pesan informatif untuk menambah akun terlebih dahulu.
   - Bot menginisialisasi buffer PIN keypad dengan prefix `view_all_pin`.
   - Bot menampilkan pesan prompt input PIN dengan inline numeric keypad tersamar (`PIN: • • • • _ _`).
2. Pengguna memasukkan PIN melalui keypad:
   - Jika tombol `Batal` ditekan, bersihkan buffer dan kembali ke menu utama.
   - Jika PIN salah, catat percobaan gagal, tampilkan sisa kesempatan atau waktu kunci jika mencapai batas maksimum (exponential lockout).
   - Jika PIN benar, catat keberhasilan, turunkan kunci enkripsi AES-256-GCM dari PIN + `kdf_salt` pengguna, dan dekripsi secret dari seluruh akun yang terdaftar.

### 3.2. Struktur Sesi Memori (`active_view_all`)
Setelah PIN berhasil diverifikasi, bot menyimpan data sesi sementara di `context.user_data["active_view_all"]`:
```python
context.user_data["active_view_all"] = {
    "accounts": [
        {
            "id": acc.id,
            "label": acc.label,
            "issuer": acc.issuer,
            "type": acc.type,
            "digits": acc.digits,
            "period": acc.period,
            "secret": decrypted_secret,
            "hotp_counter": acc.hotp_counter,
            "emoji": get_issuer_emoji(acc.issuer),
        },
        ...
    ],
    "page": 1,
    "total_pages": math.ceil(len(accounts) / 10),
    "expires_at": time.time() + auto_del_secs,
    "chat_id": chat_id,
    "message_id": message_id,
}
```
*Catatan Keamanan:* Sesi ini hanya hidup di memori RAM selama durasi `AUTO_DELETE_SECONDS` (default: 90 detik) dan otomatis dibersihkan saat timer habis atau pengguna kembali ke menu.

---

## 4. Tampilan Pesan & Format Layout (Message Presentation & Layout)

### 4.1. Ketentuan Format:
- **1 Akun 1 Baris:** Setiap baris berisi emoji, nama akun/issuer, kode OTP dalam tag `<code>...</code>` (bisa langsung di-tap untuk copy), dan sisa detik (TOTP) atau nomor counter (HOTP).
- **Maksimal 10 Akun per Halaman:** Jika total akun > 10, tampilan dipaginasi menjadi beberapa halaman.
- **Header:** Menyebutkan judul halaman dan informasi auto-refresh serta masa berlaku pesan.
- **Footer:** Instruksi tap-to-copy dan notifikasi timer penghapusan otomatis.

### 4.2. Contoh Format Pesan:
```html
🔑 <b>Semua Kode OTP (Halaman 1/2)</b>
⏱️ <i>Auto-refresh tiap 5 detik • Dihapus dalam 90 detik.</i>

1. 🐙 <b>GitHub: alice</b>: <code>123456</code> (⏳ 18s)
2. 🌐 <b>Google Work</b>: <code>654321</code> (⏳ 18s)
3. 💬 <b>Discord</b>: <code>789012</code> (⏳ 18s)
4. 💳 <b>PayPal</b>: <code>345678</code> (⏳ 18s)
5. 🔢 <b>AWS Root</b>: <code>901234</code> (HOTP #5)
...

Tap kode di atas untuk menyalin ke clipboard.
```

---

## 5. Navigasi & Kontrol Inline Keyboard

Keyboard inline menyesuaikan jumlah halaman:
- **Jika Total Akun > 10 (Multi-halaman):**
  - Baris 1: `[◀️ Sebelumnya]` `[ 1 / 2 ]` `[Selanjutnya ▶️]`
  - Baris 2: `[🔄 Refresh Semua]` `[🔙 Menu Utama]`
- **Jika Total Akun <= 10 (Satu halaman):**
  - Baris 1: `[🔄 Refresh Semua]` `[🔙 Menu Utama]`

### 5.1. Navigasi Halaman (`view_all:page:{p}`)
- Pengguna dapat berpindah halaman secara instan tanpa harus memasukkan PIN ulang selama sesi 90 detik masih aktif.
- Perpindahan halaman memperbarui `active_view_all["page"]` dan langsung me-render 10 akun untuk halaman yang dipilih.

---

## 6. Pembaruan Otomatis & Pembersihan (Auto-Refresh & Lifecycle)

### 6.1. Dynamic Auto-Refresh (Interval 5 Detik)
- Menggunakan background job `view_all_countdown_job`:
  - Didaftarkan ke `context.job_queue.run_repeating(..., interval=5, first=5, name=f"view_all_cd_{chat_id}_{message_id}")`.
  - Tiap 5 detik, menghitung ulang nilai TOTP dan sisa detik interval untuk semua akun pada halaman yang sedang aktif.
  - Memperbarui teks pesan via `context.bot.edit_message_text(..., parse_mode=ParseMode.HTML)`.
  - Jika waktu saat ini >= `expires_at`, job otomatis dihentikan (`schedule_removal()`).

### 6.2. Manual Refresh (`view_all:refresh`)
- Tombol `🔄 Refresh Semua` memperbarui kode dan progress bar seketika tanpa menunggu siklus 5 detik.
- Menampilkan toast alert singkat `🔄 Semua kode OTP diperbarui!`.

### 6.3. Auto-Delete & Auto-Restore Menu (`AUTO_DELETE_SECONDS`)
- Menggunakan timer `context.job_queue.run_once(..., when=auto_del_secs, name=f"view_all_del_{chat_id}_{message_id}")`:
  - Saat timer habis (90 detik):
    1. Pesan berisi kode-kode OTP dihapus dari chat Telegram (`delete_message`).
    2. Data sesi `active_view_all` dan countdown job dibatalkan dan dihapus dari memori.
    3. Bot otomatis mengirim pesan **Menu Utama** ke obrolan pengguna agar riwayat chat tetap rapi dan siap digunakan kembali.

---

## 7. Penanganan Kesalahan & Edge Cases

| Skenario | Penanganan |
| :--- | :--- |
| **Tidak ada akun tersimpan** | Tampilkan pesan bahwa belum ada akun tersimpan dan tombol kembali ke menu utama. |
| **Sesi kedaluwarsa saat klik refresh / ganti halaman** | Berikan notifikasi `⏱️ Sesi telah berakhir. Masukkan PIN kembali.` dan arahkan kembali ke input PIN. |
| **Klik tombol cepat (*Double Tap*)** | Blok `try...except` mengabaikan error `BadRequest: Message is not modified`. |
| **Pesan terhapus manual oleh pengguna** | `global_error_handler` dan pengecekan job mengabaikan `Message to edit not found` dan menghentikan countdown job. |
| **User klik "Kembali ke Menu Utama"** | Bersihkan sesi memori `active_view_all`, hentikan countdown job dan auto-delete job, lalu render menu utama. |

---

## 8. Strategi Pengujian (Testing Strategy)
Menambahkan unit test otomatis komprehensif di `tests/test_view_all_codes.py`:
1. **Verifikasi Keypad PIN View All:** Input PIN benar membuka daftar kode semua akun.
2. **Verifikasi Lockout Enforcement:** Percobaan PIN salah terhitung dan memblokir akses jika mencapai batas.
3. **Verifikasi Format Layout:** Memastikan format 1 akun per baris, tag `<code>`, emoji issuer, dan nomor urut tampil tepat.
4. **Verifikasi Pagination:** Pengguna dengan 15 akun terbagi menjadi 2 halaman (10 di hal 1, 5 di hal 2) dan tombol navigasi berfungsi tanpa minta PIN ulang.
5. **Verifikasi Auto-Refresh & Auto-Delete:** Job countdown memperbarui kode dan job auto-delete menghapus pesan serta mengirimkan menu utama kembali.
