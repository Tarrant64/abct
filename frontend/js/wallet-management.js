/**
 * Wallet Management Module
 * Handles wallet CRUD, chain filtering, discovery, import/export,
 * manual token management, exchange status, and asset tab switching.
 *
 * Dependencies: authFetch (session-auth.js), setSafeHTML (inline or app.js), DOMPurify
 */
(function () {
    'use strict';

    // Ensure setSafeHTML is available (defined in inline script or app.js)
    if (typeof setSafeHTML === 'undefined') {
        window.setSafeHTML = function (element, html) {
            if (!element) return;
            if (typeof DOMPurify !== 'undefined') {
                element.innerHTML = DOMPurify.sanitize(html);
            } else {
                console.warn('DOMPurify not loaded, falling back to textContent');
                element.textContent = html;
            }
        };
    }

    let wallets = [];
    let currentFilter = 'all';

    // ===== Chain Detection State =====
    let detectedChain = null;
    let detectedChains = [];
    let detectionTimer = null;

    const CHAIN_DISPLAY_NAMES = {
        cardano: 'Cardano', bitcoin: 'Bitcoin', ethereum: 'Ethereum', solana: 'Solana',
        polygon: 'Polygon', base: 'Base', algorand: 'Algorand', bsc: 'BNB Smart Chain',
        arbitrum: 'Arbitrum', avalanche: 'Avalanche', tron: 'Tron', xrp: 'XRP Ledger',
        hedera: 'Hedera', multiversx: 'MultiversX', sui: 'Sui', aptos: 'Aptos',
        filecoin: 'Filecoin', litecoin: 'Litecoin', dogecoin: 'Dogecoin', zcash: 'Zcash',
        tezos: 'Tezos', stacks: 'Stacks', vechain: 'VeChain', cosmos: 'Cosmos',
        near: 'NEAR', icp: 'ICP', ton: 'TON', polkadot: 'Polkadot', kusama: 'Kusama',
        stellar: 'Stellar', kaspa: 'Kaspa', osmosis: 'Osmosis', celestia: 'Celestia',
        injective: 'Injective', dydx: 'dYdX', sei: 'Sei', akash: 'Akash', kaia: 'Kaia',
        ergo: 'Ergo', iota: 'IOTA', waves: 'Waves', mina: 'Mina', zilliqa: 'Zilliqa',
        optimism: 'Optimism', zksync: 'zkSync', linea: 'Linea', scroll: 'Scroll',
        fantom: 'Fantom', cronos: 'Cronos', gnosis: 'Gnosis', moonbeam: 'Moonbeam'
    };

    const CHAIN_SYMBOLS = {
        cardano: 'ADA', bitcoin: 'BTC', ethereum: 'ETH', solana: 'SOL', polygon: 'MATIC',
        algorand: 'ALGO', bsc: 'BNB', arbitrum: 'ARB', avalanche: 'AVAX', tron: 'TRX',
        xrp: 'XRP', hedera: 'HBAR', multiversx: 'EGLD', sui: 'SUI', aptos: 'APT',
        filecoin: 'FIL', litecoin: 'LTC', dogecoin: 'DOGE', zcash: 'ZEC', tezos: 'XTZ',
        stacks: 'STX', vechain: 'VET', cosmos: 'ATOM', near: 'NEAR', icp: 'ICP',
        ton: 'TON', polkadot: 'DOT', kusama: 'KSM', stellar: 'XLM', kaspa: 'KAS',
        osmosis: 'OSMO', celestia: 'TIA', injective: 'INJ', dydx: 'DYDX', sei: 'SEI',
        akash: 'AKT', kaia: 'KAIA', ergo: 'ERG', iota: 'IOTA', waves: 'WAVES',
        mina: 'MINA', zilliqa: 'ZIL', optimism: 'OP', zksync: 'ZK', linea: 'LINEA',
        scroll: 'SCROLL', fantom: 'FTM', cronos: 'CRO', gnosis: 'GNO', moonbeam: 'GLMR',
        base: 'BASE'
    };

    const CHAIN_LOGO_OVERRIDES = {
        base: 'https://avatars.githubusercontent.com/u/108554348?s=32',
        arbitrum: 'https://avatars.githubusercontent.com/u/119917794?s=32'
    };

    function getChainLogo(chainId) {
        if (CHAIN_LOGO_OVERRIDES[chainId]) return CHAIN_LOGO_OVERRIDES[chainId];
        const sym = CHAIN_SYMBOLS[chainId] || chainId.toUpperCase();
        return `https://img.logokit.com/crypto/${sym}?size=32`;
    }

    // Entry point for lazy-loading from assets page
    function loadWalletManagement() {
        loadWallets();
    }

    // Toggle select all for xpub addresses
    function toggleSelectAllXpub() {
        const checked = document.getElementById('selectAllXpub').checked;
        document.querySelectorAll('#xpubList input[type="checkbox"]:not(:disabled)').forEach(cb => {
            cb.checked = checked;
        });
    }

    async function loadWallets() {
        try {
            const response = await authFetch('/wallets');
            const data = await response.json();
            wallets = data.wallets || [];
            updateCounts();
            renderWalletsList();
            // Also refresh the Self-Custody portfolio view on assets page
            if (typeof refreshWallets === 'function') {
                refreshWallets();
            }
        } catch (error) {
            console.error('Error loading wallets:', error);
            showStatus('Failed to load wallets', 'error');
        }
    }

    function updateCounts() {
        const counts = { all: wallets.length };
        ['cardano', 'bitcoin', 'ethereum', 'solana', 'polygon', 'base', 'algorand', 'bsc', 'arbitrum', 'avalanche', 'tron'].forEach(chain => {
            counts[chain] = wallets.filter(w => w.blockchain === chain).length;
        });

        Object.entries(counts).forEach(([chain, count]) => {
            const el = document.getElementById(`count-${chain}`);
            if (el) el.textContent = count;
        });
    }

    function filterByChain(chain) {
        currentFilter = chain;

        // Update tab states
        document.querySelectorAll('.chain-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.chain === chain);
        });

        renderWalletsList();
    }

    // Attach event listeners after DOM update (must be defined before renderWalletsList)
    function attachWalletEventListeners() {
        console.log('Attaching wallet event listeners...');

        // Stake group toggle listeners
        const stakeHeaders = document.querySelectorAll('.stake-group-header');
        console.log('Found', stakeHeaders.length, 'stake group headers');
        stakeHeaders.forEach(header => {
            header.addEventListener('click', function() {
                const stakeGroup = this.closest('.stake-group');
                const stakeKey = stakeGroup.dataset.stakeKey;
                toggleStakeGroup(stakeKey);
            });
        });

        // Token count badge listeners
        const tokenBadges = document.querySelectorAll('.token-count');
        console.log('Found', tokenBadges.length, 'token count badges');
        tokenBadges.forEach(badge => {
            badge.addEventListener('click', function(event) {
                event.stopPropagation();
                const walletId = parseInt(this.dataset.walletId);
                toggleWalletAssets(walletId, event);
            });
        });

        // Edit button listeners
        const editButtons = document.querySelectorAll('.wallet-edit-btn');
        console.log('Found', editButtons.length, 'edit buttons');
        editButtons.forEach(btn => {
            btn.addEventListener('click', function(event) {
                event.stopPropagation();
                const id = parseInt(this.dataset.walletId);
                const address = this.dataset.walletAddress;
                const label = this.dataset.walletLabel;
                console.log('Edit clicked for wallet', id);
                openEditModal(id, address, label);
            });
        });

        // Sync button listeners
        const syncButtons = document.querySelectorAll('.wallet-sync-btn');
        syncButtons.forEach(btn => {
            btn.addEventListener('click', function(event) {
                event.stopPropagation();
                syncWalletBalance(this.dataset.syncAddress, this);
            });
        });

        // Delete button listeners
        const deleteButtons = document.querySelectorAll('.wallet-delete-btn');
        console.log('Found', deleteButtons.length, 'delete buttons');
        deleteButtons.forEach(btn => {
            btn.addEventListener('click', function(event) {
                event.stopPropagation();
                const walletKey = this.dataset.walletKey;
                console.log('Delete clicked for wallet', walletKey);
                deleteWallet(walletKey);
            });
        });

        console.log('Event listeners attached successfully');
    }

    function renderWalletsList() {
        const container = document.getElementById('walletList');
        const filtered = currentFilter === 'all'
            ? wallets
            : wallets.filter(w => w.blockchain === currentFilter);

        if (filtered.length === 0) {
            setSafeHTML(container, `
                <div class="empty-state">
                    <h3>No wallets found</h3>
                    <p>${currentFilter === 'all' ? 'Add your first wallet to get started' : `No ${currentFilter} wallets yet`}</p>
                </div>
            `);

            return;
        }

        // Separate Cardano wallets (to group by stake key) from others
        const cardanoWallets = filtered.filter(w => w.blockchain === 'cardano');
        const otherWallets = filtered.filter(w => w.blockchain !== 'cardano');

        // Group Cardano wallets by stake key
        const stakeGroups = {};
        const enterpriseWallets = []; // Wallets without stake keys

        cardanoWallets.forEach(wallet => {
            if (wallet.stake_key) {
                if (!stakeGroups[wallet.stake_key]) {
                    stakeGroups[wallet.stake_key] = [];
                }
                stakeGroups[wallet.stake_key].push(wallet);
            } else {
                enterpriseWallets.push(wallet);
            }
        });

        let html = '';

        // Render Cardano stake key groups
        Object.entries(stakeGroups).forEach(([stakeKey, groupWallets]) => {
            const totalAda = groupWallets.reduce((sum, w) => sum + (parseFloat(w.balance) || 0), 0);
            const totalAssets = groupWallets.reduce((sum, w) => sum + (w.native_assets_count || 0), 0);
            const groupLabel = groupWallets[0].label || '';
            const groupHandle = groupWallets.find(w => w.ada_handle);
            const groupHandleBadge = groupHandle ? `<span class="ada-handle-badge">${groupHandle.ada_handle}</span>` : '';

            const stakeKeyDisplay = stakeKey.length > 14 ? `${stakeKey.slice(0, 8)}...${stakeKey.slice(-4)}` : stakeKey;

            html += `
                <div class="stake-group" data-stake-key="${stakeKey}">
                    <div class="stake-group-header">
                        <div class="stake-group-info">
                            <span class="expand-icon">▶</span>
                            <span class="chain cardano">cardano</span>
                            <span class="stake-key-display">${stakeKeyDisplay}</span>
                            <button class="copy-address-btn" onclick="copyToClipboard('${stakeKey}', this); event.stopPropagation();" title="Copy stake key">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                </svg>
                            </button>
                            ${groupLabel ? `<span class="group-label">${groupLabel}</span>` : ''}
                            ${groupHandleBadge}
                        </div>
                        <div class="stake-group-summary">
                            <span class="wallet-count">${groupWallets.length} wallet${groupWallets.length !== 1 ? 's' : ''}</span>
                            <span class="total-balance">${totalAda.toFixed(2)} ADA</span>
                            <span class="asset-count">${totalAssets} token${totalAssets !== 1 ? 's' : ''}</span>
                        </div>
                    </div>
                    <div class="stake-group-wallets" style="display: none;">
                        ${groupWallets.map(wallet => renderWalletItem(wallet, true)).join('')}
                    </div>
                </div>
            `;
        });

        // Render enterprise Cardano wallets (no stake key)
        enterpriseWallets.forEach(wallet => {
            html += renderWalletItem(wallet, false);
        });

        // Render other chain wallets
        otherWallets.forEach(wallet => {
            html += renderWalletItem(wallet, false);
        });

        // Use innerHTML directly for internally generated HTML (not user input)
        // DOMPurify was stripping data attributes needed for event listeners
        container.innerHTML = html;

        // Attach event listeners after DOM is updated
        attachWalletEventListeners();
    }

    function renderWalletItem(wallet, isGrouped = false) {
        const walletContainerId = `wallet-${wallet.id}`;
        const hasAssets = wallet.native_assets_count && wallet.native_assets_count > 0;

        const displayAddress = formatAddressDisplay(wallet.address, wallet.blockchain);

        return `
            <div class="wallet-item ${isGrouped ? 'grouped' : ''}" data-chain="${wallet.blockchain}" data-wallet-id="${wallet.id}" data-wallet-address="${wallet.address}" data-wallet-label="${wallet.label || ''}" id="${walletContainerId}">
                <div class="wallet-info" style="flex: 1; min-width: 0;">
                    <div style="display: flex; align-items: center;">
                        <div class="wallet-address">${displayAddress}</div>
                        <button class="copy-address-btn" onclick="copyToClipboard('${wallet.address}', this)" title="Copy address">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                            </svg>
                        </button>
                    </div>
                    <div class="wallet-label">
                        ${!isGrouped ? `<span class="chain ${wallet.blockchain}">${wallet.blockchain}</span>` : ''}
                        ${wallet.label ? `<span class="label-text">${wallet.label}</span>` : ''}
                        ${wallet.ada_handle ? `<span class="ada-handle-badge">${wallet.ada_handle}</span>` : ''}
                        ${hasAssets ? `<span class="token-count" data-wallet-id="${wallet.id}">${wallet.native_assets_count} token${wallet.native_assets_count !== 1 ? 's' : ''} ▼</span>` : ''}
                    </div>
                    <div class="wallet-assets-container" id="assets-${wallet.id}">
                        <div style="text-align: center; padding: 10px;"><div class="loading"></div></div>
                    </div>
                </div>
                <div class="wallet-balance">
                    <div class="amount">${formatBalance(wallet.balance, wallet.balance_unit)}</div>
                    <div class="unit">${getUnitDisplay(wallet.balance_unit)}</div>
                </div>
                <div class="wallet-actions">
                    <button class="btn btn-secondary btn-small wallet-sync-btn" data-sync-address="${wallet.address}" title="Refresh balance">&#8635;</button>
                    <button class="btn btn-secondary btn-small wallet-edit-btn" data-wallet-id="${wallet.id}" data-wallet-address="${wallet.address}" data-wallet-label="${wallet.label || ''}">
                        Edit
                    </button>
                    <button class="btn btn-danger btn-small wallet-delete-btn" data-wallet-key="${wallet.blockchain}:${wallet.address}">
                        Delete
                    </button>
                </div>
            </div>
        `;
    }

    async function toggleWalletAssets(walletId, event) {
        event.stopPropagation();  // Prevent other click handlers from firing

        const container = document.getElementById(`assets-${walletId}`);
        if (!container) return;

        // Toggle visibility
        if (container.classList.contains('expanded')) {
            container.classList.remove('expanded');
            return;
        }

        // Show container
        container.classList.add('expanded');

        // Check if assets are already loaded
        if (container.dataset.loaded === 'true') return;

        // Fetch assets
        try {
            const response = await authFetch(`/wallets/id/${walletId}/assets`);
            const data = await response.json();
            const assets = data.assets || [];

            if (assets.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 10px; color: #888;">No native assets</div>';
            } else {
                container.innerHTML = assets.map(asset => {
                    const logoHtml = asset.logo_url
                        ? `<img src="${asset.logo_url}" alt="${asset.asset_name || 'Unknown'}" class="token-logo" onerror="this.style.display='none';">`
                        : '';

                    return `
                        <div class="wallet-asset-item">
                            ${logoHtml}
                            <div class="wallet-asset-name">${asset.asset_name || 'Unknown'}</div>
                            <div class="wallet-asset-quantity">${formatTokenQuantity(asset.quantity)}</div>
                        </div>
                    `;
                }).join('');
            }

            container.dataset.loaded = 'true';
        } catch (error) {
            console.error('Error loading wallet assets:', error);
            container.innerHTML = '<div style="text-align: center; padding: 10px; color: #dc3545;">Failed to load assets</div>';
        }
    }

    function toggleStakeGroup(stakeKey) {
        // Use CSS.escape() to properly escape the stake key for CSS selectors
        const escapedStakeKey = CSS.escape(stakeKey);
        const group = document.querySelector(`.stake-group[data-stake-key="${escapedStakeKey}"]`);
        if (!group) return;

        const walletsDiv = group.querySelector('.stake-group-wallets');
        const icon = group.querySelector('.expand-icon');

        if (walletsDiv.style.display === 'none' || walletsDiv.style.display === '') {
            walletsDiv.style.display = 'block';
            icon.textContent = '▼';
            group.classList.add('expanded');
        } else {
            walletsDiv.style.display = 'none';
            icon.textContent = '▶';
            group.classList.remove('expanded');
        }
    }

    function formatBalance(balance, unit) {
        const num = parseFloat(balance) || 0;
        if (unit === 'SAT') {
            return (num / 100000000).toFixed(8);
        }
        return num.toFixed(6);
    }

    function getUnitDisplay(unit) {
        const units = {
            'ADA': 'ADA',
            'SAT': 'BTC',
            'ETH': 'ETH',
            'ETH_BASE': 'ETH',
            'SOL': 'SOL',
            'MATIC': 'POL'
        };
        return units[unit] || unit;
    }

    // Sync a single wallet's balance
    async function syncWalletBalance(address, btn) {
        const origText = btn.textContent;
        btn.disabled = true;
        btn.textContent = '⟳';
        btn.style.animation = 'spin 1s linear infinite';

        try {
            const response = await authFetch(`/wallets/${address}/refresh`, { method: 'POST' });
            if (!response.ok) throw new Error('Refresh failed');

            const data = await response.json();
            if (data.success) {
                // Update balance in-place
                const walletItem = btn.closest('.wallet-item');
                if (walletItem) {
                    const amountEl = walletItem.querySelector('.wallet-balance .amount');
                    if (amountEl && data.balance !== undefined) {
                        amountEl.textContent = formatBalance(data.balance, data.unit);
                    }
                }
                btn.textContent = '✓';
            } else {
                btn.textContent = '✗';
            }
        } catch (err) {
            console.error('Sync wallet error:', err);
            btn.textContent = '✗';
        } finally {
            btn.style.animation = '';
            setTimeout(() => {
                btn.textContent = origText;
                btn.disabled = false;
            }, 3000);
        }
    }

    // Format address: first 8 chars + "..." + last 4 chars
    function formatAddressDisplay(address, blockchain) {
        if (!address) return '';
        if (address.length <= 14) return address;
        return `${address.slice(0, 8)}...${address.slice(-4)}`;
    }

    // Copy to Clipboard (with HTTP fallback for Docker deployments)
    function copyToClipboard(text, button) {
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(text).then(() => {
                showCopyFeedback(button);
            }).catch(() => {
                fallbackCopy(text, button);
            });
        } else {
            fallbackCopy(text, button);
        }
    }

    function fallbackCopy(text, button) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
            showCopyFeedback(button);
        } catch (err) {
            console.error('Fallback copy failed:', err);
            alert('Copied: ' + text);
        } finally {
            document.body.removeChild(textarea);
        }
    }

    function showCopyFeedback(button) {
        const originalHTML = button.innerHTML;
        button.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
        button.classList.add('copied');
        setTimeout(() => {
            button.innerHTML = originalHTML;
            button.classList.remove('copied');
        }, 1500);
    }

    // Add Wallet Modal
    function openAddModal() {
        document.getElementById('addModal').classList.add('active');
        document.getElementById('walletAddress').value = '';
        document.getElementById('walletLabel').value = '';
        document.getElementById('cardanoDiscoveryOption').style.display = 'none';
        document.getElementById('bitcoinXpubOption').style.display = 'none';
        document.getElementById('enableXpub').checked = false;
        document.getElementById('chainDetectionResult').style.display = 'none';
        document.getElementById('btnSubmitAdd').disabled = true;
        document.getElementById('addressLabel').textContent = 'Wallet Address';
        document.getElementById('walletAddress').placeholder = 'Paste address: addr1..., 0x..., bc1..., base58...';
        detectedChain = null;
        detectedChains = [];
        if (detectionTimer) clearTimeout(detectionTimer);
    }

    function closeAddModal() {
        document.getElementById('addModal').classList.remove('active');
    }

    // Auto-detect chain from address input
    document.addEventListener('DOMContentLoaded', function () {
        var walletAddressEl = document.getElementById('walletAddress');
        if (walletAddressEl) {
            walletAddressEl.addEventListener('input', function() {
                const addr = this.value.trim();
                if (detectionTimer) clearTimeout(detectionTimer);

                if (!addr || addr.length < 6) {
                    document.getElementById('chainDetectionResult').style.display = 'none';
                    detectedChain = null;
                    detectedChains = [];
                    updateSubmitButton();
                    handleSpecialChainOptions(null);
                    return;
                }

                detectionTimer = setTimeout(() => detectChain(addr), 300);
            });
        }

        // Form submit handler
        var addForm = document.getElementById('addWalletForm');
        if (addForm) {
            addForm.addEventListener('submit', function(event) {
                event.preventDefault();
                addWallet(event);
            });
        }

        // Cancel button handler
        var cancelBtn = document.getElementById('btnCancelAdd');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', closeAddModal);
        }

        // Xpub checkbox handler
        var xpubCheckbox = document.getElementById('enableXpub');
        if (xpubCheckbox) {
            xpubCheckbox.addEventListener('change', function() {
                const addressLabel = document.getElementById('addressLabel');
                const addressInput = document.getElementById('walletAddress');
                if (this.checked) {
                    addressLabel.textContent = 'Extended Public Key';
                    addressInput.placeholder = 'Enter xpub, ypub, or zpub...';
                } else {
                    addressLabel.textContent = 'Wallet Address';
                    addressInput.placeholder = 'Paste address: addr1..., 0x..., bc1..., base58...';
                }
            });
        }
    });

    // Chain detection functions
    async function detectChain(address) {
        const resultEl = document.getElementById('chainDetectionResult');
        resultEl.style.display = 'block';
        resultEl.className = 'chain-detection-result';
        setSafeHTML(resultEl, '<div class="detection-loading"><div class="spinner-small"></div> Detecting blockchain...</div>');
        detectedChain = null;
        detectedChains = [];
        updateSubmitButton();

        try {
            const response = await authFetch('/wallets/detect?address=' + encodeURIComponent(address));
            if (!response.ok) throw new Error('Detection failed');
            const data = await response.json();

            detectedChains = data.detected || [];

            if (detectedChains.length === 1) {
                detectedChain = detectedChains[0];
                resultEl.className = 'chain-detection-result detected';
                const name = CHAIN_DISPLAY_NAMES[detectedChain] || detectedChain;
                const logo = getChainLogo(detectedChain);
                setSafeHTML(resultEl, `
                    <div class="detection-single">
                        <img src="${logo}" alt="${name}">
                        <span class="chain-name">${name}</span>
                        <span class="checkmark">&#10003;</span>
                    </div>
                `);
                // Fix onerror stripped by DOMPurify
                resultEl.querySelectorAll('img').forEach(img => {
                    img.addEventListener('error', () => { img.style.display = 'none'; });
                });
                handleSpecialChainOptions(detectedChain, data.is_stake, data.is_xpub);
            } else if (detectedChains.length > 1) {
                resultEl.className = 'chain-detection-result';
                let chipsHtml = '<div class="chain-chip-group"><span class="chip-label">Multiple chains detected — select one:</span>';
                detectedChains.forEach(cid => {
                    const name = CHAIN_DISPLAY_NAMES[cid] || cid;
                    const logo = getChainLogo(cid);
                    chipsHtml += `<button type="button" class="chain-chip" data-chain="${cid}"><img src="${logo}" alt="${name}"> ${name}</button>`;
                });
                chipsHtml += '</div>';
                setSafeHTML(resultEl, chipsHtml);
                // Attach chip click listeners + fix onerror
                resultEl.querySelectorAll('.chain-chip').forEach(chip => {
                    chip.addEventListener('click', () => selectChainChip(chip.getAttribute('data-chain')));
                });
                resultEl.querySelectorAll('img').forEach(img => {
                    img.addEventListener('error', () => { img.style.display = 'none'; });
                });
                handleSpecialChainOptions(null);
            } else {
                resultEl.className = 'chain-detection-result';
                setSafeHTML(resultEl, `
                    <div class="detection-none">
                        Chain not detected. Check the address format or
                        <a href="https://github.com/Tarrant64/abct/issues" target="_blank" rel="noopener">request chain support</a>.
                    </div>
                `);
                handleSpecialChainOptions(null);
            }
        } catch (err) {
            resultEl.className = 'chain-detection-result';
            setSafeHTML(resultEl, '<div class="detection-none">Detection error. Please try again.</div>');
            handleSpecialChainOptions(null);
        }
        updateSubmitButton();
    }

    function selectChainChip(chainId) {
        detectedChain = chainId;
        const resultEl = document.getElementById('chainDetectionResult');
        resultEl.querySelectorAll('.chain-chip').forEach(chip => {
            chip.classList.toggle('active', chip.getAttribute('data-chain') === chainId);
        });
        resultEl.className = 'chain-detection-result detected';
        handleSpecialChainOptions(chainId);
        updateSubmitButton();
    }

    function handleSpecialChainOptions(chain, isStake, isXpub) {
        const discoveryOption = document.getElementById('cardanoDiscoveryOption');
        const xpubOption = document.getElementById('bitcoinXpubOption');
        discoveryOption.style.display = chain === 'cardano' ? 'block' : 'none';
        xpubOption.style.display = (chain === 'bitcoin' || isXpub) ? 'block' : 'none';
        if (chain !== 'bitcoin' && !isXpub) {
            document.getElementById('enableXpub').checked = false;
        }
    }

    function updateSubmitButton() {
        document.getElementById('btnSubmitAdd').disabled = !detectedChain;
    }

    let discoveredAddresses = [];

    async function addWallet(event) {
        event.preventDefault();

        const chain = detectedChain;
        const address = document.getElementById('walletAddress').value.trim();
        const label = document.getElementById('walletLabel').value.trim();
        const enableDiscovery = document.getElementById('enableDiscovery').checked;
        const enableXpub = document.getElementById('enableXpub').checked;

        if (!chain) return;

        // Close the add modal first
        closeAddModal();

        // For Cardano with discovery enabled, find related wallets
        if (chain === 'cardano' && enableDiscovery && (address.startsWith('addr1') || address.startsWith('stake1'))) {
            try {
                await discoverCardanoWallets(address, label);
            } catch (error) {
                showStatus(error.message || 'Discovery failed', 'error');
                await loadWallets(); // Still reload in case some wallets were added
            }
            return;
        }

        // For Bitcoin xpub, discover addresses
        if (chain === 'bitcoin' && (enableXpub || isXpubAddress(address))) {
            try {
                await discoverBitcoinXpub(address, label);
            } catch (error) {
                showStatus(error.message || 'xpub discovery failed', 'error');
                await loadWallets(); // Still reload in case some wallets were added
            }
            return;
        }

        // For other chains, add directly
        try {
            const response = await authFetch('/wallets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    address: `${chain}:${address}`,
                    label: label || null
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to add wallet');
            }

            showStatus('Wallet added successfully', 'success');
            await loadWallets();
        } catch (error) {
            showStatus(error.message, 'error');
        }
    }

    // Check if address is an xpub
    function isXpubAddress(addr) {
        return addr && (addr.startsWith('xpub') || addr.startsWith('ypub') || addr.startsWith('zpub'));
    }

    // Store discovered xpub addresses
    let discoveredXpubAddresses = [];

    // Discover Bitcoin addresses from xpub
    async function discoverBitcoinXpub(xpub, label) {
        showStatus('Discovering Bitcoin addresses from xpub...', 'success');

        try {
            const response = await authFetch('/wallets/xpub/discover', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ xpub, gap_limit: 20 })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'xpub discovery failed');
            }

            const data = await response.json();
            discoveredXpubAddresses = data.addresses || [];

            if (discoveredXpubAddresses.length === 0) {
                showStatus('No addresses with balance found for this xpub', 'error');
                return;
            }

            // Show xpub discovery modal
            document.getElementById('xpubType').textContent = data.address_type || data.xpub_type;
            document.getElementById('xpubTotal').textContent = data.total_addresses;
            document.getElementById('xpubBalance').textContent = data.total_balance_btc;
            document.getElementById('xpubNew').textContent = data.new_addresses_count;
            document.getElementById('xpubLabel').value = label || `xpub (${xpub.slice(0, 8)}...)`;

            // Render address list
            const listEl = document.getElementById('xpubList');
            setSafeHTML(listEl, discoveredXpubAddresses.map((addr, idx) => `
                <div class="discover-item ${addr.already_tracked ? 'tracked' : ''}">
                    <input type="checkbox"
                           id="xpub-${idx}"
                           ${addr.already_tracked ? 'disabled' : 'checked'}
                           data-address="${addr.address}">
                    <div class="address">${addr.address.slice(0, 8)}...${addr.address.slice(-4)}</div>
                    <div class="balance">${addr.balance_btc.toFixed(8)} BTC</div>
                    <div class="chain-type">${addr.chain === 'receive' ? 'Receive' : 'Change'}</div>
                    <div class="status ${addr.already_tracked ? 'tracked' : 'new'}">
                        ${addr.already_tracked ? 'Tracked' : 'New'}
                    </div>
                </div>
            `).join(''));

            document.getElementById('xpubModal').classList.add('active');

        } catch (error) {
            showStatus(error.message, 'error');
        }
    }

    function closeXpubModal() {
        document.getElementById('xpubModal').classList.remove('active');
    }

    async function addSelectedXpubAddresses() {
        const label = document.getElementById('xpubLabel').value.trim();
        const checkboxes = document.querySelectorAll('#xpubList input[type="checkbox"]:checked:not(:disabled)');
        const selectedAddresses = Array.from(checkboxes).map(cb => cb.dataset.address);

        if (selectedAddresses.length === 0) {
            showStatus('No addresses selected', 'error');
            return;
        }

        closeXpubModal();
        showStatus(`Adding ${selectedAddresses.length} Bitcoin addresses...`, 'success');

        try {
            const response = await authFetch('/wallets/xpub/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    addresses: selectedAddresses,
                    label: label || null
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to add addresses');
            }

            const result = await response.json();
            showStatus(result.message, 'success');
            await loadWallets();

        } catch (error) {
            showStatus(error.message, 'error');
        }
    }

    async function discoverCardanoWallets(address, label) {
        showStatus('Discovering related wallets...', 'success');

        try {
            const response = await authFetch('/wallets/discover', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ address })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Discovery failed');
            }

            const data = await response.json();
            discoveredAddresses = data.addresses || [];

            // If no addresses found
            if (discoveredAddresses.length === 0) {
                showStatus('No addresses found for this stake key', 'error');
                await loadWallets(); // Reload anyway
                return;
            }

            // If only one address and it's already tracked, just reload
            if (discoveredAddresses.length === 1 && discoveredAddresses[0].already_tracked) {
                showStatus('This wallet is already tracked', 'error');
                await loadWallets();
                return;
            }

            // Check if all addresses are already tracked
            const newAddresses = discoveredAddresses.filter(a => !a.already_tracked);
            if (newAddresses.length === 0) {
                showStatus('All discovered wallets are already tracked', 'error');
                await loadWallets();
                return;
            }

            // Show discovery modal
            document.getElementById('discoverStakeKey').textContent =
                data.stake_address ? `Stake Key: ${data.stake_address}` : 'Enterprise address (no stake key)';
            document.getElementById('discoverTotal').textContent = data.total_addresses;
            document.getElementById('discoverWithUtxos').textContent = data.total_with_utxos;
            document.getElementById('discoverNew').textContent = data.new_addresses_count;
            document.getElementById('discoverLabel').value = label || '';

            // Render address list
            const listEl = document.getElementById('discoverList');
            setSafeHTML(listEl, discoveredAddresses.map((addr, idx) => `
                <div class="discover-item ${addr.already_tracked ? 'tracked' : ''}">
                    <input type="checkbox"
                           id="discover-${idx}"
                           ${addr.already_tracked ? 'disabled' : (addr.has_utxos ? 'checked' : '')}
                           data-address="${addr.address}">
                    <div class="address">${addr.address_short}</div>
                    <div class="balance ${addr.has_utxos ? 'has-utxos' : ''}">${addr.balance_ada.toFixed(2)} ADA</div>
                    <div class="status ${addr.already_tracked ? 'tracked' : 'new'}">
                        ${addr.already_tracked ? 'Tracked' : 'New'}
                    </div>
                </div>
            `).join(''));

            // Make sure modal is visible
            const modal = document.getElementById('discoverModal');
            modal.classList.add('active');
            modal.style.display = 'flex'; // Force display

        } catch (error) {
            console.error('Discovery error:', error);
            showStatus(error.message || 'Discovery failed', 'error');
            await loadWallets(); // Reload anyway in case some wallets were added
            throw error; // Re-throw so parent knows it failed
        }
    }

    function closeDiscoverModal() {
        document.getElementById('discoverModal').classList.remove('active');
        discoveredAddresses = [];
    }

    function toggleSelectAllDiscover() {
        const selectAll = document.getElementById('selectAllDiscover').checked;
        discoveredAddresses.forEach((addr, idx) => {
            const checkbox = document.getElementById(`discover-${idx}`);
            if (checkbox && !checkbox.disabled) {
                checkbox.checked = selectAll && addr.has_utxos;
            }
        });
    }

    async function addDiscoveredWallets() {
        const label = document.getElementById('discoverLabel').value.trim();
        const selectedAddresses = [];

        discoveredAddresses.forEach((addr, idx) => {
            const checkbox = document.getElementById(`discover-${idx}`);
            if (checkbox && checkbox.checked && !addr.already_tracked) {
                selectedAddresses.push(addr.address);
            }
        });

        if (selectedAddresses.length === 0) {
            showStatus('No wallets selected', 'error');
            return;
        }

        const btn = document.getElementById('addDiscoveredBtn');
        btn.disabled = true;
        btn.textContent = 'Adding...';

        try {
            const response = await authFetch('/wallets/add-multiple', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    addresses: selectedAddresses,
                    label: label || null
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to add wallets');
            }

            const result = await response.json();
            closeDiscoverModal();
            showStatus(result.message + ' - Loading balances...', 'success');

            // Reload wallets to show the new ones
            await loadWallets();

            // Give a moment for balances to load, then reload again
            setTimeout(async () => {
                await loadWallets();
                showStatus('Wallets added successfully', 'success');
            }, 2000);

        } catch (error) {
            showStatus(error.message, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Add Selected Wallets';
        }
    }

    // Edit Modal
    function openEditModal(id, address, label) {
        document.getElementById('editModal').classList.add('active');
        document.getElementById('editWalletId').value = id;
        document.getElementById('editWalletAddress').value = address;
        document.getElementById('editWalletLabel').value = label;
    }

    function closeEditModal() {
        document.getElementById('editModal').classList.remove('active');
    }

    async function saveLabel(event) {
        event.preventDefault();

        const id = document.getElementById('editWalletId').value;
        const label = document.getElementById('editWalletLabel').value.trim();

        try {
            const response = await authFetch(`/wallets/${id}/label`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label: label || null })
            });

            if (!response.ok) {
                throw new Error('Failed to update label');
            }

            closeEditModal();
            showStatus('Label updated', 'success');
            await loadWallets();
        } catch (error) {
            showStatus(error.message, 'error');
        }
    }

    // Delete Wallet
    async function deleteWallet(address) {
        if (!confirm(`Delete wallet ${address}?`)) return;

        try {
            const response = await authFetch(`/wallets/${encodeURIComponent(address)}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error('Failed to delete wallet');
            }

            showStatus('Wallet deleted', 'success');
            await loadWallets();
        } catch (error) {
            showStatus(error.message, 'error');
        }
    }

    // Import Modal
    function openImportModal() {
        document.getElementById('importModal').classList.add('active');
        document.getElementById('importText').value = '';
        document.getElementById('importPreview').style.display = 'none';
        document.getElementById('importBtn').disabled = true;
    }

    function closeImportModal() {
        document.getElementById('importModal').classList.remove('active');
    }

    function previewImport() {
        const text = document.getElementById('importText').value;
        const lines = text.split('\n').filter(line => line.trim() && !line.trim().startsWith('#'));

        const validWallets = [];
        const validChains = ['cardano', 'bitcoin', 'ethereum', 'solana', 'polygon', 'base', 'algorand', 'bsc', 'arbitrum', 'avalanche', 'tron'];

        lines.forEach(line => {
            const trimmed = line.trim();
            const colonIndex = trimmed.indexOf(':');
            if (colonIndex > 0) {
                const chain = trimmed.substring(0, colonIndex).toLowerCase();
                const address = trimmed.substring(colonIndex + 1);
                if (validChains.includes(chain) && address.length > 10) {
                    validWallets.push({ chain, address });
                }
            }
        });

        const previewEl = document.getElementById('importPreview');
        const listEl = document.getElementById('importPreviewList');
        const countEl = document.getElementById('importCount');
        const importBtn = document.getElementById('importBtn');

        if (validWallets.length > 0) {
            previewEl.style.display = 'block';
            countEl.textContent = validWallets.length;
            setSafeHTML(listEl, validWallets.slice(0, 10).map(w => `
                <div class="import-item">
                    <span class="chain ${w.chain}">${w.chain}</span>
                    <span class="address">${w.address}</span>
                </div>
            `).join('') + (validWallets.length > 10 ? `<div class="import-item">... and ${validWallets.length - 10} more</div>` : ''));
            importBtn.disabled = false;
        } else {
            previewEl.style.display = 'none';
            importBtn.disabled = true;
        }
    }

    async function importWallets() {
        const importBtn = document.getElementById('importBtn');
        importBtn.disabled = true;
        importBtn.textContent = 'Importing...';

        try {
            const text = document.getElementById('importText').value;
            const lines = text.split('\n').filter(line => line.trim() && !line.trim().startsWith('#'));

            const validChains = ['cardano', 'bitcoin', 'ethereum', 'solana', 'polygon', 'base', 'algorand', 'bsc', 'arbitrum', 'avalanche', 'tron'];
            let added = 0;
            let failed = 0;
            let lastError = '';

            for (const line of lines) {
                const trimmed = line.trim();
                const colonIndex = trimmed.indexOf(':');
                if (colonIndex > 0) {
                    const chain = trimmed.substring(0, colonIndex).toLowerCase();
                    const address = trimmed.substring(colonIndex + 1);
                    if (validChains.includes(chain) && address.length > 10) {
                        try {
                            const response = await authFetch('/wallets', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ address: `${chain}:${address}` })
                            });
                            if (response.ok) {
                                added++;
                            } else {
                                failed++;
                                try {
                                    const errData = await response.json();
                                    lastError = errData.detail || response.statusText;
                                } catch {
                                    lastError = response.statusText;
                                }
                                console.error(`Failed to import ${chain}:${address.substring(0,20)}...: ${lastError}`);
                            }
                        } catch (err) {
                            failed++;
                            lastError = err.message;
                            console.error(`Error importing wallet: ${err.message}`);
                        }
                    }
                }
            }

            closeImportModal();
            let msg = `Imported ${added} wallets`;
            if (failed > 0) {
                msg += `, ${failed} failed`;
                if (lastError) msg += ` (${lastError})`;
            }
            showStatus(msg, added > 0 ? 'success' : 'error');
            await loadWallets();
        } catch (err) {
            console.error('Import error:', err);
            closeImportModal();
            showStatus(`Import error: ${err.message}`, 'error');
        } finally {
            importBtn.disabled = false;
            importBtn.textContent = 'Import Wallets';
        }
    }

    // Export Wallets
    function exportWallets() {
        const content = wallets.map(w => `${w.blockchain}:${w.address}`).join('\n');
        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'wallets.txt';
        a.click();
        URL.revokeObjectURL(url);
        showStatus('Wallets exported', 'success');
    }

    // ==========================================
    // Asset Tab Switching
    // ==========================================
    let currentAssetTab = 'wallets';
    let manualTokens = [];

    function switchAssetTab(tab) {
        currentAssetTab = tab;

        // Update tab states
        document.querySelectorAll('.asset-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.type === tab);
        });

        // Show/hide sections
        document.getElementById('walletsSection').style.display = tab === 'wallets' ? 'block' : 'none';
        document.getElementById('exchangesSection').style.display = tab === 'exchanges' ? 'block' : 'none';
        document.getElementById('tokensSection').style.display = tab === 'tokens' ? 'block' : 'none';

        // Show/hide header actions
        document.getElementById('walletHeaderActions').style.display = tab === 'wallets' ? 'flex' : 'none';
        document.getElementById('tokenHeaderActions').style.display = tab === 'tokens' ? 'flex' : 'none';

        // Load data based on tab
        if (tab === 'tokens') {
            loadManualTokens();
        } else if (tab === 'exchanges') {
            loadExchangeStatus();
        }
    }

    // ==========================================
    // Manual Tokens Management
    // ==========================================
    async function loadManualTokens() {
        try {
            const response = await authFetch('/portfolio/custom-tokens');
            const data = await response.json();
            manualTokens = data.tokens || [];
            renderTokens();
        } catch (error) {
            console.error('Error loading tokens:', error);
            showStatus('Failed to load tokens', 'error');
        }
    }

    function renderTokens() {
        const container = document.getElementById('tokenList');

        if (manualTokens.length === 0) {
            setSafeHTML(container, `
                <div class="empty-state">
                    <h3>No manual tokens</h3>
                    <p>Add tokens manually to track holdings not in your wallets.</p>
                </div>
            `);

            return;
        }

        setSafeHTML(container, manualTokens.map(token => `
            <div class="token-item">
                <div class="token-info">
                    <div class="token-name">${token.ticker || token.name || 'Unknown Token'}</div>
                    <div class="token-details">
                        <span class="chain ${token.chain || 'cardano'}">${token.chain || 'cardano'}</span>
                        ${token.label ? `<span class="label">${token.label}</span>` : ''}
                        ${token.policy_id ? `<span class="policy-id">${token.policy_id.slice(0, 12)}...</span>` : ''}
                    </div>
                </div>
                <div class="token-quantity">
                    <div class="amount">${formatTokenQuantity(token.quantity)}</div>
                    ${token.value_usd ? `<div class="value">$${token.value_usd.toFixed(2)}</div>` : ''}
                </div>
                <div class="token-actions">
                    <button class="btn btn-secondary btn-small" onclick="openEditTokenModal(${token.id}, '${token.ticker || token.name}', '${token.quantity}', '${token.label || ''}')">
                        Edit
                    </button>
                    <button class="btn btn-danger btn-small" onclick="deleteToken(${token.id})">
                        Delete
                    </button>
                </div>
            </div>
        `).join(''));
    }

    function formatTokenQuantity(qty) {
        const num = parseFloat(qty);
        if (num >= 1000000) {
            return (num / 1000000).toFixed(2) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(2) + 'K';
        }
        return num.toLocaleString(undefined, { maximumFractionDigits: 6 });
    }

    // Exchange Management
    async function loadExchangeStatus() {
        try {
            const response = await authFetch('/exchanges/status');
            const data = await response.json();
            renderExchangeStatus(data.exchanges);
        } catch (error) {
            console.error('Error loading exchange status:', error);
            const container = document.getElementById('exchangeStatusList');
            setSafeHTML(container, `
                <div class="empty-state">
                    <p style="color: #ff6b6b;">Failed to load exchange status</p>
                </div>
            `);
        }
    }

    function renderExchangeStatus(exchanges) {
        const container = document.getElementById('exchangeStatusList');

        const exchangeInfo = [
            {
                key: 'coinbase',
                name: 'Coinbase',
                logo: 'https://www.coinbase.com/favicon.ico'
            },
            {
                key: 'binance',
                name: 'Binance.com',
                logo: 'https://public.bnbstatic.com/static/images/common/favicon.ico'
            },
            {
                key: 'binance_us',
                name: 'Binance.US',
                logo: 'https://public.bnbstatic.us/static/images/common/favicon.ico'
            },
            {
                key: 'okx',
                name: 'OKX',
                logo: 'https://static.okx.com/cdn/assets/imgs/MjAyMTQ/5C7F82ADE3C3FC61.png'
            },
            {
                key: 'bitget',
                name: 'Bitget',
                logo: 'https://www.bitget.com/favicon.ico'
            },
            {
                key: 'gate',
                name: 'Gate.io',
                logo: 'https://www.gate.io/favicon.ico'
            },
            {
                key: 'kucoin',
                name: 'KuCoin',
                logo: 'https://assets.staticimg.com/cms/media/7xbKmPPqZHqXfggnJcDJFPWIB5cxwOT8rCRNsCiI4.png'
            }
        ];

        const html = exchangeInfo.map(exchange => {
            const status = exchanges[exchange.key];
            const isConfigured = status?.configured || false;

            return `
                <div class="exchange-status-card ${isConfigured ? 'configured' : 'not-configured'}">
                    <img src="${exchange.logo}" alt="${exchange.name}" class="exchange-logo-large" onerror="this.style.display='none'">
                    <div class="exchange-status-info">
                        <h4>${exchange.name}</h4>
                        <span class="exchange-status-badge ${isConfigured ? 'configured' : 'not-configured'}">
                            ${isConfigured ? 'Configured' : 'Not Configured'}
                        </span>
                    </div>
                </div>
            `;
        }).join('');

        setSafeHTML(container, html);
    }

    // Add Token Modal
    function openAddTokenModal() {
        document.getElementById('addTokenModal').classList.add('active');
        document.getElementById('tokenChain').value = '';
        document.getElementById('tokenIdentifier').value = '';
        document.getElementById('tokenAmount').value = '';
        document.getElementById('tokenLabel').value = '';
    }

    function closeAddTokenModal() {
        document.getElementById('addTokenModal').classList.remove('active');
    }

    async function addManualToken(event) {
        event.preventDefault();

        const chain = document.getElementById('tokenChain').value;
        const identifier = document.getElementById('tokenIdentifier').value.trim();
        const quantity = document.getElementById('tokenAmount').value.trim();
        const label = document.getElementById('tokenLabel').value.trim();

        try {
            const response = await authFetch('/portfolio/custom-tokens', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chain: chain,
                    ticker_or_policy: identifier,
                    quantity: quantity,
                    label: label || null
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to add token');
            }

            closeAddTokenModal();
            showStatus('Token added successfully', 'success');
            await loadManualTokens();
        } catch (error) {
            showStatus(error.message, 'error');
        }
    }

    // Edit Token Modal
    function openEditTokenModal(id, name, quantity, label) {
        document.getElementById('editTokenModal').classList.add('active');
        document.getElementById('editTokenId').value = id;
        document.getElementById('editTokenName').value = name;
        document.getElementById('editTokenAmount').value = quantity;
        document.getElementById('editTokenLabel').value = label;
    }

    function closeEditTokenModal() {
        document.getElementById('editTokenModal').classList.remove('active');
    }

    async function saveTokenEdit(event) {
        event.preventDefault();

        const id = document.getElementById('editTokenId').value;
        const quantity = document.getElementById('editTokenAmount').value.trim();
        const label = document.getElementById('editTokenLabel').value.trim();

        try {
            const response = await authFetch(`/portfolio/custom-tokens/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    quantity: quantity,
                    label: label || null
                })
            });

            if (!response.ok) {
                throw new Error('Failed to update token');
            }

            closeEditTokenModal();
            showStatus('Token updated', 'success');
            await loadManualTokens();
        } catch (error) {
            showStatus(error.message, 'error');
        }
    }

    async function deleteToken(id) {
        if (!confirm('Delete this token?')) return;

        try {
            const response = await authFetch(`/portfolio/custom-tokens/${id}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error('Failed to delete token');
            }

            showStatus('Token deleted', 'success');
            await loadManualTokens();
        } catch (error) {
            showStatus(error.message, 'error');
        }
    }

    // Status Messages
    function showStatus(message, type) {
        const statusBar = document.getElementById('statusBar');
        const statusMessage = document.getElementById('statusMessage');

        if (!statusBar || !statusMessage) {
            console.log(`Status: ${message}${type === 'error' ? ' (error)' : ''}`);
            return;
        }

        statusMessage.textContent = message;
        statusBar.classList.remove('hidden', 'error', 'success');

        if (type === 'error') {
            statusBar.classList.add('error');
        } else if (type === 'success') {
            statusBar.classList.add('success');
        }

        // Auto-hide after 5 seconds
        setTimeout(() => {
            statusBar.classList.add('hidden');
        }, 5000);
    }

    // ==========================================
    // Expose functions to global scope for HTML onclick handlers
    // ==========================================
    window.loadWalletManagement = loadWalletManagement;
    window.loadWallets = loadWallets;
    window.filterByChain = filterByChain;
    window.toggleSelectAllXpub = toggleSelectAllXpub;
    window.openAddModal = openAddModal;
    window.closeAddModal = closeAddModal;
    window.addWallet = addWallet;
    window.deleteWallet = deleteWallet;
    window.openEditModal = openEditModal;
    window.closeEditModal = closeEditModal;
    window.saveLabel = saveLabel;
    window.openImportModal = openImportModal;
    window.closeImportModal = closeImportModal;
    window.previewImport = previewImport;
    window.importWallets = importWallets;
    window.exportWallets = exportWallets;
    window.copyToClipboard = copyToClipboard;
    window.closeXpubModal = closeXpubModal;
    window.addSelectedXpubAddresses = addSelectedXpubAddresses;
    window.discoverCardanoWallets = discoverCardanoWallets;
    window.discoverBitcoinXpub = discoverBitcoinXpub;
    window.closeDiscoverModal = closeDiscoverModal;
    window.toggleSelectAllDiscover = toggleSelectAllDiscover;
    window.addDiscoveredWallets = addDiscoveredWallets;
    window.switchAssetTab = switchAssetTab;
    window.openAddTokenModal = openAddTokenModal;
    window.closeAddTokenModal = closeAddTokenModal;
    window.addManualToken = addManualToken;
    window.openEditTokenModal = openEditTokenModal;
    window.closeEditTokenModal = closeEditTokenModal;
    window.saveTokenEdit = saveTokenEdit;
    window.deleteToken = deleteToken;
    window.showStatus = showStatus;
    window.toggleStakeGroup = toggleStakeGroup;
    window.toggleWalletAssets = toggleWalletAssets;
    window.formatTokenQuantity = formatTokenQuantity;

})();
