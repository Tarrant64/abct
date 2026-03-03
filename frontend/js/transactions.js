/**
 * Transaction History - Frontend JavaScript
 */

let currentTransactions = [];
let cexTransactions = [];
let showCex = false;
let expandedRows = new Set();
let currentPage = 1;
let pageSize = 20;
let filteredTransactions = [];
let fetchStatusPoll = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    loadSavedTheme();
    await loadTransactions();
    checkFetchStatus(); // Check if there's an ongoing fetch
});

/**
 * Load transactions from API
 */
async function loadTransactions() {
    const days = document.getElementById('daysFilter').value;
    const blockchain = document.getElementById('blockchainFilter').value;
    const direction = document.getElementById('directionFilter').value;
    const search = document.getElementById('searchBox').value.trim();

    showLoading(true);
    hideEmptyState();

    const params = new URLSearchParams({
        days: days,
        ...(blockchain && { blockchain }),
        ...(direction && { direction }),
        ...(search && { search })
    });

    try {
        const response = await authFetch(`/transactions?${params}`);

        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            console.error('Non-JSON response received:', response.status, response.statusText);
            showStatus('Server error: Invalid response format', 'error');
            showEmptyState();
            return;
        }

        const data = await response.json();

        if (data.success) {
            currentTransactions = data.transactions || [];
            // If CEX is on, reload CEX too and merge
            if (showCex) {
                await loadCexTransactionsOnly();
            }
            const merged = getMergedTransactions();
            renderTransactions(merged);
            updateTransactionCount(merged.length);

            if (merged.length === 0) {
                showEmptyState();
            }
        } else {
            showStatus(data.message || 'Error loading transactions', 'error');
        }
    } catch (error) {
        console.error('Error loading transactions:', error);
        showStatus('Failed to load transactions', 'error');
        showEmptyState();
    } finally {
        showLoading(false);
    }
}

/**
 * Refresh transactions from blockchain APIs (background)
 */
async function refreshTransactions() {
    const days = document.getElementById('daysFilter').value;
    const blockchain = document.getElementById('blockchainFilter').value;

    const params = new URLSearchParams({
        days: days,
        ...(blockchain && { blockchain })
    });

    try {
        const response = await authFetch(`/transactions/refresh/start?${params}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            showFetchIndicator('Fetching transactions...', 'running');
            startStatusPolling();
        } else {
            showStatus(data.message || 'Error starting fetch', 'error');
        }
    } catch (error) {
        console.error('Error starting transaction fetch:', error);
        showStatus('Failed to start transaction fetch', 'error');
    }
}

/**
 * Full historical resync - fetches ALL transactions from the beginning of time
 */
async function fullResyncTransactions() {
    const blockchain = document.getElementById('blockchainFilter').value;

    if (!confirm('This will fetch ALL historical transactions from your wallets. ' +
                 'This may take several minutes depending on how many wallets and transactions you have. ' +
                 'Continue?')) {
        return;
    }

    const params = new URLSearchParams({
        ...(blockchain && { blockchain })
    });

    try {
        const response = await authFetch(`/transactions/refresh/full?${params}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            showFetchIndicator('Full resync: fetching all historical transactions...', 'running');
            startStatusPolling();
        } else {
            showStatus(data.message || 'Error starting full resync', 'error');
        }
    } catch (error) {
        console.error('Error starting full resync:', error);
        showStatus('Failed to start full resync', 'error');
    }
}

/**
 * Check fetch status (on page load)
 */
async function checkFetchStatus() {
    try {
        const response = await authFetch('/transactions/refresh/status');
        const data = await response.json();

        if (data.success && data.status === 'running') {
            showFetchIndicator('Fetching transactions...', 'running');
            startStatusPolling();
        }
    } catch (error) {
        // Silently fail - probably no task running
    }
}

/**
 * Start polling for fetch status
 */
function startStatusPolling() {
    if (fetchStatusPoll) {
        clearInterval(fetchStatusPoll);
    }

    fetchStatusPoll = setInterval(async () => {
        try {
            const response = await authFetch('/transactions/refresh/status');
            const data = await response.json();

            if (data.success) {
                if (data.status === 'running') {
                    showFetchIndicator(data.message || 'Fetching transactions...', 'running');
                } else if (data.status === 'completed') {
                    const total = data.total_fetched || 0;
                    showFetchIndicator(`Fetched ${total} transactions`, 'completed');
                    stopStatusPolling();

                    // Reload transactions after 2 seconds
                    setTimeout(async () => {
                        hideFetchIndicator();
                        await loadTransactions();
                        showStatus(`Loaded ${total} new transactions`, 'success');
                    }, 2000);
                } else if (data.status === 'failed') {
                    showFetchIndicator('Fetch failed', 'failed');
                    stopStatusPolling();
                    setTimeout(hideFetchIndicator, 3000);
                }
            }
        } catch (error) {
            console.error('Error polling fetch status:', error);
            stopStatusPolling();
        }
    }, 2000); // Poll every 2 seconds
}

/**
 * Stop status polling
 */
function stopStatusPolling() {
    if (fetchStatusPoll) {
        clearInterval(fetchStatusPoll);
        fetchStatusPoll = null;
    }
}

/**
 * Show fetch indicator
 */
function showFetchIndicator(message, status) {
    let indicator = document.getElementById('fetchIndicator');

    if (!indicator) {
        // Create indicator if it doesn't exist
        indicator = document.createElement('div');
        indicator.id = 'fetchIndicator';
        indicator.className = 'fetch-indicator';
        document.body.appendChild(indicator);
    }

    indicator.className = `fetch-indicator ${status}`;
    indicator.innerHTML = `
        <div class="fetch-content">
            ${status === 'running' ? '<div class="fetch-spinner"></div>' : ''}
            <span class="fetch-message">${message}</span>
        </div>
    `;
    indicator.style.display = 'flex';
}

/**
 * Hide fetch indicator
 */
function hideFetchIndicator() {
    const indicator = document.getElementById('fetchIndicator');
    if (indicator) {
        indicator.style.display = 'none';
    }
}

/**
 * Render transactions in the table with pagination
 */
function renderTransactions(transactions) {
    const tbody = document.getElementById('txTableBody');
    const table = document.getElementById('txTable');
    const paginationControls = document.getElementById('paginationControls');

    // Store all transactions
    filteredTransactions = transactions || [];

    if (filteredTransactions.length === 0) {
        table.style.display = 'none';
        paginationControls.style.display = 'none';
        return;
    }

    // Calculate pagination
    const totalPages = Math.ceil(filteredTransactions.length / pageSize);
    const startIdx = (currentPage - 1) * pageSize;
    const endIdx = Math.min(startIdx + pageSize, filteredTransactions.length);
    const pageTransactions = filteredTransactions.slice(startIdx, endIdx);

    // Clear and render table
    tbody.innerHTML = '';
    table.style.display = 'table';
    paginationControls.style.display = 'flex';

    pageTransactions.forEach((tx, pageIndex) => {
        const globalIndex = startIdx + pageIndex;
        const isCex = tx._isCex === true;

        // Create main row
        const row = document.createElement('tr');
        row.className = `tx-row${isCex ? ' cex-row' : ''}`;
        row.id = `tx-row-${globalIndex}`;
        row.onclick = () => toggleDetails(globalIndex);

        const expandIcon = expandedRows.has(globalIndex) ? '&#9660;' : '&#9658;';

        if (isCex) {
            // CEX transaction row — handles all v2 types
            const cexDirClass = getCexDirectionClass(tx.side);
            const cexDirLabel = getCexDirectionLabel(tx.side, tx.tx_type);
            const tokenCol = getCexTokenDisplay(tx);
            const hashDisplay = tx.network_hash
                ? formatHash(tx.network_hash, getCexHashChain(tx.token))
                : (tx.order_id ? truncateHash(tx.order_id) : 'N/A');
            row.innerHTML = `
                <td class="expand-cell">${expandIcon}</td>
                <td><span class="tx-badge time-badge">${formatTime(tx.time)}</span></td>
                <td><span class="chain-badge chain-${tx.exchange}">${formatExchangeName(tx.exchange)}</span></td>
                <td><span class="direction-badge direction-${cexDirClass}">${cexDirLabel}</span></td>
                <td class="amount-cell"><span class="tx-badge amount-badge">${wrapBlurValue(formatCexAmount(tx))}</span></td>
                <td>${tokenCol}</td>
                <td class="hash-cell"><span class="tx-badge hash-badge">${hashDisplay}</span></td>
            `;
        } else {
            // Blockchain transaction row (original)
            const tokenDisplay = formatTokens(tx);
            row.innerHTML = `
                <td class="expand-cell">${expandIcon}</td>
                <td><span class="tx-badge time-badge">${formatTime(tx.tx_time)}</span></td>
                <td><span class="chain-badge chain-${tx.blockchain}">${formatChainName(tx.blockchain)}</span></td>
                <td><span class="direction-badge direction-${tx.direction}">${tx.direction}</span></td>
                <td class="amount-cell"><span class="tx-badge amount-badge">${wrapBlurValue(formatAmount(tx.amount))} ${tx.token_symbol}</span></td>
                <td>${tokenDisplay}</td>
                <td class="hash-cell"><span class="tx-badge hash-badge">${formatHash(tx.tx_hash, tx.blockchain)}</span></td>
            `;
        }

        tbody.appendChild(row);

        // Create expandable details row
        const detailsRow = document.createElement('tr');
        detailsRow.id = `details-${globalIndex}`;
        detailsRow.className = 'tx-details-row';
        detailsRow.style.display = expandedRows.has(globalIndex) ? 'table-row' : 'none';

        if (isCex) {
            // CEX details — rich display for all v2 transaction types
            const tradeDesc = getCexTradeDescription(tx);
            const addrDetails = getCexAddressDetails(tx);
            detailsRow.innerHTML = `
                <td colspan="7">
                    <div class="tx-details">
                        <div class="detail-grid">
                            <div class="detail-item">
                                <strong>Description:</strong>
                                <span>${tradeDesc}</span>
                            </div>
                            ${tx.quote_amount && tx.side !== 'DEPOSIT' && tx.side !== 'WITHDRAWAL' ? `<div class="detail-item">
                                <strong>USD Value:</strong>
                                <span>${wrapBlurValue('$' + formatAmount(tx.quote_amount))}</span>
                            </div>` : ''}
                            ${tx.price > 0 ? `<div class="detail-item">
                                <strong>Price:</strong>
                                <span>${wrapBlurValue('$' + formatAmount(tx.price))} per ${tx.token}</span>
                            </div>` : ''}
                            ${tx.fee > 0 ? `<div class="detail-item">
                                <strong>Fee:</strong>
                                <span>${wrapBlurValue(formatAmount(tx.fee))} ${tx.fee_token}</span>
                            </div>` : ''}
                            <div class="detail-item">
                                <strong>Exchange:</strong>
                                <span>${formatExchangeName(tx.exchange)}</span>
                            </div>
                            ${tx.tx_type ? `<div class="detail-item">
                                <strong>Type:</strong>
                                <span>${tx.tx_type}</span>
                            </div>` : ''}
                            ${addrDetails}
                            ${tx.network_hash ? `<div class="detail-item detail-full">
                                <strong>Network Hash:</strong>
                                <div class="detail-content">
                                    <span class="hash-full">${wrapBlurValue(tx.network_hash)}</span>
                                    <button class="copy-address-btn" onclick="copyToClipboard('${tx.network_hash}', this); event.stopPropagation();" title="Copy hash">
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                        </svg>
                                    </button>
                                </div>
                            </div>` : ''}
                            ${tx.order_id ? `<div class="detail-item detail-full">
                                <strong>Transaction ID:</strong>
                                <div class="detail-content">
                                    <span class="hash-full">${wrapBlurValue(tx.order_id)}</span>
                                    <button class="copy-address-btn" onclick="copyToClipboard('${tx.order_id}', this); event.stopPropagation();" title="Copy ID">
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                        </svg>
                                    </button>
                                </div>
                            </div>` : ''}
                        </div>
                    </div>
                </td>
            `;
        } else {
            // Blockchain details (original)
            detailsRow.innerHTML = `
                <td colspan="7">
                    <div class="tx-details">
                        <div class="detail-grid">
                            <div class="detail-item">
                                <strong>From:</strong>
                                <div class="detail-content">
                                    <span class="address">${wrapBlurValue(formatAddress(tx.from_address))}</span>
                                    ${tx.from_address ? `<button class="copy-address-btn" onclick="copyToClipboard('${tx.from_address}', this); event.stopPropagation();" title="Copy address">
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                        </svg>
                                    </button>` : ''}
                                </div>
                            </div>
                            <div class="detail-item">
                                <strong>To:</strong>
                                <div class="detail-content">
                                    <span class="address">${wrapBlurValue(formatAddress(tx.to_address))}</span>
                                    ${tx.to_address ? `<button class="copy-address-btn" onclick="copyToClipboard('${tx.to_address}', this); event.stopPropagation();" title="Copy address">
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                        </svg>
                                    </button>` : ''}
                                </div>
                            </div>
                            <div class="detail-item">
                                <strong>Fee:</strong>
                                <span>${formatFee(tx.fee, tx.blockchain)}</span>
                            </div>
                            <div class="detail-item">
                                <strong>Status:</strong>
                                <span class="status-${tx.status}">${tx.status}</span>
                            </div>
                            <div class="detail-item">
                                <strong>Wallet:</strong>
                                <span>${wrapBlurValue(tx.wallet_name || tx.wallet_address || 'Unknown')}</span>
                            </div>
                            <div class="detail-item detail-full">
                                <strong>Full Hash:</strong>
                                <div class="detail-content">
                                    <span class="hash-full">${wrapBlurValue(tx.tx_hash)}</span>
                                    <button class="copy-address-btn" onclick="copyToClipboard('${tx.tx_hash}', this); event.stopPropagation();" title="Copy hash">
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                        </svg>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </td>
            `;
        }

        tbody.appendChild(detailsRow);
    });

    // Update pagination controls
    updatePaginationControls(startIdx + 1, endIdx, filteredTransactions.length, currentPage, totalPages);
}

/**
 * Toggle details row
 */
function toggleDetails(index) {
    const detailsRow = document.getElementById(`details-${index}`);
    const mainRow = document.getElementById(`tx-row-${index}`);

    if (!detailsRow || !mainRow) return;

    if (expandedRows.has(index)) {
        expandedRows.delete(index);
        detailsRow.style.display = 'none';
        mainRow.querySelector('.expand-cell').innerHTML = '&#9658;';
    } else {
        expandedRows.add(index);
        detailsRow.style.display = 'table-row';
        mainRow.querySelector('.expand-cell').innerHTML = '&#9660;';
    }
}

/**
 * Format timestamp
 */
function formatTime(timestamp) {
    if (!timestamp) return 'N/A';

    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) {
        return `${diffMins}m ago`;
    } else if (diffHours < 24) {
        return `${diffHours}h ago`;
    } else if (diffDays < 7) {
        return `${diffDays}d ago`;
    } else {
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
}

/**
 * Format chain name
 */
function formatChainName(chain) {
    const names = {
        'cardano': 'Cardano',
        'ethereum': 'Ethereum',
        'bitcoin': 'Bitcoin',
        'solana': 'Solana',
        'polygon': 'Polygon',
        'base': 'Base'
    };
    return names[chain] || chain;
}

/**
 * Format amount with privacy mode
 */
function formatAmount(amount) {
    if (isPrivacyMode()) {
        return '****';
    }

    if (!amount) return '0';

    const num = parseFloat(amount);
    if (isNaN(num)) return amount;

    if (num < 0.01) {
        return num.toFixed(6);
    } else if (num < 1) {
        return num.toFixed(4);
    } else {
        return num.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
}

/**
 * Format transaction hash
 */
function formatHash(hash, blockchain) {
    if (!hash) return 'N/A';

    const truncated = truncateHash(hash);
    const blurredHash = wrapBlurValue(truncated);
    const explorerUrl = getExplorerUrl(hash, blockchain);

    if (explorerUrl) {
        return `<a href="${explorerUrl}" target="_blank" class="hash-link" onclick="event.stopPropagation()">${blurredHash}</a>`;
    }

    return blurredHash;
}

/**
 * Truncate hash for display
 */
function truncateHash(hash) {
    if (!hash || hash.length < 14) return hash;
    return `${hash.substring(0, 8)}...${hash.substring(hash.length - 4)}`;
}

/**
 * Get blockchain explorer URL
 */
function getExplorerUrl(hash, blockchain) {
    const explorers = {
        'cardano': `https://cardanoscan.io/transaction/${hash}`,
        'ethereum': `https://etherscan.io/tx/${hash}`,
        'bitcoin': `https://blockchain.com/btc/tx/${hash}`,
        'solana': `https://solscan.io/tx/${hash}`,
        'polygon': `https://polygonscan.com/tx/${hash}`,
        'base': `https://basescan.org/tx/${hash}`
    };
    return explorers[blockchain] || null;
}

/**
 * Format address with truncation
 */
function formatAddress(address) {
    if (!address) return 'N/A';
    if (address.length < 14) return address;
    return `${address.substring(0, 8)}...${address.substring(address.length - 4)}`;
}

/**
 * Wrap value in blur-value span for privacy mode
 */
function wrapBlurValue(value) {
    if (!value || value === 'N/A') return value;
    return `<span class="blur-value">${value}</span>`;
}

/**
 * Format fee
 */
function formatFee(fee, blockchain) {
    if (!fee) return wrapBlurValue('0');

    const num = parseFloat(fee);
    if (isNaN(num)) return wrapBlurValue(fee);

    const symbols = {
        'cardano': 'ADA',
        'ethereum': 'ETH',
        'bitcoin': 'BTC',
        'solana': 'SOL',
        'polygon': 'MATIC',
        'base': 'ETH'
    };

    const symbol = symbols[blockchain] || '';
    return `${wrapBlurValue(num.toFixed(6))} ${symbol}`;
}

/**
 * Copy to clipboard
 */
async function copyToClipboard(text, button) {
    try {
        // Try modern clipboard API first (requires HTTPS)
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
        } else {
            // Fallback for HTTP (Docker deployments)
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }

        // Add visual feedback
        if (button) {
            button.classList.add('copied');
            setTimeout(() => {
                button.classList.remove('copied');
            }, 2000);
        }

        showStatus('Copied to clipboard', 'success');
    } catch (err) {
        console.error('Failed to copy:', err);
        showStatus('Failed to copy', 'error');
    }
}

/**
 * Handle search keyup
 */
function handleSearchKeyup(event) {
    if (event.key === 'Enter') {
        loadTransactions();
    }
}

/**
 * Toggle CEX transactions visibility
 */
async function toggleCexTransactions() {
    const checkbox = document.getElementById('showCexCheckbox');
    showCex = checkbox && checkbox.checked;

    // Show/hide Sync CEX button
    const syncBtn = document.getElementById('refreshCexBtn');
    if (syncBtn) {
        syncBtn.style.display = showCex ? 'inline-flex' : 'none';
    }

    if (showCex) {
        await loadCexTransactionsOnly();
    } else {
        cexTransactions = [];
    }

    currentPage = 1;
    const merged = getMergedTransactions();
    renderTransactions(merged);
    updateTransactionCount(merged.length);

    if (merged.length === 0) {
        showEmptyState();
    } else {
        hideEmptyState();
    }
}

/**
 * Load CEX transactions (without reloading blockchain transactions)
 */
async function loadCexTransactionsOnly() {
    const days = document.getElementById('daysFilter').value;
    try {
        const response = await authFetch(`/exchanges/transactions?days=${days}`);
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            cexTransactions = [];
            return;
        }
        const data = await response.json();
        if (data.success) {
            cexTransactions = (data.transactions || []).map(tx => ({
                ...tx,
                _isCex: true
            }));
        } else {
            cexTransactions = [];
        }
    } catch (error) {
        console.error('Error loading CEX transactions:', error);
        cexTransactions = [];
    }
}

/**
 * Get merged and sorted transactions
 */
function getMergedTransactions() {
    if (!showCex || cexTransactions.length === 0) {
        return currentTransactions;
    }

    // Merge blockchain + CEX, sort by time descending
    const merged = [...currentTransactions, ...cexTransactions];
    merged.sort((a, b) => {
        const timeA = a.tx_time || a.time || '';
        const timeB = b.tx_time || b.time || '';
        return timeB.localeCompare(timeA);
    });
    return merged;
}

/**
 * Format exchange name for display
 */
function formatExchangeName(exchange) {
    const names = {
        'coinbase': 'Coinbase',
        'binance': 'Binance',
        'binance_us': 'Binance US'
    };
    return names[exchange] || exchange;
}

/**
 * Get CSS class for CEX direction badge
 */
function getCexDirectionClass(side) {
    const map = {
        'BUY': 'buy',
        'SELL': 'sell',
        'SEND': 'sent',
        'RECEIVE': 'received',
        'DEPOSIT': 'received',
        'WITHDRAWAL': 'sent',
        'REWARD': 'received',
    };
    return map[side] || 'buy';
}

/**
 * Get display label for CEX direction
 */
function getCexDirectionLabel(side, txType) {
    if (txType === 'subscription') return 'Recurring Buy';
    if (txType === 'staking_reward' || txType === 'inflation_reward') return 'Reward';
    const map = {
        'BUY': 'Buy',
        'SELL': 'Sell',
        'SEND': 'Send',
        'RECEIVE': 'Receive',
        'DEPOSIT': 'Deposit',
        'WITHDRAWAL': 'Withdraw',
        'REWARD': 'Reward',
    };
    return map[side] || side;
}

/**
 * Get token column display for CEX transaction
 */
function getCexTokenDisplay(tx) {
    const side = tx.side;
    if (side === 'BUY' || side === 'SELL') {
        return `<span class="token-badge">${tx.token}/${tx.quote_token || 'USD'}</span>`;
    } else if (side === 'DEPOSIT' || side === 'WITHDRAWAL') {
        return `<span class="token-badge">${tx.quote_token || 'USD'}</span>`;
    } else {
        return `<span class="token-badge">${tx.token || tx.quote_token || '—'}</span>`;
    }
}

/**
 * Format amount for CEX transaction display
 */
function formatCexAmount(tx) {
    const side = tx.side;
    if (side === 'DEPOSIT' || side === 'WITHDRAWAL') {
        // Show USD amount for fiat operations
        return '$' + formatAmount(tx.quote_amount || tx.amount);
    }
    return formatAmount(tx.amount) + ' ' + (tx.token || '');
}

/**
 * Get a reasonable blockchain for explorer linking from CEX token symbol
 */
function getCexHashChain(tokenSymbol) {
    const map = {
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'SOL': 'solana',
        'ADA': 'cardano',
        'MATIC': 'polygon',
    };
    return map[(tokenSymbol || '').toUpperCase()] || 'ethereum';
}

/**
 * Build rich trade description for CEX details panel
 */
function getCexTradeDescription(tx) {
    const amt = wrapBlurValue(formatAmount(tx.amount));
    const usd = wrapBlurValue('$' + formatAmount(tx.quote_amount));
    const token = tx.token || '';
    const quote = tx.quote_token || 'USD';

    switch (tx.side) {
        case 'BUY':
            return `Bought ${amt} ${token} for ${usd}`;
        case 'SELL':
            return `Sold ${amt} ${token} for ${usd}`;
        case 'SEND':
            return `Sent ${amt} ${token}${tx.to_address ? ' to ' + wrapBlurValue(formatAddress(tx.to_address)) : ''}`;
        case 'RECEIVE':
            return `Received ${amt} ${token}${tx.from_address ? ' from ' + wrapBlurValue(formatAddress(tx.from_address)) : ''}`;
        case 'DEPOSIT':
            return `Deposited ${usd} to ${formatExchangeName(tx.exchange)}`;
        case 'WITHDRAWAL':
            return `Withdrew ${usd} from ${formatExchangeName(tx.exchange)}`;
        case 'REWARD':
            return `Earned ${amt} ${token} staking reward`;
        default:
            return `${tx.side} ${amt} ${token}`;
    }
}

/**
 * Build address detail items for CEX expanded row
 */
function getCexAddressDetails(tx) {
    let html = '';
    if (tx.to_address) {
        html += `<div class="detail-item">
            <strong>To:</strong>
            <div class="detail-content">
                <span class="address">${wrapBlurValue(formatAddress(tx.to_address))}</span>
                <button class="copy-address-btn" onclick="copyToClipboard('${tx.to_address}', this); event.stopPropagation();" title="Copy address">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                </button>
            </div>
        </div>`;
    }
    if (tx.from_address) {
        html += `<div class="detail-item">
            <strong>From:</strong>
            <div class="detail-content">
                <span class="address">${wrapBlurValue(formatAddress(tx.from_address))}</span>
                <button class="copy-address-btn" onclick="copyToClipboard('${tx.from_address}', this); event.stopPropagation();" title="Copy address">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                </button>
            </div>
        </div>`;
    }
    return html;
}

/**
 * Refresh CEX transactions (full re-fetch from exchange APIs)
 */
async function refreshCexTransactions() {
    const btn = document.getElementById('refreshCexBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-small"></span> Syncing...';
    }

    try {
        const response = await authFetch('/exchanges/transactions/refresh', {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            const results = data.results || {};
            let msg = 'CEX sync complete';
            for (const [ex, info] of Object.entries(results)) {
                if (info.new !== undefined) {
                    msg += ` | ${ex}: ${info.new} new (${info.total_stored} total)`;
                }
            }
            showStatus(msg, 'success');

            // Reload CEX transactions
            await loadCexTransactionsOnly();
            currentPage = 1;
            const merged = getMergedTransactions();
            renderTransactions(merged);
            updateTransactionCount(merged.length);
        } else {
            showStatus('CEX sync failed', 'error');
        }
    } catch (error) {
        console.error('Error refreshing CEX transactions:', error);
        showStatus('Failed to sync CEX transactions', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '&#128260; Sync CEX';
        }
    }
}

/**
 * Update transaction count badge
 */
function updateTransactionCount(count) {
    const badge = document.getElementById('txCount');
    if (badge) {
        badge.textContent = count;
    }
}

/**
 * Show/hide loading indicator
 */
function showLoading(show) {
    const indicator = document.getElementById('loadingIndicator');
    if (indicator) {
        indicator.style.display = show ? 'block' : 'none';
    }
}

/**
 * Show/hide empty state
 */
function showEmptyState() {
    const emptyState = document.getElementById('emptyState');
    const table = document.getElementById('txTable');
    if (emptyState && table) {
        emptyState.style.display = 'block';
        table.style.display = 'none';
    }
}

function hideEmptyState() {
    const emptyState = document.getElementById('emptyState');
    if (emptyState) {
        emptyState.style.display = 'none';
    }
}

/**
 * Show/hide processing modal
 */
function showProcessingModal(show) {
    const modal = document.getElementById('processingModal');
    if (modal) {
        modal.style.display = show ? 'flex' : 'none';
    }
}

/**
 * Update processing status message
 */
function updateProcessingStatus(message) {
    const status = document.getElementById('processingStatus');
    if (status) {
        status.textContent = message;
    }
}

/**
 * Show status message
 */
function showStatus(message, type = 'info') {
    const statusBar = document.getElementById('statusBar');
    const statusMessage = document.getElementById('statusMessage');

    if (statusBar && statusMessage) {
        statusMessage.textContent = message;
        statusBar.className = `status-bar ${type}`;
        statusBar.classList.remove('hidden');

        setTimeout(() => {
            statusBar.classList.add('hidden');
        }, 5000);
    }
}

/**
 * Check if privacy mode is enabled
 * Checks body class first (most reliable), then localStorage.
 * Supports both 'true' (app.js convention) and 'enabled' (legacy) values.
 */
function isPrivacyMode() {
    if (document.body.classList.contains('privacy-mode')) return true;
    const val = localStorage.getItem('privacyMode');
    return val === 'true' || val === 'enabled';
}

// Only define togglePrivacyMode, loadSavedTheme, changeTheme if app.js
// hasn't already defined them (app.js loads first on data.html/wallets.html).
// On standalone transactions.html, app.js is NOT loaded, so these are needed.
if (typeof window._appJsPrivacyLoaded === 'undefined') {

/**
 * Toggle privacy mode (standalone version for transactions.html)
 */
function togglePrivacyMode() {
    const privacyBtn = document.getElementById('privacyBtn');
    const body = document.body;
    const isEnabled = body.classList.toggle('privacy-mode');

    localStorage.setItem('privacyMode', isEnabled ? 'true' : 'false');

    if (privacyBtn) {
        privacyBtn.classList.toggle('active', isEnabled);
    }

    // Sync avatar dropdown indicator if present
    if (typeof syncPrivacyIndicator === 'function') {
        syncPrivacyIndicator();
    }

    // Re-render to apply privacy mode to transaction data
    if (typeof renderTransactions === 'function' && typeof currentTransactions !== 'undefined') {
        renderTransactions(currentTransactions);
    }
}

/**
 * Load and apply saved theme
 */
function loadSavedTheme() {
    const theme = localStorage.getItem('theme') || 'dark-mode';
    document.documentElement.setAttribute('data-theme', theme);

    const themeSelect = document.getElementById('themeSelect');
    if (themeSelect) {
        themeSelect.value = theme;
    }

    // Load privacy mode state
    const privacyBtn = document.getElementById('privacyBtn');
    if (isPrivacyMode()) {
        if (privacyBtn) {
            privacyBtn.classList.add('active');
        }
        document.body.classList.add('privacy-mode');
    }
}

/**
 * Change theme
 */
function changeTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
}

} // end if (typeof window._appJsPrivacyLoaded === 'undefined')

/**
 * Format tokens (handle multiple for Cardano)
 */
function formatTokens(tx) {
    // Check if metadata contains multiple tokens (Cardano multi-asset transactions)
    if (tx.metadata && typeof tx.metadata === 'string') {
        try {
            const metadata = JSON.parse(tx.metadata);
            if (metadata.tokens && Array.isArray(metadata.tokens) && metadata.tokens.length > 1) {
                // Multiple tokens - show up to 3, then "..."
                const tokenNames = metadata.tokens.map(t => t.symbol || t.name).filter(Boolean);
                if (tokenNames.length <= 3) {
                    return `<div class="token-list">${tokenNames.map(name =>
                        `<span class="token-item">${name}</span>`
                    ).join('')}</div>`;
                } else {
                    return `<div class="token-list">
                        ${tokenNames.slice(0, 3).map(name =>
                            `<span class="token-item">${name}</span>`
                        ).join('')}
                        <span class="token-more">+${tokenNames.length - 3} more</span>
                    </div>`;
                }
            }
        } catch (e) {
            // Ignore parsing errors
        }
    }

    // Single token or fallback
    const tokenName = tx.token_name || tx.token_symbol || 'N/A';
    return `<span class="token-badge">${tokenName}</span>`;
}

/**
 * Update pagination controls
 */
function updatePaginationControls(start, end, total, page, totalPages) {
    document.getElementById('pageStart').textContent = start;
    document.getElementById('pageEnd').textContent = end;
    document.getElementById('totalTransactions').textContent = total;
    document.getElementById('currentPage').textContent = page;
    document.getElementById('totalPages').textContent = totalPages;

    // Update button states
    const firstBtn = document.getElementById('firstPageBtn');
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');
    const lastBtn = document.getElementById('lastPageBtn');

    firstBtn.disabled = page === 1;
    prevBtn.disabled = page === 1;
    nextBtn.disabled = page === totalPages;
    lastBtn.disabled = page === totalPages;
}

/**
 * Pagination functions
 */
function goToFirstPage() {
    currentPage = 1;
    renderTransactions(filteredTransactions);
}

function previousPage() {
    if (currentPage > 1) {
        currentPage--;
        renderTransactions(filteredTransactions);
    }
}

function nextPage() {
    const totalPages = Math.ceil(filteredTransactions.length / pageSize);
    if (currentPage < totalPages) {
        currentPage++;
        renderTransactions(filteredTransactions);
    }
}

function goToLastPage() {
    currentPage = Math.ceil(filteredTransactions.length / pageSize);
    renderTransactions(filteredTransactions);
}

function changePageSize() {
    const select = document.getElementById('pageSizeSelect');
    pageSize = parseInt(select.value);
    currentPage = 1; // Reset to first page
    renderTransactions(filteredTransactions);
}

/**
 * Toggle collapsible section
 */
function toggleSection(headerElement) {
    const section = headerElement.parentElement;
    const content = section.querySelector('.section-content');
    const icon = headerElement.querySelector('.collapse-icon');

    if (content && icon) {
        if (content.style.display === 'none') {
            content.style.display = 'block';
            icon.textContent = '▼';
        } else {
            content.style.display = 'none';
            icon.textContent = '▶';
        }
    }
}

/**
 * Toggle waffle menu
 */
function toggleWaffleMenu() {
    const menu = document.getElementById('waffleMenu');
    if (menu) {
        menu.classList.toggle('active');
    }
}

// Close waffle menu when clicking outside
document.addEventListener('click', (e) => {
    const menu = document.getElementById('waffleMenu');
    const btn = document.querySelector('.waffle-menu-btn');

    if (menu && btn && !menu.contains(e.target) && !btn.contains(e.target)) {
        menu.classList.remove('active');
    }
});
