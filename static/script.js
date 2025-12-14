/**
 * Trading Bot Manager - Frontend JavaScript
 * Handles all UI interactions and API communication
 */

// State management
let currentScript = null;
let scripts = [];
let logsInterval = null;
let displayedLogCount = 0;

// DOM Elements
const elements = {
    scriptsList: document.getElementById('scriptsList'),
    welcomeScreen: document.getElementById('welcomeScreen'),
    editorScreen: document.getElementById('editorScreen'),
    currentScriptName: document.getElementById('currentScriptName'),
    currentScriptStatus: document.getElementById('currentScriptStatus'),
    headerActions: document.getElementById('headerActions'),
    runBtn: document.getElementById('runBtn'),
    stopBtn: document.getElementById('stopBtn'),
    saveBtn: document.getElementById('saveBtn'),
    deleteBtn: document.getElementById('deleteBtn'),
    autoRestartCheckbox: document.getElementById('autoRestartCheckbox'),
    codeEditor: document.getElementById('codeEditor'),
    lineNumbers: document.getElementById('lineNumbers'),
    lineCount: document.getElementById('lineCount'),
    logsContent: document.getElementById('logsContent'),
    addScriptBtn: document.getElementById('addScriptBtn'),
    addScriptModal: document.getElementById('addScriptModal'),
    closeModal: document.getElementById('closeModal'),
    cancelBtn: document.getElementById('cancelBtn'),
    submitScript: document.getElementById('submitScript'),
    scriptName: document.getElementById('scriptName'),
    scriptDescription: document.getElementById('scriptDescription'),
    scriptContent: document.getElementById('scriptContent'),
    fileDropZone: document.getElementById('fileDropZone'),
    fileInput: document.getElementById('fileInput'),
    toastContainer: document.getElementById('toastContainer'),
    runningCount: document.getElementById('runningCount'),
    totalScripts: document.getElementById('totalScripts'),
    activeScripts: document.getElementById('activeScripts'),
    codePanel: document.getElementById('codePanel'),
    logsPanel: document.getElementById('logsPanel'),
    welcomeTitle: document.getElementById('welcomeTitle'),
    welcomeDescription: document.getElementById('welcomeDescription'),
    welcomeBtnText: document.getElementById('welcomeBtnText')
};

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    loadScripts();
    setupEventListeners();
    updateLineNumbers();
});

// Setup all event listeners
function setupEventListeners() {
    // Add script modal
    elements.addScriptBtn.addEventListener('click', openModal);
    elements.closeModal.addEventListener('click', closeModal);
    elements.cancelBtn.addEventListener('click', closeModal);
    elements.submitScript.addEventListener('click', submitNewScript);
    
    // File upload
    elements.fileDropZone.addEventListener('click', () => elements.fileInput.click());
    elements.fileInput.addEventListener('change', handleFileSelect);
    elements.fileDropZone.addEventListener('dragover', handleDragOver);
    elements.fileDropZone.addEventListener('dragleave', handleDragLeave);
    elements.fileDropZone.addEventListener('drop', handleDrop);
    
    // Script actions
    elements.runBtn.addEventListener('click', runCurrentScript);
    elements.stopBtn.addEventListener('click', stopCurrentScript);
    elements.saveBtn.addEventListener('click', saveCurrentScript);
    elements.deleteBtn.addEventListener('click', deleteCurrentScript);
    elements.autoRestartCheckbox.addEventListener('change', toggleAutoRestart);
    
    // Editor
    elements.codeEditor.addEventListener('input', updateLineNumbers);
    elements.codeEditor.addEventListener('scroll', syncScroll);
    elements.codeEditor.addEventListener('keydown', handleTab);
    
    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });
    
    // Close modal on outside click
    elements.addScriptModal.addEventListener('click', (e) => {
        if (e.target === elements.addScriptModal) closeModal();
    });
    
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 's') {
            e.preventDefault();
            if (currentScript) saveCurrentScript();
        }
    });
    
    // Mobile menu
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const mobileOverlay = document.getElementById('mobileOverlay');
    const sidebar = document.querySelector('.sidebar');
    
    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', () => {
            sidebar.classList.add('open');
            mobileOverlay.classList.add('active');
        });
    }
    
    if (mobileOverlay) {
        mobileOverlay.addEventListener('click', closeMobileMenu);
    }
}

// Close mobile menu
function closeMobileMenu() {
    const sidebar = document.querySelector('.sidebar');
    const mobileOverlay = document.getElementById('mobileOverlay');
    if (sidebar) sidebar.classList.remove('open');
    if (mobileOverlay) mobileOverlay.classList.remove('active');
}

// Load all scripts from the server
async function loadScripts() {
    try {
        const response = await fetch('/api/scripts');
        scripts = await response.json();
        renderScriptsList();
        updateStats();
    } catch (error) {
        showToast('Failed to load scripts', 'error');
    }
}

// Render the scripts list in the sidebar
function renderScriptsList() {
    if (scripts.length === 0) {
        elements.scriptsList.innerHTML = `
            <div class="empty-scripts">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="12" y1="18" x2="12" y2="12"/>
                    <line x1="9" y1="15" x2="15" y2="15"/>
                </svg>
                <p>No bots yet.<br>Click + to add one.</p>
            </div>
        `;
        return;
    }
    
    elements.scriptsList.innerHTML = scripts.map(script => `
        <div class="script-item ${currentScript?.id === script.id ? 'active' : ''}" 
             data-id="${script.id}" 
             onclick="selectScript('${script.id}')">
            <div class="script-item-header">
                <span class="script-name">${escapeHtml(script.name)}</span>
                <span class="script-status-badge ${script.status}">
                    <span class="status-dot"></span>
                    ${script.status}
                </span>
            </div>
            <div class="script-meta">${script.created}</div>
        </div>
    `).join('');
}

// Select a script to view/edit
async function selectScript(scriptId) {
    try {
        const response = await fetch(`/api/scripts/${scriptId}`);
        if (!response.ok) throw new Error('Script not found');
        
        currentScript = await response.json();
        displayedLogCount = 0;  // Reset log count for new script
        
        // Update UI
        elements.welcomeScreen.style.display = 'none';
        elements.editorScreen.style.display = 'flex';
        elements.headerActions.style.display = 'flex';
        
        elements.currentScriptName.textContent = currentScript.name;
        updateScriptStatus();
        
        // Update auto-restart checkbox
        elements.autoRestartCheckbox.checked = currentScript.auto_restart || false;
        
        elements.codeEditor.value = currentScript.content;
        updateLineNumbers();
        
        // Update sidebar selection
        document.querySelectorAll('.script-item').forEach(item => {
            item.classList.toggle('active', item.dataset.id === scriptId);
        });
        
        // Switch to code tab
        switchTab('code');
        
        // Start logs polling if running
        if (currentScript.status === 'running') {
            startLogsPolling();
        } else {
            stopLogsPolling();
        }
        
        // Close mobile menu if open
        if (window.innerWidth <= 768) {
            closeMobileMenu();
        }
        
    } catch (error) {
        showToast('Failed to load script', 'error');
    }
}

// Update script status display
function updateScriptStatus() {
    const isRunning = currentScript?.status === 'running';
    
    elements.currentScriptStatus.textContent = isRunning ? '● Running' : '○ Stopped';
    elements.currentScriptStatus.className = `script-status ${currentScript?.status || ''}`;
    
    elements.runBtn.style.display = isRunning ? 'none' : 'flex';
    elements.stopBtn.style.display = isRunning ? 'flex' : 'none';
}

// Run the current script
async function runCurrentScript() {
    if (!currentScript) return;
    
    try {
        const response = await fetch(`/api/scripts/${currentScript.id}/run`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentScript.status = 'running';
            updateScriptStatus();
            updateScriptInList(currentScript.id, 'running');
            startLogsPolling();
            showToast('Bot started successfully', 'success');
        } else {
            showToast(data.error || 'Failed to start bot', 'error');
        }
    } catch (error) {
        showToast('Failed to start bot', 'error');
    }
}

// Stop the current script
async function stopCurrentScript() {
    if (!currentScript) return;
    
    try {
        const response = await fetch(`/api/scripts/${currentScript.id}/stop`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentScript.status = 'stopped';
            updateScriptStatus();
            updateScriptInList(currentScript.id, 'stopped');
            stopLogsPolling();
            showToast('Bot stopped', 'info');
        } else {
            showToast(data.error || 'Failed to stop bot', 'error');
        }
    } catch (error) {
        showToast('Failed to stop bot', 'error');
    }
}

// Save the current script
async function saveCurrentScript() {
    if (!currentScript) return;
    
    try {
        const response = await fetch(`/api/scripts/${currentScript.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: elements.codeEditor.value
            })
        });
        
        if (response.ok) {
            showToast('Changes saved', 'success');
        } else {
            showToast('Failed to save changes', 'error');
        }
    } catch (error) {
        showToast('Failed to save changes', 'error');
    }
}

// Delete the current script
async function deleteCurrentScript() {
    if (!currentScript) return;

    if (!confirm(`Are you sure you want to delete "${currentScript.name}"? This action cannot be undone.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/scripts/${currentScript.id}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Bot deleted', 'info');

            // Remove from local list
            scripts = scripts.filter(s => s.id !== currentScript.id);
            currentScript = null;

            // Reset UI
            elements.welcomeScreen.style.display = 'flex';
            elements.editorScreen.style.display = 'none';
            elements.headerActions.style.display = 'none';
            elements.currentScriptName.textContent = 'Select a Script';
            elements.currentScriptStatus.textContent = '';

            renderScriptsList();
            updateStats();
            stopLogsPolling();
        } else {
            showToast(data.error || 'Failed to delete bot', 'error');
        }
    } catch (error) {
        showToast('Failed to delete bot: ' + error.message, 'error');
    }
}

// Toggle auto-restart setting
async function toggleAutoRestart() {
    if (!currentScript) return;
    
    try {
        const response = await fetch(`/api/scripts/${currentScript.id}/auto-restart`, {
            method: 'PUT'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentScript.auto_restart = data.auto_restart;
            
            // Update in local scripts list
            const script = scripts.find(s => s.id === currentScript.id);
            if (script) {
                script.auto_restart = data.auto_restart;
            }
            
            showToast(
                data.auto_restart ? 'Auto-restart enabled' : 'Auto-restart disabled',
                'success'
            );
        } else {
            // Revert checkbox on error
            elements.autoRestartCheckbox.checked = currentScript.auto_restart || false;
            showToast(data.error || 'Failed to update setting', 'error');
        }
    } catch (error) {
        // Revert checkbox on error
        elements.autoRestartCheckbox.checked = currentScript.auto_restart || false;
        showToast('Failed to update setting', 'error');
    }
}

// Update a script's status in the list
function updateScriptInList(scriptId, status) {
    const script = scripts.find(s => s.id === scriptId);
    if (script) {
        script.status = status;
        renderScriptsList();
        updateStats();
    }
}

// Open the add script modal
function openModal() {
    elements.addScriptModal.classList.add('active');
    elements.scriptName.value = '';
    elements.scriptDescription.value = '';
    elements.scriptContent.value = '';
    elements.scriptName.focus();
}

// Close the add script modal
function closeModal() {
    elements.addScriptModal.classList.remove('active');
}

// Submit a new script
async function submitNewScript() {
    const name = elements.scriptName.value.trim();
    const content = elements.scriptContent.value.trim();
    const description = elements.scriptDescription.value.trim();
    
    if (!name) {
        showToast('Please enter a bot name', 'error');
        elements.scriptName.focus();
        return;
    }
    
    if (!content) {
        showToast('Please enter or upload Python code', 'error');
        elements.scriptContent.focus();
        return;
    }
    
    try {
        const response = await fetch('/api/scripts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, content, description })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            scripts.push(data.script);
            renderScriptsList();
            updateStats();
            closeModal();
            selectScript(data.script.id);
            showToast('Bot added successfully', 'success');
        } else {
            showToast(data.error || 'Failed to add bot', 'error');
        }
    } catch (error) {
        showToast('Failed to add bot', 'error');
    }
}

// Handle file selection
function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) readFile(file);
}

// Handle drag over
function handleDragOver(e) {
    e.preventDefault();
    elements.fileDropZone.classList.add('dragover');
}

// Handle drag leave
function handleDragLeave(e) {
    e.preventDefault();
    elements.fileDropZone.classList.remove('dragover');
}

// Handle file drop
function handleDrop(e) {
    e.preventDefault();
    elements.fileDropZone.classList.remove('dragover');
    
    const file = e.dataTransfer.files[0];
    if (file && file.name.endsWith('.py')) {
        readFile(file);
    } else {
        showToast('Please drop a .py file', 'error');
    }
}

// Read file content
function readFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        elements.scriptContent.value = e.target.result;
        if (!elements.scriptName.value) {
            elements.scriptName.value = file.name.replace('.py', '');
        }
        showToast('File loaded', 'success');
    };
    reader.readAsText(file);
}

// Update line numbers
function updateLineNumbers() {
    const lines = elements.codeEditor.value.split('\n');
    const lineCount = lines.length;
    
    elements.lineNumbers.innerHTML = Array.from(
        { length: lineCount }, 
        (_, i) => `<div>${i + 1}</div>`
    ).join('');
    
    elements.lineCount.textContent = `${lineCount} line${lineCount !== 1 ? 's' : ''}`;
}

// Sync scroll between editor and line numbers
function syncScroll() {
    elements.lineNumbers.scrollTop = elements.codeEditor.scrollTop;
}

// Handle tab key in editor
function handleTab(e) {
    if (e.key === 'Tab') {
        e.preventDefault();
        const start = elements.codeEditor.selectionStart;
        const end = elements.codeEditor.selectionEnd;
        
        elements.codeEditor.value = 
            elements.codeEditor.value.substring(0, start) + 
            '    ' + 
            elements.codeEditor.value.substring(end);
        
        elements.codeEditor.selectionStart = elements.codeEditor.selectionEnd = start + 4;
        updateLineNumbers();
    }
}

// Switch between code and logs tabs
function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });
    
    elements.codePanel.classList.toggle('active', tabName === 'code');
    elements.logsPanel.classList.toggle('active', tabName === 'logs');
    
    if (tabName === 'logs' && currentScript) {
        fetchLogs(true);  // Force refresh when switching to logs tab
    }
}

// Start polling for logs
function startLogsPolling() {
    displayedLogCount = 0;  // Reset when starting fresh
    fetchLogs(true);  // Force full refresh on start
    if (logsInterval) clearInterval(logsInterval);
    logsInterval = setInterval(fetchLogs, 10000);  // Poll every 10 seconds
}

// Stop polling for logs
function stopLogsPolling() {
    if (logsInterval) {
        clearInterval(logsInterval);
        logsInterval = null;
    }
}

// Check if user is scrolled near the bottom
function isNearBottom() {
    const threshold = 100;  // pixels from bottom
    const { scrollTop, scrollHeight, clientHeight } = elements.logsContent;
    return scrollHeight - scrollTop - clientHeight < threshold;
}

// Fetch logs from the server
async function fetchLogs(forceFullRefresh = false) {
    if (!currentScript) return;
    
    try {
        const response = await fetch(`/api/scripts/${currentScript.id}/logs`);
        const data = await response.json();
        
        if (data.logs && data.logs.length > 0) {
            const wasNearBottom = isNearBottom();
            
            // Check if we need full refresh or just append
            if (forceFullRefresh || displayedLogCount === 0 || data.logs.length < displayedLogCount) {
                // Full refresh needed (first load, cleared logs, or reset)
                elements.logsContent.innerHTML = data.logs.map(log => 
                    `<div class="log-line">${escapeHtml(log)}</div>`
                ).join('');
                displayedLogCount = data.logs.length;
                
                // Scroll to bottom on initial load
                elements.logsContent.scrollTop = elements.logsContent.scrollHeight;
            } else if (data.logs.length > displayedLogCount) {
                // Append only new logs
                const newLogs = data.logs.slice(displayedLogCount);
                
                newLogs.forEach(log => {
                    const logLine = document.createElement('div');
                    logLine.className = 'log-line log-line-new';
                    logLine.innerHTML = escapeHtml(log);
                    elements.logsContent.appendChild(logLine);
                    
                    // Remove animation class after animation completes
                    setTimeout(() => logLine.classList.remove('log-line-new'), 500);
                });
                
                displayedLogCount = data.logs.length;
                
                // Only auto-scroll if user was already near bottom
                if (wasNearBottom) {
                    elements.logsContent.scrollTop = elements.logsContent.scrollHeight;
                }
            }
        } else {
            // No logs - show placeholder
            if (displayedLogCount > 0 || elements.logsContent.querySelector('.log-placeholder') === null) {
                displayedLogCount = 0;
                elements.logsContent.innerHTML = `
                    <div class="log-placeholder">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <circle cx="12" cy="12" r="10"/>
                            <polyline points="12 6 12 12 16 14"/>
                        </svg>
                        <p>No logs yet. Run the script to see output.</p>
                    </div>
                `;
            }
        }
    } catch (error) {
        console.error('Failed to fetch logs:', error);
    }
}

// Update statistics
function updateStats() {
    const running = scripts.filter(s => s.status === 'running').length;

    elements.runningCount.textContent = running;
    elements.totalScripts.textContent = scripts.length;
    elements.activeScripts.textContent = running;

    // Update welcome content based on whether there are bots
    if (scripts.length > 0) {
        elements.welcomeTitle.textContent = 'Dashboard';
        elements.welcomeDescription.textContent = 'Select a bot from the sidebar to view its code and logs, or add a new one.';
        elements.welcomeBtnText.textContent = 'Add New Bot';
    } else {
        elements.welcomeTitle.textContent = 'Welcome to BotTrader';
        elements.welcomeDescription.textContent = 'Your automated trading command center. Upload, manage, and monitor your Binance trading bots all in one place.';
        elements.welcomeBtnText.textContent = 'Add Your First Bot';
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
    
    // Remove after 3 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Expose selectScript to global scope for onclick handlers
window.selectScript = selectScript;

// ==================== DASHBOARD POSITIONS ====================

let allPositions = [];
let currentPositionData = null;

// DOM elements for positions
const positionElements = {
    positionsLoading: document.getElementById('positionsLoading'),
    positionsTableWrapper: document.getElementById('positionsTableWrapper'),
    positionsTableBody: document.getElementById('positionsTableBody'),
    emptyPositions: document.getElementById('emptyPositions'),
    positionCount: document.getElementById('positionCount'),
    refreshPositionsBtn: document.getElementById('refreshPositionsBtn'),
    // Close position modal
    closePositionModal: document.getElementById('closePositionModal'),
    closePositionModalClose: document.getElementById('closePositionModalClose'),
    closePositionSymbol: document.getElementById('closePositionSymbol'),
    closePositionSide: document.getElementById('closePositionSide'),
    closePositionAccount: document.getElementById('closePositionAccount'),
    closePositionSize: document.getElementById('closePositionSize'),
    closePositionPnl: document.getElementById('closePositionPnl'),
    closePercentageSlider: document.getElementById('closePercentageSlider'),
    closePercentageValue: document.getElementById('closePercentageValue'),
    closeQuantityValue: document.getElementById('closeQuantityValue'),
    cancelClosePosition: document.getElementById('cancelClosePosition'),
    confirmClosePosition: document.getElementById('confirmClosePosition'),
    // Stop loss modal
    editStopLossModal: document.getElementById('editStopLossModal'),
    editStopLossModalClose: document.getElementById('editStopLossModalClose'),
    slSymbol: document.getElementById('slSymbol'),
    slSide: document.getElementById('slSide'),
    slAccount: document.getElementById('slAccount'),
    slCurrentStop: document.getElementById('slCurrentStop'),
    newStopPrice: document.getElementById('newStopPrice'),
    slHint: document.getElementById('slHint'),
    removeStopLossBtn: document.getElementById('removeStopLossBtn'),
    cancelEditStopLoss: document.getElementById('cancelEditStopLoss'),
    confirmEditStopLoss: document.getElementById('confirmEditStopLoss')
};

// Load all positions on page load (uses server-side cache)
document.addEventListener('DOMContentLoaded', () => {
    loadAllPositions();  // Uses cached data if < 15 min old
    setupPositionEventListeners();
});

// Setup event listeners for positions
function setupPositionEventListeners() {
    // Refresh button - force refresh from Binance API
    if (positionElements.refreshPositionsBtn) {
        positionElements.refreshPositionsBtn.addEventListener('click', () => loadAllPositions(true));
    }

    // Close position modal
    if (positionElements.closePositionModalClose) {
        positionElements.closePositionModalClose.addEventListener('click', closeClosePositionModal);
    }
    if (positionElements.cancelClosePosition) {
        positionElements.cancelClosePosition.addEventListener('click', closeClosePositionModal);
    }
    if (positionElements.confirmClosePosition) {
        positionElements.confirmClosePosition.addEventListener('click', executeClosePosition);
    }
    if (positionElements.closePositionModal) {
        positionElements.closePositionModal.addEventListener('click', (e) => {
            if (e.target === positionElements.closePositionModal) closeClosePositionModal();
        });
    }

    // Percentage buttons
    document.querySelectorAll('#closePositionModal .pct-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#closePositionModal .pct-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const pct = parseInt(btn.dataset.pct);
            positionElements.closePercentageSlider.value = pct;
            updateCloseQuantity();
        });
    });

    // Slider
    if (positionElements.closePercentageSlider) {
        positionElements.closePercentageSlider.addEventListener('input', () => {
            document.querySelectorAll('#closePositionModal .pct-btn').forEach(b => b.classList.remove('active'));
            updateCloseQuantity();
        });
    }

    // Stop loss modal
    if (positionElements.editStopLossModalClose) {
        positionElements.editStopLossModalClose.addEventListener('click', closeEditStopLossModal);
    }
    if (positionElements.cancelEditStopLoss) {
        positionElements.cancelEditStopLoss.addEventListener('click', closeEditStopLossModal);
    }
    if (positionElements.confirmEditStopLoss) {
        positionElements.confirmEditStopLoss.addEventListener('click', executeUpdateStopLoss);
    }
    if (positionElements.removeStopLossBtn) {
        positionElements.removeStopLossBtn.addEventListener('click', executeRemoveStopLoss);
    }
    if (positionElements.editStopLossModal) {
        positionElements.editStopLossModal.addEventListener('click', (e) => {
            if (e.target === positionElements.editStopLossModal) closeEditStopLossModal();
        });
    }
}

// Load all positions from all accounts
async function loadAllPositions(forceRefresh = false) {
    if (!positionElements.positionsLoading) return;

    positionElements.positionsLoading.style.display = 'flex';
    positionElements.positionsTableWrapper.style.display = 'none';
    positionElements.emptyPositions.style.display = 'none';
    positionElements.refreshPositionsBtn.classList.add('loading');

    try {
        const url = forceRefresh ? '/api/positions/all?force=true' : '/api/positions/all';
        const response = await fetch(url);
        const data = await response.json();

        if (response.ok) {
            allPositions = data;
            renderPositions();
        } else {
            console.error('Error loading positions:', data.error);
            showToast(data.error || 'Failed to load positions', 'error');
        }
    } catch (error) {
        console.error('Error loading positions:', error);
        showToast('Failed to load positions', 'error');
    } finally {
        positionElements.positionsLoading.style.display = 'none';
        positionElements.refreshPositionsBtn.classList.remove('loading');
    }
}

// Render positions table
function renderPositions() {
    positionElements.positionCount.textContent = allPositions.length;

    if (allPositions.length === 0) {
        positionElements.positionsTableWrapper.style.display = 'none';
        positionElements.emptyPositions.style.display = 'flex';
        return;
    }

    positionElements.emptyPositions.style.display = 'none';
    positionElements.positionsTableWrapper.style.display = 'block';

    positionElements.positionsTableBody.innerHTML = allPositions.map(pos => {
        const pnlClass = pos.unrealized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
        const pnlPrefix = pos.unrealized_pnl >= 0 ? '+' : '';
        const testnetBadge = pos.is_testnet ? '<span class="testnet-badge">TESTNET</span>' : '';
        const sizeInUsd = Math.abs(pos.quantity * pos.mark_price);

        return `
            <tr>
                <td><a href="/accounts/${pos.account_id}" class="account-link">${escapeHtml(pos.account_name)}${testnetBadge}</a></td>
                <td class="symbol">${pos.symbol}</td>
                <td><span class="side ${pos.side.toLowerCase()}">${pos.side}</span></td>
                <td><span class="size-qty">${pos.quantity}</span><span class="size-usd">$${sizeInUsd.toFixed(2)}</span></td>
                <td>${formatPrice(pos.entry_price)}</td>
                <td>${formatPrice(pos.mark_price)}</td>
                <td class="sl-tp-cell">
                    <div class="sl-tp-row">
                        <span class="sl-label">SL:</span>
                        <span class="${pos.stop_price ? 'has-sl' : 'no-sl'}">${pos.stop_price ? formatPrice(pos.stop_price) : '—'}</span>
                    </div>
                    <div class="sl-tp-row">
                        <span class="tp-label">TP:</span>
                        <span class="${pos.tp_price ? 'has-tp' : 'no-tp'}">${pos.tp_price ? formatPrice(pos.tp_price) : '—'}</span>
                        <button class="edit-sl-btn" onclick="openEditStopLossModal(${pos.account_id}, '${pos.symbol}', '${pos.side}', ${pos.quantity}, ${pos.stop_price || 'null'}, ${pos.stop_order_id || 'null'}, '${escapeHtml(pos.account_name)}')" title="Edit Stop Loss">
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                            </svg>
                        </button>
                    </div>
                </td>
                <td class="${pnlClass}">${pnlPrefix}$${pos.unrealized_pnl.toFixed(2)}</td>
                <td><span class="leverage-badge">${pos.leverage}x</span></td>
                <td class="actions-cell">
                    <button class="close-position-btn" onclick="openClosePositionModal(${pos.account_id}, '${pos.symbol}', '${pos.side}', ${pos.quantity}, ${pos.unrealized_pnl}, '${escapeHtml(pos.account_name)}')">Close</button>
                </td>
            </tr>
        `;
    }).join('');
}

// Format price for display
function formatPrice(price) {
    if (price >= 1000) return price.toFixed(2);
    if (price >= 1) return price.toFixed(4);
    return price.toFixed(6);
}

// Open close position modal
function openClosePositionModal(accountId, symbol, side, quantity, pnl, accountName) {
    currentPositionData = { accountId, symbol, side, quantity, pnl, accountName };

    positionElements.closePositionSymbol.textContent = symbol;
    positionElements.closePositionSide.textContent = side;
    positionElements.closePositionSide.className = `position-side ${side.toLowerCase()}`;
    positionElements.closePositionAccount.textContent = accountName;
    positionElements.closePositionSize.textContent = quantity;
    positionElements.closePositionPnl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
    positionElements.closePositionPnl.className = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';

    // Reset to 100%
    positionElements.closePercentageSlider.value = 100;
    document.querySelectorAll('#closePositionModal .pct-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('#closePositionModal .pct-btn[data-pct="100"]').classList.add('active');
    updateCloseQuantity();

    positionElements.closePositionModal.classList.add('active');
}

// Close the close position modal
function closeClosePositionModal() {
    positionElements.closePositionModal.classList.remove('active');
    currentPositionData = null;
}

// Update close quantity based on slider
function updateCloseQuantity() {
    if (!currentPositionData) return;
    const percentage = parseInt(positionElements.closePercentageSlider.value);
    positionElements.closePercentageValue.textContent = `${percentage}%`;
    const closeQty = (currentPositionData.quantity * percentage / 100).toFixed(6);
    positionElements.closeQuantityValue.textContent = closeQty;
}

// Execute close position
async function executeClosePosition() {
    if (!currentPositionData) return;

    const percentage = parseInt(positionElements.closePercentageSlider.value);
    const closeQty = currentPositionData.quantity * percentage / 100;

    positionElements.confirmClosePosition.disabled = true;
    positionElements.confirmClosePosition.innerHTML = '<span class="btn-loading"><span class="btn-spinner"></span>Closing...</span>';

    try {
        const response = await fetch(`/api/accounts/${currentPositionData.accountId}/close-position`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentPositionData.symbol,
                side: currentPositionData.side,
                quantity: closeQty
            })
        });

        const data = await response.json();

        if (response.ok) {
            showToast(`Position closed: ${currentPositionData.symbol}`, 'success');
            closeClosePositionModal();
            loadAllPositions();
        } else {
            showToast(data.error || 'Failed to close position', 'error');
        }
    } catch (error) {
        console.error('Error closing position:', error);
        showToast('Failed to close position', 'error');
    } finally {
        positionElements.confirmClosePosition.disabled = false;
        positionElements.confirmClosePosition.innerHTML = 'Close Position';
    }
}

// Open edit stop loss modal
function openEditStopLossModal(accountId, symbol, side, quantity, stopPrice, stopOrderId, accountName) {
    currentPositionData = { accountId, symbol, side, quantity, stopPrice, stopOrderId, accountName };

    positionElements.slSymbol.textContent = symbol;
    positionElements.slSide.textContent = side;
    positionElements.slSide.className = `position-side ${side.toLowerCase()}`;
    positionElements.slAccount.textContent = accountName;

    if (stopPrice) {
        positionElements.slCurrentStop.textContent = formatPrice(stopPrice);
        positionElements.slCurrentStop.className = 'has-sl';
        positionElements.removeStopLossBtn.style.display = 'block';
    } else {
        positionElements.slCurrentStop.textContent = 'None';
        positionElements.slCurrentStop.className = 'no-sl';
        positionElements.removeStopLossBtn.style.display = 'none';
    }

    positionElements.newStopPrice.value = '';
    positionElements.slHint.textContent = side === 'LONG' ? 'Set below entry price' : 'Set above entry price';

    positionElements.editStopLossModal.classList.add('active');
}

// Close edit stop loss modal
function closeEditStopLossModal() {
    positionElements.editStopLossModal.classList.remove('active');
    currentPositionData = null;
}

// Execute update stop loss
async function executeUpdateStopLoss() {
    if (!currentPositionData) return;

    const newPrice = parseFloat(positionElements.newStopPrice.value);
    if (!newPrice || isNaN(newPrice)) {
        showToast('Please enter a valid stop price', 'error');
        return;
    }

    positionElements.confirmEditStopLoss.disabled = true;
    positionElements.confirmEditStopLoss.innerHTML = '<span class="btn-loading"><span class="btn-spinner"></span>Updating...</span>';

    try {
        const response = await fetch(`/api/accounts/${currentPositionData.accountId}/update-stop-loss`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentPositionData.symbol,
                position_side: currentPositionData.side,
                stop_price: newPrice,
                quantity: currentPositionData.quantity,
                old_order_id: currentPositionData.stopOrderId
            })
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Stop loss updated', 'success');
            closeEditStopLossModal();
            loadAllPositions();
        } else {
            showToast(data.error || 'Failed to update stop loss', 'error');
        }
    } catch (error) {
        console.error('Error updating stop loss:', error);
        showToast('Failed to update stop loss', 'error');
    } finally {
        positionElements.confirmEditStopLoss.disabled = false;
        positionElements.confirmEditStopLoss.innerHTML = 'Update Stop Loss';
    }
}

// Execute remove stop loss
async function executeRemoveStopLoss() {
    if (!currentPositionData || !currentPositionData.stopOrderId) return;

    positionElements.removeStopLossBtn.disabled = true;
    positionElements.removeStopLossBtn.innerHTML = 'Removing...';

    try {
        const response = await fetch(`/api/accounts/${currentPositionData.accountId}/cancel-stop-loss`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentPositionData.symbol,
                order_id: currentPositionData.stopOrderId
            })
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Stop loss removed', 'success');
            closeEditStopLossModal();
            loadAllPositions();
        } else {
            showToast(data.error || 'Failed to remove stop loss', 'error');
        }
    } catch (error) {
        console.error('Error removing stop loss:', error);
        showToast('Failed to remove stop loss', 'error');
    } finally {
        positionElements.removeStopLossBtn.disabled = false;
        positionElements.removeStopLossBtn.innerHTML = 'Remove SL';
    }
}

// Expose functions to global scope
window.openClosePositionModal = openClosePositionModal;
window.openEditStopLossModal = openEditStopLossModal;

