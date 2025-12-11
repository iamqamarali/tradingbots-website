/**
 * Logs Page JavaScript
 * Handles all log viewing, refreshing, and clearing functionality
 */

// DOM Elements
const elements = {
    logsGrid: document.getElementById('logsGrid'),
    totalBots: document.getElementById('totalBots'),
    runningBots: document.getElementById('runningBots'),
    nextClear: document.getElementById('nextClear'),
    clearAllBtn: document.getElementById('clearAllBtn'),
    toastContainer: document.getElementById('toastContainer'),
    refreshIndicator: document.getElementById('refreshIndicator')
};

// Refresh interval
let refreshInterval = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadLogs();
    loadStatus();
    startAutoRefresh();
    setupEventListeners();
});

function setupEventListeners() {
    elements.clearAllBtn.addEventListener('click', clearAllLogs);
}

// Load all logs
async function loadLogs() {
    try {
        const response = await fetch('/api/logs');
        const data = await response.json();
        
        renderLogs(data);
    } catch (error) {
        console.error('Failed to load logs:', error);
        showToast('Failed to load logs', 'error');
    }
}

// Load system status
async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        elements.totalBots.textContent = data.total_scripts;
        elements.runningBots.textContent = data.running_scripts;
        elements.nextClear.textContent = formatNextClear(data.next_log_clear);
    } catch (error) {
        console.error('Failed to load status:', error);
    }
}

// Format next clear time
function formatNextClear(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = date - now;
    
    if (diff <= 0) return 'Soon';
    
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    
    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    }
    return `${minutes}m`;
}

// Render all log panels
function renderLogs(data) {
    const scriptIds = Object.keys(data);
    
    if (scriptIds.length === 0) {
        elements.logsGrid.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="16" y1="13" x2="8" y2="13"/>
                    <line x1="16" y1="17" x2="8" y2="17"/>
                </svg>
                <h3>No Bots Found</h3>
                <p>Add some trading bots to see their logs here.</p>
                <a href="/">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                    </svg>
                    Add Your First Bot
                </a>
            </div>
        `;
        return;
    }
    
    elements.logsGrid.innerHTML = scriptIds.map(scriptId => {
        const script = data[scriptId];
        const logsHtml = script.logs.length > 0 
            ? script.logs.map(log => {
                let lineClass = 'log-line';
                if (log.includes('[SYSTEM]')) lineClass += ' system';
                if (log.includes('[ERROR]') || log.includes('Error')) lineClass += ' error';
                return `<div class="${lineClass}">${escapeHtml(log)}</div>`;
            }).join('')
            : `<div class="log-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="12" y1="8" x2="12" y2="12"/>
                    <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <p>No logs yet</p>
            </div>`;
        
        return `
            <div class="log-panel" data-script-id="${scriptId}">
                <div class="log-panel-header">
                    <div class="log-panel-info">
                        <span class="log-panel-name">${escapeHtml(script.name)}</span>
                        <span class="log-panel-status ${script.status}">
                            <span class="dot"></span>
                            ${script.status}
                        </span>
                    </div>
                    <div class="log-panel-actions">
                        <button class="log-action-btn clear" onclick="clearScriptLogs('${scriptId}')" title="Clear logs">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                            </svg>
                        </button>
                        <button class="log-action-btn" onclick="scrollToBottom('${scriptId}')" title="Scroll to bottom">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="12" y1="5" x2="12" y2="19"></line>
                                <polyline points="19 12 12 19 5 12"></polyline>
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="log-panel-content" id="logs-${scriptId}">
                    ${logsHtml}
                </div>
            </div>
        `;
    }).join('');
    
    // Auto-scroll all log panels to bottom
    scriptIds.forEach(scriptId => {
        scrollToBottom(scriptId);
    });
}

// Clear logs for a specific script
async function clearScriptLogs(scriptId) {
    try {
        const response = await fetch(`/api/scripts/${scriptId}/logs`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('Logs cleared', 'success');
            loadLogs();
        } else {
            showToast('Failed to clear logs', 'error');
        }
    } catch (error) {
        showToast('Failed to clear logs', 'error');
    }
}

// Clear all logs
async function clearAllLogs() {
    if (!confirm('Are you sure you want to clear ALL logs? This cannot be undone.')) {
        return;
    }
    
    try {
        const response = await fetch('/api/logs', {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('All logs cleared', 'success');
            loadLogs();
        } else {
            showToast('Failed to clear logs', 'error');
        }
    } catch (error) {
        showToast('Failed to clear logs', 'error');
    }
}

// Scroll log panel to bottom
function scrollToBottom(scriptId) {
    const panel = document.getElementById(`logs-${scriptId}`);
    if (panel) {
        panel.scrollTop = panel.scrollHeight;
    }
}

// Start auto-refresh
function startAutoRefresh() {
    refreshInterval = setInterval(() => {
        loadLogs();
        loadStatus();
    }, 3000);
}

// Stop auto-refresh
function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// Show toast notification
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icons = {
        success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
        error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };
    
    toast.innerHTML = `
        <div class="toast-icon">${icons[type]}</div>
        <span class="toast-message">${escapeHtml(message)}</span>
    `;
    
    elements.toastContainer.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Expose functions to global scope
window.clearScriptLogs = clearScriptLogs;
window.scrollToBottom = scrollToBottom;

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
});






