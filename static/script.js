/**
 * Trading Bot Manager - Frontend JavaScript
 * Handles all UI interactions and API communication
 */

// State management
let currentScript = null;
let scripts = [];
let logsInterval = null;

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
    logsPanel: document.getElementById('logsPanel')
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
            showToast('Failed to delete bot', 'error');
        }
    } catch (error) {
        showToast('Failed to delete bot', 'error');
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
        fetchLogs();
    }
}

// Start polling for logs
function startLogsPolling() {
    fetchLogs();
    if (logsInterval) clearInterval(logsInterval);
    logsInterval = setInterval(fetchLogs, 2000);
}

// Stop polling for logs
function stopLogsPolling() {
    if (logsInterval) {
        clearInterval(logsInterval);
        logsInterval = null;
    }
}

// Fetch logs from the server
async function fetchLogs() {
    if (!currentScript) return;
    
    try {
        const response = await fetch(`/api/scripts/${currentScript.id}/logs`);
        const data = await response.json();
        
        if (data.logs && data.logs.length > 0) {
            elements.logsContent.innerHTML = data.logs.map(log => 
                `<div class="log-line">${escapeHtml(log)}</div>`
            ).join('');
            
            // Auto-scroll to bottom
            elements.logsContent.scrollTop = elements.logsContent.scrollHeight;
        } else {
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

