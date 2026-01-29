/**
 * ABCT Session Authentication Module
 *
 * Provides client-side authentication checking for protected pages.
 * Verifies session tokens and redirects to login if unauthorized.
 *
 * Build: v1769649627
 */

// Authentication state
let authCheckEnabled = true;  // Can be disabled via backend config

/**
 * Check if user is authenticated
 * Verifies token with backend and redirects to login if invalid
 *
 * @returns {Promise<boolean>} True if authenticated, false otherwise
 */
async function checkAuth() {
    // Get token from localStorage
    const token = localStorage.getItem('abct_token');

    if (!token) {
        redirectToLogin();
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
            redirectToLogin();
            return false;
        }

        // Token is valid
        return true;

    } catch (error) {
        console.error('Auth check error:', error);
        // On error, redirect to login for security
        redirectToLogin();
        return false;
    }
}

/**
 * Redirect to login page
 * Preserves current URL as return destination
 */
function redirectToLogin() {
    const currentPath = window.location.pathname + window.location.search;
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
 * Add logout button to navigation
 * Call this after page loads to add logout button to existing nav
 */
function addLogoutButton() {
    const username = getCurrentUsername();
    if (!username) return;

    // Find the header actions container
    const headerActions = document.querySelector('.header-actions');
    if (!headerActions) return;

    // Check if logout button already exists
    if (document.getElementById('logoutBtn')) return;

    // Create logout button
    const logoutBtn = document.createElement('button');
    logoutBtn.id = 'logoutBtn';
    logoutBtn.className = 'btn btn-secondary';
    logoutBtn.textContent = `Logout (${username})`;
    logoutBtn.title = 'Logout from ABCT';
    logoutBtn.onclick = logout;

    // Add to header (before waffle menu)
    const waffleContainer = headerActions.querySelector('.waffle-menu-container');
    if (waffleContainer) {
        headerActions.insertBefore(logoutBtn, waffleContainer);
    } else {
        headerActions.appendChild(logoutBtn);
    }
}

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
        // Add logout button to navigation
        addLogoutButton();
    }

    return isAuthenticated;
}

// Auto-initialize on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAuth);
} else {
    initAuth();
}

// Export functions for use in other scripts
window.checkAuth = checkAuth;
window.logout = logout;
window.getCurrentUsername = getCurrentUsername;
window.addLogoutButton = addLogoutButton;
window.initAuth = initAuth;
