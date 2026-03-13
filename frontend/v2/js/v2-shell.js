/**
 * ABCT V2 Shell — Shared sidebar and topbar component
 * Injected by all V2 pages to avoid HTML duplication.
 */

const V2_NAV = [
    { section: 'Portfolio', items: [
        { id: 'dashboard', label: 'Dashboard', href: '/v2/', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>' },
        { id: 'assets', label: 'Assets', href: '/v2/assets', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v12M6 12h12"/></svg>' },
        { id: 'nfts', label: 'NFTs', href: '/v2/nfts', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>' },
        { id: 'defi', label: 'DeFi & Staking', href: '/v2/defi', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>' },
        { id: 'exchanges', label: 'Exchanges', href: '/v2/exchanges', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3l4 4-4 4"/><path d="M20 7H4"/><path d="M8 21l-4-4 4-4"/><path d="M4 17h16"/></svg>' },
    ]},
    { section: 'Analytics', items: [
        { id: 'analytics', label: 'Analytics', href: '/v2/analytics', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/></svg>' },
        { id: 'transactions', label: 'Transactions', href: '/v2/transactions', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>' },
        { id: 'pnl', label: 'P&L', href: '/v2/pnl', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>' },
        { id: 'security', label: 'Security', href: '/v2/security', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>' },
    ]},
    { section: 'System', items: [
        { id: 'wallets', label: 'Wallets', href: '/v2/wallets', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 12V8H6a2 2 0 01-2-2c0-1.1.9-2 2-2h12v4"/><path d="M4 6v12c0 1.1.9 2 2 2h14v-4"/><circle cx="18" cy="12" r="2"/></svg>' },
        { id: 'settings', label: 'Settings', href: '/v2/settings', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 010 4h-.09c-.658.003-1.25.396-1.51 1z"/></svg>' },
        { id: 'help', label: 'Help', href: '/v2/help', icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>' },
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
            <div class="v2-sidebar-logo" onclick="window.location='/v2/'">
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
                <button class="v2-user-dropdown-item" onclick="window.location='/v2/settings'">Settings</button>
                <button class="v2-user-dropdown-item" onclick="window.location='/v2/help'">Help & Guide</button>
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

// Export for use in page scripts
if (typeof window !== 'undefined') {
    window.v2InitShell = v2InitShell;
    window.V2_NAV = V2_NAV;
    window.V2_THEMES = V2_THEMES;
}
