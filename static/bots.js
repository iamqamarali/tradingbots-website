// Bots Page JavaScript

let botsData = [];
let accountsData = [];

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadAccounts().then(() => loadBots());
});

// Load all accounts for dropdown
async function loadAccounts() {
    try {
        const response = await fetch('/api/accounts');
        accountsData = await response.json();
    } catch (error) {
        console.error('Error loading accounts:', error);
    }
}

// Load all bots
async function loadBots() {
    try {
        const response = await fetch('/api/bots');
        botsData = await response.json();
        
        updateStats();
        renderBots();
    } catch (error) {
        console.error('Error loading bots:', error);
        showToast('Failed to load bots', 'error');
    }
}

// Update overview stats
function updateStats() {
    const totalBots = botsData.length;
    const totalTrades = botsData.reduce((sum, bot) => sum + (bot.total_trades || 0), 0);
    const totalPnL = botsData.reduce((sum, bot) => sum + (bot.total_pnl || 0), 0);
    
    // Calculate average win rate (only from bots with closed trades)
    const botsWithTrades = botsData.filter(bot => (bot.winning_trades + bot.losing_trades) > 0);
    const avgWinRate = botsWithTrades.length > 0 
        ? botsWithTrades.reduce((sum, bot) => sum + bot.win_rate, 0) / botsWithTrades.length 
        : 0;
    
    document.getElementById('totalBots').textContent = totalBots;
    document.getElementById('totalTrades').textContent = totalTrades;
    document.getElementById('avgWinRate').textContent = `${avgWinRate.toFixed(1)}%`;
    
    const pnlElement = document.getElementById('totalPnL');
    pnlElement.textContent = `${totalPnL >= 0 ? '+' : ''}$${totalPnL.toFixed(2)}`;
    pnlElement.className = `stat-value ${totalPnL >= 0 ? 'positive' : 'negative'}`;
    
    // Update PnL icon color
    const pnlCard = document.getElementById('pnlCard');
    if (pnlCard) {
        pnlCard.className = `stat-icon pnl ${totalPnL < 0 ? 'negative' : ''}`;
    }
    
    document.getElementById('botCount').textContent = `${totalBots} bot${totalBots !== 1 ? 's' : ''}`;
}

// Render bots grid
function renderBots() {
    const grid = document.getElementById('botsGrid');
    const loadingState = document.getElementById('loadingState');
    const emptyState = document.getElementById('emptyState');
    
    loadingState.style.display = 'none';
    
    if (botsData.length === 0) {
        grid.style.display = 'none';
        emptyState.style.display = 'flex';
        return;
    }
    
    grid.style.display = 'grid';
    emptyState.style.display = 'none';
    
    grid.innerHTML = botsData.map(bot => createBotCard(bot)).join('');
    
    // Attach event listeners
    grid.querySelectorAll('.view-trades-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const botId = btn.dataset.botId;
            window.location.href = `/trades?bot_id=${botId}`;
        });
    });
    
    grid.querySelectorAll('.delete-bot-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const botId = btn.dataset.botId;
            const botName = btn.dataset.botName;
            deleteBot(botId, botName);
        });
    });
    
    // Account selector
    grid.querySelectorAll('.account-select').forEach(select => {
        select.addEventListener('change', async () => {
            const botId = select.dataset.botId;
            const accountId = select.value;
            await updateBotAccount(botId, accountId);
        });
    });
}

// Update bot's account
async function updateBotAccount(botId, accountId) {
    try {
        const response = await fetch(`/api/bots/${botId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_id: accountId || null })
        });
        
        if (response.ok) {
            const accountName = accountId 
                ? accountsData.find(a => a.id == accountId)?.name || 'Account'
                : 'None';
            showToast(`Bot linked to ${accountName}`, 'success');
        } else {
            const data = await response.json();
            showToast(data.error || 'Failed to update bot', 'error');
            loadBots(); // Refresh to revert
        }
    } catch (error) {
        console.error('Error updating bot:', error);
        showToast('Failed to update bot', 'error');
        loadBots();
    }
}

// Create bot card HTML
function createBotCard(bot) {
    const pnlClass = bot.total_pnl >= 0 ? 'positive' : 'negative';
    const pnlPrefix = bot.total_pnl >= 0 ? '+' : '';
    
    const createdDate = bot.created_at 
        ? new Date(bot.created_at).toLocaleDateString('en-US', { 
            month: 'short', 
            day: 'numeric', 
            year: 'numeric' 
        })
        : 'Unknown';
    
    // Build account options
    const accountOptions = accountsData.map(acc => 
        `<option value="${acc.id}" ${bot.account_id === acc.id ? 'selected' : ''}>${escapeHtml(acc.name)}</option>`
    ).join('');
    
    return `
        <div class="bot-card" data-bot-id="${bot.id}">
            <div class="bot-card-header">
                <div class="bot-info">
                    <span class="bot-name">${escapeHtml(bot.name)}</span>
                    <span class="bot-symbol">${escapeHtml(bot.symbol)}</span>
                </div>
                <div class="bot-actions">
                    <button class="bot-action-btn delete delete-bot-btn" 
                            data-bot-id="${bot.id}" 
                            data-bot-name="${escapeHtml(bot.name)}"
                            title="Delete Bot">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                </div>
            </div>
            <div class="bot-account-row">
                <label>Account:</label>
                <select class="account-select" data-bot-id="${bot.id}">
                    <option value="">No Account</option>
                    ${accountOptions}
                </select>
            </div>
            <div class="bot-card-stats">
                <div class="bot-stat">
                    <span class="bot-stat-value">${bot.total_trades || 0}</span>
                    <span class="bot-stat-label">Trades</span>
                </div>
                <div class="bot-stat">
                    <span class="bot-stat-value">${bot.win_rate || 0}%</span>
                    <span class="bot-stat-label">Win Rate</span>
                </div>
                <div class="bot-stat">
                    <span class="bot-stat-value ${pnlClass}">${pnlPrefix}$${(bot.total_pnl || 0).toFixed(2)}</span>
                    <span class="bot-stat-label">PnL</span>
                </div>
            </div>
            <div class="bot-card-footer">
                <span class="bot-date">Created ${createdDate}</span>
                <button class="view-trades-btn" data-bot-id="${bot.id}">
                    View Trades
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="9 18 15 12 9 6"/>
                    </svg>
                </button>
            </div>
        </div>
    `;
}

// Delete bot
async function deleteBot(botId, botName) {
    if (!confirm(`Delete "${botName}"?\n\nThis will permanently delete:\n• The bot record\n• All trade history\n• The script file (if exists)\n\nThis cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/bots/${botId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast(`Bot "${botName}" deleted`, 'success');
            loadBots();
        } else {
            const data = await response.json();
            showToast(data.error || 'Failed to delete bot', 'error');
        }
    } catch (error) {
        console.error('Error deleting bot:', error);
        showToast('Failed to delete bot', 'error');
    }
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Toast notification
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

