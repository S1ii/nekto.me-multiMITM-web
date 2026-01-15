from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
import uvicorn
import asyncio
import logging

from src.chat_manager import ChatManager
from src.client import Client
from src.config import get_clients

# Настройка минимального логирования
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

manager: Optional[ChatManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global manager
    manager = ChatManager()
    
    clients = list(get_clients())
    male_clients = [c for c in clients if c.search_parameters.get('mySex') == 'M']
    female_clients = [c for c in clients if c.search_parameters.get('mySex') == 'F']
    
    print("\n" + "="*60)
    print("🚀 NektoMe Chat Manager")
    print("="*60)
    
    # Создаем комнаты
    for i in range(min(len(male_clients), len(female_clients))):
        room = manager.create_room(male_clients[i], female_clients[i])
        print(f"  ✓ Room {i+1}: M:{male_clients[i].token[:10]} ↔ F:{female_clients[i].token[:10]}")
    
    # Подключаем клиентов
    all_clients = male_clients + female_clients
    connected = 0
    
    for client in all_clients:
        try:
            await client.connect()
            connected += 1
        except Exception as e:
            print(f"  ✗ Failed: {client.token[:10]} - {str(e)[:40]}")
    
    print(f"\n  📊 Connected: {connected}/{len(all_clients)} clients")
    print(f"  🌐 Dashboard: http://localhost:8000")
    print("="*60 + "\n")
    
    yield
    
    # Shutdown
    print("\n⏹ Shutting down...")

app = FastAPI(title="NektoMe Chat Manager", lifespan=lifespan)

class SendMessageRequest(BaseModel):
    room_id: str
    sex: str
    message: str

class ToggleControlRequest(BaseModel):
    room_id: str
    sex: str

class ForceCloseRequest(BaseModel):
    room_id: str

class RestartSearchRequest(BaseModel):
    room_id: str

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    return """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NektoMe Chat Manager</title>
    <style>
        * { 
            margin: 0; 
            padding: 0; 
            box-sizing: border-box; 
        }
        
        :root {
            --bg-primary: #0a0a0a;
            --bg-secondary: #141414;
            --bg-tertiary: #1e1e1e;
            --border: #2a2a2a;
            --text-primary: #e8e8e8;
            --text-secondary: #a0a0a0;
            --text-tertiary: #707070;
            --accent: #6366f1;
            --accent-hover: #4f46e5;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --male: #3b82f6;
            --female: #ec4899;
        }
        
        body {
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        
        header {
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
        }
        
        h1 {
            font-size: 24px;
            font-weight: 600;
            letter-spacing: -0.5px;
            margin-bottom: 8px;
        }
        
        .subtitle {
            color: var(--text-secondary);
            font-size: 14px;
        }
        
        .rooms-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(700px, 1fr));
            gap: 20px;
        }
        
        .room-card {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
            transition: border-color 0.2s;
        }
        
        .room-card:hover {
            border-color: #3a3a3a;
        }
        
        .room-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .room-info {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .room-id {
            font-size: 13px;
            color: var(--text-secondary);
            font-family: 'SF Mono', Monaco, monospace;
        }
        
        .status-indicators {
            display: flex;
            gap: 8px;
        }
        
        .status-badge {
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
        }
        
        .status-active {
            background: rgba(16, 185, 129, 0.1);
            color: var(--success);
        }
        
        .status-active .status-dot {
            background: var(--success);
            box-shadow: 0 0 8px var(--success);
        }
        
        .status-waiting {
            background: rgba(245, 158, 11, 0.1);
            color: var(--warning);
        }
        
        .status-waiting .status-dot {
            background: var(--warning);
        }
        
        .status-offline {
            background: rgba(239, 68, 68, 0.1);
            color: var(--danger);
        }
        
        .status-offline .status-dot {
            background: var(--danger);
        }
        
        .msg-count {
            background: var(--bg-tertiary);
            color: var(--text-secondary);
        }
        
        .chat-area {
            height: 450px;
            overflow-y: auto;
            padding: 20px;
            background: var(--bg-primary);
        }
        
        .chat-area::-webkit-scrollbar {
            width: 8px;
        }
        
        .chat-area::-webkit-scrollbar-track {
            background: transparent;
        }
        
        .chat-area::-webkit-scrollbar-thumb {
            background: var(--bg-tertiary);
            border-radius: 4px;
        }
        
        .chat-area::-webkit-scrollbar-thumb:hover {
            background: #2a2a2a;
        }
        
        .message {
            margin-bottom: 16px;
            display: flex;
            flex-direction: column;
            animation: fadeIn 0.3s;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message-m {
            align-items: flex-end;
        }
        
        .message-f {
            align-items: flex-start;
        }
        
        .message-header {
            font-size: 11px;
            color: var(--text-tertiary);
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 6px;
            font-weight: 500;
        }
        
        .manual-badge {
            background: rgba(139, 92, 246, 0.2);
            color: #a78bfa;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .message-bubble {
            padding: 12px 16px;
            border-radius: 12px;
            max-width: 75%;
            word-wrap: break-word;
            font-size: 14px;
            line-height: 1.5;
        }
        
        .message-m .message-bubble {
            background: linear-gradient(135deg, var(--male), #2563eb);
            color: white;
        }
        
        .message-f .message-bubble {
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border);
        }
        
        .message-system {
            align-items: center;
        }
        
        .message-system .message-bubble {
            background: transparent;
            color: var(--text-tertiary);
            border: 1px solid var(--border);
            border-style: dashed;
            padding: 8px 12px;
            font-size: 12px;
            text-align: center;
            max-width: 90%;
        }
        
        .control-panel {
            padding: 16px 20px;
            background: var(--bg-secondary);
            border-top: 1px solid var(--border);
        }
        
        .control-buttons {
            display: flex;
            gap: 8px;
            margin-bottom: 12px;
        }
        
        .btn {
            padding: 8px 16px;
            border: 1px solid var(--border);
            border-radius: 8px;
            cursor: pointer;
            font-weight: 500;
            font-size: 13px;
            transition: all 0.2s;
            background: var(--bg-tertiary);
            color: var(--text-primary);
        }
        
        .btn:hover {
            background: #2a2a2a;
            border-color: #3a3a3a;
        }
        
        .btn-manual {
            flex: 1;
        }
        
        .btn-manual.active {
            background: linear-gradient(135deg, var(--accent), var(--accent-hover));
            border-color: var(--accent);
            color: white;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }
        
        .input-group {
            display: flex;
            gap: 8px;
        }
        
        .input-group input {
            flex: 1;
            padding: 10px 14px;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 14px;
            background: var(--bg-tertiary);
            color: var(--text-primary);
            transition: all 0.2s;
        }
        
        .input-group input:focus {
            outline: none;
            border-color: var(--accent);
            background: var(--bg-primary);
        }
        
        .input-group input::placeholder {
            color: var(--text-tertiary);
        }
        
        .btn-send {
            background: linear-gradient(135deg, var(--accent), var(--accent-hover));
            color: white;
            padding: 10px 24px;
            border: none;
        }
        
        .btn-send:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
        }
        
        .btn-send:disabled {
            background: var(--bg-tertiary);
            color: var(--text-tertiary);
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger), #dc2626);
            color: white;
            border: none;
        }
        
        .btn-danger:hover {
            background: linear-gradient(135deg, #dc2626, #b91c1c);
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
        }
        
        .btn-danger:disabled {
            background: var(--bg-tertiary);
            color: var(--text-tertiary);
            cursor: not-allowed;
            box-shadow: none;
        }
        
        .btn-warning {
            background: linear-gradient(135deg, var(--warning), #d97706);
            color: white;
            border: none;
        }
        
        .btn-warning:hover {
            background: linear-gradient(135deg, #d97706, #b45309);
            box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
        }
        
        .btn-warning:disabled {
            background: var(--bg-tertiary);
            color: var(--text-tertiary);
            cursor: not-allowed;
            box-shadow: none;
        }
        
        .connection-status {
            display: flex;
            gap: 12px;
            font-size: 11px;
            color: var(--text-tertiary);
            font-family: 'SF Mono', Monaco, monospace;
        }
        
        .conn-indicator {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .conn-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            transition: all 0.3s;
        }
        
        .conn-online {
            background: var(--success);
            box-shadow: 0 0 8px var(--success);
        }
        
        .conn-offline {
            background: var(--danger);
        }
        
        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--text-tertiary);
            gap: 8px;
        }
        
        .empty-icon {
            font-size: 32px;
            opacity: 0.5;
        }
        
        .manual-notice {
            background: rgba(139, 92, 246, 0.1);
            border: 1px solid rgba(139, 92, 246, 0.3);
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 12px;
            font-size: 12px;
            color: #a78bfa;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .manual-notice-icon {
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>NektoMe Chat Manager</h1>
            <div class="subtitle">Real-time monitoring and control</div>
        </header>
        <div class="rooms-grid" id="rooms-grid"></div>
    </div>

    <script>
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
                    // Обновляем только шапку и контрольную панель, не трогая chat-area
                    updateRoomMeta(data.room_id); 
                }
            } else if (data.type === 'new_message') {
                const room = rooms.get(data.room_id);
                if (room) {
                    room.messages.push(data.message);
                    room.messages_count++;
                    appendMessage(data.room_id, data.message); // Добавляем только одно сообщение
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
                        <span>${new Date(msg.timestamp).toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'})}</span>
                    </div>
                    <div class="message-bubble">${escapeHtml(msg.message)}</div>
                `;
            }
            
            // Удаляем пустую заглушку, если она была
            const emptyState = chatArea.querySelector('.empty-state');
            if (emptyState) emptyState.remove();

            chatArea.appendChild(msgDiv);
            chatArea.scrollTop = chatArea.scrollHeight; // Скроллим вниз
        }

        function updateRoomMeta(roomId) {
            // Эта функция обновит только статусы и кнопки, не перерисовывая весь чат
            const room = rooms.get(roomId);
            const card = document.getElementById(`room-${roomId}`);
            if (!card) return;
            
            // Обновляем статусы в header
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
            
            // Обновляем connection indicators
            const connIndicators = card.querySelectorAll('.conn-dot');
            if (connIndicators.length >= 2) {
                connIndicators[0].className = `conn-dot ${room.m_connected ? 'conn-online' : 'conn-offline'}`;
                connIndicators[1].className = `conn-dot ${room.f_connected ? 'conn-online' : 'conn-offline'}`;
            }
            
            // Перестраиваем control-panel
            const controlPanel = card.querySelector('.control-panel');
            if (controlPanel) {
                controlPanel.innerHTML = `
                    ${room.manual_control ? `
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
                    ` : `
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
                    `}
                `;
            }
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
                            <span>${new Date(msg.timestamp).toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'})}</span>
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
                    ${room.manual_control ? `
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
                    ` : `
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
                    `}
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
    </script>
</body>
</html>
    """

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    manager.websocket_clients.add(websocket)
    
    initial_state = {
        "type": "initial_state",
        "rooms": manager.get_all_rooms_status()
    }
    await websocket.send_json(initial_state)
    
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.websocket_clients.remove(websocket)

@app.post("/send-message")
async def send_message(request: SendMessageRequest):
    success = await manager.send_manual_message(
        request.room_id,
        request.sex,
        request.message
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to send message")
    
    return {"status": "ok"}

@app.post("/toggle-control")
async def toggle_control(request: ToggleControlRequest):
    success = await manager.toggle_manual_control(request.room_id, request.sex)
    
    if not success:
        raise HTTPException(status_code=404, detail="Room not found")
    
    return {"status": "ok"}

@app.post("/force-close")
async def force_close(request: ForceCloseRequest):
    success = await manager.force_close_dialog(request.room_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Room not found or not active")
    
    return {"status": "ok"}

@app.post("/restart-search")
async def restart_search(request: RestartSearchRequest):
    success = await manager.restart_search(request.room_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Room not found")
    
    return {"status": "ok"}

@app.get("/rooms")
async def get_rooms():
    return manager.get_all_rooms_status()

@app.get("/rooms/{room_id}")
async def get_room(room_id: str):
    status = manager.get_room_status(room_id)
    if not status:
        raise HTTPException(status_code=404, detail="Room not found")
    return status

if __name__ == "__main__":
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_level="warning"
    )