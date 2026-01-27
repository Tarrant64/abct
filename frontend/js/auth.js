/**
 * Authentication Helper for ABCT Frontend
 *
 * Handles HTTP Basic Auth for protected endpoints:
 * - Prompts for credentials on 401 responses
 * - Stores credentials in memory (session)
 * - Adds Authorization header to requests
 */

class AuthHelper {
    constructor() {
        this.credentials = null;
    }

    /**
     * Prompt user for admin credentials
     * @returns {Promise<Object>} Credentials object with username and password
     */
    async promptForCredentials() {
        return new Promise((resolve) => {
            const username = prompt('Admin username:');
            if (!username) {
                resolve(null);
                return;
            }

            const password = prompt('Admin password:');
            if (!password) {
                resolve(null);
                return;
            }

            resolve({ username, password });
        });
    }

    /**
     * Encode credentials to Base64 for Basic Auth
     * @param {string} username
     * @param {string} password
     * @returns {string} Base64 encoded credentials
     */
    encodeCredentials(username, password) {
        return btoa(`${username}:${password}`);
    }

    /**
     * Store credentials in memory
     * @param {Object} credentials
     */
    setCredentials(credentials) {
        this.credentials = credentials;
    }

    /**
     * Clear stored credentials
     */
    clearCredentials() {
        this.credentials = null;
    }

    /**
     * Get Authorization header value
     * @returns {string|null} Authorization header value or null
     */
    getAuthHeader() {
        if (!this.credentials) {
            return null;
        }
        return `Basic ${this.encodeCredentials(this.credentials.username, this.credentials.password)}`;
    }

    /**
     * Enhanced fetch that handles 401 responses
     * @param {string} url
     * @param {Object} options
     * @returns {Promise<Response>}
     */
    async fetch(url, options = {}) {
        // Add auth header if we have credentials
        const authHeader = this.getAuthHeader();
        if (authHeader) {
            options.headers = {
                ...options.headers,
                'Authorization': authHeader
            };
        }

        let response = await fetch(url, options);

        // If 401, prompt for credentials and retry
        if (response.status === 401) {
            const credentials = await this.promptForCredentials();

            if (!credentials) {
                // User cancelled, return the 401 response
                return response;
            }

            // Store credentials and retry request
            this.setCredentials(credentials);

            const authHeader = this.getAuthHeader();
            options.headers = {
                ...options.headers,
                'Authorization': authHeader
            };

            response = await fetch(url, options);

            // If still 401, credentials were wrong
            if (response.status === 401) {
                this.clearCredentials();
                alert('Invalid credentials. Please try again.');
            }
        }

        return response;
    }

    /**
     * Check if authentication is required (for testing)
     * @returns {Promise<boolean>}
     */
    async isAuthRequired() {
        try {
            // Try a protected endpoint without credentials
            const response = await fetch('/api/settings/apis', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ test: true })
            });

            // If we get 401 or 503, auth is required
            return response.status === 401 || response.status === 503;
        } catch (error) {
            return false;
        }
    }
}

// Create singleton instance
const authHelper = new AuthHelper();

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = authHelper;
}
