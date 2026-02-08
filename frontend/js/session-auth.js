/**
 * ABCT Session Authentication Module
 *
 * Provides client-side authentication checking for protected pages.
 * Verifies session tokens and redirects to login if unauthorized.
 *
 * Build: v1769920589
 */

// Authentication state
let authCheckEnabled = true;  // Can be disabled via backend config

/**
 * Authenticated fetch wrapper
 * Automatically includes auth token in requests
 * @param {string} url - The URL to fetch
 * @param {Object} options - Fetch options
 * @returns {Promise<Response>} Fetch response
 */
async function authFetch(url, options = {}) {
    const token = localStorage.getItem('abct_token');
    if (token) {
        options.headers = {
            ...options.headers,
            'Authorization': `Bearer ${token}`
        };
    }
    return fetch(url, options);
}

/**
 * Check if user is authenticated
 * Verifies token with backend and redirects to login if invalid
 *
 * @returns {Promise<boolean>} True if authenticated, false otherwise
 */
async function checkAuth(redirectPath) {
    // Get token from localStorage
    const token = localStorage.getItem('abct_token');

    if (!token) {
        redirectToLogin(redirectPath);
        return false;
    }

    try {
        // Verify token with backend
        const response = await fetch('/auth/verify?token=' + encodeURIComponent(token), {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error('Token verification failed');
        }

        const data = await response.json();

        if (!data.valid) {
            // Token is invalid or expired
            localStorage.removeItem('abct_token');
            localStorage.removeItem('abct_username');
            localStorage.removeItem('is_demo');
            redirectToLogin(redirectPath);
            return false;
        }

        // Token is valid
        return true;

    } catch (error) {
        console.error('Auth check error:', error);
        // On error, redirect to login for security
        redirectToLogin(redirectPath);
        return false;
    }
}

/**
 * Redirect to login page
 * Preserves current URL as return destination
 * @param {string} customPath - Optional custom path to redirect after login
 */
function redirectToLogin(customPath) {
    const currentPath = customPath || (window.location.pathname + window.location.search);
    const loginUrl = `/login.html?redirect=${encodeURIComponent(currentPath)}`;
    window.location.href = loginUrl;
}

/**
 * Logout user
 * Clears session and redirects to login
 */
async function logout() {
    const token = localStorage.getItem('abct_token');

    try {
        // Notify backend of logout
        if (token) {
            await fetch('/auth/logout', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ token })
            });
        }
    } catch (error) {
        console.error('Logout error:', error);
    }

    // Clear local storage
    localStorage.removeItem('abct_token');
    localStorage.removeItem('abct_username');
    localStorage.removeItem('is_demo');

    // Redirect to login
    window.location.href = '/login.html?logout=1';
}

/**
 * Get current authenticated username
 *
 * @returns {string|null} Username or null if not authenticated
 */
function getCurrentUsername() {
    return localStorage.getItem('abct_username');
}

/**
 * Check if current user is demo account
 *
 * @returns {boolean} True if demo mode, false otherwise
 */
function isDemoMode() {
    return localStorage.getItem('is_demo') === 'true';
}

/**
 * Initialize user avatar in the new nav header.
 * Populates avatar letter, username, hides change-password in demo mode.
 */
function initUserAvatar() {
    const username = getCurrentUsername();
    if (!username) return;

    // Set avatar letter
    const avatar = document.getElementById('userAvatar');
    if (avatar) {
        avatar.textContent = username.charAt(0).toUpperCase();
    }

    // Set username in dropdown
    const menuName = document.getElementById('userMenuName');
    if (menuName) {
        menuName.textContent = username;
    }

    // Hide change password in demo mode
    if (isDemoMode()) {
        const cpItem = document.getElementById('changePasswordMenuItem');
        if (cpItem) cpItem.style.display = 'none';
    }

    // Sync privacy mode indicator
    syncPrivacyIndicator();
}

/**
 * Toggle user avatar dropdown menu
 */
function toggleUserMenu() {
    const menu = document.getElementById('userMenu');
    if (menu) {
        menu.classList.toggle('active');
    }
}

/**
 * Close user avatar dropdown menu
 */
function closeUserMenu() {
    const menu = document.getElementById('userMenu');
    if (menu) {
        menu.classList.remove('active');
    }
}

/**
 * Sync privacy mode indicator text in avatar dropdown
 */
function syncPrivacyIndicator() {
    const indicator = document.getElementById('privacyIndicator');
    if (indicator) {
        const isEnabled = document.body.classList.contains('privacy-mode');
        indicator.textContent = isEnabled ? 'ON' : 'OFF';
    }
}

// Close user menu when clicking outside
document.addEventListener('click', function(event) {
    const container = document.querySelector('.user-avatar-container');
    if (container && !container.contains(event.target)) {
        closeUserMenu();
    }
});

/**
 * Initialize authentication on page load
 * Call this at the top of your page's JavaScript
 */
async function initAuth() {
    // Check if we're on the login page
    if (window.location.pathname === '/login.html') {
        // If already logged in, redirect to dashboard
        const token = localStorage.getItem('abct_token');
        if (token) {
            try {
                const response = await fetch('/auth/verify?token=' + encodeURIComponent(token));
                const data = await response.json();
                if (data.valid) {
                    window.location.href = '/';
                    return;
                }
            } catch (e) {
                // Ignore errors on login page
            }
        }
        return;  // Don't do auth check on login page
    }

    // For protected pages, check authentication
    const isAuthenticated = await checkAuth();

    if (isAuthenticated) {
        // Initialize user avatar in nav header
        initUserAvatar();

        // Add demo mode banner if in demo mode
        if (isDemoMode()) {
            addDemoBanner();
            applyDemoRestrictions();
        }

        // Password change prompts removed - users can change password via admin menu
    }

    return isAuthenticated;
}

// Auto-initialize on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAuth);
} else {
    initAuth();
}

/**
 * Show change password modal
 */
function showChangePasswordModal() {
    // Create modal if it doesn't exist
    let modal = document.getElementById('changePasswordModal');
    if (!modal) {
        modal = createChangePasswordModal();
        document.body.appendChild(modal);
    }

    // Clear form
    document.getElementById('currentPassword').value = '';
    document.getElementById('newPassword').value = '';
    document.getElementById('confirmPassword').value = '';
    document.getElementById('passwordError').style.display = 'none';

    // Show modal
    modal.style.display = 'flex';
}

/**
 * Close change password modal
 */
function closeChangePasswordModal() {
    const modal = document.getElementById('changePasswordModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

/**
 * Create change password modal
 */
function createChangePasswordModal() {
    const modal = document.createElement('div');
    modal.id = 'changePasswordModal';
    modal.style.cssText = `
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.7);
        z-index: 10000;
        align-items: center;
        justify-content: center;
    `;

    const modalContent = document.createElement('div');
    modalContent.style.cssText = `
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 30px;
        max-width: 450px;
        width: 90%;
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    `;

    modalContent.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: var(--text-primary);">Change Password</h2>
        <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 20px;">
            Please change your password from the default for security.
        </p>

        <div id="passwordError" style="display: none; background: rgba(255,107,107,0.1); border: 1px solid var(--accent-error); border-radius: 6px; padding: 12px; margin-bottom: 15px; color: var(--accent-error); font-size: 14px;"></div>

        <div style="margin-bottom: 15px;">
            <label style="display: block; color: var(--text-primary); font-size: 14px; margin-bottom: 5px;">Current Password</label>
            <input type="password" id="currentPassword" style="width: 100%; padding: 10px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-primary); font-size: 14px;">
        </div>

        <div style="margin-bottom: 15px;">
            <label style="display: block; color: var(--text-primary); font-size: 14px; margin-bottom: 5px;">New Password (min 8 characters)</label>
            <input type="password" id="newPassword" style="width: 100%; padding: 10px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-primary); font-size: 14px;">
        </div>

        <div style="margin-bottom: 20px;">
            <label style="display: block; color: var(--text-primary); font-size: 14px; margin-bottom: 5px;">Confirm New Password</label>
            <input type="password" id="confirmPassword" style="width: 100%; padding: 10px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-primary); font-size: 14px;">
        </div>

        <div style="display: flex; gap: 10px; justify-content: flex-end;">
            <button onclick="window.closeChangePasswordModal()" style="padding: 10px 20px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-primary); cursor: pointer; font-size: 14px;">Cancel</button>
            <button onclick="window.submitPasswordChange()" style="padding: 10px 20px; background: var(--accent-success); border: none; border-radius: 6px; color: white; cursor: pointer; font-size: 14px; font-weight: 600;">Change Password</button>
        </div>
    `;

    modal.appendChild(modalContent);

    // Close on background click
    modal.onclick = (e) => {
        if (e.target === modal) {
            closeChangePasswordModal();
        }
    };

    return modal;
}

/**
 * Submit password change
 */
async function submitPasswordChange() {
    const currentPassword = document.getElementById('currentPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    const errorDiv = document.getElementById('passwordError');

    // Validation
    if (!currentPassword || !newPassword || !confirmPassword) {
        errorDiv.textContent = 'All fields are required';
        errorDiv.style.display = 'block';
        return;
    }

    if (newPassword.length < 8) {
        errorDiv.textContent = 'New password must be at least 8 characters';
        errorDiv.style.display = 'block';
        return;
    }

    if (newPassword !== confirmPassword) {
        errorDiv.textContent = 'New passwords do not match';
        errorDiv.style.display = 'block';
        return;
    }

    if (newPassword === currentPassword) {
        errorDiv.textContent = 'New password must be different from current password';
        errorDiv.style.display = 'block';
        return;
    }

    try {
        const token = localStorage.getItem('abct_token');
        const response = await fetch('/auth/change-password', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword
            })
        });

        const data = await response.json();

        if (!response.ok) {
            errorDiv.textContent = data.detail || 'Password change failed';
            errorDiv.style.display = 'block';
            return;
        }

        // Success
        alert('Password changed successfully! You can now use your new password to login.');
        closeChangePasswordModal();

    } catch (error) {
        console.error('Password change error:', error);
        errorDiv.textContent = 'Connection error. Please try again.';
        errorDiv.style.display = 'block';
    }
}

/**
 * Add demo mode banner to page
 */
function addDemoBanner() {
    // Check if banner already exists
    if (document.getElementById('demoBanner')) return;

    const banner = document.createElement('div');
    banner.id = 'demoBanner';
    banner.style.cssText = `
        position: sticky;
        top: 0;
        left: 0;
        right: 0;
        background: rgba(217, 119, 6, 0.15);
        color: #d97706;
        padding: 4px 16px;
        text-align: center;
        font-weight: 500;
        font-size: 11px;
        z-index: 999;
        letter-spacing: 0.5px;
        border-bottom: 1px solid rgba(217, 119, 6, 0.2);
    `;
    banner.innerHTML = `DEMO MODE - Simulated data`;

    // Insert at the very top of the body
    document.body.insertBefore(banner, document.body.firstChild);
}

/**
 * Apply demo mode restrictions to the page
 */
function applyDemoRestrictions() {
    // Wait for DOM to be ready
    setTimeout(() => {
        // Disable all "Add" and modification buttons
        const buttons = document.querySelectorAll('button, a, input[type="submit"]');
        buttons.forEach(btn => {
            const text = btn.textContent.toLowerCase();
            const id = btn.id ? btn.id.toLowerCase() : '';
            const classList = btn.className ? btn.className.toLowerCase() : '';

            // Check if this is a button that should be disabled in demo mode
            const shouldDisable =
                text.includes('add wallet') || text.includes('add exchange') ||
                text.includes('add token') || text.includes('add api') ||
                text.includes('create backup') || text.includes('restore') ||
                text.includes('import') || text.includes('export backup') ||
                text.includes('save') && (classList.includes('btn') || btn.type === 'submit') ||
                text.includes('delete') || text.includes('remove') ||
                text.includes('update') && (classList.includes('btn') || btn.type === 'submit') ||
                id.includes('addwallet') || id.includes('addexchange') ||
                id.includes('saveapi') || id.includes('deleteapi') ||
                classList.includes('btn-add') || classList.includes('btn-save') ||
                classList.includes('btn-delete');

            if (shouldDisable) {
                btn.disabled = true;
                btn.style.opacity = '0.5';
                btn.style.cursor = 'not-allowed';
                btn.title = 'Disabled in demo mode - This is simulated data';

                // Add click handler to show message
                const handleClick = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    showDemoModeAlert();
                    return false;
                };

                // Remove existing listeners and add new one
                btn.onclick = handleClick;
                btn.addEventListener('click', handleClick, true);
            }
        });

        // Make form inputs readonly in certain contexts (but not search/filter)
        const inputs = document.querySelectorAll('input[type="text"], input[type="password"], textarea, input[type="number"]');
        inputs.forEach(input => {
            const placeholder = input.placeholder ? input.placeholder.toLowerCase() : '';
            const id = input.id ? input.id.toLowerCase() : '';

            // Don't disable search/filter inputs
            if (placeholder.includes('search') || placeholder.includes('filter') ||
                id.includes('search') || id.includes('filter')) {
                return;
            }

            // Make inputs in forms readonly (for editing)
            const parentForm = input.closest('form');
            const parentModal = input.closest('.modal');

            if (parentForm || parentModal) {
                input.readOnly = true;
                input.style.opacity = '0.7';
                input.style.cursor = 'not-allowed';
                input.title = 'Read-only in demo mode';

                // Add click handler
                input.addEventListener('click', (e) => {
                    showDemoModeAlert();
                });
            }
        });

        // Add demo tooltips to data displays
        const dataElements = document.querySelectorAll('.balance, .wallet-card, .exchange-card, .summary-card');
        dataElements.forEach(elem => {
            if (!elem.title || elem.title === '') {
                elem.title = 'This is simulated data for demonstration purposes';
            }
        });

        // Check if we're on backup page and add specific notice
        if (window.location.pathname.includes('backup.html')) {
            addBackupDemoNotice();
        }

        // Check if we're on security page
        if (window.location.pathname.includes('security.html')) {
            addSecurityDemoNotice();
        }
    }, 500);
}

/**
 * Show demo mode alert
 */
function showDemoModeAlert() {
    alert('This feature is disabled in demo mode.\n\nAll data shown is simulated for demonstration purposes.');
}

/**
 * Add demo notice to backup page
 */
function addBackupDemoNotice() {
    const backupManager = document.querySelector('.backup-manager');
    if (!backupManager || document.getElementById('demoBackupNotice')) return;

    const notice = document.createElement('div');
    notice.id = 'demoBackupNotice';
    notice.style.cssText = `
        background: rgba(245, 158, 11, 0.15);
        border: 2px solid #f59e0b;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 25px;
        color: #f59e0b;
    `;
    notice.innerHTML = `
        <h3 style="margin: 0 0 10px 0; font-size: 16px;">
            <span style="font-size: 20px;">🎭</span> Demo Mode - Backup Disabled
        </h3>
        <p style="margin: 0; font-size: 14px; color: #888;">
            Backup and restore features are disabled in demo mode.
            This account uses simulated data for demonstration purposes.
        </p>
    `;

    // Insert after header
    const header = backupManager.querySelector('.backup-header');
    if (header) {
        header.parentNode.insertBefore(notice, header.nextSibling);
    }
}

/**
 * Add demo notice to security page
 */
function addSecurityDemoNotice() {
    const securityManager = document.querySelector('.security-manager');
    if (!securityManager || document.getElementById('demoSecurityNotice')) return;

    const notice = document.createElement('div');
    notice.id = 'demoSecurityNotice';
    notice.style.cssText = `
        background: rgba(245, 158, 11, 0.15);
        border: 2px solid #f59e0b;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 25px;
        color: #f59e0b;
    `;
    notice.innerHTML = `
        <h3 style="margin: 0 0 10px 0; font-size: 16px;">
            <span style="font-size: 20px;">🎭</span> Demo Mode - Settings Read-Only
        </h3>
        <p style="margin: 0; font-size: 14px; color: #888;">
            Security settings cannot be modified in demo mode.
            This account uses default demonstration settings.
        </p>
    `;

    // Insert after header
    const header = securityManager.querySelector('.security-header');
    if (header) {
        header.parentNode.insertBefore(notice, header.nextSibling);
    }
}

// Export functions for use in other scripts
window.authFetch = authFetch;
window.checkAuth = checkAuth;
window.logout = logout;
window.getCurrentUsername = getCurrentUsername;
window.isDemoMode = isDemoMode;
window.initUserAvatar = initUserAvatar;
window.toggleUserMenu = toggleUserMenu;
window.closeUserMenu = closeUserMenu;
window.syncPrivacyIndicator = syncPrivacyIndicator;
window.initAuth = initAuth;
window.showChangePasswordModal = showChangePasswordModal;
window.closeChangePasswordModal = closeChangePasswordModal;
window.submitPasswordChange = submitPasswordChange;
window.addDemoBanner = addDemoBanner;
window.applyDemoRestrictions = applyDemoRestrictions;
window.showDemoModeAlert = showDemoModeAlert;
