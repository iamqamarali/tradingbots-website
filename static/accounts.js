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
    const winRate = account.win_rate || 0;
    const winRateClass = winRate >= 50 ? 'positive' : (winRate > 0 ? 'negative' : '');

    const createdDate = account.created_at
        ? new Date(account.created_at).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        })
        : 'Unknown';

    const lastSync = account.last_sync_time
        ? new Date(account.last_sync_time).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        })
        : 'Never';

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
                    <span class="account-stat-value ${winRateClass}">${winRate.toFixed(1)}%</span>
                    <span class="account-stat-label">Win Rate</span>
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
                <span class="account-date">Synced: ${lastSync}</span>
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
    setupClosePositionModal();
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
            
            // Update balance details if available
            if (data.starting_balance !== undefined) {
                const startBalEl = document.getElementById('startingBalance');
                if (startBalEl) {
                    startBalEl.textContent = `$${(data.starting_balance || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
                }
                
                // Calculate net profit
                const netProfit = data.balance - (data.starting_balance || 0);
                const netProfitEl = document.getElementById('netProfit');
                if (netProfitEl && data.starting_balance > 0) {
                    netProfitEl.textContent = `${netProfit >= 0 ? '+' : ''}$${netProfit.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
                    netProfitEl.className = `detail-value ${netProfit >= 0 ? 'positive' : 'negative'}`;
                }
                
                // Calculate percentage
                const netPctEl = document.getElementById('netProfitPct');
                if (netPctEl && data.starting_balance > 0) {
                    const pct = (netProfit / data.starting_balance) * 100;
                    netPctEl.textContent = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
                    netPctEl.className = `detail-value ${pct >= 0 ? 'positive' : 'negative'}`;
                }
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

            tbody.innerHTML = positions.map(pos => {
                // Calculate position size in $
                const sizeInDollars = pos.quantity * pos.mark_price;
                return `
                <tr>
                    <td class="symbol">${pos.symbol}</td>
                    <td><span class="side ${pos.side.toLowerCase()}">${pos.side}</span></td>
                    <td>$${sizeInDollars.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td>$${pos.entry_price.toFixed(4)}</td>
                    <td>$${pos.mark_price.toFixed(4)}</td>
                    <td class="${pos.unrealized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}">
                        ${pos.unrealized_pnl >= 0 ? '+' : ''}$${pos.unrealized_pnl.toFixed(2)}
                    </td>
                    <td><span class="leverage-badge">${pos.leverage}x</span></td>
                    <td>
                        <button class="close-position-btn"
                            data-symbol="${pos.symbol}"
                            data-side="${pos.side}"
                            data-quantity="${pos.quantity}"
                            data-pnl="${pos.unrealized_pnl}">
                            Close
                        </button>
                    </td>
                </tr>
            `}).join('');

            // Add event listeners for close buttons
            tbody.querySelectorAll('.close-position-btn').forEach(btn => {
                btn.addEventListener('click', () => openClosePositionModal(btn.dataset));
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
        pnl: parseFloat(posData.pnl)
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
            updateCloseQuantity(pct);

            pctBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });

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
    const percent = parseInt(document.getElementById('closePercentSlider').value);
    const quantityToClose = (currentPosition.quantity * percent / 100);

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
            showToast(`Closed ${percent}% of ${currentPosition.symbol} position`, 'success');
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

