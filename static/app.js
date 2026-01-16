const ws = new WebSocket(`ws://${window.location.host}/ws`);
const rooms = new Map();

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

function renderRooms() {
    const grid = document.getElementById('rooms-grid');
    grid.innerHTML = '';
    rooms.forEach((room, roomId) => {
        grid.appendChild(createRoomCard(room));
    });
}

function renderRoom(roomId) {
    const room = rooms.get(roomId);
    const oldCard = document.getElementById(`room-${roomId}`);
    if (oldCard) {
        oldCard.replaceWith(createRoomCard(room));
    }
}

function appendMessage(roomId, msg) {
    const chatArea = document.getElementById(`chat-${roomId}`);
    if (!chatArea) return;

    const msgDiv = document.createElement('div');
    if (msg.from === 'system') {
        msgDiv.className = 'message message-system';
        msgDiv.innerHTML = `<div class="message-bubble">${escapeHtml(msg.message)}</div>`;
    } else {
        msgDiv.className = `message message-${msg.from.toLowerCase()}`;
        msgDiv.innerHTML = `
            <div class="message-header">
                <span>${msg.from}</span>
                ${msg.is_manual ? '<span class="manual-badge">manual</span>' : ''}
                <span>${new Date(msg.timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
            <div class="message-bubble">${escapeHtml(msg.message)}</div>
        `;
    }

    const emptyState = chatArea.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    chatArea.appendChild(msgDiv);
    chatArea.scrollTop = chatArea.scrollHeight;
}

function updateRoomMeta(roomId) {
    const room = rooms.get(roomId);
    const card = document.getElementById(`room-${roomId}`);
    if (!card) return;

    const statusClass = room.is_active ? 'status-active' :
        (room.m_connected && room.f_connected) ? 'status-waiting' : 'status-offline';
    const statusText = room.is_active ? 'Active' :
        (room.m_connected && room.f_connected) ? 'Searching' : 'Offline';

    const statusBadge = card.querySelector('.status-badge:not(.msg-count)');
    if (statusBadge) {
        statusBadge.className = `status-badge ${statusClass}`;
        statusBadge.innerHTML = `<span class="status-dot"></span>${statusText}`;
    }

    const msgCountBadge = card.querySelector('.status-badge.msg-count');
    if (msgCountBadge) {
        msgCountBadge.textContent = room.messages_count;
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
}

function createControlPanelHTML(room) {
    if (room.manual_control) {
        return `
            <div class="manual-notice">
                <span class="manual-notice-icon">🎮</span>
                <span>Manual control: ${room.manual_control}. Chatting with real user.</span>
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
                    Send
                </button>
            </div>
            <div class="control-buttons" style="margin-top: 12px;">
                <button class="btn btn-warning" 
                        onclick="restartSearch('${room.room_id}')">
                    🔄 Restart & Exit Manual
                </button>
            </div>
        `;
    }
    return `
        <div class="control-buttons">
            <button class="btn btn-manual" 
                    onclick="toggleControl('${room.room_id}', 'M')"
                    ${!room.is_active ? 'disabled' : ''}>
                Control M
            </button>
            <button class="btn btn-manual" 
                    onclick="toggleControl('${room.room_id}', 'F')"
                    ${!room.is_active ? 'disabled' : ''}>
                Control F
            </button>
            <button class="btn btn-warning" 
                    onclick="restartSearch('${room.room_id}')">
                🔄 Restart
            </button>
            <button class="btn btn-danger" 
                    onclick="forceCloseDialog('${room.room_id}')"
                    ${!room.is_active ? 'disabled' : ''}>
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
        (room.m_connected && room.f_connected) ? 'status-waiting' : 'status-offline';
    const statusText = room.is_active ? 'Active' :
        (room.m_connected && room.f_connected) ? 'Searching' : 'Offline';

    const chatContent = room.messages.length > 0 ? room.messages.map(msg => {
        if (msg.from === 'system') {
            return `
                <div class="message message-system">
                    <div class="message-bubble">${escapeHtml(msg.message)}</div>
                </div>
            `;
        }
        return `
            <div class="message message-${msg.from.toLowerCase()}">
                <div class="message-header">
                    <span>${msg.from === 'M' ? 'M' : 'F'}</span>
                    ${msg.is_manual ? '<span class="manual-badge">manual</span>' : ''}
                    <span>${new Date(msg.timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
                <div class="message-bubble">${escapeHtml(msg.message)}</div>
            </div>
        `;
    }).join('') : `
        <div class="empty-state">
            <div class="empty-icon">💬</div>
            <div>No messages yet</div>
        </div>
    `;

    card.innerHTML = `
        <div class="room-header">
            <div class="room-info">
                <div class="room-id">${room.room_id.slice(0, 12)}</div>
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
                <span class="status-badge msg-count">${room.messages_count}</span>
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

function handleKeyPress(event, roomId, sex) {
    if (event.key === 'Enter') {
        sendMessage(roomId, sex);
    }
}
