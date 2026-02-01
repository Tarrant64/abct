/**
 * Blockchain Prices Widget
 * Displays live prices for major blockchains (ADA, BTC, ETH, SOL, MATIC)
 */

let blockchainPricesCache = null;
let blockchainPricesInterval = null;

/**
 * Render blockchain prices widget
 */
async function renderBlockchainPrices(container) {
    container.innerHTML = '<div class="widget-loading"><div class="spinner"></div></div>';

    try {
        const data = await fetchBlockchainPrices();
        updateBlockchainPricesUI(container, data);

        // Auto-refresh every 2 minutes
        blockchainPricesInterval = setInterval(async () => {
            try {
                const refreshedData = await fetchBlockchainPrices();
                updateBlockchainPricesUI(container, refreshedData);
            } catch (error) {
                console.error('Blockchain prices refresh error:', error);
            }
        }, 2 * 60 * 1000);

        return { container, interval: blockchainPricesInterval };
    } catch (error) {
        console.error('Blockchain prices error:', error);
        container.innerHTML = `
            <div class="widget-error">
                <div class="widget-error-icon">⚠️</div>
                <div>Failed to load price data</div>
            </div>
        `;
        throw error;
    }
}

/**
 * Fetch blockchain prices
 */
async function fetchBlockchainPrices() {
    console.log('[Blockchain Prices Widget] Fetching prices...');
    const response = await authFetch('/prices/all');
    if (!response.ok) {
        console.error('[Blockchain Prices Widget] Fetch failed:', response.status, response.statusText);
        if (response.status === 401 || response.status === 403) {
            throw new Error('Authentication required - please login');
        }
        throw new Error('Failed to fetch blockchain prices');
    }
    const data = await response.json();
    console.log('[Blockchain Prices Widget] Data received:', data);
    const prices = data.prices || data;
    console.log('[Blockchain Prices Widget] Parsed prices:', prices);
    blockchainPricesCache = prices;
    return blockchainPricesCache;
}

/**
 * Update blockchain prices UI
 */
function updateBlockchainPricesUI(container, data) {
    console.log('[Blockchain Prices Widget] Updating UI with data:', data);

    // Use direct symbol keys (ADA, BTC, etc.) instead of full names
    const symbols = ['ADA', 'BTC', 'ETH', 'SOL', 'MATIC'];

    let html = '<div class="blockchain-prices">';

    for (const symbol of symbols) {
        const priceData = data[symbol];
        if (!priceData) {
            console.warn(`[Blockchain Prices Widget] No price data for ${symbol}`);
            continue;
        }

        const price = priceData.usd || 0;
        const change24h = priceData.usd_24h_change || 0;
        const changeClass = change24h >= 0 ? 'positive' : 'negative';
        const changeSymbol = change24h >= 0 ? '+' : '';

        html += `
            <div class="price-card">
                <div class="price-card-symbol">${symbol}</div>
                <div class="price-card-value" data-privacy>$${formatPrice(price)}</div>
                <div class="price-card-change ${changeClass}">
                    ${changeSymbol}${change24h.toFixed(2)}%
                </div>
            </div>
        `;
    }

    html += '</div>';
    container.innerHTML = html;
    console.log('[Blockchain Prices Widget] UI updated');

    // Apply privacy mode if enabled
    if (typeof applyPrivacyMode === 'function') {
        applyPrivacyMode();
    }
}

/**
 * Refresh blockchain prices
 */
async function refreshBlockchainPrices(instance) {
    if (instance && instance.container) {
        const data = await fetchBlockchainPrices();
        updateBlockchainPricesUI(instance.container, data);
    }
}

/**
 * Destroy blockchain prices widget
 */
function destroyBlockchainPrices(instance) {
    if (blockchainPricesInterval) {
        clearInterval(blockchainPricesInterval);
        blockchainPricesInterval = null;
    }
    if (instance && instance.interval) {
        clearInterval(instance.interval);
    }
}

/**
 * Format price with appropriate decimal places
 */
function formatPrice(price) {
    if (price === null || price === undefined) return '0.00';
    if (price >= 1) {
        return price.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    } else {
        // For prices < $1, show more decimals
        return price.toLocaleString('en-US', {
            minimumFractionDigits: 4,
            maximumFractionDigits: 6
        });
    }
}
