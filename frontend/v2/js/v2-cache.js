/**
 * ABCT V2 API Cache — Client-side response caching with configurable TTL
 *
 * Provides:
 *   - In-memory response cache with per-endpoint TTL
 *   - v2CachedFetch() wrapper around v2Fetch() that checks cache first
 *   - Prefetch support for preloading data on hover/navigation
 *   - Cache invalidation on sync/refresh actions
 *   - Deduplication of in-flight requests (no double fetches)
 */

// ============================================================================
// CACHE STORE
// ============================================================================

const V2_CACHE = {
    _store: new Map(),       // key -> { data, timestamp, response }
    _inflight: new Map(),    // key -> Promise (dedup in-flight requests)

    // TTL configuration (milliseconds) — matched to data freshness needs
    TTL: {
        '/prices/all':              30 * 1000,   // 30 seconds — prices change fast
        '/prices/global':           60 * 1000,   // 1 minute
        '/prices/top-movers':       60 * 1000,   // 1 minute
        '/portfolio/instant':       30 * 1000,   // 30 seconds
        '/portfolio/all-holdings':  60 * 1000,   // 1 minute
        '/portfolio/summary':       60 * 1000,   // 1 minute
        '/portfolio/assets':        60 * 1000,   // 1 minute
        '/wallets':                120 * 1000,   // 2 minutes — wallets rarely change
        '/exchanges/all':           60 * 1000,   // 1 minute
        '/exchanges/coinbase':      60 * 1000,   // 1 minute
        '/defi/summary':            60 * 1000,   // 1 minute
        '/nfts/all/summary':       120 * 1000,   // 2 minutes
        '/transactions/stats':      60 * 1000,   // 1 minute
        '/balance-history/data':    60 * 1000,   // 1 minute
        '/custom-tokens':          120 * 1000,   // 2 minutes
        '/spam/status':            120 * 1000,   // 2 minutes
        '/search':                  10 * 1000,   // 10 seconds — search results are contextual
        '_default':                 30 * 1000,   // Default 30s for unlisted endpoints
    },

    /**
     * Get a cached entry if it exists and is still fresh.
     * @param {string} key - Cache key (URL + params)
     * @returns {object|null} - Cached data or null if expired/missing
     */
    get(key) {
        const entry = this._store.get(key);
        if (!entry) return null;

        const ttl = this._getTTL(key);
        if (Date.now() - entry.timestamp > ttl) {
            this._store.delete(key);
            return null;
        }
        return entry.data;
    },

    /**
     * Store a response in cache.
     * @param {string} key - Cache key
     * @param {*} data - Parsed JSON response data
     */
    set(key, data) {
        this._store.set(key, {
            data: data,
            timestamp: Date.now(),
        });
    },

    /**
     * Get TTL for a given cache key.
     * Matches the URL path portion against configured TTLs.
     */
    _getTTL(key) {
        // Strip query params for matching
        const path = key.split('?')[0];
        if (this.TTL[path] !== undefined) return this.TTL[path];
        // Try partial match (e.g., /wallets/xxx/governance matches /wallets)
        for (const pattern of Object.keys(this.TTL)) {
            if (pattern !== '_default' && path.startsWith(pattern)) {
                return this.TTL[pattern];
            }
        }
        return this.TTL['_default'];
    },

    /**
     * Clear specific cache entries by URL prefix.
     * @param {string} prefix - URL prefix to match (e.g., '/prices' clears all price entries)
     */
    clearByPrefix(prefix) {
        for (const key of this._store.keys()) {
            if (key.startsWith(prefix) || key.split('?')[0].startsWith(prefix)) {
                this._store.delete(key);
            }
        }
    },

    /**
     * Clear ALL cache entries. Used on Sync All / manual refresh.
     */
    clearAll() {
        this._store.clear();
        this._inflight.clear();
    },

    /**
     * Get the number of cached entries (for debugging).
     */
    get size() {
        return this._store.size;
    },
};


// ============================================================================
// CACHED FETCH WRAPPER
// ============================================================================

/**
 * Fetch with caching. Checks cache first, returns cached data if fresh.
 * Deduplicates in-flight requests to the same URL.
 *
 * @param {string} url - API endpoint URL
 * @param {object} options - Fetch options (method, headers, body, etc.)
 * @param {object} cacheOptions - Cache control options
 * @param {boolean} cacheOptions.skipCache - Force bypass cache (e.g., for refresh=true)
 * @param {number} cacheOptions.ttl - Override TTL for this specific request
 * @returns {Promise<{data: *, fromCache: boolean}>} - Parsed JSON data and cache status
 */
async function v2CachedFetch(url, options, cacheOptions) {
    options = options || {};
    cacheOptions = cacheOptions || {};

    // Only cache GET requests (no body, no method or GET method)
    const method = (options.method || 'GET').toUpperCase();
    if (method !== 'GET') {
        const response = await v2Fetch(url, options);
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        return { data: data, fromCache: false };
    }

    // Build cache key from URL
    var cacheKey = url;

    // Check cache first (unless skipCache)
    if (!cacheOptions.skipCache) {
        var cached = V2_CACHE.get(cacheKey);
        if (cached !== null) {
            return { data: cached, fromCache: true };
        }
    }

    // Deduplicate in-flight requests
    if (V2_CACHE._inflight.has(cacheKey)) {
        var result = await V2_CACHE._inflight.get(cacheKey);
        return { data: result, fromCache: false };
    }

    // Make the request
    var fetchPromise = (async function() {
        try {
            var response = await v2Fetch(url, options);
            if (!response.ok) throw new Error('HTTP ' + response.status);
            var data = await response.json();
            // Store in cache
            V2_CACHE.set(cacheKey, data);
            return data;
        } finally {
            V2_CACHE._inflight.delete(cacheKey);
        }
    })();

    V2_CACHE._inflight.set(cacheKey, fetchPromise);

    var data = await fetchPromise;
    return { data: data, fromCache: false };
}


// ============================================================================
// PREFETCH — Preload common data on nav hover
// ============================================================================

/**
 * Prefetch commonly-needed data endpoints. Called on sidebar hover
 * or proactively from the dashboard. Non-blocking, fire-and-forget.
 */
function v2PrefetchCommon() {
    var endpoints = ['/prices/all', '/wallets', '/portfolio/all-holdings'];

    endpoints.forEach(function(url) {
        // Only prefetch if not already cached
        if (V2_CACHE.get(url) === null && !V2_CACHE._inflight.has(url)) {
            v2CachedFetch(url).catch(function() {
                // Silently ignore prefetch errors
            });
        }
    });
}

/**
 * Prefetch data specific to a target page. Called on nav link hover.
 * @param {string} pageId - The page identifier (e.g., 'assets', 'defi', 'nfts')
 */
function v2PrefetchForPage(pageId) {
    var endpoints = [];

    switch (pageId) {
        case 'assets':
            endpoints = ['/prices/all', '/wallets', '/exchanges/all', '/defi/summary', '/custom-tokens'];
            break;
        case 'defi':
            endpoints = ['/prices/all', '/wallets', '/defi/summary', '/portfolio/all-holdings', '/portfolio/instant'];
            break;
        case 'nfts':
            endpoints = ['/nfts/all/summary'];
            break;
        case 'exchanges':
            endpoints = ['/exchanges/all'];
            break;
        case 'analytics':
            endpoints = ['/prices/global', '/prices/top-movers', '/portfolio/all-holdings'];
            break;
        case 'transactions':
            endpoints = ['/transactions/stats?days=90', '/transactions/stats?days=7'];
            break;
        case 'wallets':
            endpoints = ['/wallets'];
            break;
        case 'dashboard':
            endpoints = ['/prices/all', '/portfolio/instant', '/balance-history/data?range=1w', '/transactions/stats?days=7', '/exchanges/all', '/nfts/all/summary'];
            break;
        case 'pnl':
            endpoints = ['/pnl/summary', '/pnl/unrealized'];
            break;
        case 'security':
            endpoints = ['/spam/status', '/privacy/approvals/wallets', '/privacy/wallets/summary'];
            break;
    }

    endpoints.forEach(function(url) {
        if (V2_CACHE.get(url) === null && !V2_CACHE._inflight.has(url)) {
            v2CachedFetch(url).catch(function() {
                // Silently ignore prefetch errors
            });
        }
    });
}


// ============================================================================
// EXPORTS
// ============================================================================

if (typeof window !== 'undefined') {
    window.V2_CACHE = V2_CACHE;
    window.v2CachedFetch = v2CachedFetch;
    window.v2PrefetchCommon = v2PrefetchCommon;
    window.v2PrefetchForPage = v2PrefetchForPage;
}
