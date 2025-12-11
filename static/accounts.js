// Accounts Page JavaScript

let accountsData = [];
let accountToDelete = null;

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
    } catch (error) {
        console.error('Error loading accounts:', error);
        showToast('Failed to load accounts', 'error');
    }
}

function updateStats() {
    const totalAccounts = accountsData.length;
    const totalTrades = accountsData.reduce((sum, acc) => sum + (acc.total_trades || 0), 0);
    const totalPnL = accountsData.reduce((sum, acc) => sum + (acc.total_pnl || 0), 0);
    const totalCommission = accountsData.reduce((sum, acc) => sum + (acc.total_commission || 0), 0);
    
    document.getElementById('totalAccounts').textContent = totalAccounts;
    document.getElementById('totalTrades').textContent = totalTrades;
    
    const pnlElement = document.getElementById('totalPnL');
    pnlElement.textContent = `${totalPnL >= 0 ? '+' : ''}$${totalPnL.toFixed(2)}`;
    pnlElement.className = `stat-value ${totalPnL >= 0 ? 'positive' : 'negative'}`;
    
    const pnlIcon = document.getElementById('pnlIconCard');
    if (pnlIcon) {
        pnlIcon.className = `stat-icon pnl-icon ${totalPnL < 0 ? 'negative' : ''}`;
    }
    
    document.getElementById('totalCommission').textContent = `$${totalCommission.toFixed(2)}`;
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
            // Don't navigate if clicking delete button
            if (e.target.closest('.delete-account-btn')) return;
            
            const accountId = card.dataset.accountId;
            window.location.href = `/accounts/${accountId}`;
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
    const pnlClass = account.total_pnl >= 0 ? 'positive' : 'negative';
    const pnlPrefix = account.total_pnl >= 0 ? '+' : '';
    
    const createdDate = account.created_at 
        ? new Date(account.created_at).toLocaleDateString('en-US', { 
            month: 'short', 
            day: 'numeric', 
            year: 'numeric' 
        })
        : 'Unknown';
    
    return `
        <div class="account-card" data-account-id="${account.id}">
            <div class="account-card-header">
                <div class="account-info">
                    <div class="account-name-row">
                        <span class="account-name">${escapeHtml(account.name)}</span>
                        ${account.is_testnet ? '<span class="testnet-badge">TESTNET</span>' : ''}
                    </div>
                    <span class="account-api-key">${account.api_key}</span>
                </div>
                <div class="account-actions">
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
            <div class="account-card-stats">
                <div class="account-stat">
                    <span class="account-stat-value">${account.total_trades || 0}</span>
                    <span class="account-stat-label">Trades</span>
                </div>
                <div class="account-stat">
                    <span class="account-stat-value ${pnlClass}">${pnlPrefix}$${(account.total_pnl || 0).toFixed(2)}</span>
                    <span class="account-stat-label">PnL</span>
                </div>
                <div class="account-stat">
                    <span class="account-stat-value">$${(account.total_commission || 0).toFixed(2)}</span>
                    <span class="account-stat-label">Fees</span>
                </div>
            </div>
            <div class="account-card-footer">
                <span class="account-date">Added ${createdDate}</span>
                <button class="view-account-btn">
                    View Details
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="9 18 15 12 9 6"/>
                    </svg>
                </button>
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
            showToast(`Account "${name}" created successfully`, 'success');
            document.getElementById('addAccountModal').classList.remove('active');
            clearAddAccountForm();
            loadAccounts();
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
    loadTrades();
    loadStats();
    setupDetailPageEventListeners();
}

function setupDetailPageEventListeners() {
    // Sync button
    const syncBtn = document.getElementById('syncBtn');
    if (syncBtn) {
        syncBtn.addEventListener('click', syncTrades);
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
        refreshPositionsBtn.addEventListener('click', loadPositions);
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
    } catch (error) {
        console.error('Error loading account:', error);
        showToast('Failed to load account details', 'error');
    }
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
    
    if (refreshBtn) refreshBtn.classList.add('loading');
    if (loading) loading.style.display = 'flex';
    if (table) table.style.display = 'none';
    if (empty) empty.style.display = 'none';
    
    try {
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/positions`);
        const positions = await response.json();
        
        if (loading) loading.style.display = 'none';
        
        if (response.ok && positions.length > 0) {
            if (table) table.style.display = 'table';
            
            tbody.innerHTML = positions.map(pos => `
                <tr>
                    <td class="symbol">${pos.symbol}</td>
                    <td><span class="side ${pos.side.toLowerCase()}">${pos.side}</span></td>
                    <td>${pos.quantity}</td>
                    <td>$${pos.entry_price.toFixed(4)}</td>
                    <td>$${pos.mark_price.toFixed(4)}</td>
                    <td class="${pos.unrealized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}">
                        ${pos.unrealized_pnl >= 0 ? '+' : ''}$${pos.unrealized_pnl.toFixed(2)}
                    </td>
                    <td><span class="leverage-badge">${pos.leverage}x</span></td>
                </tr>
            `).join('');
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
                
                return `
                    <tr>
                        <td>${tradeTime}</td>
                        <td class="symbol">${trade.symbol}</td>
                        <td><span class="side ${trade.side.toLowerCase()}">${trade.side}</span></td>
                        <td>${trade.quantity}</td>
                        <td>$${trade.price.toFixed(4)}</td>
                        <td class="${trade.realized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}">
                            ${trade.realized_pnl >= 0 ? '+' : ''}$${trade.realized_pnl.toFixed(2)}
                        </td>
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
            document.getElementById('statTotalTrades').textContent = stats.total_trades || 0;
            document.getElementById('statWinRate').textContent = `${stats.win_rate || 0}%`;
            
            const pnlElement = document.getElementById('statTotalPnL');
            const pnl = stats.total_pnl || 0;
            pnlElement.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
            pnlElement.className = `mini-stat-value ${pnl >= 0 ? 'positive' : 'negative'}`;
            
            document.getElementById('statTotalFees').textContent = `$${(stats.total_commission || 0).toFixed(2)}`;
        }
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

async function syncTrades() {
    console.log('=== syncTrades() called ===');
    console.log('ACCOUNT_ID:', ACCOUNT_ID);

    const syncBtn = document.getElementById('syncBtn');
    const syncModal = document.getElementById('syncModal');
    const syncProgress = document.getElementById('syncProgress');
    const syncStatus = document.getElementById('syncStatus');

    console.log('syncBtn:', syncBtn);
    console.log('syncModal:', syncModal);

    syncBtn.classList.add('syncing');
    syncModal.classList.add('active');
    syncProgress.style.width = '30%';
    syncStatus.textContent = 'Fetching trades from Binance...';

    try {
        // Simulate progress
        setTimeout(() => {
            syncProgress.style.width = '60%';
            syncStatus.textContent = 'Processing trades...';
        }, 1000);

        const url = `/api/accounts/${ACCOUNT_ID}/sync`;
        console.log('Fetching URL:', url);

        const response = await fetch(url, {
            method: 'POST'
        });

        console.log('Response status:', response.status);
        console.log('Response ok:', response.ok);

        const data = await response.json();
        console.log('Response data:', data);

        syncProgress.style.width = '100%';

        if (response.ok) {
            syncStatus.textContent = `Done! Added ${data.new_trades} new trades.`;
            showToast(`Synced ${data.new_trades} new trades`, 'success');

            // Reload data
            setTimeout(() => {
                syncModal.classList.remove('active');
                loadTrades();
                loadStats();
            }, 1500);
        } else {
            console.error('Sync failed with error:', data.error);
            syncModal.classList.remove('active');
            showToast(data.error || 'Sync failed', 'error');
        }
    } catch (error) {
        console.error('Error syncing trades:', error);
        console.error('Error stack:', error.stack);
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

