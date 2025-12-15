// Accounts Page JavaScript

let accountsData = [];
let accountToDelete = null;
let accountToEdit = null;
let availableBalance = 0;  // Store available balance for Add to Position modal

// Check if we're on detail page or list page
const isDetailPage = typeof ACCOUNT_ID !== 'undefined';

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    if (isDetailPage) {
        initDetailPage();
    } else {
        initListPage();
    }
});

// ==================== LIST PAGE ====================

function initListPage() {
    loadAccounts();
    setupListPageEventListeners();
}

function setupListPageEventListeners() {
    // Add Account Modal
    const addAccountBtn = document.getElementById('addAccountBtn');
    const addAccountModal = document.getElementById('addAccountModal');
    const closeModal = document.getElementById('closeModal');
    const cancelBtn = document.getElementById('cancelBtn');
    const submitAccount = document.getElementById('submitAccount');
    const togglePassword = document.getElementById('togglePassword');
    
    if (addAccountBtn) {
        addAccountBtn.addEventListener('click', () => {
            addAccountModal.classList.add('active');
        });
    }
    
    if (closeModal) {
        closeModal.addEventListener('click', () => {
            addAccountModal.classList.remove('active');
            clearAddAccountForm();
        });
    }
    
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            addAccountModal.classList.remove('active');
            clearAddAccountForm();
        });
    }
    
    if (submitAccount) {
        submitAccount.addEventListener('click', createAccount);
    }
    
    if (togglePassword) {
        togglePassword.addEventListener('click', () => {
            const apiSecret = document.getElementById('apiSecret');
            if (apiSecret.type === 'password') {
                apiSecret.type = 'text';
            } else {
                apiSecret.type = 'password';
            }
        });
    }
    
    // Delete Modal
    const deleteModal = document.getElementById('deleteModal');
    const closeDeleteModal = document.getElementById('closeDeleteModal');
    const cancelDeleteBtn = document.getElementById('cancelDeleteBtn');
    const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
    
    if (closeDeleteModal) {
        closeDeleteModal.addEventListener('click', () => {
            deleteModal.classList.remove('active');
            accountToDelete = null;
        });
    }
    
    if (cancelDeleteBtn) {
        cancelDeleteBtn.addEventListener('click', () => {
            deleteModal.classList.remove('active');
            accountToDelete = null;
        });
    }
    
    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', confirmDeleteAccount);
    }

    // Edit Modal
    const editAccountModal = document.getElementById('editAccountModal');
    const closeEditModalBtn = document.getElementById('closeEditModal');
    const cancelEditBtn = document.getElementById('cancelEditBtn');
    const saveEditBtn = document.getElementById('saveEditBtn');

    if (closeEditModalBtn) {
        closeEditModalBtn.addEventListener('click', closeEditModal);
    }

    if (cancelEditBtn) {
        cancelEditBtn.addEventListener('click', closeEditModal);
    }

    if (saveEditBtn) {
        saveEditBtn.addEventListener('click', saveAccountEdit);
    }

    if (editAccountModal) {
        editAccountModal.addEventListener('click', (e) => {
            if (e.target === editAccountModal) {
                closeEditModal();
            }
        });
    }

    // Close modals on overlay click
    if (addAccountModal) {
        addAccountModal.addEventListener('click', (e) => {
            if (e.target === addAccountModal) {
                addAccountModal.classList.remove('active');
                clearAddAccountForm();
            }
        });
    }
    
    if (deleteModal) {
        deleteModal.addEventListener('click', (e) => {
            if (e.target === deleteModal) {
                deleteModal.classList.remove('active');
                accountToDelete = null;
            }
        });
    }
}

async function loadAccounts() {
    try {
        const response = await fetch('/api/accounts');
        accountsData = await response.json();

        updateStats();
        renderAccounts();

        // Load balances for each account asynchronously
        loadAccountBalances();
    } catch (error) {
        console.error('Error loading accounts:', error);
        showToast('Failed to load accounts', 'error');
    }
}

async function loadAccountBalances() {
    // Fetch balances for all accounts in parallel
    const balancePromises = accountsData.map(async (account) => {
        try {
            const response = await fetch(`/api/accounts/${account.id}/balance`);
            if (response.ok) {
                const data = await response.json();
                return { accountId: account.id, balance: data.balance || 0 };
            }
        } catch (error) {
            console.error(`Error loading balance for account ${account.id}:`, error);
        }
        return { accountId: account.id, balance: null };
    });

    const results = await Promise.all(balancePromises);

    // Update the balance displays
    results.forEach(({ accountId, balance }) => {
        const balanceEl = document.querySelector(`.account-balance[data-account-id="${accountId}"]`);
        if (balanceEl && balance !== null) {
            balanceEl.textContent = `$${balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        } else if (balanceEl) {
            balanceEl.textContent = 'N/A';
        }
    });
}

function updateStats() {
    const totalAccounts = accountsData.length;
    document.getElementById('accountCount').textContent = `${totalAccounts} account${totalAccounts !== 1 ? 's' : ''}`;
}

function renderAccounts() {
    const grid = document.getElementById('accountsGrid');
    const loadingState = document.getElementById('loadingState');
    const emptyState = document.getElementById('emptyState');

    loadingState.style.display = 'none';

    if (accountsData.length === 0) {
        grid.style.display = 'none';
        emptyState.style.display = 'flex';
        return;
    }

    grid.style.display = 'grid';
    emptyState.style.display = 'none';

    grid.innerHTML = accountsData.map(account => createAccountCard(account)).join('');

    // Attach event listeners
    grid.querySelectorAll('.account-card').forEach(card => {
        card.addEventListener('click', (e) => {
            // Don't navigate if clicking action buttons
            if (e.target.closest('.delete-account-btn')) return;
            if (e.target.closest('.edit-account-btn')) return;

            const accountId = card.dataset.accountId;
            window.location.href = `/accounts/${accountId}`;
        });
    });

    grid.querySelectorAll('.edit-account-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const accountId = btn.dataset.accountId;
            const accountName = btn.dataset.accountName;
            showEditModal(accountId, accountName);
        });
    });

    grid.querySelectorAll('.delete-account-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const accountId = btn.dataset.accountId;
            const accountName = btn.dataset.accountName;
            showDeleteModal(accountId, accountName);
        });
    });
}

function createAccountCard(account) {
    const balance = account.balance !== undefined ? account.balance : null;
    const balanceDisplay = balance !== null ? `$${balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'Loading...';

    return `
        <div class="account-card account-card-simple" data-account-id="${account.id}">
            <div class="account-card-header">
                <div class="account-info">
                    <div class="account-name-row">
                        <span class="account-name">${escapeHtml(account.name)}</span>
                        ${account.is_testnet ? '<span class="testnet-badge">TESTNET</span>' : ''}
                    </div>
                    <span class="account-balance" data-account-id="${account.id}">${balanceDisplay}</span>
                </div>
                <div class="account-actions">
                    <button class="account-action-btn edit edit-account-btn"
                            data-account-id="${account.id}"
                            data-account-name="${escapeHtml(account.name)}"
                            title="Edit Account">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                        </svg>
                    </button>
                    <button class="account-action-btn delete delete-account-btn"
                            data-account-id="${account.id}"
                            data-account-name="${escapeHtml(account.name)}"
                            title="Delete Account">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    `;
}

async function createAccount() {
    const name = document.getElementById('accountName').value.trim();
    const apiKey = document.getElementById('apiKey').value.trim();
    const apiSecret = document.getElementById('apiSecret').value.trim();
    const isTestnet = document.getElementById('isTestnet').checked;

    if (!name || !apiKey || !apiSecret) {
        showToast('Please fill in all required fields', 'error');
        return;
    }

    const submitBtn = document.getElementById('submitAccount');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnLoading = submitBtn.querySelector('.btn-loading');

    // Show loading state
    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';
    submitBtn.disabled = true;

    try {
        const response = await fetch('/api/accounts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, api_key: apiKey, api_secret: apiSecret, is_testnet: isTestnet })
        });

        const data = await response.json();

        if (response.ok) {
            document.getElementById('addAccountModal').classList.remove('active');
            clearAddAccountForm();
            // Wait for accounts to load before showing success
            await loadAccounts();
            showToast(`Account "${name}" created successfully`, 'success');
        } else {
            showToast(data.error || 'Failed to create account', 'error');
        }
    } catch (error) {
        console.error('Error creating account:', error);
        showToast('Failed to create account', 'error');
    } finally {
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
        submitBtn.disabled = false;
    }
}

function clearAddAccountForm() {
    document.getElementById('accountName').value = '';
    document.getElementById('apiKey').value = '';
    document.getElementById('apiSecret').value = '';
    document.getElementById('isTestnet').checked = false;
}

// ==================== EDIT ACCOUNT ====================

function showEditModal(accountId, accountName) {
    accountToEdit = { id: accountId, name: accountName };
    document.getElementById('editAccountName').value = accountName;
    document.getElementById('editAccountModal').classList.add('active');
    document.getElementById('editAccountName').focus();
}

function closeEditModal() {
    document.getElementById('editAccountModal').classList.remove('active');
    accountToEdit = null;
}

async function saveAccountEdit() {
    if (!accountToEdit) return;

    const newName = document.getElementById('editAccountName').value.trim();

    if (!newName) {
        showToast('Account name is required', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/accounts/${accountToEdit.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName })
        });

        const data = await response.json();

        if (response.ok) {
            showToast(`Account renamed to "${newName}"`, 'success');
            closeEditModal();
            loadAccounts();
        } else {
            showToast(data.error || 'Failed to update account', 'error');
        }
    } catch (error) {
        console.error('Error updating account:', error);
        showToast('Failed to update account', 'error');
    }
}

// ==================== DELETE ACCOUNT ====================

function showDeleteModal(accountId, accountName) {
    accountToDelete = { id: accountId, name: accountName };
    document.getElementById('deleteAccountName').textContent = accountName;
    document.getElementById('deleteModal').classList.add('active');
}

async function confirmDeleteAccount() {
    if (!accountToDelete) return;
    
    try {
        const response = await fetch(`/api/accounts/${accountToDelete.id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast(`Account "${accountToDelete.name}" deleted`, 'success');
            document.getElementById('deleteModal').classList.remove('active');
            accountToDelete = null;
            loadAccounts();
        } else {
            const data = await response.json();
            showToast(data.error || 'Failed to delete account', 'error');
        }
    } catch (error) {
        console.error('Error deleting account:', error);
        showToast('Failed to delete account', 'error');
    }
}

// ==================== DETAIL PAGE ====================

function initDetailPage() {
    loadAccountDetails();
    loadBalance();
    loadPositions();
    loadOrders();
    loadTrades();
    loadStats();
    setupDetailPageEventListeners();
    setupClosePositionModal();
    setupEditStopLossModal();
    setupEditTakeProfitModal();
    setupAddToPositionModal();
    setupSectionTabs();
}

function setupDetailPageEventListeners() {
    // Sync buttons (header and trades section)
    const syncBtn = document.getElementById('syncBtn');
    const syncTradesBtn = document.getElementById('syncTradesBtn');
    if (syncBtn) {
        syncBtn.addEventListener('click', syncTrades);
    }
    if (syncTradesBtn) {
        syncTradesBtn.addEventListener('click', syncTrades);
    }
    
    // Close All button
    const closeAllBtn = document.getElementById('closeAllBtn');
    const closeAllModal = document.getElementById('closeAllModal');
    const closeCloseAllModal = document.getElementById('closeCloseAllModal');
    const cancelCloseAllBtn = document.getElementById('cancelCloseAllBtn');
    const confirmCloseAllBtn = document.getElementById('confirmCloseAllBtn');
    
    if (closeAllBtn) {
        closeAllBtn.addEventListener('click', () => {
            closeAllModal.classList.add('active');
        });
    }
    
    if (closeCloseAllModal) {
        closeCloseAllModal.addEventListener('click', () => {
            closeAllModal.classList.remove('active');
        });
    }
    
    if (cancelCloseAllBtn) {
        cancelCloseAllBtn.addEventListener('click', () => {
            closeAllModal.classList.remove('active');
        });
    }
    
    if (confirmCloseAllBtn) {
        confirmCloseAllBtn.addEventListener('click', closeAllPositions);
    }
    
    // Refresh buttons
    const refreshBalanceBtn = document.getElementById('refreshBalanceBtn');
    if (refreshBalanceBtn) {
        refreshBalanceBtn.addEventListener('click', loadBalance);
    }
    
    const refreshPositionsBtn = document.getElementById('refreshPositionsBtn');
    if (refreshPositionsBtn) {
        refreshPositionsBtn.addEventListener('click', () => {
            loadPositions();
            loadOrders();
        });
    }
    
    const refreshTradesBtn = document.getElementById('refreshTradesBtn');
    if (refreshTradesBtn) {
        refreshTradesBtn.addEventListener('click', loadTrades);
    }
    
    // Close modal on overlay click
    if (closeAllModal) {
        closeAllModal.addEventListener('click', (e) => {
            if (e.target === closeAllModal) {
                closeAllModal.classList.remove('active');
            }
        });
    }
}

async function loadAccountDetails() {
    try {
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}`);
        if (!response.ok) {
            window.location.href = '/accounts';
            return;
        }

        const account = await response.json();

        document.getElementById('accountName').textContent = account.name;
        document.getElementById('accountKey').textContent = `API Key: ${account.api_key}`;

        if (account.is_testnet) {
            document.getElementById('testnetBadge').style.display = 'inline';
        }

        // Render attached bots
        renderAttachedBots(account.scripts || []);
    } catch (error) {
        console.error('Error loading account:', error);
        showToast('Failed to load account details', 'error');
    }
}

function renderAttachedBots(scripts) {
    const section = document.getElementById('attachedBotsSection');
    const grid = document.getElementById('attachedBotsGrid');
    const countEl = document.getElementById('botsCount');

    if (!section || !grid) return;

    if (!scripts || scripts.length === 0) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'block';
    countEl.textContent = `${scripts.length} bot${scripts.length !== 1 ? 's' : ''}`;

    grid.innerHTML = scripts.map(bot => `
        <a href="/scripts?open=${bot.id}" class="attached-bot-card" title="Open ${escapeHtml(bot.name)}">
            <div class="bot-card-header">
                <span class="bot-status-indicator ${bot.status}"></span>
                <span class="bot-name">${escapeHtml(bot.name)}</span>
            </div>
            <div class="bot-card-status">
                <span class="status-badge ${bot.status}">${bot.status}</span>
            </div>
        </a>
    `).join('');
}

async function loadBalance() {
    const refreshBtn = document.getElementById('refreshBalanceBtn');
    if (refreshBtn) refreshBtn.classList.add('loading');

    try {
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/balance`);
        const data = await response.json();

        if (response.ok) {
            const balanceAmount = document.querySelector('.balance-amount');
            if (balanceAmount) {
                balanceAmount.textContent = `$${data.balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            }

            // Store available balance for Add to Position modal
            availableBalance = data.available_balance || data.balance || 0;

            // Update starting balance if available
            if (data.starting_balance !== undefined) {
                const startBalEl = document.getElementById('startingBalance');
                if (startBalEl) {
                    startBalEl.textContent = `$${(data.starting_balance || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
                }
            }
            // Note: Realized profit and ROI are updated via loadStats() which uses actual trade PnL
        } else {
            console.error('Balance error:', data.error);
        }
    } catch (error) {
        console.error('Error loading balance:', error);
    } finally {
        if (refreshBtn) refreshBtn.classList.remove('loading');
    }
}

async function loadPositions() {
    const refreshBtn = document.getElementById('refreshPositionsBtn');
    const loading = document.getElementById('positionsLoading');
    const table = document.getElementById('positionsTable');
    const empty = document.getElementById('emptyPositions');
    const tbody = document.getElementById('positionsBody');
    const countEl = document.getElementById('positionsCount');

    if (refreshBtn) refreshBtn.classList.add('loading');
    if (loading) loading.style.display = 'flex';
    if (table) table.style.display = 'none';
    if (empty) empty.style.display = 'none';

    try {
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/positions`);
        const data = await response.json();

        // Handle new response format with debug info
        let positions = [];
        if (Array.isArray(data)) {
            positions = data;
        } else if (data.positions) {
            positions = data.positions;
            // Log debug info to console
            if (data._debug) {
                console.log('=== POSITIONS DEBUG INFO ===');
                console.log('Messages:', data._debug.messages);
                console.log('Regular orders from library:', data._debug.regular_orders);
                console.log('Direct API orders:', data._debug.direct_api_orders);
                console.log('Algo orders:', data._debug.algo_orders);
                console.log('============================');
            }
        }

        if (loading) loading.style.display = 'none';

        // Update count badge
        if (countEl) countEl.textContent = positions.length || 0;

        if (response.ok && positions.length > 0) {
            if (table) table.style.display = 'table';

            tbody.innerHTML = positions.map(pos => {
                // Calculate position size in $
                const sizeInDollars = pos.quantity * pos.mark_price;
                const hasStopLoss = pos.stop_price && pos.stop_price > 0;
                const hasTakeProfit = pos.tp_price && pos.tp_price > 0;
                const stopLossDisplay = hasStopLoss ? `$${pos.stop_price.toFixed(4)}` : '-';
                const takeProfitDisplay = hasTakeProfit ? `$${pos.tp_price.toFixed(4)}` : '-';
                
                return `
                <tr>
                    <td class="symbol">${pos.symbol}</td>
                    <td><span class="side ${pos.side.toLowerCase()}">${pos.side}</span></td>
                    <td>$${sizeInDollars.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td>$${pos.entry_price.toFixed(4)}</td>
                    <td>$${pos.mark_price.toFixed(4)}</td>
                    <td class="sl-tp-cell">
                        <div class="sl-tp-row">
                            <span class="sl-label">SL:</span>
                            <span class="${hasStopLoss ? 'has-sl' : 'no-sl'}">${stopLossDisplay}</span>
                            <button class="edit-sl-btn" title="Edit Stop Loss"
                                data-symbol="${pos.symbol}"
                                data-side="${pos.side}"
                                data-quantity="${pos.quantity}"
                                data-entry-price="${pos.entry_price}"
                                data-mark-price="${pos.mark_price}"
                                data-stop-price="${pos.stop_price || ''}"
                                data-stop-order-id="${pos.stop_order_id || ''}">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                                </svg>
                            </button>
                        </div>
                        <div class="sl-tp-row">
                            <span class="tp-label">TP:</span>
                            <span class="${hasTakeProfit ? 'has-tp' : 'no-tp'}">${takeProfitDisplay}</span>
                            <button class="edit-tp-btn" title="Edit Take Profit"
                                data-symbol="${pos.symbol}"
                                data-side="${pos.side}"
                                data-quantity="${pos.quantity}"
                                data-entry-price="${pos.entry_price}"
                                data-mark-price="${pos.mark_price}"
                                data-tp-price="${pos.tp_price || ''}"
                                data-tp-order-id="${pos.tp_order_id || ''}">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                                </svg>
                            </button>
                        </div>
                    </td>
                    <td class="${pos.unrealized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}">
                        ${pos.unrealized_pnl >= 0 ? '+' : ''}$${pos.unrealized_pnl.toFixed(2)}
                    </td>
                    <td><span class="leverage-badge">${pos.leverage}x</span></td>
                    <td class="actions-cell">
                        <button class="add-position-btn"
                            data-symbol="${pos.symbol}"
                            data-side="${pos.side}"
                            data-quantity="${pos.quantity}"
                            data-entry-price="${pos.entry_price}"
                            data-mark-price="${pos.mark_price}"
                            data-leverage="${pos.leverage}">
                            Add
                        </button>
                        <button class="close-position-btn"
                            data-symbol="${pos.symbol}"
                            data-side="${pos.side}"
                            data-quantity="${pos.quantity}"
                            data-pnl="${pos.unrealized_pnl}"
                            data-mark-price="${pos.mark_price}">
                            Close
                        </button>
                    </td>
                </tr>
            `}).join('');

            // Add event listeners for close buttons
            tbody.querySelectorAll('.close-position-btn').forEach(btn => {
                btn.addEventListener('click', () => openClosePositionModal(btn.dataset));
            });

            // Add event listeners for add-to-position buttons
            tbody.querySelectorAll('.add-position-btn').forEach(btn => {
                btn.addEventListener('click', () => openAddToPositionModal(btn.dataset));
            });

            // Add event listeners for edit stop-loss buttons
            tbody.querySelectorAll('.edit-sl-btn').forEach(btn => {
                btn.addEventListener('click', () => openEditStopLossModal(btn.dataset));
            });

            // Add event listeners for edit take-profit buttons
            tbody.querySelectorAll('.edit-tp-btn').forEach(btn => {
                btn.addEventListener('click', () => openEditTakeProfitModal(btn.dataset));
            });
        } else {
            if (empty) empty.style.display = 'flex';
        }
    } catch (error) {
        console.error('Error loading positions:', error);
        if (loading) loading.style.display = 'none';
        if (empty) empty.style.display = 'flex';
    } finally {
        if (refreshBtn) refreshBtn.classList.remove('loading');
    }
}

async function loadOrders() {
    const loading = document.getElementById('ordersLoading');
    const table = document.getElementById('ordersTable');
    const empty = document.getElementById('emptyOrders');
    const tbody = document.getElementById('ordersBody');
    const countEl = document.getElementById('ordersCount');

    if (!tbody) return; // Not on detail page

    if (loading) loading.style.display = 'flex';
    if (table) table.style.display = 'none';
    if (empty) empty.style.display = 'none';

    try {
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/orders`);
        const data = await response.json();

        // Handle new response format with debug info
        let orders = [];
        if (Array.isArray(data)) {
            orders = data;
        } else if (data.orders) {
            orders = data.orders;
            // Log debug info to console
            if (data._debug) {
                console.log('=== ORDERS DEBUG INFO ===');
                console.log('Messages:', data._debug.messages);
                console.log('Regular orders from library:', data._debug.regular_orders);
                console.log('Direct API orders:', data._debug.direct_api_orders);
                console.log('Algo orders:', data._debug.algo_orders);
                console.log('=========================');
            }
        }

        if (loading) loading.style.display = 'none';

        // Update count badge
        if (countEl) countEl.textContent = orders.length || 0;

        if (response.ok && orders.length > 0) {
            if (table) table.style.display = 'table';

            tbody.innerHTML = orders.map(order => {
                const orderTime = new Date(order.time).toLocaleString();
                const typeClass = getOrderTypeClass(order.type);
                const priceDisplay = order.price > 0 ? `$${order.price.toFixed(4)}` : 'Market';
                const stopPriceDisplay = order.stop_price ? `$${order.stop_price.toFixed(4)}` : '-';

                return `
                <tr>
                    <td class="order-time">${orderTime}</td>
                    <td class="symbol">${order.symbol}</td>
                    <td><span class="order-type ${typeClass}">${formatOrderType(order.type)}</span></td>
                    <td><span class="side ${order.side.toLowerCase()}">${order.side}</span></td>
                    <td>${order.quantity}</td>
                    <td>${priceDisplay}</td>
                    <td>${stopPriceDisplay}</td>
                    <td>${order.reduce_only ? 'Yes' : 'No'}</td>
                    <td>
                        <button class="cancel-order-btn"
                            data-order-id="${order.order_id}"
                            data-symbol="${order.symbol}"
                            data-is-algo="${order.is_algo || false}">
                            Cancel
                        </button>
                    </td>
                </tr>
            `}).join('');

            // Add event listeners for cancel buttons
            tbody.querySelectorAll('.cancel-order-btn').forEach(btn => {
                const isAlgo = btn.dataset.isAlgo === 'true';
                btn.addEventListener('click', () => cancelOrder(btn.dataset.orderId, btn.dataset.symbol, isAlgo));
            });
        } else {
            if (empty) empty.style.display = 'flex';
        }
    } catch (error) {
        console.error('Error loading orders:', error);
        if (loading) loading.style.display = 'none';
        if (empty) empty.style.display = 'flex';
    }
}

function getOrderTypeClass(type) {
    if (type.includes('LIMIT')) return 'limit';
    if (type.includes('MARKET')) return 'market';
    if (type.includes('STOP')) return 'stop';
    if (type.includes('TAKE_PROFIT')) return 'take-profit';
    return '';
}

function formatOrderType(type) {
    return type.replace(/_/g, ' ');
}

async function cancelOrder(orderId, symbol, isAlgo = false) {
    if (!confirm(`Are you sure you want to cancel this order?`)) return;

    try {
        console.log(`%c[Cancel Order] Attempting to cancel order ${orderId} for ${symbol}`, 'color: #3b82f6; font-weight: bold');
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/orders/${orderId}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol, is_algo: isAlgo })
        });

        const data = await response.json();

        // Always log debug info from server
        if (data._debug && data._debug.length > 0) {
            console.log('%c[Cancel Order] Server Debug Log:', 'color: #f59e0b; font-weight: bold');
            console.table(data._debug.map((msg, i) => ({ step: i + 1, message: msg })));
        }

        if (response.ok) {
            console.log('%c[Cancel Order] SUCCESS', 'color: #22c55e; font-weight: bold');
            showToast('Order cancelled', 'success');
            loadOrders();
            loadPositions();
        } else {
            console.error('%c[Cancel Order] FAILED:', 'color: #ef4444; font-weight: bold', data.error);
            // Show detailed error in toast
            const errorMsg = data.error || 'Failed to cancel order';
            showToast(`Cancel failed: ${errorMsg}`, 'error');
        }
    } catch (error) {
        console.error('%c[Cancel Order] EXCEPTION:', 'color: #ef4444; font-weight: bold', error);
        showToast(`Cancel failed: ${error.message}`, 'error');
    }
}

function setupSectionTabs() {
    const tabs = document.querySelectorAll('.section-tab');
    const positionsTab = document.getElementById('positionsTab');
    const ordersTab = document.getElementById('ordersTab');

    if (!tabs.length) return;

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Update active tab
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Show corresponding content
            const tabName = tab.dataset.tab;
            if (tabName === 'positions') {
                if (positionsTab) positionsTab.classList.add('active');
                if (ordersTab) ordersTab.classList.remove('active');
            } else if (tabName === 'orders') {
                if (positionsTab) positionsTab.classList.remove('active');
                if (ordersTab) ordersTab.classList.add('active');
            }
        });
    });
}

async function loadTrades() {
    const loading = document.getElementById('tradesLoading');
    const table = document.getElementById('tradesTable');
    const empty = document.getElementById('emptyTrades');
    const tbody = document.getElementById('tradesBody');
    
    if (loading) loading.style.display = 'flex';
    if (table) table.style.display = 'none';
    if (empty) empty.style.display = 'none';
    
    try {
        const response = await fetch(`/api/trades?account_id=${ACCOUNT_ID}&limit=20`);
        const trades = await response.json();
        
        if (loading) loading.style.display = 'none';
        
        if (trades.length > 0) {
            if (table) table.style.display = 'table';

            tbody.innerHTML = trades.map(trade => {
                const tradeTime = trade.trade_time
                    ? new Date(trade.trade_time).toLocaleString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                    })
                    : 'Unknown';

                // Calculate trade size in $
                const sizeInDollars = trade.quantity * trade.price;
                const fee = trade.commission || 0;

                return `
                    <tr>
                        <td>${tradeTime}</td>
                        <td class="symbol">${trade.symbol}</td>
                        <td><span class="side ${trade.side.toLowerCase()}">${trade.side}</span></td>
                        <td>$${sizeInDollars.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                        <td>$${trade.price.toFixed(4)}</td>
                        <td class="${trade.realized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}">
                            ${trade.realized_pnl >= 0 ? '+' : ''}$${trade.realized_pnl.toFixed(2)}
                        </td>
                        <td class="fee">$${fee.toFixed(4)}</td>
                    </tr>
                `;
            }).join('');
        } else {
            if (empty) empty.style.display = 'flex';
        }
    } catch (error) {
        console.error('Error loading trades:', error);
        if (loading) loading.style.display = 'none';
        if (empty) empty.style.display = 'flex';
    }
}

async function loadStats() {
    try {
        const response = await fetch(`/api/trades/stats?account_id=${ACCOUNT_ID}`);
        const stats = await response.json();
        
        if (response.ok) {
            updateStatsDisplay(stats);
        }
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

function updateStatsDisplay(stats) {
    if (!stats) return;
    
    // Primary stats
    document.getElementById('statTotalTrades').textContent = stats.total_trades || 0;
    
    const winRate = stats.win_rate || 0;
    const winRateEl = document.getElementById('statWinRate');
    winRateEl.textContent = `${winRate}%`;
    winRateEl.className = `mini-stat-value ${winRate >= 50 ? 'positive' : (winRate > 0 ? 'negative' : '')}`;
    
    const pnlElement = document.getElementById('statTotalPnL');
    const pnl = stats.total_pnl || 0;
    pnlElement.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
    pnlElement.className = `mini-stat-value ${pnl >= 0 ? 'positive' : 'negative'}`;
    
    const profitFactor = stats.profit_factor || 0;
    const pfEl = document.getElementById('statProfitFactor');
    if (pfEl) {
        pfEl.textContent = profitFactor >= 999 ? '∞' : profitFactor.toFixed(2);
        pfEl.className = `mini-stat-value ${profitFactor >= 1 ? 'positive' : 'negative'}`;
    }
    
    // Secondary stats
    const winningEl = document.getElementById('statWinningTrades');
    if (winningEl) {
        winningEl.textContent = stats.winning_trades || 0;
        winningEl.className = 'mini-stat-value positive';
    }
    
    const losingEl = document.getElementById('statLosingTrades');
    if (losingEl) {
        losingEl.textContent = stats.losing_trades || 0;
        losingEl.className = 'mini-stat-value negative';
    }
    
    const avgWin = stats.avg_win || 0;
    const avgWinEl = document.getElementById('statAvgWin');
    if (avgWinEl) {
        avgWinEl.textContent = `+$${avgWin.toFixed(2)}`;
        avgWinEl.className = 'mini-stat-value positive';
    }
    
    const avgLoss = stats.avg_loss || 0;
    const avgLossEl = document.getElementById('statAvgLoss');
    if (avgLossEl) {
        avgLossEl.textContent = `$${avgLoss.toFixed(2)}`;
        avgLossEl.className = 'mini-stat-value negative';
    }
    
    const largestWin = stats.largest_win || 0;
    const largestWinEl = document.getElementById('statLargestWin');
    if (largestWinEl) {
        largestWinEl.textContent = `+$${largestWin.toFixed(2)}`;
        largestWinEl.className = 'mini-stat-value positive';
    }
    
    const largestLoss = stats.largest_loss || 0;
    const largestLossEl = document.getElementById('statLargestLoss');
    if (largestLossEl) {
        largestLossEl.textContent = `$${largestLoss.toFixed(2)}`;
        largestLossEl.className = 'mini-stat-value negative';
    }
    
    document.getElementById('statTotalFees').textContent = `$${(stats.total_commission || 0).toFixed(2)}`;
    
    const volumeEl = document.getElementById('statTotalVolume');
    if (volumeEl) {
        const volume = stats.total_volume || 0;
        volumeEl.textContent = volume >= 1000000 ? `$${(volume / 1000000).toFixed(1)}M` : 
                              volume >= 1000 ? `$${(volume / 1000).toFixed(1)}K` : 
                              `$${volume.toFixed(0)}`;
    }
    
    // Balance related stats (if available from sync)
    if (stats.starting_balance !== undefined) {
        const startBalEl = document.getElementById('startingBalance');
        if (startBalEl) startBalEl.textContent = `$${(stats.starting_balance || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
    }
    
    if (stats.net_profit !== undefined) {
        const netProfitEl = document.getElementById('netProfit');
        if (netProfitEl) {
            const netProfit = stats.net_profit || 0;
            netProfitEl.textContent = `${netProfit >= 0 ? '+' : ''}$${netProfit.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
            netProfitEl.className = `detail-value ${netProfit >= 0 ? 'positive' : 'negative'}`;
        }
    }
    
    if (stats.net_profit_pct !== undefined) {
        const netPctEl = document.getElementById('netProfitPct');
        if (netPctEl) {
            const pct = stats.net_profit_pct || 0;
            netPctEl.textContent = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
            netPctEl.className = `detail-value ${pct >= 0 ? 'positive' : 'negative'}`;
        }
    }
    
    if (stats.unrealized_pnl !== undefined) {
        const unrealizedEl = document.getElementById('unrealizedPnl');
        if (unrealizedEl) {
            const upnl = stats.unrealized_pnl || 0;
            unrealizedEl.textContent = `${upnl >= 0 ? '+' : ''}$${upnl.toFixed(2)}`;
            unrealizedEl.className = `detail-value ${upnl >= 0 ? 'positive' : 'negative'}`;
        }
    }
}

async function syncTrades() {
    console.log('=== syncTrades() called ===');
    console.log('ACCOUNT_ID:', ACCOUNT_ID);

    const syncBtn = document.getElementById('syncBtn');
    const syncModal = document.getElementById('syncModal');
    const syncProgress = document.getElementById('syncProgress');
    const syncStatus = document.getElementById('syncStatus');

    syncBtn.classList.add('syncing');
    syncModal.classList.add('active');
    syncProgress.style.width = '20%';
    syncStatus.textContent = 'Fetching account balance...';

    try {
        // Simulate progress stages
        setTimeout(() => {
            syncProgress.style.width = '40%';
            syncStatus.textContent = 'Fetching trades from Binance...';
        }, 500);
        
        setTimeout(() => {
            syncProgress.style.width = '70%';
            syncStatus.textContent = 'Processing and calculating stats...';
        }, 2000);

        const url = `/api/accounts/${ACCOUNT_ID}/sync`;
        const response = await fetch(url, { method: 'POST' });
        const data = await response.json();

        syncProgress.style.width = '100%';

        if (response.ok) {
            syncStatus.textContent = `Done! Added ${data.new_trades} new trades.`;
            showToast(`Synced ${data.new_trades} new trades`, 'success');

            // Update balance display immediately with sync data
            if (data.balance !== undefined) {
                const balanceAmount = document.querySelector('.balance-amount');
                if (balanceAmount) {
                    balanceAmount.textContent = `$${data.balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                }
            }
            
            // Update stats immediately with sync data
            if (data.stats) {
                updateStatsDisplay(data.stats);
            }

            // Reload other data
            setTimeout(() => {
                syncModal.classList.remove('active');
                loadTrades();
                loadPositions();
            }, 1500);
        } else {
            console.error('Sync failed with error:', data.error);
            syncModal.classList.remove('active');
            showToast(data.error || 'Sync failed', 'error');
        }
    } catch (error) {
        console.error('Error syncing trades:', error);
        syncModal.classList.remove('active');
        showToast('Failed to sync trades', 'error');
    } finally {
        syncBtn.classList.remove('syncing');
    }
}

async function closeAllPositions() {
    const confirmBtn = document.getElementById('confirmCloseAllBtn');
    const btnText = confirmBtn.querySelector('.btn-text');
    const btnLoading = confirmBtn.querySelector('.btn-loading');
    
    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';
    confirmBtn.disabled = true;
    
    try {
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/close-all`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            if (data.closed.length > 0) {
                showToast(`Closed ${data.closed.length} position(s)`, 'success');
            } else {
                showToast('No positions to close', 'info');
            }
            
            if (data.errors.length > 0) {
                data.errors.forEach(err => showToast(err, 'error'));
            }
            
            document.getElementById('closeAllModal').classList.remove('active');
            loadPositions();
            loadBalance();
        } else {
            showToast(data.error || 'Failed to close positions', 'error');
        }
    } catch (error) {
        console.error('Error closing positions:', error);
        showToast('Failed to close positions', 'error');
    } finally {
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
        confirmBtn.disabled = false;
    }
}

// ==================== CLOSE POSITION ====================

let currentPosition = null;

function openClosePositionModal(posData) {
    currentPosition = {
        symbol: posData.symbol,
        side: posData.side,
        quantity: parseFloat(posData.quantity),
        pnl: parseFloat(posData.pnl),
        markPrice: parseFloat(posData.markPrice)
    };

    // Update modal content
    document.getElementById('closePositionSymbol').textContent = currentPosition.symbol;
    const sideEl = document.getElementById('closePositionSide');
    sideEl.textContent = currentPosition.side;
    sideEl.className = `position-side ${currentPosition.side.toLowerCase()}`;
    document.getElementById('closePositionSize').textContent = currentPosition.quantity;
    const pnlEl = document.getElementById('closePositionPnl');
    pnlEl.textContent = `${currentPosition.pnl >= 0 ? '+' : ''}$${currentPosition.pnl.toFixed(2)}`;
    pnlEl.className = currentPosition.pnl >= 0 ? 'pnl-positive' : 'pnl-negative';

    // Reset slider to 100%
    document.getElementById('closePercentSlider').value = 100;
    document.getElementById('closePercentValue').textContent = '100';

    // Clear USDC input
    document.getElementById('closeUsdc').value = '';
    updateCloseQuantity(100);

    // Reset percentage buttons
    document.querySelectorAll('.pct-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelector('.pct-btn[data-pct="100"]').classList.add('active');

    // Show modal
    document.getElementById('closePositionModal').classList.add('active');
}

function updateCloseQuantity(percent) {
    if (!currentPosition) return;
    const qty = (currentPosition.quantity * percent / 100).toFixed(6);
    document.getElementById('closeQuantityValue').textContent = qty;
}

function setupClosePositionModal() {
    const modal = document.getElementById('closePositionModal');
    const closeBtn = document.getElementById('closePositionModalBtn');
    const cancelBtn = document.getElementById('cancelClosePositionBtn');
    const confirmBtn = document.getElementById('confirmClosePositionBtn');
    const slider = document.getElementById('closePercentSlider');
    const pctBtns = document.querySelectorAll('.pct-btn');

    // Close modal handlers
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            modal.classList.remove('active');
            currentPosition = null;
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            modal.classList.remove('active');
            currentPosition = null;
        });
    }

    // Close on overlay click
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
                currentPosition = null;
            }
        });
    }

    // Slider change
    if (slider) {
        slider.addEventListener('input', (e) => {
            const val = e.target.value;
            document.getElementById('closePercentValue').textContent = val;
            updateCloseQuantity(val);

            // Update active button
            pctBtns.forEach(btn => btn.classList.remove('active'));
            const matchingBtn = document.querySelector(`.pct-btn[data-pct="${val}"]`);
            if (matchingBtn) matchingBtn.classList.add('active');
        });
    }

    // Percentage buttons
    pctBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const pct = btn.dataset.pct;
            slider.value = pct;
            document.getElementById('closePercentValue').textContent = pct;
            document.getElementById('closeUsdc').value = ''; // Clear USDC input
            updateCloseQuantity(pct);

            pctBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });

    // USDC input - calculate quantity from USDC
    const usdcInput = document.getElementById('closeUsdc');
    if (usdcInput) {
        usdcInput.addEventListener('input', () => {
            if (!currentPosition) return;
            const usdc = parseFloat(usdcInput.value) || 0;
            const qty = usdc / currentPosition.markPrice;
            document.getElementById('closeQuantityValue').textContent = qty.toFixed(6);

            // Clear percentage selection when using USDC
            pctBtns.forEach(b => b.classList.remove('active'));
        });
    }

    // Confirm close
    if (confirmBtn) {
        confirmBtn.addEventListener('click', closePosition);
    }
}

async function closePosition() {
    if (!currentPosition) return;

    const confirmBtn = document.getElementById('confirmClosePositionBtn');
    const btnText = confirmBtn.querySelector('.btn-text');
    const btnLoading = confirmBtn.querySelector('.btn-loading');

    // Check if USDC was entered, otherwise use percentage
    const usdcValue = parseFloat(document.getElementById('closeUsdc').value);
    let quantityToClose;
    let closeMessage;

    if (usdcValue && usdcValue > 0) {
        quantityToClose = usdcValue / currentPosition.markPrice;
        closeMessage = `Closed $${usdcValue.toFixed(2)} of ${currentPosition.symbol} position`;
    } else {
        const percent = parseInt(document.getElementById('closePercentSlider').value);
        quantityToClose = (currentPosition.quantity * percent / 100);
        closeMessage = `Closed ${percent}% of ${currentPosition.symbol} position`;
    }

    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';
    confirmBtn.disabled = true;

    try {
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/close-position`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentPosition.symbol,
                side: currentPosition.side,
                quantity: quantityToClose
            })
        });

        const data = await response.json();

        if (response.ok) {
            showToast(closeMessage, 'success');
            document.getElementById('closePositionModal').classList.remove('active');
            currentPosition = null;
            loadPositions();
            loadBalance();
        } else {
            showToast(data.error || 'Failed to close position', 'error');
        }
    } catch (error) {
        console.error('Error closing position:', error);
        showToast('Failed to close position', 'error');
    } finally {
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
        confirmBtn.disabled = false;
    }
}

// ==================== UTILITIES ====================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ==================== STOP LOSS MANAGEMENT ====================

let currentStopLossPosition = null;

function openEditStopLossModal(posData) {
    currentStopLossPosition = {
        symbol: posData.symbol,
        side: posData.side,
        quantity: parseFloat(posData.quantity),
        entryPrice: parseFloat(posData.entryPrice),
        markPrice: parseFloat(posData.markPrice),
        stopPrice: posData.stopPrice ? parseFloat(posData.stopPrice) : null,
        stopOrderId: posData.stopOrderId ? parseInt(posData.stopOrderId) : null
    };

    // Update modal content
    document.getElementById('slSymbol').textContent = currentStopLossPosition.symbol;
    const sideEl = document.getElementById('slSide');
    sideEl.textContent = currentStopLossPosition.side;
    sideEl.className = `position-side ${currentStopLossPosition.side.toLowerCase()}`;
    
    document.getElementById('slEntryPrice').textContent = `$${currentStopLossPosition.entryPrice.toFixed(4)}`;
    document.getElementById('slMarkPrice').textContent = `$${currentStopLossPosition.markPrice.toFixed(4)}`;
    document.getElementById('slQuantity').textContent = currentStopLossPosition.quantity;
    
    const currentStopEl = document.getElementById('slCurrentStop');
    const removeBtn = document.getElementById('removeStopLossBtn');
    
    if (currentStopLossPosition.stopPrice) {
        currentStopEl.textContent = `$${currentStopLossPosition.stopPrice.toFixed(4)}`;
        currentStopEl.className = 'has-sl';
        document.getElementById('newStopPrice').value = currentStopLossPosition.stopPrice;
        removeBtn.style.display = 'inline-flex';
    } else {
        currentStopEl.textContent = 'None';
        currentStopEl.className = 'no-sl';
        document.getElementById('newStopPrice').value = '';
        removeBtn.style.display = 'none';
    }
    
    // Show hint based on position side
    const hintEl = document.getElementById('slHint');
    if (currentStopLossPosition.side === 'LONG') {
        hintEl.innerHTML = `<span class="hint-warning">For LONG position, stop loss should be <strong>below</strong> entry price ($${currentStopLossPosition.entryPrice.toFixed(2)})</span>`;
    } else {
        hintEl.innerHTML = `<span class="hint-warning">For SHORT position, stop loss should be <strong>above</strong> entry price ($${currentStopLossPosition.entryPrice.toFixed(2)})</span>`;
    }

    // Show modal
    document.getElementById('editStopLossModal').classList.add('active');
}

function setupEditStopLossModal() {
    const modal = document.getElementById('editStopLossModal');
    if (!modal) return;
    
    const closeBtn = document.getElementById('closeEditStopLossModal');
    const cancelBtn = document.getElementById('cancelEditStopLossBtn');
    const confirmBtn = document.getElementById('confirmEditStopLossBtn');
    const removeBtn = document.getElementById('removeStopLossBtn');

    // Close modal handlers
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            modal.classList.remove('active');
            currentStopLossPosition = null;
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            modal.classList.remove('active');
            currentStopLossPosition = null;
        });
    }

    // Close on overlay click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('active');
            currentStopLossPosition = null;
        }
    });

    // Confirm update
    if (confirmBtn) {
        confirmBtn.addEventListener('click', updateStopLoss);
    }
    
    // Remove stop loss
    if (removeBtn) {
        removeBtn.addEventListener('click', removeStopLoss);
    }
}

async function updateStopLoss() {
    if (!currentStopLossPosition) return;

    const newStopPrice = parseFloat(document.getElementById('newStopPrice').value);
    
    if (!newStopPrice || newStopPrice <= 0) {
        showToast('Please enter a valid stop price', 'error');
        return;
    }
    
    // Validate stop price direction
    if (currentStopLossPosition.side === 'LONG' && newStopPrice >= currentStopLossPosition.markPrice) {
        showToast('Stop loss for LONG position should be below current price', 'error');
        return;
    }
    if (currentStopLossPosition.side === 'SHORT' && newStopPrice <= currentStopLossPosition.markPrice) {
        showToast('Stop loss for SHORT position should be above current price', 'error');
        return;
    }

    const confirmBtn = document.getElementById('confirmEditStopLossBtn');
    const btnText = confirmBtn.querySelector('.btn-text');
    const btnLoading = confirmBtn.querySelector('.btn-loading');

    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';
    confirmBtn.disabled = true;

    try {
        console.log(`%c[Update SL] Updating stop loss for ${currentStopLossPosition.symbol}`, 'color: #3b82f6; font-weight: bold');
        console.log(`  Old order ID: ${currentStopLossPosition.stopOrderId || 'none'}, New price: ${newStopPrice}`);
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/update-stop-loss`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentStopLossPosition.symbol,
                position_side: currentStopLossPosition.side,
                stop_price: newStopPrice,
                old_order_id: currentStopLossPosition.stopOrderId
            })
        });

        const data = await response.json();

        // Always log debug info from server
        if (data._debug && data._debug.length > 0) {
            console.log('%c[Update SL] Server Debug Log:', 'color: #f59e0b; font-weight: bold');
            console.table(data._debug.map((msg, i) => ({ step: i + 1, message: msg })));
        }

        if (response.ok) {
            console.log('%c[Update SL] SUCCESS', 'color: #22c55e; font-weight: bold');
            showToast(`Stop loss set at $${newStopPrice.toFixed(4)}`, 'success');
            document.getElementById('editStopLossModal').classList.remove('active');
            currentStopLossPosition = null;
            await loadPositions();
            loadOrders();
        } else {
            console.error('%c[Update SL] FAILED:', 'color: #ef4444; font-weight: bold', data.error);
            showToast(`Update SL failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('%c[Update SL] EXCEPTION:', 'color: #ef4444; font-weight: bold', error);
        showToast(`Update SL failed: ${error.message}`, 'error');
    } finally {
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
        confirmBtn.disabled = false;
    }
}

async function removeStopLoss() {
    if (!currentStopLossPosition || !currentStopLossPosition.stopOrderId) return;

    const removeBtn = document.getElementById('removeStopLossBtn');
    removeBtn.disabled = true;
    removeBtn.textContent = 'Removing...';

    try {
        console.log(`%c[Remove SL] Removing stop loss for ${currentStopLossPosition.symbol}`, 'color: #3b82f6; font-weight: bold');
        console.log(`  Order ID: ${currentStopLossPosition.stopOrderId}`);
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/cancel-stop-loss`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentStopLossPosition.symbol,
                order_id: currentStopLossPosition.stopOrderId
            })
        });

        const data = await response.json();

        // Always log debug info from server
        if (data._debug && data._debug.length > 0) {
            console.log('%c[Remove SL] Server Debug Log:', 'color: #f59e0b; font-weight: bold');
            console.table(data._debug.map((msg, i) => ({ step: i + 1, message: msg })));
        }

        if (response.ok) {
            console.log('%c[Remove SL] SUCCESS', 'color: #22c55e; font-weight: bold');
            showToast('Stop loss removed', 'success');
            document.getElementById('editStopLossModal').classList.remove('active');
            currentStopLossPosition = null;
            await loadPositions();
            loadOrders();
        } else {
            console.error('%c[Remove SL] FAILED:', 'color: #ef4444; font-weight: bold', data.error);
            showToast(`Remove SL failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('%c[Remove SL] EXCEPTION:', 'color: #ef4444; font-weight: bold', error);
        showToast(`Remove SL failed: ${error.message}`, 'error');
    } finally {
        removeBtn.disabled = false;
        removeBtn.textContent = 'Remove SL';
    }
}

// ==================== TAKE PROFIT MANAGEMENT ====================

let currentTakeProfitPosition = null;

function openEditTakeProfitModal(posData) {
    currentTakeProfitPosition = {
        symbol: posData.symbol,
        side: posData.side,
        quantity: parseFloat(posData.quantity),
        entryPrice: parseFloat(posData.entryPrice),
        markPrice: parseFloat(posData.markPrice),
        tpPrice: posData.tpPrice ? parseFloat(posData.tpPrice) : null,
        tpOrderId: posData.tpOrderId ? parseInt(posData.tpOrderId) : null
    };

    // Update modal content
    document.getElementById('tpSymbol').textContent = currentTakeProfitPosition.symbol;
    const sideEl = document.getElementById('tpSide');
    sideEl.textContent = currentTakeProfitPosition.side;
    sideEl.className = `position-side ${currentTakeProfitPosition.side.toLowerCase()}`;

    document.getElementById('tpEntryPrice').textContent = `$${currentTakeProfitPosition.entryPrice.toFixed(4)}`;
    document.getElementById('tpMarkPrice').textContent = `$${currentTakeProfitPosition.markPrice.toFixed(4)}`;

    const currentTPEl = document.getElementById('tpCurrentTP');
    const removeBtn = document.getElementById('removeTakeProfitBtn');

    if (currentTakeProfitPosition.tpPrice && currentTakeProfitPosition.tpOrderId) {
        currentTPEl.textContent = `$${currentTakeProfitPosition.tpPrice.toFixed(4)}`;
        currentTPEl.className = 'has-tp';
        removeBtn.style.display = 'block';
    } else {
        currentTPEl.textContent = currentTakeProfitPosition.tpPrice ? `$${currentTakeProfitPosition.tpPrice.toFixed(4)}` : 'None';
        currentTPEl.className = currentTakeProfitPosition.tpPrice ? 'has-tp' : 'no-tp';
        removeBtn.style.display = 'none';
    }

    // Clear input
    document.getElementById('newTakeProfitPrice').value = '';

    // Show hint based on position side
    const hintEl = document.getElementById('tpHint');
    if (currentTakeProfitPosition.side === 'LONG') {
        hintEl.innerHTML = `<span class="hint-success">For LONG position, take profit should be <strong>above</strong> entry price ($${currentTakeProfitPosition.entryPrice.toFixed(2)})</span>`;
    } else {
        hintEl.innerHTML = `<span class="hint-success">For SHORT position, take profit should be <strong>below</strong> entry price ($${currentTakeProfitPosition.entryPrice.toFixed(2)})</span>`;
    }

    // Show modal
    document.getElementById('editTakeProfitModal').classList.add('active');
}

function setupEditTakeProfitModal() {
    const modal = document.getElementById('editTakeProfitModal');
    if (!modal) return;

    const closeBtn = document.getElementById('closeEditTakeProfitModal');
    const cancelBtn = document.getElementById('cancelEditTakeProfitBtn');
    const confirmBtn = document.getElementById('confirmEditTakeProfitBtn');
    const removeBtn = document.getElementById('removeTakeProfitBtn');

    // Close modal handlers
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            modal.classList.remove('active');
            currentTakeProfitPosition = null;
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            modal.classList.remove('active');
            currentTakeProfitPosition = null;
        });
    }

    // Close on overlay click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('active');
            currentTakeProfitPosition = null;
        }
    });

    // Confirm button
    if (confirmBtn) {
        confirmBtn.addEventListener('click', updateTakeProfit);
    }

    // Remove button
    if (removeBtn) {
        removeBtn.addEventListener('click', removeTakeProfit);
    }
}

async function updateTakeProfit() {
    if (!currentTakeProfitPosition) return;

    const newTPPrice = parseFloat(document.getElementById('newTakeProfitPrice').value);

    if (!newTPPrice || newTPPrice <= 0) {
        showToast('Please enter a valid take profit price', 'error');
        return;
    }

    // Validate TP price direction
    if (currentTakeProfitPosition.side === 'LONG' && newTPPrice <= currentTakeProfitPosition.markPrice) {
        showToast('Take profit for LONG position should be above current price', 'error');
        return;
    }
    if (currentTakeProfitPosition.side === 'SHORT' && newTPPrice >= currentTakeProfitPosition.markPrice) {
        showToast('Take profit for SHORT position should be below current price', 'error');
        return;
    }

    const confirmBtn = document.getElementById('confirmEditTakeProfitBtn');
    const btnText = confirmBtn.querySelector('.btn-text');
    const btnLoading = confirmBtn.querySelector('.btn-loading');

    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';
    confirmBtn.disabled = true;

    try {
        console.log(`%c[Update TP] Updating take profit for ${currentTakeProfitPosition.symbol}`, 'color: #3b82f6; font-weight: bold');
        console.log(`  Old order ID: ${currentTakeProfitPosition.tpOrderId || 'none'}, New price: ${newTPPrice}`);
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/update-take-profit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentTakeProfitPosition.symbol,
                position_side: currentTakeProfitPosition.side,
                tp_price: newTPPrice,
                old_order_id: currentTakeProfitPosition.tpOrderId
            })
        });

        const data = await response.json();

        // Always log debug info from server
        if (data._debug && data._debug.length > 0) {
            console.log('%c[Update TP] Server Debug Log:', 'color: #f59e0b; font-weight: bold');
            console.table(data._debug.map((msg, i) => ({ step: i + 1, message: msg })));
        }

        if (response.ok) {
            console.log('%c[Update TP] SUCCESS', 'color: #22c55e; font-weight: bold');
            showToast(`Take profit set at $${newTPPrice.toFixed(4)}`, 'success');
            document.getElementById('editTakeProfitModal').classList.remove('active');
            currentTakeProfitPosition = null;
            await loadPositions();
            loadOrders();
        } else {
            console.error('%c[Update TP] FAILED:', 'color: #ef4444; font-weight: bold', data.error);
            showToast(`Update TP failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('%c[Update TP] EXCEPTION:', 'color: #ef4444; font-weight: bold', error);
        showToast(`Update TP failed: ${error.message}`, 'error');
    } finally {
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
        confirmBtn.disabled = false;
    }
}

async function removeTakeProfit() {
    if (!currentTakeProfitPosition || !currentTakeProfitPosition.tpOrderId) return;

    const removeBtn = document.getElementById('removeTakeProfitBtn');
    removeBtn.disabled = true;
    removeBtn.textContent = 'Removing...';

    try {
        console.log(`%c[Remove TP] Removing take profit for ${currentTakeProfitPosition.symbol}`, 'color: #3b82f6; font-weight: bold');
        console.log(`  Order ID: ${currentTakeProfitPosition.tpOrderId}`);
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/cancel-take-profit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentTakeProfitPosition.symbol,
                order_id: currentTakeProfitPosition.tpOrderId
            })
        });

        const data = await response.json();

        // Always log debug info from server
        if (data._debug && data._debug.length > 0) {
            console.log('%c[Remove TP] Server Debug Log:', 'color: #f59e0b; font-weight: bold');
            console.table(data._debug.map((msg, i) => ({ step: i + 1, message: msg })));
        }

        if (response.ok) {
            console.log('%c[Remove TP] SUCCESS', 'color: #22c55e; font-weight: bold');
            showToast('Take profit removed', 'success');
            document.getElementById('editTakeProfitModal').classList.remove('active');
            currentTakeProfitPosition = null;
            await loadPositions();
            loadOrders();
        } else {
            console.error('%c[Remove TP] FAILED:', 'color: #ef4444; font-weight: bold', data.error);
            showToast(`Remove TP failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('%c[Remove TP] EXCEPTION:', 'color: #ef4444; font-weight: bold', error);
        showToast(`Remove TP failed: ${error.message}`, 'error');
    } finally {
        removeBtn.disabled = false;
        removeBtn.textContent = 'Remove TP';
    }
}

// ==================== EQUITY CURVE ====================

let equityChart = null;

async function loadEquityCurve() {
    const chartLoading = document.getElementById('chartLoading');
    const chartEmpty = document.getElementById('chartEmpty');
    const chartCanvas = document.getElementById('equityChart');

    if (!chartCanvas) return;

    try {
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/equity-curve`);
        const data = await response.json();

        chartLoading.style.display = 'none';

        if (!data.data_points || data.data_points.length === 0) {
            chartEmpty.style.display = 'flex';
            chartCanvas.style.display = 'none';
            return;
        }

        chartEmpty.style.display = 'none';
        chartCanvas.style.display = 'block';

        renderEquityChart(data);
    } catch (error) {
        console.error('Error loading equity curve:', error);
        chartLoading.style.display = 'none';
        chartEmpty.style.display = 'flex';
    }
}

function renderEquityChart(data) {
    const canvas = document.getElementById('equityChart');
    const ctx = canvas.getContext('2d');

    // Get container dimensions
    const container = canvas.parentElement;
    canvas.width = container.clientWidth;
    canvas.height = 280;

    const points = data.data_points;
    const padding = { top: 30, right: 20, bottom: 40, left: 70 };
    const chartWidth = canvas.width - padding.left - padding.right;
    const chartHeight = canvas.height - padding.top - padding.bottom;

    // Get min/max values
    const pnlValues = points.map(p => p.pnl);
    let minPnl = Math.min(0, ...pnlValues);
    let maxPnl = Math.max(0, ...pnlValues);

    // Add padding to range
    const range = maxPnl - minPnl || 1;
    minPnl -= range * 0.1;
    maxPnl += range * 0.1;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw background
    ctx.fillStyle = 'rgba(24, 24, 32, 0.3)';
    ctx.fillRect(padding.left, padding.top, chartWidth, chartHeight);

    // Draw zero line
    const zeroY = padding.top + chartHeight - ((0 - minPnl) / (maxPnl - minPnl)) * chartHeight;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(padding.left, zeroY);
    ctx.lineTo(canvas.width - padding.right, zeroY);
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw Y-axis labels
    ctx.fillStyle = '#71717a';
    ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.textAlign = 'right';

    const ySteps = 5;
    for (let i = 0; i <= ySteps; i++) {
        const value = minPnl + (maxPnl - minPnl) * (i / ySteps);
        const y = padding.top + chartHeight - (i / ySteps) * chartHeight;

        ctx.fillText(`$${value.toFixed(0)}`, padding.left - 10, y + 4);

        // Grid line
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(canvas.width - padding.right, y);
        ctx.stroke();
    }

    // Draw X-axis labels
    ctx.textAlign = 'center';
    const xLabels = Math.min(5, points.length);
    for (let i = 0; i < xLabels; i++) {
        const idx = Math.floor(i * (points.length - 1) / (xLabels - 1 || 1));
        const point = points[idx];
        const x = padding.left + (idx / (points.length - 1 || 1)) * chartWidth;

        const date = new Date(point.timestamp);
        const label = `${date.getMonth() + 1}/${date.getDate()}`;
        ctx.fillText(label, x, canvas.height - 10);
    }

    // Draw gradient fill under line
    const gradient = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartHeight);
    const lastPnl = points[points.length - 1].pnl;
    if (lastPnl >= 0) {
        gradient.addColorStop(0, 'rgba(74, 222, 128, 0.3)');
        gradient.addColorStop(1, 'rgba(74, 222, 128, 0)');
    } else {
        gradient.addColorStop(0, 'rgba(239, 68, 68, 0.3)');
        gradient.addColorStop(1, 'rgba(239, 68, 68, 0)');
    }

    ctx.beginPath();
    ctx.moveTo(padding.left, zeroY);

    for (let i = 0; i < points.length; i++) {
        const x = padding.left + (i / (points.length - 1 || 1)) * chartWidth;
        const y = padding.top + chartHeight - ((points[i].pnl - minPnl) / (maxPnl - minPnl)) * chartHeight;

        if (i === 0) {
            ctx.lineTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    }

    // Close path for fill
    const lastX = padding.left + chartWidth;
    ctx.lineTo(lastX, zeroY);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Draw line
    ctx.beginPath();
    for (let i = 0; i < points.length; i++) {
        const x = padding.left + (i / (points.length - 1 || 1)) * chartWidth;
        const y = padding.top + chartHeight - ((points[i].pnl - minPnl) / (maxPnl - minPnl)) * chartHeight;

        if (i === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    }

    ctx.strokeStyle = lastPnl >= 0 ? '#4ade80' : '#f87171';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Draw points for trades
    for (let i = 0; i < points.length; i++) {
        const x = padding.left + (i / (points.length - 1 || 1)) * chartWidth;
        const y = padding.top + chartHeight - ((points[i].pnl - minPnl) / (maxPnl - minPnl)) * chartHeight;
        const tradePnl = points[i].trade_pnl;

        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fillStyle = tradePnl >= 0 ? '#4ade80' : '#f87171';
        ctx.fill();
    }

    // Draw current PnL label
    ctx.fillStyle = '#e4e4e7';
    ctx.font = 'bold 14px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.textAlign = 'left';
    const pnlText = `PnL: ${lastPnl >= 0 ? '+' : ''}$${lastPnl.toFixed(2)}`;
    ctx.fillStyle = lastPnl >= 0 ? '#4ade80' : '#f87171';
    ctx.fillText(pnlText, padding.left + 10, padding.top + 20);

    // Draw trade count
    ctx.fillStyle = '#71717a';
    ctx.font = '12px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.fillText(`${points.length} trades`, canvas.width - padding.right - 60, padding.top + 20);
}

// ==================== ADD TO POSITION ====================

let currentAddPosition = null;

function openAddToPositionModal(posData) {
    const leverage = parseInt(posData.leverage) || 1;
    currentAddPosition = {
        symbol: posData.symbol,
        side: posData.side,
        quantity: parseFloat(posData.quantity),
        entryPrice: parseFloat(posData.entryPrice),
        markPrice: parseFloat(posData.markPrice),
        leverage: leverage
    };

    // Update modal content
    document.getElementById('addPosSymbol').textContent = currentAddPosition.symbol;
    const sideEl = document.getElementById('addPosSide');
    sideEl.textContent = currentAddPosition.side;
    sideEl.className = `position-side ${currentAddPosition.side.toLowerCase()}`;

    document.getElementById('addPosCurrentSize').textContent = currentAddPosition.quantity;
    document.getElementById('addPosEntryPrice').textContent = `$${currentAddPosition.entryPrice.toFixed(4)}`;
    document.getElementById('addPosMarkPrice').textContent = `$${currentAddPosition.markPrice.toFixed(4)}`;
    document.getElementById('addPosLeverage').textContent = `${leverage}x`;

    // Calculate and display available balance and max add
    const avail = availableBalance || 0;
    const maxAdd = avail * leverage;
    document.getElementById('addPosAvailBalance').textContent = `$${avail.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    document.getElementById('addPosMaxAdd').textContent = `$${maxAdd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    // Store max add for percentage buttons
    currentAddPosition.maxAdd = maxAdd;

    // Clear USDC input and calculated qty
    document.getElementById('addPosUsdc').value = '';
    document.getElementById('addPosCalcQty').textContent = '0.00';

    // Show modal
    document.getElementById('addToPositionModal').classList.add('active');
}

function setupAddToPositionModal() {
    const modal = document.getElementById('addToPositionModal');
    if (!modal) return;

    const closeBtn = document.getElementById('closeAddToPositionModal');
    const cancelBtn = document.getElementById('cancelAddToPositionBtn');
    const confirmBtn = document.getElementById('confirmAddToPositionBtn');
    const usdcInput = document.getElementById('addPosUsdc');

    // Close modal handlers
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            modal.classList.remove('active');
            currentAddPosition = null;
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            modal.classList.remove('active');
            currentAddPosition = null;
        });
    }

    // Close on overlay click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('active');
            currentAddPosition = null;
        }
    });

    // USDC input - calculate quantity
    if (usdcInput) {
        usdcInput.addEventListener('input', () => {
            if (!currentAddPosition) return;
            const usdc = parseFloat(usdcInput.value) || 0;
            const qty = usdc / currentAddPosition.markPrice;
            document.getElementById('addPosCalcQty').textContent = qty.toFixed(6);
        });
    }

    // Quick percentage buttons
    const quickBtns = modal.querySelectorAll('.add-pos-quick-btns .quick-btn');
    quickBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            if (!currentAddPosition || !currentAddPosition.maxAdd) return;
            const pct = parseInt(btn.dataset.pct) || 0;
            const amount = (currentAddPosition.maxAdd * pct / 100);
            // Round to 2 decimal places
            const roundedAmount = Math.floor(amount * 100) / 100;
            usdcInput.value = roundedAmount.toFixed(2);
            // Trigger input event to update calculated quantity
            usdcInput.dispatchEvent(new Event('input'));
        });
    });

    // Confirm add to position
    if (confirmBtn) {
        confirmBtn.addEventListener('click', addToPosition);
    }
}

async function addToPosition() {
    if (!currentAddPosition) return;

    const usdcAmount = parseFloat(document.getElementById('addPosUsdc').value);

    if (!usdcAmount || usdcAmount <= 0) {
        showToast('Please enter a valid USDC amount', 'error');
        return;
    }

    // Calculate quantity from USDC
    const quantityToAdd = usdcAmount / currentAddPosition.markPrice;

    const confirmBtn = document.getElementById('confirmAddToPositionBtn');
    const btnText = confirmBtn.querySelector('.btn-text');
    const btnLoading = confirmBtn.querySelector('.btn-loading');

    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';
    confirmBtn.disabled = true;

    try {
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/add-to-position`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentAddPosition.symbol,
                side: currentAddPosition.side,
                quantity: quantityToAdd
            })
        });

        const data = await response.json();

        if (response.ok) {
            showToast(`Added ${quantityToAdd} to ${currentAddPosition.symbol} position`, 'success');
            document.getElementById('addToPositionModal').classList.remove('active');
            currentAddPosition = null;
            loadPositions();
            loadBalance();
        } else {
            showToast(data.error || 'Failed to add to position', 'error');
        }
    } catch (error) {
        console.error('Error adding to position:', error);
        showToast('Failed to add to position', 'error');
    } finally {
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
        confirmBtn.disabled = false;
    }
}

// ==================== NEW TRADE MODAL ====================

let tradeState = {
    symbol: 'SOLUSDC',
    marginType: 'CROSSED',
    leverage: 5,
    orderType: 'LIMIT',
    availableBalance: 0,
    currentPrice: 0
};

function setupTradeModal() {
    const newTradeBtn = document.getElementById('newTradeBtn');
    const tradeModal = document.getElementById('newTradeModal');
    const closeTradeModal = document.getElementById('closeTradeModal');
    const leverageModal = document.getElementById('leverageModal');
    const closeLeverageModal = document.getElementById('closeLeverageModal');

    if (!newTradeBtn || !tradeModal) return;

    // Open trade modal
    newTradeBtn.addEventListener('click', () => {
        // Sync available balance from global variable
        tradeState.availableBalance = availableBalance || 0;
        tradeModal.classList.add('active');
        fetchCurrentPrice();
        updateTradeInfo();
        updateTradeButtonText();

        // Reset to default state
        document.getElementById('tradeSize').value = '';
        document.getElementById('tradeSizeSlider').value = 0;
    });

    // Close trade modal
    closeTradeModal?.addEventListener('click', () => {
        tradeModal.classList.remove('active');
    });

    tradeModal.addEventListener('click', (e) => {
        if (e.target === tradeModal) {
            tradeModal.classList.remove('active');
        }
    });

    // Symbol selector
    const symbolSelect = document.getElementById('tradeSymbol');
    symbolSelect?.addEventListener('change', (e) => {
        tradeState.symbol = e.target.value;
        fetchCurrentPrice();
        updateTradeInfo();
    });

    // Margin type toggles
    const marginCross = document.getElementById('marginCross');
    const marginIsolated = document.getElementById('marginIsolated');

    marginCross?.addEventListener('click', () => {
        marginCross.classList.add('active');
        marginIsolated.classList.remove('active');
        tradeState.marginType = 'CROSSED';
    });

    marginIsolated?.addEventListener('click', () => {
        marginIsolated.classList.add('active');
        marginCross.classList.remove('active');
        tradeState.marginType = 'ISOLATED';
    });

    // Leverage button
    const leverageBtn = document.getElementById('leverageBtn');
    leverageBtn?.addEventListener('click', () => {
        leverageModal.classList.add('active');
        document.getElementById('leverageSlider').value = tradeState.leverage;
        document.getElementById('leverageDisplayValue').textContent = tradeState.leverage;
    });

    // Close leverage modal
    closeLeverageModal?.addEventListener('click', () => {
        leverageModal.classList.remove('active');
    });

    leverageModal?.addEventListener('click', (e) => {
        if (e.target === leverageModal) {
            leverageModal.classList.remove('active');
        }
    });

    // Leverage slider
    const leverageSlider = document.getElementById('leverageSlider');
    leverageSlider?.addEventListener('input', (e) => {
        document.getElementById('leverageDisplayValue').textContent = e.target.value;
    });

    // Confirm leverage
    const confirmLeverageBtn = document.getElementById('confirmLeverageBtn');
    confirmLeverageBtn?.addEventListener('click', () => {
        tradeState.leverage = parseInt(document.getElementById('leverageSlider').value);
        document.getElementById('leverageValue').textContent = tradeState.leverage;
        leverageModal.classList.remove('active');
        updateTradeInfo();
    });

    // Order type tabs
    const orderTabs = document.querySelectorAll('.order-tab');
    orderTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            orderTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            tradeState.orderType = tab.dataset.type;

            // Show/hide price inputs based on order type
            const priceGroup = document.getElementById('priceInputGroup');
            const stopPriceGroup = document.getElementById('stopPriceInputGroup');

            if (tradeState.orderType === 'MARKET') {
                priceGroup.style.display = 'none';
                stopPriceGroup.style.display = 'none';
            } else if (tradeState.orderType === 'STOP') {
                priceGroup.style.display = 'block';
                stopPriceGroup.style.display = 'block';
            } else {
                priceGroup.style.display = 'block';
                stopPriceGroup.style.display = 'none';
            }

            // Update button text based on order type
            updateTradeButtonText();
        });
    });

    // BBO button (Best Bid/Offer)
    const bboBtn = document.getElementById('bboBtn');
    bboBtn?.addEventListener('click', () => {
        if (tradeState.currentPrice > 0) {
            document.getElementById('tradePrice').value = tradeState.currentPrice.toFixed(2);
        }
    });

    // Size slider
    const sizeSlider = document.getElementById('tradeSizeSlider');
    const sizeInput = document.getElementById('tradeSize');

    sizeSlider?.addEventListener('input', (e) => {
        const pct = parseInt(e.target.value);
        const maxSize = calculateMaxSize();
        const size = (maxSize * pct / 100).toFixed(2);
        sizeInput.value = size;
        updateTradeInfo();
    });

    // Slider label clicks
    document.querySelectorAll('.slider-labels span').forEach(label => {
        label.addEventListener('click', () => {
            const value = label.dataset.value;
            sizeSlider.value = value;
            sizeSlider.dispatchEvent(new Event('input'));
        });
    });

    // Size input change
    sizeInput?.addEventListener('input', () => {
        updateTradeInfo();
    });

    // TP/SL checkbox
    const tpslCheckbox = document.getElementById('tradeTpSl');
    const tpslGroup = document.getElementById('tradeTpSlGroup');

    tpslCheckbox?.addEventListener('change', () => {
        tpslGroup.style.display = tpslCheckbox.checked ? 'grid' : 'none';
    });

    // Trade buttons
    const buyBtn = document.getElementById('tradeBuyBtn');
    const sellBtn = document.getElementById('tradeSellBtn');

    buyBtn?.addEventListener('click', () => executeTrade('BUY'));
    sellBtn?.addEventListener('click', () => executeTrade('SELL'));
}

async function fetchCurrentPrice() {
    try {
        const response = await fetch(`/api/ticker/${tradeState.symbol}`);
        if (response.ok) {
            const data = await response.json();
            tradeState.currentPrice = parseFloat(data.price);
            // Auto-fill price for limit orders
            if (tradeState.orderType === 'LIMIT') {
                document.getElementById('tradePrice').value = tradeState.currentPrice.toFixed(2);
            }
        }
    } catch (error) {
        console.error('Error fetching price:', error);
    }
}

function calculateMaxSize() {
    // Max size based on available balance and leverage
    const balance = tradeState.availableBalance || 0;
    return balance * tradeState.leverage;
}

function updateTradeInfo() {
    const sizeInput = document.getElementById('tradeSize');
    const size = parseFloat(sizeInput?.value) || 0;
    const leverage = tradeState.leverage;
    const available = tradeState.availableBalance || 0;

    // Available balance
    const availEl = document.getElementById('tradeAvailable');
    if (availEl) {
        availEl.textContent = `${available.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDC`;
    }

    // Max position size = Available * Leverage
    const maxSize = available * leverage;
    const maxEl = document.getElementById('tradeMax');
    if (maxEl) {
        maxEl.textContent = `${maxSize.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDC`;
    }

    // Cost = Size / Leverage (margin required)
    const cost = size / leverage;
    const costEl = document.getElementById('tradeCost');
    if (costEl) {
        costEl.textContent = `${cost.toFixed(2)} USDC`;
    }
}

function updateTradeButtonText() {
    const buyBtn = document.getElementById('tradeBuyBtn');
    const sellBtn = document.getElementById('tradeSellBtn');
    const orderType = tradeState.orderType;

    let buyText = 'Buy/Long';
    let sellText = 'Sell/Short';

    if (orderType === 'MARKET') {
        buyText = 'Market Buy/Long';
        sellText = 'Market Sell/Short';
    } else if (orderType === 'LIMIT') {
        buyText = 'Limit Buy/Long';
        sellText = 'Limit Sell/Short';
    } else if (orderType === 'STOP') {
        buyText = 'Stop Buy/Long';
        sellText = 'Stop Sell/Short';
    }

    if (buyBtn) {
        const btnText = buyBtn.querySelector('.btn-text');
        if (btnText) btnText.textContent = buyText;
    }
    if (sellBtn) {
        const btnText = sellBtn.querySelector('.btn-text');
        if (btnText) btnText.textContent = sellText;
    }
}

async function executeTrade(side) {
    const symbol = tradeState.symbol;
    const orderType = tradeState.orderType;
    const price = parseFloat(document.getElementById('tradePrice')?.value) || 0;
    const stopPrice = parseFloat(document.getElementById('tradeStopPrice')?.value) || 0;
    const size = parseFloat(document.getElementById('tradeSize')?.value) || 0;
    const leverage = tradeState.leverage;
    const marginType = tradeState.marginType;
    const reduceOnly = document.getElementById('tradeReduceOnly')?.checked || false;
    const tif = document.getElementById('tradeTif')?.value || 'GTC';

    // TP/SL values
    const tpslEnabled = document.getElementById('tradeTpSl')?.checked || false;
    const tpPrice = parseFloat(document.getElementById('tradeTpPrice')?.value) || 0;
    const slPrice = parseFloat(document.getElementById('tradeSlPrice')?.value) || 0;

    // Log all parameters for debugging
    console.log('%c[New Trade] Parameters:', 'color: #3b82f6; font-weight: bold');
    console.table({
        symbol,
        side,
        orderType,
        price,
        stopPrice,
        size,
        leverage,
        marginType,
        reduceOnly,
        tif,
        tpslEnabled,
        tpPrice,
        slPrice
    });

    // Validation
    if (size <= 0) {
        showToast('Please enter a valid size', 'error');
        return;
    }

    if (orderType === 'LIMIT' && price <= 0) {
        showToast('Please enter a valid limit price', 'error');
        return;
    }

    if (orderType === 'STOP') {
        if (price <= 0) {
            showToast('Please enter a valid limit price for stop order', 'error');
            return;
        }
        if (stopPrice <= 0) {
            showToast('Please enter a valid stop/trigger price', 'error');
            return;
        }
    }

    // Check max size
    const maxSize = calculateMaxSize();
    if (size > maxSize && !reduceOnly) {
        showToast(`Size exceeds max (${maxSize.toFixed(2)} USDC)`, 'error');
        return;
    }

    // Button loading state
    const btn = side === 'BUY' ? document.getElementById('tradeBuyBtn') : document.getElementById('tradeSellBtn');
    const btnText = btn.querySelector('.btn-text');
    const btnLoading = btn.querySelector('.btn-loading');

    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';
    btn.disabled = true;

    try {
        console.log(`%c[New Trade] Executing ${side} ${orderType} order`, 'color: #3b82f6; font-weight: bold');

        const requestBody = {
            symbol,
            side,
            order_type: orderType,
            quantity: size,
            leverage,
            margin_type: marginType,
            reduce_only: reduceOnly,
            time_in_force: tif
        };

        // Only include price for LIMIT and STOP orders
        if (orderType === 'LIMIT' || orderType === 'STOP') {
            requestBody.price = price;
        }

        // Include stop price only for STOP orders
        if (orderType === 'STOP') {
            requestBody.stop_price = stopPrice;
        }

        // Include TP/SL if enabled
        if (tpslEnabled) {
            if (tpPrice > 0) requestBody.tp_price = tpPrice;
            if (slPrice > 0) requestBody.sl_price = slPrice;
        }

        console.log('%c[New Trade] Request body:', 'color: #f59e0b; font-weight: bold', requestBody);

        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/trade`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();

        if (data._debug) {
            console.log('%c[New Trade] Server Debug Log:', 'color: #f59e0b; font-weight: bold');
            console.table(data._debug.map((msg, i) => ({ step: i + 1, message: msg })));
        }

        if (response.ok) {
            console.log('%c[New Trade] SUCCESS', 'color: #22c55e; font-weight: bold');
            const orderTypeLabel = orderType === 'MARKET' ? 'Market' : orderType === 'LIMIT' ? 'Limit' : 'Stop';
            showToast(`${orderTypeLabel} ${side} order placed successfully`, 'success');
            document.getElementById('newTradeModal').classList.remove('active');
            // Refresh positions and orders
            loadPositions();
            loadOrders();
            loadBalance();
        } else {
            console.error('%c[New Trade] FAILED:', 'color: #ef4444; font-weight: bold', data.error);
            showToast(`Trade failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('%c[New Trade] EXCEPTION:', 'color: #ef4444; font-weight: bold', error);
        showToast(`Trade failed: ${error.message}`, 'error');
    } finally {
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
        btn.disabled = false;
    }
}

// Initialize trade modal on page load
document.addEventListener('DOMContentLoaded', () => {
    setupTradeModal();
});

