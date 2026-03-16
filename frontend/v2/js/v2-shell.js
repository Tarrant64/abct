/**
 * ABCT V2 Shell — Shared sidebar and topbar component
 * Injected by all V2 pages to avoid HTML duplication.
 */

const V2_NAV = [
    { section: 'Portfolio', items: [
        { id: 'dashboard', label: 'Dashboard', href: '/next/', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>' },
        { id: 'assets', label: 'Assets', href: '/next/assets', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v12M6 12h12"/></svg>' },
        { id: 'nfts', label: 'NFTs', href: '/next/nfts', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>' },
        { id: 'defi', label: 'DeFi & Staking', href: '/next/defi', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>' },
        { id: 'exchanges', label: 'Exchanges', href: '/next/exchanges', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3l4 4-4 4"/><path d="M20 7H4"/><path d="M8 21l-4-4 4-4"/><path d="M4 17h16"/></svg>' },
    ]},
    { section: 'Analytics', items: [
        { id: 'analytics', label: 'Analytics', href: '/next/analytics', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/></svg>' },
        { id: 'transactions', label: 'Transactions', href: '/next/transactions', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>' },
        { id: 'pnl', label: 'P&L', href: '/next/pnl', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>' },
        { id: 'security', label: 'Security', href: '/next/security', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>' },
    ]},
    { section: 'System', items: [
        { id: 'wallets', label: 'Wallets', href: '/next/wallets', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 12V8H6a2 2 0 01-2-2c0-1.1.9-2 2-2h12v4"/><path d="M4 6v12c0 1.1.9 2 2 2h14v-4"/><circle cx="18" cy="12" r="2"/></svg>' },
        { id: 'settings', label: 'Settings', href: '/next/settings', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 010 4h-.09c-.658.003-1.25.396-1.51 1z"/></svg>' },
        { id: 'help', label: 'Help', href: '/next/help', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>' },
    ]},
];

const V2_THEMES = [
    { value: 'dark-mode', label: 'Dark Mode' },
    { value: 'light', label: 'Light' },
    { value: 'cypherpunk1', label: 'Cypherpunk' },
    { value: 'ocean-depths', label: 'Ocean Depths' },
    { value: 'sunset-horizon', label: 'Sunset Horizon' },
    { value: 'cypher', label: 'Cypher' },
    { value: 'cypher2', label: 'Cypher 2' },
    { value: 'cypher3', label: 'Cypher 3' },
];

/**
 * Build and inject the V2 sidebar into the page.
 * Call this from pages that use the shared shell.
 * @param {string} activePage - The data-page id to mark as active
 */
function v2InitShell(activePage) {
    // Build sidebar HTML
    const currentPath = window.location.pathname;

    let navHtml = '';
    V2_NAV.forEach(section => {
        navHtml += `<div class="v2-nav-section"><div class="v2-nav-label">${section.section}</div>`;
        section.items.forEach(item => {
            const isActive = item.id === activePage;
            navHtml += `<a href="${item.href}" class="v2-nav-item${isActive ? ' active' : ''}" data-page="${item.id}">
                <span class="v2-nav-icon">${item.icon}</span>
                <span class="nav-text">${item.label}</span>
            </a>`;
        });
        navHtml += '</div>';
    });

    // Theme options
    let themeOptions = V2_THEMES.map(t => `<option value="${t.value}">${t.label}</option>`).join('');

    // Inject sidebar
    const sidebarEl = document.getElementById('v2Sidebar');
    if (sidebarEl) {
        setSafeHTML(sidebarEl, `
            <div class="v2-sidebar-logo" onclick="window.location='/next/'">
                <img class="logo-icon" src="/static/abct-logo2.png" alt="ABCT" width="36" height="36">
                <span class="logo-text">ABCT</span>
            </div>
            <div class="v2-nav">${navHtml}</div>
            <div class="v2-sidebar-footer">
                <a href="/" class="v2-v1-link">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                    <span class="nav-text">Classic View</span>
                </a>
                <button class="v2-sidebar-collapse-btn" onclick="toggleSidebar()">
                    <span class="collapse-arrow"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 17l-5-5 5-5M18 17l-5-5 5-5"/></svg></span>
                    <span class="nav-text">Collapse</span>
                </button>
            </div>
        `);
    }

    // Inject user dropdown in topbar
    const userMenu = document.querySelector('.v2-user-menu');
    if (userMenu && !document.getElementById('userDropdown')) {
        setSafeHTML(userMenu, `
            <div class="v2-avatar" onclick="toggleUserMenu()">?</div>
            <div class="v2-user-dropdown" id="userDropdown">
                <div class="v2-user-dropdown-header" id="userDropdownName">User</div>
                <div class="v2-user-dropdown-divider"></div>
                <div class="v2-user-dropdown-theme">
                    <span>Theme</span>
                    <select id="v2ThemeSelect" onchange="changeTheme(this.value)">${themeOptions}</select>
                </div>
                <div class="v2-user-dropdown-divider"></div>
                <button class="v2-user-dropdown-item" onclick="window.location='/next/settings'">Settings</button>
                <button class="v2-user-dropdown-item" onclick="window.location='/next/help'">Help & Guide</button>
                <button class="v2-user-dropdown-item" onclick="openChangePasswordModal()">Change Password</button>
                <div class="v2-user-dropdown-divider"></div>
                <button class="v2-user-dropdown-item logout" onclick="logout()">Logout</button>
            </div>
        `);
    }

    // Apply saved state
    loadSavedTheme();
    if (localStorage.getItem('v2_sidebar_collapsed') === 'true') {
        document.getElementById('v2Sidebar').classList.add('collapsed');
        document.getElementById('v2Layout').classList.add('sidebar-collapsed');
    }

    // Add toast container if not present
    if (!document.getElementById('toastContainer')) {
        const tc = document.createElement('div');
        tc.className = 'v2-toast-container';
        tc.id = 'toastContainer';
        document.body.appendChild(tc);
    }

    // Close user menu on outside click
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.v2-user-menu')) {
            const d = document.getElementById('userDropdown');
            if (d) d.classList.remove('open');
        }
    });
}

// ============================================================================
// CHANGE PASSWORD MODAL
// ============================================================================

function openChangePasswordModal() {
    // Close user menu
    var dd = document.getElementById('userDropdown');
    if (dd) dd.classList.remove('open');

    // Create modal if not present
    if (!document.getElementById('changePwOverlay')) {
        var overlay = document.createElement('div');
        overlay.id = 'changePwOverlay';
        overlay.className = 'v2-modal-overlay';
        overlay.addEventListener('click', closeChangePasswordModal);
        document.body.appendChild(overlay);

        var modal = document.createElement('div');
        modal.id = 'changePwModal';
        modal.className = 'v2-modal';
        modal.style.maxWidth = '420px';
        modal.innerHTML = '<div class="v2-modal-header"><span class="v2-modal-title">Change Password</span><button class="v2-modal-close" id="changePwClose">&times;</button></div>' +
            '<div class="v2-modal-body" style="padding:20px;">' +
            '<div id="changePwError" style="display:none;background:rgba(255,82,82,0.1);border:1px solid rgba(255,82,82,0.3);border-radius:8px;color:var(--v2-red,#ff5252);padding:10px;font-size:13px;text-align:center;margin-bottom:12px;"></div>' +
            '<div id="changePwSuccess" style="display:none;background:rgba(0,210,106,0.1);border:1px solid rgba(0,210,106,0.3);border-radius:8px;color:var(--v2-accent);padding:10px;font-size:13px;text-align:center;margin-bottom:12px;"></div>' +
            '<div style="display:flex;flex-direction:column;gap:14px;">' +
            '<div><label style="display:block;font-size:12px;color:var(--v2-text-secondary);margin-bottom:4px;">Current Password</label><input type="password" id="cpwCurrent" style="width:100%;background:var(--v2-bg-input);border:1px solid var(--v2-border-input);border-radius:8px;color:var(--v2-text-primary);padding:10px 14px;font-size:14px;outline:none;box-sizing:border-box;" autocomplete="current-password"></div>' +
            '<div><label style="display:block;font-size:12px;color:var(--v2-text-secondary);margin-bottom:4px;">New Password</label><input type="password" id="cpwNew" style="width:100%;background:var(--v2-bg-input);border:1px solid var(--v2-border-input);border-radius:8px;color:var(--v2-text-primary);padding:10px 14px;font-size:14px;outline:none;box-sizing:border-box;" autocomplete="new-password"></div>' +
            '<div><label style="display:block;font-size:12px;color:var(--v2-text-secondary);margin-bottom:4px;">Confirm New Password</label><input type="password" id="cpwConfirm" style="width:100%;background:var(--v2-bg-input);border:1px solid var(--v2-border-input);border-radius:8px;color:var(--v2-text-primary);padding:10px 14px;font-size:14px;outline:none;box-sizing:border-box;" autocomplete="new-password"></div>' +
            '<button id="cpwSubmitBtn" style="background:var(--v2-accent);color:var(--v2-bg-base);border:none;border-radius:8px;padding:12px;font-size:14px;font-weight:600;cursor:pointer;">Change Password</button>' +
            '</div></div>';
        document.body.appendChild(modal);

        document.getElementById('changePwClose').addEventListener('click', closeChangePasswordModal);
        document.getElementById('cpwSubmitBtn').addEventListener('click', submitChangePassword);
    }

    // Reset fields
    document.getElementById('cpwCurrent').value = '';
    document.getElementById('cpwNew').value = '';
    document.getElementById('cpwConfirm').value = '';
    document.getElementById('changePwError').style.display = 'none';
    document.getElementById('changePwSuccess').style.display = 'none';

    document.getElementById('changePwOverlay').classList.add('open');
    document.getElementById('changePwModal').classList.add('open');
}

function closeChangePasswordModal() {
    var overlay = document.getElementById('changePwOverlay');
    var modal = document.getElementById('changePwModal');
    if (overlay) overlay.classList.remove('open');
    if (modal) modal.classList.remove('open');
}

async function submitChangePassword() {
    var errEl = document.getElementById('changePwError');
    var successEl = document.getElementById('changePwSuccess');
    var btn = document.getElementById('cpwSubmitBtn');
    errEl.style.display = 'none';
    successEl.style.display = 'none';

    var current = document.getElementById('cpwCurrent').value;
    var newPw = document.getElementById('cpwNew').value;
    var confirm = document.getElementById('cpwConfirm').value;

    if (!current || !newPw || !confirm) {
        errEl.textContent = 'All fields are required';
        errEl.style.display = 'block';
        return;
    }
    if (newPw.length < 8) {
        errEl.textContent = 'New password must be at least 8 characters';
        errEl.style.display = 'block';
        return;
    }
    if (newPw !== confirm) {
        errEl.textContent = 'New passwords do not match';
        errEl.style.display = 'block';
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Changing...';

    try {
        var token = localStorage.getItem('abct_token');
        var resp = await fetch('/auth/change-password', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token
            },
            body: JSON.stringify({ current_password: current, new_password: newPw })
        });
        var data = await resp.json();

        if (resp.ok && data.success) {
            successEl.textContent = 'Password changed successfully';
            successEl.style.display = 'block';
            setTimeout(closeChangePasswordModal, 1500);
        } else {
            errEl.textContent = data.detail || data.message || 'Failed to change password';
            errEl.style.display = 'block';
        }
    } catch(e) {
        errEl.textContent = 'Connection error';
        errEl.style.display = 'block';
    }

    btn.disabled = false;
    btn.textContent = 'Change Password';
}

// Export for use in page scripts
if (typeof window !== 'undefined') {
    window.v2InitShell = v2InitShell;
    window.V2_NAV = V2_NAV;
    window.V2_THEMES = V2_THEMES;
    window.openChangePasswordModal = openChangePasswordModal;
    window.closeChangePasswordModal = closeChangePasswordModal;
}
