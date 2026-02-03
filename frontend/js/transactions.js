/**
 * Transaction History - Frontend JavaScript
 */

let currentTransactions = [];
let expandedRows = new Set();

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    loadSavedTheme();
    await loadTransactions();
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
        const data = await response.json();

        if (data.success) {
            currentTransactions = data.transactions || [];
            renderTransactions(currentTransactions);
            updateTransactionCount(currentTransactions.length);

            if (currentTransactions.length === 0) {
                showEmptyState();
            }
        } else {
            showStatus('Error loading transactions', 'error');
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
 * Refresh transactions from blockchain APIs
 */
async function refreshTransactions() {
    const days = document.getElementById('daysFilter').value;
    const blockchain = document.getElementById('blockchainFilter').value;

    showProcessingModal(true);
    updateProcessingStatus('Fetching transactions from blockchains...');

    const params = new URLSearchParams({
        days: days,
        ...(blockchain && { blockchain })
    });

    try {
        const response = await authFetch(`/transactions/refresh?${params}`, {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            const totalFetched = data.total_fetched || 0;
            showStatus(`Fetched ${totalFetched} transactions`, 'success');

            // Reload the table
            await loadTransactions();
        } else {
            showStatus('Error refreshing transactions', 'error');
        }
    } catch (error) {
        console.error('Error refreshing transactions:', error);
        showStatus('Failed to refresh transactions', 'error');
    } finally {
        showProcessingModal(false);
    }
}

/**
 * Render transactions in the table
 */
function renderTransactions(transactions) {
    const tbody = document.getElementById('txTableBody');
    const table = document.getElementById('txTable');

    if (!transactions || transactions.length === 0) {
        table.style.display = 'none';
        return;
    }

    tbody.innerHTML = '';
    table.style.display = 'table';

    transactions.forEach((tx, index) => {
        // Create main row
        const row = document.createElement('tr');
        row.className = 'tx-row';
        row.id = `tx-row-${index}`;
        row.onclick = () => toggleDetails(index);

        const expandIcon = expandedRows.has(index) ? '&#9660;' : '&#9658;';

        row.innerHTML = `
            <td class="expand-cell">${expandIcon}</td>
            <td>${formatTime(tx.tx_time)}</td>
            <td><span class="chain-badge chain-${tx.blockchain}">${formatChainName(tx.blockchain)}</span></td>
            <td><span class="direction-badge direction-${tx.direction}">${tx.direction}</span></td>
            <td class="amount-cell">${formatAmount(tx.amount)} ${tx.token_symbol}</td>
            <td>${tx.token_name || tx.token_symbol || 'N/A'}</td>
            <td class="hash-cell">${formatHash(tx.tx_hash, tx.blockchain)}</td>
        `;

        tbody.appendChild(row);

        // Create expandable details row
        const detailsRow = document.createElement('tr');
        detailsRow.id = `details-${index}`;
        detailsRow.className = 'tx-details-row';
        detailsRow.style.display = expandedRows.has(index) ? 'table-row' : 'none';
        detailsRow.innerHTML = `
            <td colspan="7">
                <div class="tx-details">
                    <div class="detail-grid">
                        <div class="detail-item">
                            <strong>From:</strong>
                            <span class="address">${formatAddress(tx.from_address)}</span>
                        </div>
                        <div class="detail-item">
                            <strong>To:</strong>
                            <span class="address">${formatAddress(tx.to_address)}</span>
                        </div>
                        <div class="detail-item">
                            <strong>Fee:</strong>
                            <span>${formatFee(tx.fee, tx.blockchain)}</span>
                        </div>
                        <div class="detail-item">
                            <strong>Status:</strong>
                            <span class="status-${tx.status}">${tx.status}</span>
                        </div>
                        <div class="detail-item detail-full">
                            <strong>Full Hash:</strong>
                            <span class="hash-full">${tx.tx_hash}</span>
                            <button class="btn-copy" onclick="copyToClipboard('${tx.tx_hash}', event)" title="Copy hash">&#128203;</button>
                        </div>
                        <div class="detail-item detail-full">
                            <strong>Wallet:</strong>
                            <span>${tx.wallet_name || tx.wallet_address || 'Unknown'}</span>
                        </div>
                    </div>
                </div>
            </td>
        `;

        tbody.appendChild(detailsRow);
    });
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
    const explorerUrl = getExplorerUrl(hash, blockchain);

    if (explorerUrl) {
        return `<a href="${explorerUrl}" target="_blank" class="hash-link" onclick="event.stopPropagation()">${truncated}</a>`;
    }

    return truncated;
}

/**
 * Truncate hash for display
 */
function truncateHash(hash) {
    if (!hash || hash.length < 16) return hash;
    return `${hash.substring(0, 8)}...${hash.substring(hash.length - 8)}`;
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
    if (address.length < 16) return address;
    return `${address.substring(0, 10)}...${address.substring(address.length - 10)}`;
}

/**
 * Format fee
 */
function formatFee(fee, blockchain) {
    if (!fee) return '0';

    const num = parseFloat(fee);
    if (isNaN(num)) return fee;

    const symbols = {
        'cardano': 'ADA',
        'ethereum': 'ETH',
        'bitcoin': 'BTC',
        'solana': 'SOL',
        'polygon': 'MATIC',
        'base': 'ETH'
    };

    const symbol = symbols[blockchain] || '';
    return `${num.toFixed(6)} ${symbol}`;
}

/**
 * Copy to clipboard
 */
async function copyToClipboard(text, event) {
    if (event) {
        event.stopPropagation();
    }

    try {
        await navigator.clipboard.writeText(text);
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
 */
function isPrivacyMode() {
    return localStorage.getItem('privacyMode') === 'enabled';
}

/**
 * Toggle privacy mode
 */
function togglePrivacyMode() {
    const privacyBtn = document.getElementById('privacyBtn');
    const currentMode = localStorage.getItem('privacyMode');

    if (currentMode === 'enabled') {
        localStorage.setItem('privacyMode', 'disabled');
        privacyBtn.classList.remove('active');
    } else {
        localStorage.setItem('privacyMode', 'enabled');
        privacyBtn.classList.add('active');
    }

    // Re-render to apply privacy mode
    renderTransactions(currentTransactions);
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
    if (isPrivacyMode() && privacyBtn) {
        privacyBtn.classList.add('active');
    }
}

/**
 * Change theme
 */
function changeTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
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
