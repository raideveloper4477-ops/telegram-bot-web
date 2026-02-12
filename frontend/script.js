// Global state
let currentBotId = null;
let timerInterval = null;
let logsPollInterval = null;
let statusPollInterval = null;
let resourcesPollInterval = null;
let timerSeconds = 0;
let botStartTime = null;

// API base URL (relative)
const API = {
    // Auth
    signup: '/signup',
    login: '/login',
    logout: '/logout',
    
    // Bots
    createBot: '/bot/create',
    listBots: '/my/bots',
    upload: '/upload',
    startBot: '/bot/start',
    stopBot: '/bot/stop',
    restartBot: '/bot/restart',
    logs: '/bot/logs',
    status: '/bot/status',
    resources: '/bot/resources',
    command: '/bot/command',
    downloadLogs: '/bot/logs/download',
    
    // Account
    changePassword: '/account/change-password',
    deleteAccount: '/account/delete',
    
    // Plan
    planInfo: '/plan/info',
    upgradePlan: '/upgrade-plan'
};

// Toast notifications
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type === 'error' ? 'toast-error' : ''}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.remove();
    }, 5000);
}

// Loading spinner
function showLoading(button) {
    const originalText = button.textContent;
    button.disabled = true;
    button.innerHTML = '<span class="spinner"></span> Loading...';
    return function restore() {
        button.disabled = false;
        button.textContent = originalText;
    };
}

// ------------------ Authentication ------------------
document.addEventListener('DOMContentLoaded', function() {
    // Signup form
    const signupForm = document.getElementById('signup-form');
    if (signupForm) {
        signupForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(signupForm);
            const data = Object.fromEntries(formData.entries());
            
            const submitBtn = signupForm.querySelector('button[type="submit"]');
            const restore = showLoading(submitBtn);
            
            try {
                const res = await fetch(API.signup, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await res.json();
                if (result.success) {
                    showToast('Account created! Redirecting to login...');
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 2000);
                } else {
                    showToast(result.message || 'Signup failed', 'error');
                    restore();
                }
            } catch (err) {
                showToast('Network error', 'error');
                restore();
            }
        });
    }
    
    // Login form
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(loginForm);
            const data = Object.fromEntries(formData.entries());
            
            const submitBtn = loginForm.querySelector('button[type="submit"]');
            const restore = showLoading(submitBtn);
            
            try {
                const res = await fetch(API.login, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await res.json();
                if (result.success) {
                    showToast('Login successful!');
                    window.location.href = '/dashboard';
                } else {
                    showToast(result.message || 'Login failed', 'error');
                    restore();
                }
            } catch (err) {
                showToast('Network error', 'error');
                restore();
            }
        });
    }
    
    // Logout
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            await fetch(API.logout);
            window.location.href = '/';
        });
    }
    
    // Dashboard initialization
    if (window.location.pathname === '/dashboard') {
        initDashboard();
    }
    
    // Admin dashboard initialization
    if (window.location.pathname === '/admin') {
        initAdminDashboard();
    }
    
    // Upgrade page
    if (window.location.pathname === '/upgrade') {
        initUpgradePage();
    }
});

// ------------------ Dashboard ------------------
async function initDashboard() {
    // Load user plan
    await loadPlanInfo();
    
    // Load bots list
    await loadBots();
    
    // Setup event listeners
    setupDashboardEvents();
    
    // Start polling
    startPolling();
}

async function loadPlanInfo() {
    try {
        const res = await fetch(API.planInfo);
        const data = await res.json();
        const planBadge = document.getElementById('plan-badge');
        if (planBadge) {
            planBadge.textContent = data.plan;
        }
    } catch (err) {
        console.error('Failed to load plan info', err);
    }
}

async function loadBots() {
    try {
        const res = await fetch(API.listBots);
        const bots = await res.json();
        const select = document.getElementById('bot-select');
        if (!select) return;
        
        select.innerHTML = '<option value="">-- Select a bot --</option>';
        bots.forEach(bot => {
            const option = document.createElement('option');
            option.value = bot.id;
            option.textContent = `${bot.bot_name} (${bot.status})`;
            select.appendChild(option);
        });
        
        // If there's a bot, select the first one
        if (bots.length > 0) {
            select.value = bots[0].id;
            currentBotId = bots[0].id;
            loadBotDetails(currentBotId);
        } else {
            // Show create bot form
            document.getElementById('no-bot-message').style.display = 'block';
            document.getElementById('bot-controls').style.display = 'none';
        }
        
        select.addEventListener('change', (e) => {
            currentBotId = e.target.value;
            if (currentBotId) {
                loadBotDetails(currentBotId);
            }
        });
    } catch (err) {
        console.error('Failed to load bots', err);
    }
}

async function loadBotDetails(botId) {
    if (!botId) return;
    
    // Update UI to show controls
    document.getElementById('no-bot-message').style.display = 'none';
    document.getElementById('bot-controls').style.display = 'block';
    
    // Load bot status
    await updateBotStatus(botId);
    
    // Load logs
    await updateLogs(botId);
    
    // Load resources
    await updateResources(botId);
}

async function updateBotStatus(botId) {
    try {
        const res = await fetch(`${API.status}?bot_id=${botId}`);
        const data = await res.json();
        const statusEl = document.getElementById('bot-status');
        if (statusEl) {
            statusEl.textContent = data.status;
            statusEl.className = `status-badge status-${data.status.toLowerCase()}`;
        }
        
        // Update timer
        if (data.start_time) {
            botStartTime = new Date(data.start_time);
            startTimer();
        } else {
            stopTimer();
        }
        
        // Update buttons state
        const startBtn = document.getElementById('start-btn');
        const stopBtn = document.getElementById('stop-btn');
        const restartBtn = document.getElementById('restart-btn');
        const commandInput = document.getElementById('command-input');
        const sendCommandBtn = document.getElementById('send-command-btn');
        
        if (data.status === 'RUNNING') {
            startBtn.disabled = true;
            stopBtn.disabled = false;
            restartBtn.disabled = false;
            if (commandInput) commandInput.disabled = false;
            if (sendCommandBtn) sendCommandBtn.disabled = false;
        } else {
            startBtn.disabled = false;
            stopBtn.disabled = true;
            restartBtn.disabled = true;
            if (commandInput) commandInput.disabled = true;
            if (sendCommandBtn) sendCommandBtn.disabled = true;
        }
    } catch (err) {
        console.error('Failed to update status', err);
    }
}

async function updateLogs(botId) {
    try {
        const res = await fetch(`${API.logs}?bot_id=${botId}`);
        const data = await res.json();
        const consoleEl = document.getElementById('console');
        if (consoleEl && data.logs) {
            consoleEl.innerHTML = data.logs.map(log => {
                const [timestamp, line, isError] = log;
                return `<div class="console-line ${isError ? 'console-error' : ''}">[${timestamp}] ${line}</div>`;
            }).join('');
            // Auto-scroll to bottom
            consoleEl.scrollTop = consoleEl.scrollHeight;
        }
    } catch (err) {
        console.error('Failed to update logs', err);
    }
}

async function updateResources(botId) {
    try {
        const res = await fetch(`${API.resources}?bot_id=${botId}`);
        const data = await res.json();
        const cpuBar = document.getElementById('cpu-bar');
        const ramBar = document.getElementById('ram-bar');
        const cpuText = document.getElementById('cpu-text');
        const ramText = document.getElementById('ram-text');
        
        if (cpuBar) {
            cpuBar.style.width = `${data.cpu}%`;
            cpuBar.className = `resource-fill ${data.cpu > 80 ? 'resource-fill-danger' : data.cpu > 50 ? 'resource-fill-warning' : ''}`;
        }
        if (cpuText) cpuText.textContent = `${data.cpu}%`;
        if (ramBar) {
            const ramPercent = Math.min((data.ram / 500) * 100, 100); // Assume 500MB max for display
            ramBar.style.width = `${ramPercent}%`;
            ramBar.className = `resource-fill ${ramPercent > 80 ? 'resource-fill-danger' : ramPercent > 50 ? 'resource-fill-warning' : ''}`;
        }
        if (ramText) ramText.textContent = `${data.ram} MB`;
    } catch (err) {
        console.error('Failed to update resources', err);
    }
}

function startTimer() {
    stopTimer(); // Clear existing
    if (!botStartTime) return;
    
    timerInterval = setInterval(() => {
        const now = new Date();
        const diff = Math.floor((now - botStartTime) / 1000);
        timerSeconds = diff;
        const hours = Math.floor(diff / 3600);
        const minutes = Math.floor((diff % 3600) / 60);
        const seconds = diff % 60;
        
        const timerEl = document.getElementById('timer');
        if (timerEl) {
            timerEl.textContent = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
            if (hours >= 23) {
                timerEl.classList.add('timer-warning');
            }
        }
    }, 1000);
}

function stopTimer() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
    const timerEl = document.getElementById('timer');
    if (timerEl) {
        timerEl.textContent = '00:00:00';
        timerEl.classList.remove('timer-warning');
    }
    timerSeconds = 0;
}

function setupDashboardEvents() {
    // Create new bot
    const createBotBtn = document.getElementById('create-bot-btn');
    if (createBotBtn) {
        createBotBtn.addEventListener('click', async () => {
            const name = prompt('Enter bot name:', 'My Bot');
            if (!name) return;
            try {
                const res = await fetch(API.createBot, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ bot_name: name })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('Bot created!');
                    await loadBots();
                } else {
                    showToast(data.error || 'Failed to create bot', 'error');
                }
            } catch (err) {
                showToast('Network error', 'error');
            }
        });
    }
    
    // Upload files
    const uploadBtn = document.getElementById('upload-btn');
    if (uploadBtn) {
        uploadBtn.addEventListener('click', async () => {
            if (!currentBotId) {
                showToast('Please select a bot', 'error');
                return;
            }
            const reqFile = document.getElementById('requirements-file').files[0];
            const botFile = document.getElementById('bot-file').files[0];
            
            if (!reqFile && !botFile) {
                showToast('Select files to upload', 'error');
                return;
            }
            
            const formData = new FormData();
            formData.append('bot_id', currentBotId);
            if (reqFile) formData.append('requirements', reqFile);
            if (botFile) formData.append('bot', botFile);
            
            try {
                const res = await fetch(API.upload, {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.success) {
                    showToast('Files uploaded successfully');
                } else {
                    showToast(data.error || 'Upload failed', 'error');
                }
            } catch (err) {
                showToast('Network error', 'error');
            }
        });
    }
    
    // Start bot
    const startBtn = document.getElementById('start-btn');
    if (startBtn) {
        startBtn.addEventListener('click', async () => {
            if (!currentBotId) return;
            const restore = showLoading(startBtn);
            try {
                const res = await fetch(API.startBot, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ bot_id: currentBotId })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('Bot started');
                    await updateBotStatus(currentBotId);
                } else {
                    showToast(data.message || 'Failed to start', 'error');
                }
            } catch (err) {
                showToast('Network error', 'error');
            }
            restore();
        });
    }
    
    // Stop bot
    const stopBtn = document.getElementById('stop-btn');
    if (stopBtn) {
        stopBtn.addEventListener('click', async () => {
            if (!currentBotId) return;
            try {
                await fetch(API.stopBot, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ bot_id: currentBotId })
                });
                showToast('Bot stopped');
                await updateBotStatus(currentBotId);
            } catch (err) {
                showToast('Network error', 'error');
            }
        });
    }
    
    // Restart bot
    const restartBtn = document.getElementById('restart-btn');
    if (restartBtn) {
        restartBtn.addEventListener('click', async () => {
            if (!currentBotId) return;
            const restore = showLoading(restartBtn);
            try {
                const res = await fetch(API.restartBot, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ bot_id: currentBotId })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('Bot restarted');
                    await updateBotStatus(currentBotId);
                } else {
                    showToast(data.message || 'Failed to restart', 'error');
                }
            } catch (err) {
                showToast('Network error', 'error');
            }
            restore();
        });
    }
    
    // Send command
    const sendCommandBtn = document.getElementById('send-command-btn');
    const commandInput = document.getElementById('command-input');
    if (sendCommandBtn && commandInput) {
        sendCommandBtn.addEventListener('click', async () => {
            const cmd = commandInput.value.trim();
            if (!cmd || !currentBotId) return;
            try {
                await fetch(API.command, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ bot_id: currentBotId, command: cmd })
                });
                commandInput.value = '';
            } catch (err) {
                showToast('Failed to send command', 'error');
            }
        });
        
        commandInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendCommandBtn.click();
            }
        });
    }
    
    // Download logs
    const downloadLogsBtn = document.getElementById('download-logs-btn');
    if (downloadLogsBtn) {
        downloadLogsBtn.addEventListener('click', () => {
            if (!currentBotId) return;
            window.location.href = `${API.downloadLogs}?bot_id=${currentBotId}`;
        });
    }
}

function startPolling() {
    // Poll logs every 2 seconds
    logsPollInterval = setInterval(() => {
        if (currentBotId) {
            updateLogs(currentBotId);
        }
    }, 2000);
    
    // Poll status every 5 seconds
    statusPollInterval = setInterval(() => {
        if (currentBotId) {
            updateBotStatus(currentBotId);
        }
    }, 5000);
    
    // Poll resources every 5 seconds
    resourcesPollInterval = setInterval(() => {
        if (currentBotId) {
            updateResources(currentBotId);
        }
    }, 5000);
}

function stopPolling() {
    if (logsPollInterval) clearInterval(logsPollInterval);
    if (statusPollInterval) clearInterval(statusPollInterval);
    if (resourcesPollInterval) clearInterval(resourcesPollInterval);
}

// ------------------ Admin Dashboard ------------------
async function initAdminDashboard() {
    loadAdminStats();
    loadAdminUsers();
    loadAdminBots();
    
    setInterval(loadAdminStats, 10000);
}

async function loadAdminStats() {
    try {
        const res = await fetch('/admin/system-stats');
        const data = await res.json();
        document.getElementById('total-users').textContent = data.total_users;
        document.getElementById('total-bots').textContent = data.total_bots;
        document.getElementById('running-bots').textContent = data.running_bots;
    } catch (err) {
        console.error('Failed to load admin stats', err);
    }
}

async function loadAdminUsers() {
    try {
        const res = await fetch('/admin/users');
        const users = await res.json();
        const tbody = document.getElementById('users-table-body');
        tbody.innerHTML = users.map(user => `
            <tr>
                <td>${user.id}</td>
                <td>${user.username}</td>
                <td>${user.first_name} ${user.last_name}</td>
                <td>${user.email_or_phone}</td>
                <td>${user.role}</td>
                <td>${user.plan}</td>
                <td>${user.suspended ? 'Yes' : 'No'}</td>
                <td>
                    <button onclick="adminToggleSuspend(${user.id}, ${!user.suspended})">${user.suspended ? 'Unsuspend' : 'Suspend'}</button>
                    <button onclick="adminDeleteUser(${user.id})">Delete</button>
                    <button onclick="adminChangePlan(${user.id})">Change Plan</button>
                </td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Failed to load users', err);
    }
}

async function loadAdminBots() {
    try {
        const res = await fetch('/admin/bots');
        const bots = await res.json();
        const tbody = document.getElementById('bots-table-body');
        tbody.innerHTML = bots.map(bot => `
            <tr>
                <td>${bot.id}</td>
                <td>${bot.owner_username}</td>
                <td>${bot.bot_name}</td>
                <td>${bot.status}</td>
                <td>${bot.running ? 'Yes' : 'No'}</td>
                <td>
                    <button onclick="adminForceStopBot(${bot.id})">Force Stop</button>
                </td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Failed to load bots', err);
    }
}

// Admin functions (exposed globally)
window.adminToggleSuspend = async function(userId, suspend) {
    await fetch('/admin/user/suspend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, suspend: suspend })
    });
    loadAdminUsers();
};

window.adminDeleteUser = async function(userId) {
    if (!confirm('Are you sure? This will delete the user and all their bots.')) return;
    await fetch('/admin/user/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId })
    });
    loadAdminUsers();
    loadAdminBots();
};

window.adminChangePlan = async function(userId) {
    const plan = prompt('Enter new plan (FREE, PRO, ULTRA):');
    if (!plan) return;
    await fetch('/admin/user/change-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, plan: plan.toUpperCase() })
    });
    loadAdminUsers();
};

window.adminForceStopBot = async function(botId) {
    await fetch('/admin/bot/force-stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bot_id: botId })
    });
    loadAdminBots();
};

// ------------------ Upgrade Page ------------------
async function initUpgradePage() {
    // Load current plan
    const res = await fetch(API.planInfo);
    const data = await res.json();
    document.getElementById('current-plan').textContent = data.plan;
    
    // Upgrade buttons
    document.querySelectorAll('.upgrade-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const plan = e.target.dataset.plan;
            const confirm = await fetch(API.upgradePlan, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ plan: plan })
            });
            const result = await confirm.json();
            if (result.success) {
                showToast(`Upgraded to ${plan} plan!`);
                setTimeout(() => window.location.reload(), 2000);
            } else {
                showToast(result.message || 'Upgrade failed', 'error');
            }
        });
    });
}