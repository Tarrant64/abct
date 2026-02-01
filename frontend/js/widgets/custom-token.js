/**
 * Custom Token Widget
 * Displays a specific token by ticker with price and recent changes
 */

let customTokenInstances = new Map(); // Map widget ID to token data
let customTokenIntervals = new Map();

/**
 * Render custom token widget
 */
async function renderCustomToken(container, widgetId, config = {}) {
    const ticker = config.ticker || null;

    if (!ticker) {
        // Show input form to select token
        container.innerHTML = `
            <div class="custom-token-setup">
                <div class="setup-icon">🪙</div>
                <h3>Add Token to Track</h3>
                <p>Enter any token ticker or name - we'll search CoinGecko if needed!</p>
                <div class="token-input-group">
                    <input type="text"
                           id="tokenTickerInput-${widgetId}"
                           placeholder="Enter ticker..."
                           class="token-ticker-input"
                           onkeypress="if(event.key==='Enter') addCustomToken('${widgetId}')">
                    <button onclick="addCustomToken('${widgetId}')" class="btn btn-primary">
                        Add Token
                    </button>
                </div>
                <div class="token-examples">
                    Examples:
                    <span class="token-example" onclick="setTokenTicker('${widgetId}', 'DOGE')">DOGE</span>
                    <span class="token-example" onclick="setTokenTicker('${widgetId}', 'SHIB')">SHIB</span>
                    <span class="token-example" onclick="setTokenTicker('${widgetId}', 'PEPE')">PEPE</span>
                    <span class="token-example" onclick="setTokenTicker('${widgetId}', 'XRP')">XRP</span>
                </div>
            </div>
        `;
        return { container, widgetId };
    }

    // Show loading state
    container.innerHTML = '<div class="widget-loading"><div class="spinner"></div></div>';

    try {
        const data = await fetchCustomTokenData(ticker);
        updateCustomTokenUI(container, ticker, data);

        // Auto-refresh every 2 minutes
        const interval = setInterval(async () => {
            try {
                const refreshedData = await fetchCustomTokenData(ticker);
                updateCustomTokenUI(container, ticker, refreshedData);
            } catch (error) {
                console.error('Custom token refresh error:', error);
            }
        }, 2 * 60 * 1000);

        customTokenIntervals.set(widgetId, interval);

        return { container, widgetId, ticker, interval };
    } catch (error) {
        console.error('Custom token error:', error);
        container.innerHTML = `
            <div class="widget-error">
                <div class="widget-error-icon">⚠️</div>
                <div>Token "${ticker}" not found</div>
                <p style="font-size: 0.85rem; margin: 0.5rem 0; color: var(--text-secondary);">
                    We searched CoinGecko but couldn't find this token.
                </p>
                <p style="font-size: 0.8rem; margin: 0.5rem 0; color: var(--text-secondary);">
                    Double-check the spelling or try a different ticker/name.
                </p>
                <div style="display: flex; gap: 0.5rem; margin-top: 1rem; flex-wrap: wrap; justify-content: center;">
                    <button onclick="changeCustomToken('${widgetId}')" class="btn btn-primary" style="font-size: 0.85rem; padding: 0.4rem 0.8rem;">
                        Try Different Token
                    </button>
                    <button onclick="removeCustomTokenWidget('${widgetId}')" class="btn btn-danger" style="font-size: 0.85rem; padding: 0.4rem 0.8rem;">
                        Remove Widget
                    </button>
                </div>
            </div>
        `;
        // Don't throw error, just show error UI
        return { container, widgetId, ticker, error: true };
    }
}

/**
 * Fetch custom token data
 */
async function fetchCustomTokenData(ticker) {
    console.log(`[Custom Token Widget] Fetching data for ${ticker}...`);

    // First, try the main price API (for tokens already tracked)
    try {
        const response = await authFetch('/prices/all');
        if (response.ok) {
            const data = await response.json();
            const prices = data.prices || data;

            const tokenData = prices[ticker.toUpperCase()];
            if (tokenData) {
                console.log(`[Custom Token Widget] Found ${ticker} in main price API:`, tokenData);
                return tokenData;
            }
        }
    } catch (error) {
        console.warn('[Custom Token Widget] Main price API failed:', error);
    }

    // Fallback: Search CoinGecko directly for any token
    console.log(`[Custom Token Widget] ${ticker} not in main API, searching CoinGecko...`);
    try {
        const searchResponse = await authFetch(`/prices/search/${encodeURIComponent(ticker)}`);
        if (!searchResponse.ok) {
            console.error('[Custom Token Widget] Search failed:', searchResponse.status, searchResponse.statusText);
            throw new Error('Failed to search for token');
        }

        const searchData = await searchResponse.json();

        if (!searchData.found) {
            console.error(`[Custom Token Widget] Token ${ticker} not found via search`);
            throw new Error(`Token ${ticker} not found`);
        }

        console.log(`[Custom Token Widget] Found ${ticker} via CoinGecko search:`, searchData);

        // Convert search result to price API format
        return {
            usd: searchData.usd,
            usd_1h_change: searchData.usd_1h_change,
            usd_24h_change: searchData.usd_24h_change,
            market_cap: searchData.market_cap,
            name: searchData.name,
            symbol: searchData.symbol
        };

    } catch (error) {
        console.error(`[Custom Token Widget] Failed to find ${ticker}:`, error);
        throw new Error(`Token ${ticker} not available`);
    }
}

/**
 * Update custom token UI
 */
function updateCustomTokenUI(container, ticker, data) {
    const price = data.usd || 0;
    const change1h = data.usd_1h_change || 0;
    const change24h = data.usd_24h_change || 0;
    const marketCap = data.market_cap || 0;

    const change1hClass = change1h >= 0 ? 'positive' : 'negative';
    const change24hClass = change24h >= 0 ? 'positive' : 'negative';

    const html = `
        <div class="custom-token-display">
            <div class="token-header">
                <div class="token-ticker">${ticker.toUpperCase()}</div>
                <button class="token-change-btn" onclick="changeCustomToken('${container.closest('.grid-stack-item')?.getAttribute('data-widget-id')}')" title="Change token">
                    ↻
                </button>
            </div>

            <div class="token-price-main" data-privacy>
                $${formatTokenPrice(price)}
            </div>

            <div class="token-changes">
                <div class="token-change-item">
                    <div class="change-label">1H Change</div>
                    <div class="change-value ${change1hClass}">
                        ${change1h >= 0 ? '+' : ''}${change1h.toFixed(2)}%
                    </div>
                </div>
                <div class="token-change-item">
                    <div class="change-label">24H Change</div>
                    <div class="change-value ${change24hClass}">
                        ${change24h >= 0 ? '+' : ''}${change24h.toFixed(2)}%
                    </div>
                </div>
            </div>

            ${marketCap > 0 ? `
                <div class="token-market-cap">
                    Market Cap: ${formatMarketCapCompact(marketCap)}
                </div>
            ` : ''}
        </div>
    `;

    container.innerHTML = html;

    // Apply privacy mode if enabled
    if (typeof applyPrivacyMode === 'function') {
        applyPrivacyMode();
    }
}

/**
 * Add custom token (called from input)
 */
window.addCustomToken = function(widgetId) {
    const input = document.getElementById(`tokenTickerInput-${widgetId}`);
    const ticker = input?.value?.trim().toUpperCase();

    if (!ticker) {
        alert('Please enter a token ticker');
        return;
    }

    // Update widget config with ticker
    const element = document.querySelector(`[data-widget-id="${widgetId}"]`);
    if (element) {
        element.setAttribute('data-widget-config', JSON.stringify({ ticker }));

        // Re-render widget with ticker
        const bodyEl = document.getElementById(`widget-body-${widgetId}`);
        if (bodyEl) {
            renderCustomToken(bodyEl, widgetId, { ticker });
        }

        // Save layout (will include ticker in config)
        if (typeof saveLayout === 'function') {
            saveLayout();
        }
    }
};

/**
 * Set token ticker (from example buttons)
 */
window.setTokenTicker = function(widgetId, ticker) {
    const input = document.getElementById(`tokenTickerInput-${widgetId}`);
    if (input) {
        input.value = ticker;
        addCustomToken(widgetId);
    }
};

/**
 * Change custom token (show input again)
 */
window.changeCustomToken = function(widgetId) {
    const element = document.querySelector(`[data-widget-id="${widgetId}"]`);
    if (element) {
        element.setAttribute('data-widget-config', JSON.stringify({}));

        const bodyEl = document.getElementById(`widget-body-${widgetId}`);
        if (bodyEl) {
            renderCustomToken(bodyEl, widgetId, {});
        }
    }
};

/**
 * Remove custom token widget
 */
window.removeCustomTokenWidget = function(widgetId) {
    if (typeof removeWidget === 'function') {
        removeWidget(widgetId);
    }
};

/**
 * Refresh custom token
 */
async function refreshCustomToken(instance) {
    if (instance && instance.ticker && instance.container) {
        const data = await fetchCustomTokenData(instance.ticker);
        updateCustomTokenUI(instance.container, instance.ticker, data);
    }
}

/**
 * Destroy custom token widget
 */
function destroyCustomToken(instance) {
    if (instance && instance.widgetId) {
        const interval = customTokenIntervals.get(instance.widgetId);
        if (interval) {
            clearInterval(interval);
            customTokenIntervals.delete(instance.widgetId);
        }
    }
    if (instance && instance.interval) {
        clearInterval(instance.interval);
    }
}

/**
 * Format token price
 */
function formatTokenPrice(price) {
    if (price === null || price === undefined) return '0.00';
    if (price >= 1000) {
        return price.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    } else if (price >= 1) {
        return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    } else if (price >= 0.01) {
        return price.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
    } else {
        return price.toLocaleString('en-US', { minimumFractionDigits: 6, maximumFractionDigits: 8 });
    }
}

/**
 * Format market cap compact
 */
function formatMarketCapCompact(marketCap) {
    if (!marketCap || marketCap === 0) return '';
    let value, suffix;
    if (marketCap >= 1e12) {
        value = (marketCap / 1e12).toFixed(2);
        suffix = 'T';
    } else if (marketCap >= 1e9) {
        value = (marketCap / 1e9).toFixed(2);
        suffix = 'B';
    } else if (marketCap >= 1e6) {
        value = (marketCap / 1e6).toFixed(0);
        suffix = 'M';
    } else {
        value = (marketCap / 1e3).toFixed(0);
        suffix = 'K';
    }
    return `$${value}${suffix}`;
}
