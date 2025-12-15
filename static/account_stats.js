// Account Stats Page JavaScript

document.addEventListener('DOMContentLoaded', () => {
    loadAccountDetails();
    loadStats();
    loadEquityCurve();
    loadSymbolPnL();
    setupSyncButton();
});

// Toast notification
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </button>
    `;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

async function loadAccountDetails() {
    try {
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}`);
        const data = await response.json();

        if (response.ok) {
            document.getElementById('accountName').textContent = data.name;
            document.title = `${data.name} Stats - Trading Bot Manager`;

            if (data.is_testnet) {
                document.getElementById('testnetBadge').style.display = 'inline-block';
            }
        }
    } catch (error) {
        console.error('Error loading account details:', error);
    }
}

async function loadStats() {
    try {
        const [statsResponse, balanceResponse] = await Promise.all([
            fetch(`/api/accounts/${ACCOUNT_ID}/stats`),
            fetch(`/api/accounts/${ACCOUNT_ID}/balance`)
        ]);

        const stats = await statsResponse.json();
        const balance = await balanceResponse.json();

        if (statsResponse.ok) {
            // Main stats
            const totalPnl = stats.total_pnl || 0;
            const pnlEl = document.getElementById('statTotalPnL');
            pnlEl.textContent = `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}`;
            pnlEl.classList.add(totalPnl >= 0 ? 'positive' : 'negative');

            // Calculate ROI
            const startingBalance = balance.starting_balance || 0;
            const roi = startingBalance > 0 ? ((totalPnl / startingBalance) * 100) : 0;
            document.getElementById('statTotalPnLPct').textContent = `${roi >= 0 ? '+' : ''}${roi.toFixed(2)}% return`;

            document.getElementById('statWinRate').textContent = `${(stats.win_rate || 0).toFixed(1)}%`;
            document.getElementById('statWinningTrades').textContent = stats.winning_trades || 0;
            document.getElementById('statLosingTrades').textContent = stats.losing_trades || 0;

            document.getElementById('statProfitFactor').textContent = (stats.profit_factor || 0).toFixed(2);
            document.getElementById('statTotalTrades').textContent = stats.total_trades || 0;

            // Detailed stats
            const avgWinEl = document.getElementById('statAvgWin');
            avgWinEl.textContent = `+$${(stats.avg_win || 0).toFixed(2)}`;

            const avgLossEl = document.getElementById('statAvgLoss');
            avgLossEl.textContent = `-$${Math.abs(stats.avg_loss || 0).toFixed(2)}`;

            const largestWinEl = document.getElementById('statLargestWin');
            largestWinEl.textContent = `+$${(stats.largest_win || 0).toFixed(2)}`;

            const largestLossEl = document.getElementById('statLargestLoss');
            largestLossEl.textContent = `-$${Math.abs(stats.largest_loss || 0).toFixed(2)}`;

            // Avg win/loss ratio
            const avgRatio = stats.avg_loss !== 0 ? Math.abs(stats.avg_win / stats.avg_loss) : 0;
            document.getElementById('statAvgRatio').textContent = avgRatio.toFixed(2);

            // Volume & Fees
            document.getElementById('statTotalVolume').textContent = `$${(stats.total_volume || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
            document.getElementById('statTotalFees').textContent = `$${(stats.total_fees || 0).toFixed(2)}`;

            const netPnl = totalPnl - (stats.total_fees || 0);
            const netPnlEl = document.getElementById('statNetPnL');
            netPnlEl.textContent = `${netPnl >= 0 ? '+' : ''}$${netPnl.toFixed(2)}`;
            netPnlEl.classList.add(netPnl >= 0 ? 'positive' : 'negative');

            const avgTradeSize = stats.total_trades > 0 ? (stats.total_volume / stats.total_trades) : 0;
            document.getElementById('statAvgTradeSize').textContent = `$${avgTradeSize.toFixed(2)}`;

            // Streaks
            document.getElementById('statCurrentStreak').textContent = stats.current_streak || 0;
            document.getElementById('statMaxWinStreak').textContent = stats.max_win_streak || 0;
            document.getElementById('statMaxLossStreak').textContent = stats.max_loss_streak || 0;
        }

        if (balanceResponse.ok) {
            document.getElementById('statStartingBalance').textContent = `$${(balance.starting_balance || 0).toFixed(2)}`;
            document.getElementById('statCurrentBalance').textContent = `$${(balance.balance || 0).toFixed(2)}`;

            const realizedProfit = (balance.balance || 0) - (balance.starting_balance || 0);
            const rpEl = document.getElementById('statRealizedProfit');
            rpEl.textContent = `${realizedProfit >= 0 ? '+' : ''}$${realizedProfit.toFixed(2)}`;
            rpEl.classList.add(realizedProfit >= 0 ? 'positive' : 'negative');

            const roi = balance.starting_balance > 0 ? ((realizedProfit / balance.starting_balance) * 100) : 0;
            const roiEl = document.getElementById('statROI');
            roiEl.textContent = `${roi >= 0 ? '+' : ''}${roi.toFixed(2)}%`;
            roiEl.classList.add(roi >= 0 ? 'positive' : 'negative');
        }
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

async function loadEquityCurve() {
    const loading = document.getElementById('chartLoading');
    const empty = document.getElementById('chartEmpty');
    const canvas = document.getElementById('equityChart');

    try {
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/equity-curve`);
        const data = await response.json();

        loading.style.display = 'none';

        if (!response.ok || !data.dates || data.dates.length === 0) {
            empty.style.display = 'flex';
            return;
        }

        canvas.style.display = 'block';

        const ctx = canvas.getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [{
                    label: 'Equity',
                    data: data.values,
                    borderColor: '#fbbf24',
                    backgroundColor: 'rgba(251, 191, 36, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: '#fbbf24'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(18, 18, 26, 0.95)',
                        titleColor: '#e4e4e7',
                        bodyColor: '#a1a1aa',
                        borderColor: 'rgba(251, 191, 36, 0.3)',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: false,
                        callbacks: {
                            label: function(context) {
                                return `$${context.parsed.y.toFixed(2)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.05)',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#71717a',
                            maxTicksLimit: 8
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.05)',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#71717a',
                            callback: function(value) {
                                return '$' + value.toFixed(0);
                            }
                        }
                    }
                },
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                }
            }
        });
    } catch (error) {
        console.error('Error loading equity curve:', error);
        loading.style.display = 'none';
        empty.style.display = 'flex';
    }
}

async function loadSymbolPnL() {
    const loading = document.getElementById('symbolPnlLoading');
    const list = document.getElementById('symbolPnlList');

    try {
        const response = await fetch(`/api/accounts/${ACCOUNT_ID}/symbol-pnl`);
        const data = await response.json();

        loading.style.display = 'none';

        if (!response.ok || !data.symbols || data.symbols.length === 0) {
            list.innerHTML = '<div class="empty-symbol-pnl">No trade data available</div>';
            list.style.display = 'block';
            return;
        }

        // Sort by absolute PnL
        data.symbols.sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl));

        list.innerHTML = data.symbols.map(sym => `
            <div class="symbol-pnl-row">
                <div class="symbol-info">
                    <span class="symbol-name">${sym.symbol}</span>
                    <span class="symbol-trades">${sym.trades} trades</span>
                </div>
                <div class="symbol-pnl ${sym.pnl >= 0 ? 'positive' : 'negative'}">
                    ${sym.pnl >= 0 ? '+' : ''}$${sym.pnl.toFixed(2)}
                </div>
            </div>
        `).join('');

        list.style.display = 'block';
    } catch (error) {
        console.error('Error loading symbol PnL:', error);
        loading.style.display = 'none';
        list.innerHTML = '<div class="empty-symbol-pnl">Failed to load data</div>';
        list.style.display = 'block';
    }
}

function setupSyncButton() {
    const syncBtn = document.getElementById('syncBtn');
    const syncModal = document.getElementById('syncModal');
    const syncProgress = document.getElementById('syncProgress');
    const syncStatus = document.getElementById('syncStatus');

    if (!syncBtn) return;

    syncBtn.addEventListener('click', async () => {
        syncModal.classList.add('active');
        syncProgress.style.width = '10%';
        syncStatus.textContent = 'Connecting to Binance...';

        try {
            syncProgress.style.width = '30%';
            syncStatus.textContent = 'Fetching trades...';

            const response = await fetch(`/api/accounts/${ACCOUNT_ID}/sync`, { method: 'POST' });
            const data = await response.json();

            syncProgress.style.width = '100%';

            if (response.ok) {
                syncStatus.textContent = `Done! Added ${data.new_trades} new trades.`;
                showToast(`Synced ${data.new_trades} new trades`, 'success');

                // Reload stats
                setTimeout(() => {
                    syncModal.classList.remove('active');
                    loadStats();
                    loadEquityCurve();
                    loadSymbolPnL();
                }, 1500);
            } else {
                syncStatus.textContent = data.error || 'Sync failed';
                showToast(data.error || 'Sync failed', 'error');
                setTimeout(() => syncModal.classList.remove('active'), 2000);
            }
        } catch (error) {
            console.error('Sync error:', error);
            syncStatus.textContent = 'Connection failed';
            showToast('Failed to sync trades', 'error');
            setTimeout(() => syncModal.classList.remove('active'), 2000);
        }
    });
}
