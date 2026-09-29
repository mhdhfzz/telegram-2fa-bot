/**
 * Telegram 2FA Authenticator Mini App
 * Fully client-side interactive logic, PIN keypad, live TOTP countdown,
 * Simple Icons integration, and native Telegram QR code scanner.
 */

(function () {
  'use strict';

  // State
  const state = {
    initData: '',
    sessionToken: '',
    pinBuffer: '',
    pinLength: 6,
    accounts: [],
    currentFilter: 'all',
    searchQuery: '',
    isLocked: false,
    lockoutTimer: null,
  };

  // Telegram WebApp Object
  const tg = window.Telegram?.WebApp;

  // DOM Elements
  const el = {
    userGreeting: document.getElementById('userGreeting'),
    btnOpenAddModal: document.getElementById('btnOpenAddModal'),
    btnLockApp: document.getElementById('btnLockApp'),
    screenLoading: document.getElementById('screenLoading'),
    screenNotRegistered: document.getElementById('screenNotRegistered'),
    notRegisteredMsg: document.getElementById('notRegisteredMsg'),
    btnCloseApp: document.getElementById('btnCloseApp'),
    screenLock: document.getElementById('screenLock'),
    pinDotsRow: document.getElementById('pinDotsRow'),
    pinErrorMsg: document.getElementById('pinErrorMsg'),
    pinLockoutMsg: document.getElementById('pinLockoutMsg'),
    screenDashboard: document.getElementById('screenDashboard'),
    searchInput: document.getElementById('searchInput'),
    btnClearSearch: document.getElementById('btnClearSearch'),
    filterPills: document.querySelectorAll('.filter-pill'),
    accountsList: document.getElementById('accountsList'),
    emptyState: document.getElementById('emptyState'),
    btnEmptyAdd: document.getElementById('btnEmptyAdd'),
    btnOpenSettingsModal: document.getElementById('btnOpenSettingsModal'),
    modalAddAccount: document.getElementById('modalAddAccount'),
    modalBackdrop: document.getElementById('modalBackdrop'),
    btnCloseModal: document.getElementById('btnCloseModal'),
    btnCancelAdd: document.getElementById('btnCancelAdd'),
    btnScanQrCode: document.getElementById('btnScanQrCode'),
    formAddAccount: document.getElementById('formAddAccount'),
    inputLabel: document.getElementById('inputLabel'),
    inputIssuer: document.getElementById('inputIssuer'),
    inputSecret: document.getElementById('inputSecret'),
    selectType: document.getElementById('selectType'),
    selectDigits: document.getElementById('selectDigits'),
    addErrorMsg: document.getElementById('addErrorMsg'),

    // Edit Modal Elements
    modalEditAccount: document.getElementById('modalEditAccount'),
    modalEditBackdrop: document.getElementById('modalEditBackdrop'),
    btnCloseEditModal: document.getElementById('btnCloseEditModal'),
    btnCancelEdit: document.getElementById('btnCancelEdit'),
    formEditAccount: document.getElementById('formEditAccount'),
    editAccountId: document.getElementById('editAccountId'),
    editInputLabel: document.getElementById('editInputLabel'),
    editInputIssuer: document.getElementById('editInputIssuer'),
    editErrorMsg: document.getElementById('editErrorMsg'),

    // Settings Modal Elements
    modalSettings: document.getElementById('modalSettings'),
    modalSettingsBackdrop: document.getElementById('modalSettingsBackdrop'),
    btnCloseSettingsModal: document.getElementById('btnCloseSettingsModal'),
    settingsTabBtns: document.querySelectorAll('.settings-tab-btn'),
    settingsTabPanes: document.querySelectorAll('.settings-tab-pane'),
    formChangePin: document.getElementById('formChangePin'),
    inputOldPin: document.getElementById('inputOldPin'),
    inputNewPin: document.getElementById('inputNewPin'),
    inputConfirmPin: document.getElementById('inputConfirmPin'),
    changePinMsg: document.getElementById('changePinMsg'),

    // Backup & Restore
    formExportBackup: document.getElementById('formExportBackup'),
    inputExportPassphrase: document.getElementById('inputExportPassphrase'),
    inputConfirmExportPassphrase: document.getElementById('inputConfirmExportPassphrase'),
    exportBackupMsg: document.getElementById('exportBackupMsg'),
    btnExportBackup: document.getElementById('btnExportBackup'),
    backupOutputArea: document.getElementById('backupOutputArea'),
    backupJsonText: document.getElementById('backupJsonText'),
    btnDownloadBackupFile: document.getElementById('btnDownloadBackupFile'),
    btnCopyBackupJson: document.getElementById('btnCopyBackupJson'),

    formImportBackup: document.getElementById('formImportBackup'),
    fileImportBackup: document.getElementById('fileImportBackup'),
    btnChooseBackupFile: document.getElementById('btnChooseBackupFile'),
    inputImportJson: document.getElementById('inputImportJson'),
    inputImportPassphrase: document.getElementById('inputImportPassphrase'),
    importBackupMsg: document.getElementById('importBackupMsg'),
    btnSubmitImportBackup: document.getElementById('btnSubmitImportBackup'),
    auditLogsContainer: document.getElementById('auditLogsContainer'),

    toast: document.getElementById('toast'),
    toastIcon: document.getElementById('toastIcon'),
    toastMessage: document.getElementById('toastMessage'),
  };

  // --- Initialize Telegram WebApp ---
  function initTelegram() {
    if (tg) {
      tg.ready();
      tg.expand();
      try {
        tg.enableClosingConfirmation();
      } catch (e) {}

      // Apply Telegram theme classes if available
      if (tg.colorScheme === 'dark') {
        document.body.classList.add('tg-theme');
      }

      state.initData = tg.initData || '';

      const user = tg.initDataUnsafe?.user;
      if (user && user.first_name) {
        el.userGreeting.textContent = `Halo, ${user.first_name}`;
      }
    }
  }

  // --- Screen Switching ---
  function showScreen(screenEl) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    screenEl.classList.add('active');
  }

  // --- Toast Notification ---
  let toastTimeout;
  function showToast(msg, icon = '✅', duration = 2500) {
    el.toastMessage.textContent = msg;
    el.toastIcon.textContent = icon;
    el.toast.classList.add('show');
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
      el.toast.classList.remove('show');
    }, duration);
  }

  // --- API Helper ---
  async function apiFetch(endpoint, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    };
    if (state.sessionToken) {
      headers['Authorization'] = `Bearer ${state.sessionToken}`;
      headers['X-Session-Token'] = state.sessionToken;
    }
    if (state.initData) {
      headers['X-Telegram-Init-Data'] = state.initData;
    }

    const res = await fetch(endpoint, {
      ...options,
      headers,
    });
    return res;
  }

  // --- Dynamic PIN Dots Setup ---
  function updatePinLength(len) {
    const parsed = parseInt(len, 10);
    if (!isNaN(parsed) && parsed >= 4 && parsed <= 8) {
      state.pinLength = parsed;
    }
    const sub = document.getElementById('authSubtitle');
    if (sub) {
      sub.textContent = `PIN ${state.pinLength}-digit Master 2FA Anda untuk mendekripsi akun`;
    }
    if (el.inputOldPin) el.inputOldPin.setAttribute('maxlength', state.pinLength);
    if (el.inputNewPin) {
      el.inputNewPin.setAttribute('maxlength', state.pinLength);
      el.inputNewPin.setAttribute('placeholder', `Masukkan ${state.pinLength} digit PIN baru`);
    }
    if (el.inputConfirmPin) {
      el.inputConfirmPin.setAttribute('maxlength', state.pinLength);
      el.inputConfirmPin.setAttribute('placeholder', `Ulangi ${state.pinLength} digit PIN baru`);
    }
    initPinDots();
  }

  function initPinDots() {
    if (!el.pinDotsRow) return;
    el.pinDotsRow.innerHTML = '';
    for (let i = 0; i < state.pinLength; i++) {
      const dot = document.createElement('div');
      dot.className = 'pin-dot';
      dot.setAttribute('data-index', String(i));
      el.pinDotsRow.appendChild(dot);
    }
    renderPinDots();
  }

  function renderPinDots() {
    if (!el.pinDotsRow) return;
    const dots = el.pinDotsRow.querySelectorAll('.pin-dot');
    dots.forEach((dot, index) => {
      if (index < state.pinBuffer.length) {
        dot.classList.add('filled');
      } else {
        dot.classList.remove('filled');
      }
    });
  }

  // --- App Startup Check ---
  async function checkInit() {
    // Read status API to get configured pin length as early as possible
    try {
      const statusRes = await fetch('/api/status');
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        if (statusData.pin_length) {
          updatePinLength(statusData.pin_length);
        }
      }
    } catch (_) {}

    initPinDots();
    showScreen(el.screenLoading);

    // If initData is empty (opened directly in regular browser outside Telegram)
    if (!state.initData) {
      // In development or test, we show a helpful message
      showScreen(el.screenNotRegistered);
      el.notRegisteredMsg.textContent = 'Aplikasi ini didesain untuk dijalankan di dalam Telegram Mini App.';
      return;
    }

    try {
      const res = await apiFetch('/api/init', {
        method: 'POST',
        body: JSON.stringify({ init_data: state.initData }),
      });
      const data = await res.json();

      if (!res.ok || !data.registered) {
        showScreen(el.screenNotRegistered);
        if (data.message) {
          el.notRegisteredMsg.textContent = data.message;
        }
        return;
      }

      if (data.pin_length) {
        updatePinLength(data.pin_length);
      }

      if (data.is_locked) {
        startLockoutCountdown(data.lockout_seconds);
      }

      showScreen(el.screenLock);
      renderPinDots();
    } catch (err) {
      console.error('Init error:', err);
      showScreen(el.screenNotRegistered);
      el.notRegisteredMsg.textContent = 'Gagal terhubung ke server. Periksa koneksi internet Anda.';
    }
  }

  function handleKeypadPress(key) {
    if (state.isLocked) return;

    if (tg?.HapticFeedback) {
      tg.HapticFeedback.impactOccurred('light');
    }

    if (key === 'clear') {
      state.pinBuffer = '';
      el.pinErrorMsg.textContent = '';
      renderPinDots();
      return;
    }

    if (key === 'backspace') {
      state.pinBuffer = state.pinBuffer.slice(0, -1);
      el.pinErrorMsg.textContent = '';
      renderPinDots();
      return;
    }

    if (state.pinBuffer.length < state.pinLength) {
      state.pinBuffer += key;
      renderPinDots();

      if (state.pinBuffer.length === state.pinLength) {
        submitPin(state.pinBuffer);
      }
    }
  }

  async function submitPin(pin) {
    el.pinErrorMsg.textContent = 'Memverifikasi PIN...';
    try {
      const res = await apiFetch('/api/auth/pin', {
        method: 'POST',
        body: JSON.stringify({
          init_data: state.initData,
          pin: pin,
        }),
      });
      const data = await res.json();

      if (!res.ok || !data.success) {
        state.pinBuffer = '';
        renderPinDots();

        if (tg?.HapticFeedback) {
          tg.HapticFeedback.notificationOccurred('error');
        }

        if (data.is_locked) {
          startLockoutCountdown(data.lockout_seconds);
        } else {
          el.pinErrorMsg.textContent = data.error || 'PIN salah. Silakan coba lagi.';
          shakePinDots();
        }
        return;
      }

      // Success!
      if (tg?.HapticFeedback) {
        tg.HapticFeedback.notificationOccurred('success');
      }

      state.sessionToken = data.token;
      state.pinBuffer = '';
      el.pinErrorMsg.textContent = '';
      showToast('PIN Terverifikasi', '🔓');

      await loadAccounts();
      showScreen(el.screenDashboard);
    } catch (err) {
      state.pinBuffer = '';
      renderPinDots();
      el.pinErrorMsg.textContent = 'Terjadi kesalahan jaringan saat verifikasi.';
    }
  }

  function shakePinDots() {
    el.pinDotsRow.style.animation = 'shake 0.35s ease';
    setTimeout(() => {
      el.pinDotsRow.style.animation = '';
    }, 400);
  }

  function startLockoutCountdown(seconds) {
    state.isLocked = true;
    let rem = seconds;
    clearInterval(state.lockoutTimer);

    function update() {
      if (rem <= 0) {
        clearInterval(state.lockoutTimer);
        state.isLocked = false;
        el.pinLockoutMsg.textContent = '';
        return;
      }
      el.pinLockoutMsg.textContent = `⏳ Terkunci! Coba lagi dalam ${rem} detik`;
      rem--;
    }
    update();
    state.lockoutTimer = setInterval(update, 1000);
  }

  // --- Accounts Management ---
  async function loadAccounts() {
    try {
      const res = await apiFetch('/api/accounts');
      if (res.status === 401) {
        // Session expired, lock screen
        lockApp();
        return;
      }
      const data = await res.json();
      state.accounts = data.accounts || [];
      renderAccounts();
    } catch (err) {
      console.error('Failed to load accounts:', err);
    }
  }

  function filterAccounts() {
    return state.accounts.filter(acc => {
      // Category filter
      if (state.currentFilter === 'favorite' && !acc.is_favorite) return false;
      if (state.currentFilter === 'totp' && acc.type !== 'totp') return false;
      if (state.currentFilter === 'hotp' && acc.type !== 'hotp') return false;

      // Search query
      if (state.searchQuery) {
        const q = state.searchQuery.toLowerCase();
        const label = (acc.label || '').toLowerCase();
        const issuer = (acc.issuer || '').toLowerCase();
        return label.includes(q) || issuer.includes(q);
      }
      return true;
    });
  }

  function renderAccounts() {
    const filtered = filterAccounts();
    el.accountsList.innerHTML = '';

    if (filtered.length === 0) {
      el.emptyState.classList.remove('hidden');
      return;
    }
    el.emptyState.classList.add('hidden');

    filtered.forEach(acc => {
      const card = createAccountCard(acc);
      el.accountsList.appendChild(card);
    });
  }

  function createAccountCard(acc) {
    const card = document.createElement('div');
    card.className = `account-card ${acc.is_favorite ? 'favorite' : ''}`;
    card.dataset.id = acc.id;

    // Platform Logo / Avatar
    // Uses Simple Icons SVG CDN if slug is present, with fallback to emoji badge
    let avatarHtml = '';
    if (acc.slug) {
      const svgUrl = `https://cdn.simpleicons.org/${acc.slug}/white`;
      avatarHtml = `
        <div class="brand-avatar" title="${escapeHtml(acc.issuer || 'Account')}">
          <img class="brand-svg-img" src="${svgUrl}" alt="${escapeHtml(acc.issuer || '')}"
               onerror="this.onerror=null; this.parentElement.innerHTML='<span class=\\'brand-emoji-fallback\\'>${acc.emoji || '🔐'}</span>';">
        </div>
      `;
    } else {
      avatarHtml = `
        <div class="brand-avatar">
          <span class="brand-emoji-fallback">${acc.emoji || '🔐'}</span>
        </div>
      `;
    }

    // OTP Code display formatting
    const rawCode = acc.code || '------';
    const formattedCode = rawCode.length === 6 ? `${rawCode.slice(0, 3)} ${rawCode.slice(3)}` : rawCode;

    card.innerHTML = `
      <div class="card-top">
        <div class="brand-info">
          ${avatarHtml}
          <div class="meta-texts">
            <span class="account-label">${escapeHtml(acc.label)}</span>
            <span class="account-issuer">${escapeHtml(acc.issuer || '2FA')}</span>
          </div>
        </div>
        <div class="card-actions-top">
          <button class="btn-star ${acc.is_favorite ? 'active' : ''}" title="Favorit" data-action="favorite">
            ${acc.is_favorite ? '⭐' : '☆'}
          </button>
          <button class="btn-card-edit" title="Edit Akun" data-action="edit">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
            </svg>
          </button>
          <button class="btn-card-del" title="Hapus Akun" data-action="delete">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/>
            </svg>
          </button>
        </div>
      </div>

      <div class="card-bottom">
        <div class="otp-code-box" data-action="copy">
          <span class="otp-code" id="code-${acc.id}">${formattedCode}</span>
          <span class="code-type-badge" id="badge-${acc.id}">${acc.type.toUpperCase()}${acc.type === 'hotp' ? ` #${acc.hotp_counter || 0}` : ''}</span>
        </div>
        <div class="timer-copy-wrap">
          ${acc.type === 'totp' ? createTimerSvg(acc) : `
            <button class="btn-hotp-next" title="Counter Berikutnya" data-action="hotp_next">
              🔢 +1
            </button>
          `}
          <button class="btn-copy" data-action="copy">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184"/>
            </svg>
            <span>Salin</span>
          </button>
        </div>
      </div>
    `;

    // Event Delegation on card
    card.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      const action = btn.dataset.action;

      if (action === 'copy') {
        const currentCode = (document.getElementById(`code-${acc.id}`)?.textContent || rawCode).replace(/\s+/g, '');
        copyCode(currentCode);
      } else if (action === 'favorite') {
        toggleFavorite(acc.id);
      } else if (action === 'edit') {
        openEditModal(acc);
      } else if (action === 'delete') {
        confirmDelete(acc.id, acc.label);
      } else if (action === 'hotp_next') {
        triggerHotpNext(acc.id);
      }
    });

    return card;
  }

  function createTimerSvg(acc) {
    const period = acc.period || 30;
    const rem = acc.remaining_seconds != null ? acc.remaining_seconds : period;
    const radius = 13;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference * (1 - rem / period);

    return `
      <div class="timer-circle-wrap" id="timer-wrap-${acc.id}">
        <svg class="timer-svg" viewBox="0 0 34 34">
          <circle class="timer-bg" cx="17" cy="17" r="${radius}" fill="none"/>
          <circle class="timer-progress ${rem <= 5 ? 'warning' : ''}" id="timer-ring-${acc.id}"
                  cx="17" cy="17" r="${radius}" fill="none"
                  stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"/>
        </svg>
        <span class="timer-text" id="timer-text-${acc.id}">${rem}s</span>
      </div>
    `;
  }

  function copyCode(code) {
    const clean = String(code).replace(/\s+/g, '');
    navigator.clipboard.writeText(clean).then(() => {
      if (tg?.HapticFeedback) {
        tg.HapticFeedback.notificationOccurred('success');
      }
      showToast(`Kode ${clean} berhasil disalin!`, '📋');
    }).catch(() => {
      showToast('Gagal menyalin kode', '❌');
    });
  }

  async function toggleFavorite(id) {
    const acc = state.accounts.find(a => a.id === id);
    if (!acc) return;

    try {
      const res = await apiFetch(`/api/accounts/${id}/favorite`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        acc.is_favorite = data.is_favorite;
        if (tg?.HapticFeedback) {
          tg.HapticFeedback.impactOccurred('medium');
        }
        renderAccounts();
      }
    } catch (err) {
      console.error(err);
    }
  }

  function confirmDelete(id, label) {
    const confirmMsg = `Apakah Anda yakin ingin menghapus akun "${label}"? Tindakan ini tidak dapat dibatalkan.`;

    if (tg?.showConfirm) {
      tg.showConfirm(confirmMsg, (confirmed) => {
        if (confirmed) doDeleteAccount(id);
      });
    } else {
      if (window.confirm(confirmMsg)) {
        doDeleteAccount(id);
      }
    }
  }

  async function doDeleteAccount(id) {
    try {
      const res = await apiFetch(`/api/accounts/${id}`, { method: 'DELETE' });
      if (res.ok) {
        state.accounts = state.accounts.filter(a => a.id !== id);
        if (tg?.HapticFeedback) {
          tg.HapticFeedback.notificationOccurred('warning');
        }
        showToast('Akun berhasil dihapus', '🗑️');
        renderAccounts();
      }
    } catch (err) {
      showToast('Gagal menghapus akun', '❌');
    }
  }

  // --- Real-Time 1-Second Countdown Ticker ---
  function updateCountdowns() {
    if (state.accounts.length === 0) return;

    const now = Math.floor(Date.now() / 1000);
    const radius = 13;
    const circumference = 2 * Math.PI * radius;

    state.accounts.forEach(acc => {
      if (acc.type !== 'totp') return;

      const period = acc.period || 30;
      const rem = period - (now % period);

      const ringEl = document.getElementById(`timer-ring-${acc.id}`);
      const textEl = document.getElementById(`timer-text-${acc.id}`);
      const codeEl = document.getElementById(`code-${acc.id}`);

      if (ringEl && textEl) {
        const offset = circumference * (1 - rem / period);
        ringEl.style.strokeDashoffset = offset;
        textEl.textContent = `${rem}s`;

        if (rem <= 5) {
          ringEl.classList.add('warning');
          if (codeEl) codeEl.classList.add('warning');
        } else {
          ringEl.classList.remove('warning');
          if (codeEl) codeEl.classList.remove('warning');
        }
      }

      // If rolled over, refresh account codes from server
      if (rem === period) {
        loadAccounts();
      }
    });
  }

  // Start ticker
  setInterval(updateCountdowns, 1000);

  // --- Add Account Modal & Telegram QR Scanner ---
  function openAddModal() {
    el.formAddAccount.reset();
    el.addErrorMsg.classList.add('hidden');
    el.modalAddAccount.classList.add('active');
  }

  function closeAddModal() {
    el.modalAddAccount.classList.remove('active');
  }

  // Telegram Native QR Scanner Integration
  function scanQrWithTelegram() {
    if (!tg?.showScanQrPopup) {
      showToast('Fitur scanner hanya aktif di Telegram', '⚠️');
      return;
    }

    tg.showScanQrPopup({ text: 'Arahkan kamera ke QR Code 2FA' }, (scannedText) => {
      if (!scannedText) return false;

      try {
        parseOtpauthUri(scannedText);
        tg.closeScanQrPopup();
        showToast('QR Code berhasil dipindai!', '📷');
        return true;
      } catch (err) {
        showToast('Format QR Code tidak valid', '❌');
        return false;
      }
    });
  }

  function parseOtpauthUri(uri) {
    if (!uri.toLowerCase().startsWith('otpauth://')) {
      throw new Error('Not otpauth');
    }
    const url = new URL(uri);
    const type = url.host.toLowerCase();
    const path = decodeURIComponent(url.pathname.replace(/^\//, ''));
    let label = path;
    let issuer = url.searchParams.get('issuer') || '';

    if (path.includes(':')) {
      const parts = path.split(':');
      if (!issuer) issuer = parts[0];
      label = parts.slice(1).join(':').trim();
    }

    const secret = url.searchParams.get('secret') || '';
    const digits = url.searchParams.get('digits') || '6';
    const period = url.searchParams.get('period') || '30';

    el.inputLabel.value = label;
    el.inputIssuer.value = issuer;
    el.inputSecret.value = secret;
    el.selectType.value = type === 'hotp' ? 'hotp' : 'totp';
    el.selectDigits.value = digits === '8' ? '8' : '6';
  }

  async function submitAddAccount(e) {
    e.preventDefault();
    el.addErrorMsg.classList.add('hidden');

    const label = el.inputLabel.value.trim();
    const issuer = el.inputIssuer.value.trim();
    const secret = el.inputSecret.value.trim();
    const type = el.selectType.value;
    const digits = parseInt(el.selectDigits.value, 10);

    if (!label || !secret) {
      el.addErrorMsg.textContent = 'Nama akun dan Secret Key wajib diisi.';
      el.addErrorMsg.classList.remove('hidden');
      return;
    }

    try {
      const res = await apiFetch('/api/accounts', {
        method: 'POST',
        body: JSON.stringify({ label, issuer, secret, type, digits }),
      });
      const data = await res.json();

      if (!res.ok || !data.success) {
        el.addErrorMsg.textContent = data.error || 'Gagal menambahkan akun.';
        el.addErrorMsg.classList.remove('hidden');
        return;
      }

      closeAddModal();
      showToast('Akun berhasil ditambahkan!', '✨');
      await loadAccounts();
    } catch (err) {
      el.addErrorMsg.textContent = 'Terjadi kesalahan jaringan saat menyimpan.';
      el.addErrorMsg.classList.remove('hidden');
    }
  }

  // --- Lock App ---
  function lockApp() {
    state.sessionToken = '';
    state.pinBuffer = '';
    renderPinDots();
    showScreen(el.screenLock);
    showToast('Aplikasi terkunci', '🔒');
  }

  // Helper Escape HTML
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // --- HOTP Counter Increment ---
  async function triggerHotpNext(id) {
    const acc = state.accounts.find(a => a.id === id);
    if (!acc) return;

    try {
      const res = await apiFetch(`/api/accounts/${id}/hotp_next`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok || !data.success) {
        showToast(data.error || 'Gagal memajukan counter HOTP', '❌');
        return;
      }

      acc.hotp_counter = data.hotp_counter;
      acc.code = data.code;

      const codeEl = document.getElementById(`code-${id}`);
      const badgeEl = document.getElementById(`badge-${id}`);
      if (codeEl) {
        const raw = String(data.code);
        codeEl.textContent = raw.length === 6 ? `${raw.slice(0, 3)} ${raw.slice(3)}` : raw;
      }
      if (badgeEl) {
        badgeEl.textContent = `HOTP #${data.hotp_counter}`;
      }

      if (tg?.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('medium');
      }
      showToast(`Counter #${data.hotp_counter} diperbarui!`, '🔢');
    } catch (err) {
      showToast('Gagal terhubung ke server', '❌');
    }
  }

  // --- Edit Account Modal ---
  function openEditModal(acc) {
    el.editAccountId.value = acc.id;
    el.editInputLabel.value = acc.label;
    el.editInputIssuer.value = acc.issuer || '';
    el.editErrorMsg.classList.add('hidden');
    el.modalEditAccount.classList.add('active');
  }

  function closeEditModal() {
    el.modalEditAccount.classList.remove('active');
  }

  async function submitEditAccount(e) {
    e.preventDefault();
    el.editErrorMsg.classList.add('hidden');

    const id = el.editAccountId.value;
    const label = el.editInputLabel.value.trim();
    const issuer = el.editInputIssuer.value.trim();

    if (!label) {
      el.editErrorMsg.textContent = 'Nama akun tidak boleh kosong.';
      el.editErrorMsg.classList.remove('hidden');
      return;
    }

    try {
      const res = await apiFetch(`/api/accounts/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ label, issuer }),
      });
      const data = await res.json();

      if (!res.ok || !data.success) {
        el.editErrorMsg.textContent = data.error || 'Gagal menyimpan perubahan.';
        el.editErrorMsg.classList.remove('hidden');
        return;
      }

      closeEditModal();
      showToast('Perubahan berhasil disimpan!', '✏️');
      await loadAccounts();
    } catch (err) {
      el.editErrorMsg.textContent = 'Terjadi kesalahan jaringan saat menyimpan.';
      el.editErrorMsg.classList.remove('hidden');
    }
  }

  // --- Settings & Security Modal ---
  function openSettingsModal() {
    switchSettingsTab('tabPin');
    el.formChangePin.reset();
    el.changePinMsg.classList.add('hidden');

    if (el.formExportBackup) el.formExportBackup.reset();
    if (el.exportBackupMsg) el.exportBackupMsg.classList.add('hidden');
    if (el.backupOutputArea) el.backupOutputArea.classList.add('hidden');

    if (el.formImportBackup) el.formImportBackup.reset();
    if (el.importBackupMsg) el.importBackupMsg.classList.add('hidden');
    if (el.fileImportBackup) el.fileImportBackup.value = '';

    el.modalSettings.classList.add('active');
  }

  function closeSettingsModal() {
    el.modalSettings.classList.remove('active');
  }

  function switchSettingsTab(targetTabId) {
    el.settingsTabBtns.forEach(btn => {
      if (btn.dataset.tab === targetTabId) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    el.settingsTabPanes.forEach(pane => {
      if (pane.id === targetTabId) {
        pane.classList.add('active');
      } else {
        pane.classList.remove('active');
      }
    });

    if (targetTabId === 'tabLogs') {
      loadAuditLogs();
    }
  }

  async function submitChangePin(e) {
    e.preventDefault();
    el.changePinMsg.classList.add('hidden');

    const oldPin = el.inputOldPin.value.trim();
    const newPin = el.inputNewPin.value.trim();
    const confirmPin = el.inputConfirmPin.value.trim();

    if (newPin.length !== state.pinLength) {
      el.changePinMsg.textContent = `PIN baru harus terdiri dari ${state.pinLength} digit.`;
      el.changePinMsg.classList.remove('hidden');
      return;
    }

    if (!/^\d+$/.test(newPin)) {
      el.changePinMsg.textContent = 'PIN baru hanya boleh berisi angka (0-9).';
      el.changePinMsg.classList.remove('hidden');
      return;
    }

    if (newPin !== confirmPin) {
      el.changePinMsg.textContent = 'Konfirmasi PIN baru tidak cocok.';
      el.changePinMsg.classList.remove('hidden');
      return;
    }

    try {
      const res = await apiFetch('/api/settings/change_pin', {
        method: 'POST',
        body: JSON.stringify({ old_pin: oldPin, new_pin: newPin }),
      });
      const data = await res.json();

      if (!res.ok || !data.success) {
        el.changePinMsg.textContent = data.error || 'Gagal mengubah PIN.';
        el.changePinMsg.classList.remove('hidden');
        return;
      }

      closeSettingsModal();
      showToast('Master PIN berhasil diperbarui!', '🔐');
    } catch (err) {
      el.changePinMsg.textContent = 'Terjadi kesalahan jaringan saat mengubah PIN.';
      el.changePinMsg.classList.remove('hidden');
    }
  }

  let currentExportFilename = 'telegram_2fa_backup.json';

  async function exportBackup(e) {
    if (e) e.preventDefault();
    if (el.exportBackupMsg) el.exportBackupMsg.classList.add('hidden');

    const passphrase = (el.inputExportPassphrase?.value || '').trim();
    const confirm = (el.inputConfirmExportPassphrase?.value || '').trim();

    if (!passphrase) {
      if (el.exportBackupMsg) {
        el.exportBackupMsg.textContent = 'Masukkan Passphrase Enkripsi Backup.';
        el.exportBackupMsg.classList.remove('hidden');
      }
      el.inputExportPassphrase?.focus();
      return;
    }

    if (passphrase.length < 4) {
      if (el.exportBackupMsg) {
        el.exportBackupMsg.textContent = 'Passphrase enkripsi minimal 4 karakter.';
        el.exportBackupMsg.classList.remove('hidden');
      }
      el.inputExportPassphrase?.focus();
      return;
    }

    if (passphrase !== confirm) {
      if (el.exportBackupMsg) {
        el.exportBackupMsg.textContent = 'Konfirmasi passphrase tidak cocok.';
        el.exportBackupMsg.classList.remove('hidden');
      }
      el.inputConfirmExportPassphrase?.focus();
      return;
    }

    const origBtnText = el.btnExportBackup.textContent;
    el.btnExportBackup.disabled = true;
    el.btnExportBackup.textContent = 'Mengekspor & mengenkripsi...';

    try {
      const res = await apiFetch('/api/settings/backup', {
        method: 'POST',
        body: JSON.stringify({ passphrase }),
      });
      const data = await res.json();

      if (!res.ok || !data.success) {
        if (el.exportBackupMsg) {
          el.exportBackupMsg.textContent = data.error || 'Gagal mengekspor data cadangan.';
          el.exportBackupMsg.classList.remove('hidden');
        }
        return;
      }

      const backupEnvelope = data.backup || data;
      currentExportFilename = data.filename || `telegram_2fa_backup_${Date.now()}.json`;

      el.backupJsonText.value = JSON.stringify(backupEnvelope, null, 2);
      el.backupOutputArea.classList.remove('hidden');

      if (tg?.HapticFeedback) {
        tg.HapticFeedback.notificationOccurred('success');
      }
      showToast('Cadangan terenkripsi berhasil dibuat!', '🔒');
    } catch (err) {
      if (el.exportBackupMsg) {
        el.exportBackupMsg.textContent = 'Terjadi kesalahan jaringan saat mengekspor cadangan.';
        el.exportBackupMsg.classList.remove('hidden');
      }
    } finally {
      el.btnExportBackup.disabled = false;
      el.btnExportBackup.textContent = origBtnText;
    }
  }

  function downloadBackupFile() {
    const val = el.backupJsonText.value;
    if (!val) {
      showToast('Tidak ada data cadangan untuk diunduh', '❌');
      return;
    }

    try {
      const blob = new Blob([val], { type: 'application/json;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = currentExportFilename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      showToast('File cadangan diunduh!', '📥');
    } catch (err) {
      showToast('Gagal mengunduh file cadangan', '❌');
    }
  }

  function copyBackupJson() {
    const val = el.backupJsonText.value;
    if (!val) return;
    navigator.clipboard.writeText(val).then(() => {
      if (tg?.HapticFeedback) {
        tg.HapticFeedback.notificationOccurred('success');
      }
      showToast('Data cadangan disalin ke clipboard!', '📋');
    }).catch(() => {
      showToast('Gagal menyalin data cadangan', '❌');
    });
  }

  async function submitImportBackup(e) {
    if (e) e.preventDefault();
    if (el.importBackupMsg) el.importBackupMsg.classList.add('hidden');
    const rawText = (el.inputImportJson.value || '').trim();
    const passphrase = (el.inputImportPassphrase.value || '').trim();

    if (!rawText) {
      el.importBackupMsg.textContent = 'Pilih file .json atau tempelkan data JSON cadangan terlebih dahulu.';
      el.importBackupMsg.classList.remove('hidden');
      return;
    }

    let parsedPayload;
    try {
      parsedPayload = JSON.parse(rawText);
    } catch (e) {
      el.importBackupMsg.textContent = 'Format JSON tidak valid. Periksa kembali isi file atau teks cadangan Anda.';
      el.importBackupMsg.classList.remove('hidden');
      return;
    }

    if (parsedPayload && typeof parsedPayload === 'object' && parsedPayload.ciphertext) {
      if (!passphrase) {
        el.importBackupMsg.textContent = 'File cadangan terenkripsi. Silakan masukkan Passphrase Dekripsi.';
        el.importBackupMsg.classList.remove('hidden');
        el.inputImportPassphrase.focus();
        return;
      }
    }

    const origBtnText = el.btnSubmitImportBackup.textContent;
    el.btnSubmitImportBackup.disabled = true;
    el.btnSubmitImportBackup.textContent = 'Memulihkan akun...';

    try {
      const res = await apiFetch('/api/settings/import', {
        method: 'POST',
        body: JSON.stringify({
          backup: parsedPayload,
          passphrase: passphrase,
        }),
      });
      const data = await res.json();

      if (!res.ok || !data.success) {
        el.importBackupMsg.textContent = data.error || 'Gagal mengimpor data cadangan.';
        el.importBackupMsg.classList.remove('hidden');
        return;
      }

      el.inputImportJson.value = '';
      el.inputImportPassphrase.value = '';
      if (el.fileImportBackup) el.fileImportBackup.value = '';

      closeSettingsModal();
      if (tg?.HapticFeedback) {
        tg.HapticFeedback.notificationOccurred('success');
      }
      showToast(data.message || `Berhasil mengimpor ${data.imported} akun!`, '📥');
      await loadAccounts();
    } catch (err) {
      el.importBackupMsg.textContent = 'Terjadi kesalahan jaringan saat mengimpor cadangan.';
      el.importBackupMsg.classList.remove('hidden');
    } finally {
      el.btnSubmitImportBackup.disabled = false;
      el.btnSubmitImportBackup.textContent = origBtnText;
    }
  }

  async function loadAuditLogs() {
    el.auditLogsContainer.innerHTML = '<div class="loading-logs">Memuat log...</div>';
    try {
      const res = await apiFetch('/api/settings/logs');
      const data = await res.json();
      if (!res.ok || !data.logs) {
        el.auditLogsContainer.innerHTML = '<div class="loading-logs">Gagal memuat log.</div>';
        return;
      }

      if (data.logs.length === 0) {
        el.auditLogsContainer.innerHTML = '<div class="loading-logs">Belum ada aktivitas tercatat.</div>';
        return;
      }

      el.auditLogsContainer.innerHTML = data.logs.map(log => `
        <div class="audit-log-item">
          <div>
            <span class="log-action-text">${log.success ? '✅' : '❌'} ${escapeHtml(log.action)}</span>
          </div>
          <span class="log-time-text">${escapeHtml(log.timestamp)}</span>
        </div>
      `).join('');
    } catch (err) {
      el.auditLogsContainer.innerHTML = '<div class="loading-logs">Kesalahan koneksi ke server.</div>';
    }
  }

  // --- Attach Event Listeners ---
  function setupEventListeners() {
    // Keypad clicks
    document.querySelectorAll('.keypad-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        handleKeypadPress(btn.dataset.key);
      });
    });

    // Close app button on unregistered screen
    el.btnCloseApp.addEventListener('click', () => {
      if (tg?.close) tg.close();
    });

    // Header actions
    el.btnOpenAddModal.addEventListener('click', openAddModal);
    el.btnEmptyAdd.addEventListener('click', openAddModal);
    el.btnLockApp.addEventListener('click', lockApp);
    el.btnOpenSettingsModal.addEventListener('click', openSettingsModal);

    // Modal Add
    el.btnCloseModal.addEventListener('click', closeAddModal);
    el.btnCancelAdd.addEventListener('click', closeAddModal);
    el.modalBackdrop.addEventListener('click', closeAddModal);
    el.btnScanQrCode.addEventListener('click', scanQrWithTelegram);
    el.formAddAccount.addEventListener('submit', submitAddAccount);

    // Modal Edit
    el.btnCloseEditModal.addEventListener('click', closeEditModal);
    el.btnCancelEdit.addEventListener('click', closeEditModal);
    el.modalEditBackdrop.addEventListener('click', closeEditModal);
    el.formEditAccount.addEventListener('submit', submitEditAccount);

    // Modal Settings
    el.btnCloseSettingsModal.addEventListener('click', closeSettingsModal);
    el.modalSettingsBackdrop.addEventListener('click', closeSettingsModal);
    el.settingsTabBtns.forEach(btn => {
      btn.addEventListener('click', () => switchSettingsTab(btn.dataset.tab));
    });
    el.formChangePin.addEventListener('submit', submitChangePin);

    // Export & Download Backup
    if (el.formExportBackup) {
      el.formExportBackup.addEventListener('submit', exportBackup);
    } else if (el.btnExportBackup) {
      el.btnExportBackup.addEventListener('click', exportBackup);
    }
    if (el.btnDownloadBackupFile) {
      el.btnDownloadBackupFile.addEventListener('click', downloadBackupFile);
    }
    if (el.btnCopyBackupJson) {
      el.btnCopyBackupJson.addEventListener('click', copyBackupJson);
    }

    // Import & File Choose
    if (el.btnChooseBackupFile && el.fileImportBackup) {
      el.btnChooseBackupFile.addEventListener('click', () => {
        el.fileImportBackup.value = '';
        el.fileImportBackup.click();
      });

      el.fileImportBackup.addEventListener('change', (e) => {
        const file = e.target.files && e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
          el.inputImportJson.value = event.target.result;
          if (el.importBackupMsg) el.importBackupMsg.classList.add('hidden');
          showToast(`File "${file.name}" dimuat!`, '📁');
          if (el.inputImportPassphrase) el.inputImportPassphrase.focus();
        };
        reader.onerror = () => {
          showToast('Gagal membaca file cadangan', '❌');
        };
        reader.readAsText(file);
      });
    }

    if (el.formImportBackup) {
      el.formImportBackup.addEventListener('submit', submitImportBackup);
    } else if (el.btnSubmitImportBackup) {
      el.btnSubmitImportBackup.addEventListener('click', submitImportBackup);
    }

    // Search
    el.searchInput.addEventListener('input', (e) => {
      state.searchQuery = e.target.value.trim();
      if (state.searchQuery) {
        el.btnClearSearch.classList.remove('hidden');
      } else {
        el.btnClearSearch.classList.add('hidden');
      }
      renderAccounts();
    });

    el.btnClearSearch.addEventListener('click', () => {
      el.searchInput.value = '';
      state.searchQuery = '';
      el.btnClearSearch.classList.add('hidden');
      renderAccounts();
    });

    // Filter pills
    el.filterPills.forEach(pill => {
      pill.addEventListener('click', () => {
        el.filterPills.forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        state.currentFilter = pill.dataset.filter;
        renderAccounts();
      });
    });
  }

  // Start app
  initTelegram();
  setupEventListeners();
  checkInit();
})();
