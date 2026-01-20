// ============================================
// NektoMe Chat Manager - Frontend Application
// ============================================

const ws = new WebSocket(`ws://${window.location.host}/ws`);
const rooms = new Map();

// WebSocket connection status
ws.onopen = () => {
    updateConnectionStatus('connected');
};

ws.onclose = () => {
    updateConnectionStatus('disconnected');
};

ws.onerror = () => {
    updateConnectionStatus('disconnected');
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === 'initial_state') {
        data.rooms.forEach(room => rooms.set(room.room_id, room));
        renderRooms();
    } else if (data.type === 'room_update') {
        const room = rooms.get(data.room_id);
        if (room) {
            Object.assign(room, data);
            updateRoomMeta(data.room_id);
        }
    } else if (data.type === 'new_message') {
        const room = rooms.get(data.room_id);
        if (room) {
            room.messages.push(data.message);
            room.messages_count++;
            appendMessage(data.room_id, data.message);
        }
    }
};

function updateConnectionStatus(status) {
    const indicator = document.querySelector('.ws-indicator');
    if (!indicator) return;

    indicator.className = `ws-indicator ${status}`;
    indicator.querySelector('span:last-child').textContent =
        status === 'connected' ? 'Connected' : 'Disconnected';
}

function renderRooms() {
    const grid = document.getElementById('rooms-grid');
    grid.innerHTML = '';

    if (rooms.size === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">
                    <i data-lucide="inbox"></i>
                </div>
                <p>No active rooms</p>
            </div>
        `;
        refreshIcons();
        return;
    }

    rooms.forEach((room, roomId) => {
        grid.appendChild(createRoomCard(room));
    });
    refreshIcons();
}

function renderRoom(roomId) {
    const room = rooms.get(roomId);
    const oldCard = document.getElementById(`room-${roomId}`);
    if (oldCard) {
        oldCard.replaceWith(createRoomCard(room));
        refreshIcons();
    }
}

function appendMessage(roomId, msg) {
    const chatArea = document.getElementById(`chat-${roomId}`);
    if (!chatArea) return;

    const msgDiv = document.createElement('div');
    if (msg.from === 'system') {
        msgDiv.className = 'message message-system';
        msgDiv.innerHTML = `
            <div class="message-bubble">
                <i data-lucide="info"></i>
                ${escapeHtml(msg.message)}
            </div>
        `;
    } else {
        msgDiv.className = `message message-${msg.from.toLowerCase()}`;
        msgDiv.innerHTML = `
            <div class="message-header">
                <i data-lucide="${msg.from === 'M' ? 'user' : 'user'}"></i>
                <span>${msg.from}</span>
                ${msg.is_manual ? '<span class="manual-badge"><i data-lucide="hand"></i>manual</span>' : ''}
                <span>${new Date(msg.timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
            <div class="message-bubble">${escapeHtml(msg.message)}</div>
        `;
    }

    const emptyState = chatArea.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    chatArea.appendChild(msgDiv);
    chatArea.scrollTop = chatArea.scrollHeight;
    refreshIcons();
}

function updateRoomMeta(roomId) {
    const room = rooms.get(roomId);
    const card = document.getElementById(`room-${roomId}`);
    if (!card) return;

    const statusClass = room.is_active ? 'status-active' :
        room.is_paused ? 'status-paused' :
            (room.m_connected && room.f_connected) ? 'status-waiting' : 'status-offline';
    const statusText = room.is_active ? 'Active' :
        room.is_paused ? 'Paused' :
            (room.m_connected && room.f_connected) ? 'Searching' : 'Offline';
    const statusIcon = room.is_active ? 'circle-dot' :
        room.is_paused ? 'pause-circle' :
            (room.m_connected && room.f_connected) ? 'loader-2' : 'circle-off';

    const statusBadge = card.querySelector('.status-badge:not(.msg-count)');
    if (statusBadge) {
        statusBadge.className = `status-badge ${statusClass}`;
        statusBadge.innerHTML = `<span class="status-dot"></span>${statusText}`;
    }

    const msgCountBadge = card.querySelector('.status-badge.msg-count');
    if (msgCountBadge) {
        msgCountBadge.innerHTML = `<i data-lucide="message-square"></i>${room.messages_count}`;
    }

    const connIndicators = card.querySelectorAll('.conn-dot');
    if (connIndicators.length >= 2) {
        connIndicators[0].className = `conn-dot ${room.m_connected ? 'conn-online' : 'conn-offline'}`;
        connIndicators[1].className = `conn-dot ${room.f_connected ? 'conn-online' : 'conn-offline'}`;
    }

    const controlPanel = card.querySelector('.control-panel');
    if (controlPanel) {
        controlPanel.innerHTML = createControlPanelHTML(room);
    }

    refreshIcons();
}

function createControlPanelHTML(room) {
    if (room.manual_control) {
        return `
            <div class="manual-notice">
                <i data-lucide="gamepad-2"></i>
                <span>Manual control: <strong>${room.manual_control}</strong>. Chatting with real user.</span>
            </div>
            <div class="input-group">
                <input type="text" 
                       id="input-${room.room_id}" 
                       placeholder="Type as ${room.manual_control}..."
                       onkeypress="handleKeyPress(event, '${room.room_id}', '${room.manual_control}')"
                       ${!room.is_active ? 'disabled' : ''}>
                <button class="btn btn-send" 
                        onclick="sendMessage('${room.room_id}', '${room.manual_control}')"
                        ${!room.is_active ? 'disabled' : ''}>
                    <i data-lucide="send"></i>
                    Send
                </button>
            </div>
            <div class="control-buttons" style="margin-top: 14px;">
                <button class="btn btn-warning" 
                        onclick="restartSearch('${room.room_id}')">
                    <i data-lucide="rotate-ccw"></i>
                    Restart & Exit Manual
                </button>
            </div>
        `;
    }
    return `
        <div class="control-buttons">
            <button class="btn btn-manual" 
                    onclick="toggleControl('${room.room_id}', 'M')"
                    ${!room.is_active ? 'disabled' : ''}>
                <i data-lucide="user"></i>
                Control M
            </button>
            <button class="btn btn-manual" 
                    onclick="toggleControl('${room.room_id}', 'F')"
                    ${!room.is_active ? 'disabled' : ''}>
                <i data-lucide="user"></i>
                Control F
            </button>
            <button class="btn ${room.is_paused ? 'btn-success' : 'btn-pause'}" 
                    onclick="togglePause('${room.room_id}')">
                <i data-lucide="${room.is_paused ? 'play' : 'pause'}"></i>
                ${room.is_paused ? 'Resume' : 'Pause'}
            </button>
            <button class="btn btn-warning" 
                    onclick="restartSearch('${room.room_id}')"
                    ${room.is_paused ? 'disabled' : ''}>
                <i data-lucide="rotate-ccw"></i>
                Restart
            </button>
            <button class="btn btn-danger" 
                    onclick="forceCloseDialog('${room.room_id}')"
                    ${!room.is_active ? 'disabled' : ''}>
                <i data-lucide="x-circle"></i>
                Force Close
            </button>
        </div>
    `;
}

function createRoomCard(room) {
    const card = document.createElement('div');
    card.className = 'room-card';
    card.id = `room-${room.room_id}`;

    const statusClass = room.is_active ? 'status-active' :
        room.is_paused ? 'status-paused' :
            (room.m_connected && room.f_connected) ? 'status-waiting' : 'status-offline';
    const statusText = room.is_active ? 'Active' :
        room.is_paused ? 'Paused' :
            (room.m_connected && room.f_connected) ? 'Searching' : 'Offline';

    const chatContent = room.messages.length > 0 ? room.messages.map(msg => {
        if (msg.from === 'system') {
            return `
                <div class="message message-system">
                    <div class="message-bubble">
                        <i data-lucide="info"></i>
                        ${escapeHtml(msg.message)}
                    </div>
                </div>
            `;
        }
        return `
            <div class="message message-${msg.from.toLowerCase()}">
                <div class="message-header">
                    <i data-lucide="user"></i>
                    <span>${msg.from}</span>
                    ${msg.is_manual ? '<span class="manual-badge"><i data-lucide="hand"></i>manual</span>' : ''}
                    <span>${new Date(msg.timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
                <div class="message-bubble">${escapeHtml(msg.message)}</div>
            </div>
        `;
    }).join('') : `
        <div class="empty-state">
            <div class="empty-icon">
                <i data-lucide="message-circle"></i>
            </div>
            <p>No messages yet</p>
        </div>
    `;

    card.innerHTML = `
        <div class="room-header">
            <div class="room-info">
                <div class="room-id">
                    <i data-lucide="hash"></i>
                    ${room.room_id.slice(-12)}
                </div>
                <div class="connection-status">
                    <span class="conn-indicator">
                        <span class="conn-dot ${room.m_connected ? 'conn-online' : 'conn-offline'}"></span>
                        M:${room.m_token}
                    </span>
                    <span class="conn-indicator">
                        <span class="conn-dot ${room.f_connected ? 'conn-online' : 'conn-offline'}"></span>
                        F:${room.f_token}
                    </span>
                </div>
            </div>
            <div class="status-indicators">
                <span class="status-badge ${statusClass}">
                    <span class="status-dot"></span>
                    ${statusText}
                </span>
                <span class="status-badge msg-count">
                    <i data-lucide="message-square"></i>
                    ${room.messages_count}
                </span>
            </div>
        </div>
        <div class="chat-area" id="chat-${room.room_id}">
            ${chatContent}
        </div>
        <div class="control-panel">
            ${createControlPanelHTML(room)}
        </div>
    `;

    setTimeout(() => {
        const chatArea = document.getElementById(`chat-${room.room_id}`);
        if (chatArea) chatArea.scrollTop = chatArea.scrollHeight;
    }, 0);

    return card;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function refreshIcons() {
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}

async function toggleControl(roomId, sex) {
    await fetch('/toggle-control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_id: roomId, sex: sex })
    });
}

async function sendMessage(roomId, sex) {
    const input = document.getElementById(`input-${roomId}`);
    const message = input.value.trim();

    if (!message) return;

    const response = await fetch('/send-message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_id: roomId, sex: sex, message: message })
    });

    if (response.ok) {
        input.value = '';
    }
}

async function forceCloseDialog(roomId) {
    if (!confirm('Are you sure you want to force close this dialog?')) return;

    await fetch('/force-close', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_id: roomId })
    });
}

async function restartSearch(roomId) {
    if (!confirm('Restart search for this room? Current dialog/search will be stopped.')) return;

    await fetch('/restart-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_id: roomId })
    });
}

async function togglePause(roomId) {
    await fetch('/toggle-pause', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_id: roomId })
    });
}

function handleKeyPress(event, roomId, sex) {
    if (event.key === 'Enter') {
        sendMessage(roomId, sex);
    }
}


// ============================================
// Chat Logs Viewer
// ============================================

let currentLogs = [];
let currentLogFilename = null;
let searchTimeout = null;

function switchTab(tab) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `tab-${tab}`);
    });

    // Load logs when switching to logs tab
    if (tab === 'logs') {
        loadLogs();
        loadLogsStats();
    }

    refreshIcons();
}

async function loadLogsStats() {
    try {
        const response = await fetch('/api/logs/stats');
        const stats = await response.json();

        document.getElementById('stat-total-logs').textContent = stats.total_logs.toLocaleString();
        document.getElementById('stat-total-messages').textContent = stats.total_messages.toLocaleString();
        document.getElementById('stat-total-size').textContent = formatFileSize(stats.total_size);

        if (stats.oldest_date && stats.newest_date) {
            const oldest = new Date(stats.oldest_date);
            const newest = new Date(stats.newest_date);
            document.getElementById('stat-date-range').textContent =
                `${oldest.toLocaleDateString('ru-RU')} - ${newest.toLocaleDateString('ru-RU')}`;
        } else {
            document.getElementById('stat-date-range').textContent = '-';
        }
    } catch (e) {
        console.error('Failed to load stats:', e);
    }
}

async function loadLogs() {
    const sidebar = document.getElementById('logs-sidebar');
    const searchQuery = document.getElementById('logs-search').value;
    const sortBy = document.getElementById('logs-sort').value;

    // Show/hide clear button
    document.getElementById('clear-search-btn').style.display = searchQuery ? 'flex' : 'none';

    sidebar.innerHTML = `
        <div class="loading-state">
            <div class="loading-spinner">
                <i data-lucide="loader-2" class="spin"></i>
            </div>
            <p>Loading logs...</p>
        </div>
    `;
    refreshIcons();

    try {
        const params = new URLSearchParams({ search: searchQuery, sort: sortBy });
        const response = await fetch(`/api/logs?${params}`);
        currentLogs = await response.json();

        renderLogsList();
    } catch (e) {
        sidebar.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">
                    <i data-lucide="alert-circle"></i>
                </div>
                <p>Failed to load logs</p>
            </div>
        `;
        refreshIcons();
    }
}

function renderLogsList() {
    const sidebar = document.getElementById('logs-sidebar');

    if (currentLogs.length === 0) {
        sidebar.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">
                    <i data-lucide="inbox"></i>
                </div>
                <p>No logs found</p>
            </div>
        `;
        refreshIcons();
        return;
    }

    sidebar.innerHTML = currentLogs.map(log => {
        const startDate = log.start_time ? new Date(log.start_time) : null;
        const endDate = log.end_time ? new Date(log.end_time) : null;
        const duration = startDate && endDate ? formatDuration(endDate - startDate) : '-';

        return `
            <div class="log-item ${currentLogFilename === log.filename ? 'active' : ''}" 
                 onclick="loadLogDetail('${log.filename}')">
                <div class="log-item-header">
                    <span class="log-date">
                        <i data-lucide="calendar"></i>
                        ${startDate ? startDate.toLocaleDateString('ru-RU') : 'Unknown'}
                    </span>
                    <span class="log-time">
                        ${startDate ? startDate.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : ''}
                    </span>
                </div>
                <div class="log-item-body">
                    <span class="log-room-id">
                        <i data-lucide="hash"></i>
                        ${log.room_id.slice(0, 16)}...
                    </span>
                </div>
                <div class="log-item-footer">
                    <span class="log-messages">
                        <i data-lucide="message-square"></i>
                        ${log.messages_count} msgs
                    </span>
                    <span class="log-duration">
                        <i data-lucide="clock"></i>
                        ${duration}
                    </span>
                    <span class="log-size">
                        ${formatFileSize(log.file_size)}
                    </span>
                </div>
            </div>
        `;
    }).join('');

    refreshIcons();
}

async function loadLogDetail(filename) {
    currentLogFilename = filename;
    renderLogsList(); // Update active state

    const detail = document.getElementById('log-detail');
    detail.innerHTML = `
        <div class="loading-state">
            <div class="loading-spinner">
                <i data-lucide="loader-2" class="spin"></i>
            </div>
            <p>Loading chat...</p>
        </div>
    `;
    refreshIcons();

    try {
        const response = await fetch(`/api/logs/${filename}`);
        const log = await response.json();

        renderLogDetail(log, filename);
    } catch (e) {
        detail.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">
                    <i data-lucide="alert-circle"></i>
                </div>
                <p>Failed to load log</p>
            </div>
        `;
        refreshIcons();
    }
}

function renderLogDetail(log, filename) {
    const detail = document.getElementById('log-detail');
    const startDate = log.start_time ? new Date(log.start_time) : null;
    const endDate = log.end_time ? new Date(log.end_time) : null;
    const duration = startDate && endDate ? formatDuration(endDate - startDate) : '-';

    const messagesHtml = log.messages.map(msg => {
        if (msg.from === 'system') {
            return `
                <div class="log-message log-message-system">
                    <div class="message-bubble">
                        <i data-lucide="info"></i>
                        ${escapeHtml(msg.message)}
                    </div>
                </div>
            `;
        }

        const isManual = msg.is_manual;
        const time = new Date(msg.timestamp).toLocaleTimeString('ru-RU', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });

        return `
            <div class="log-message log-message-${msg.from.toLowerCase()}">
                <div class="message-header">
                    <i data-lucide="user"></i>
                    <span class="sender">${msg.from}</span>
                    ${isManual ? '<span class="manual-badge"><i data-lucide="hand"></i>manual</span>' : ''}
                    <span class="time">${time}</span>
                    <button class="copy-btn" onclick="copyMessage('${escapeHtml(msg.message).replace(/'/g, "\\'")}')">
                        <i data-lucide="copy"></i>
                    </button>
                </div>
                <div class="message-bubble">${escapeHtml(msg.message)}</div>
            </div>
        `;
    }).join('');

    detail.innerHTML = `
        <div class="log-detail-header">
            <div class="log-detail-info">
                <h2>
                    <i data-lucide="scroll-text"></i>
                    Chat Log
                </h2>
                <div class="log-meta">
                    <span><i data-lucide="hash"></i>${log.room_id.slice(0, 20)}...</span>
                    <span><i data-lucide="calendar"></i>${startDate ? startDate.toLocaleString('ru-RU') : 'Unknown'}</span>
                    <span><i data-lucide="clock"></i>${duration}</span>
                    <span><i data-lucide="message-square"></i>${log.messages_count || log.messages.length} messages</span>
                </div>
                <div class="log-tokens">
                    <span class="token-m"><i data-lucide="user"></i>M: ${log.client_m_token || '-'}</span>
                    <span class="token-f"><i data-lucide="user"></i>F: ${log.client_f_token || '-'}</span>
                </div>
            </div>
            <div class="log-detail-actions">
                <button class="btn btn-export" onclick="exportLog('${filename}', 'json')">
                    <i data-lucide="download"></i>
                    JSON
                </button>
                <button class="btn btn-export" onclick="exportLog('${filename}', 'txt')">
                    <i data-lucide="file-text"></i>
                    TXT
                </button>
                <button class="btn btn-danger" onclick="deleteLog('${filename}')">
                    <i data-lucide="trash-2"></i>
                    Delete
                </button>
            </div>
        </div>
        <div class="log-messages-container">
            ${messagesHtml}
        </div>
    `;

    refreshIcons();

    // Scroll to top
    const container = detail.querySelector('.log-messages-container');
    if (container) {
        container.scrollTop = 0;
    }
}

function debounceSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        loadLogs();
    }, 300);
}

function clearSearch() {
    document.getElementById('logs-search').value = '';
    loadLogs();
}

async function deleteLog(filename) {
    if (!confirm(`Are you sure you want to delete this log?\n\n${filename}`)) return;

    try {
        const response = await fetch(`/api/logs/${filename}`, { method: 'DELETE' });

        if (response.ok) {
            currentLogFilename = null;
            loadLogs();
            loadLogsStats();

            document.getElementById('log-detail').innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">
                        <i data-lucide="check-circle"></i>
                    </div>
                    <p>Log deleted successfully</p>
                </div>
            `;
            refreshIcons();
        } else {
            alert('Failed to delete log');
        }
    } catch (e) {
        alert('Failed to delete log: ' + e.message);
    }
}

async function exportLog(filename, format) {
    try {
        const response = await fetch(`/api/logs/${filename}`);
        const log = await response.json();

        let content, mimeType, extension;

        if (format === 'json') {
            content = JSON.stringify(log, null, 2);
            mimeType = 'application/json';
            extension = 'json';
        } else {
            // TXT format
            const lines = [
                `Chat Log: ${log.room_id}`,
                `Date: ${log.start_time} - ${log.end_time}`,
                `M Token: ${log.client_m_token}`,
                `F Token: ${log.client_f_token}`,
                `Messages: ${log.messages_count || log.messages.length}`,
                '',
                '='.repeat(50),
                ''
            ];

            log.messages.forEach(msg => {
                const time = new Date(msg.timestamp).toLocaleTimeString('ru-RU');
                if (msg.from === 'system') {
                    lines.push(`[${time}] --- ${msg.message} ---`);
                } else {
                    const manual = msg.is_manual ? ' [MANUAL]' : '';
                    lines.push(`[${time}] ${msg.from}${manual}: ${msg.message}`);
                }
            });

            content = lines.join('\n');
            mimeType = 'text/plain';
            extension = 'txt';
        }

        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename.replace('.json', `.${extension}`);
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('Failed to export log: ' + e.message);
    }
}

function copyMessage(text) {
    navigator.clipboard.writeText(text).then(() => {
        // Visual feedback could be added here
    }).catch(e => {
        console.error('Failed to copy:', e);
    });
}

function formatDuration(ms) {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
        return `${hours}h ${minutes % 60}m`;
    } else if (minutes > 0) {
        return `${minutes}m ${seconds % 60}s`;
    } else {
        return `${seconds}s`;
    }
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
