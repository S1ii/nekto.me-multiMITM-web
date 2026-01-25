// ============================================
// NektoMe Chat Manager - Main Entry Point
// ============================================

// Global state
let ws = null;
const rooms = new Map();
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;
const RECONNECT_DELAY_MS = 2000;

// ============================================
// WebSocket Connection Management
// ============================================

function connectWebSocket() {
    ws = new WebSocket(`ws://${window.location.host}/ws`);

    ws.onopen = () => {
        console.log("WebSocket connected");
        reconnectAttempts = 0;
        updateConnectionStatus("connected");
    };

    ws.onclose = (event) => {
        console.log("WebSocket closed", event.code, event.reason);
        updateConnectionStatus("disconnected");
        scheduleReconnect();
    };

    ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        updateConnectionStatus("disconnected");
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWebSocketMessage(data);
        } catch (e) {
            console.error("Failed to parse WebSocket message:", e);
        }
    };
}

function scheduleReconnect() {
    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        console.error("Max reconnection attempts reached");
        return;
    }

    reconnectAttempts++;
    const delay = RECONNECT_DELAY_MS * Math.min(reconnectAttempts, 5);
    console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);

    setTimeout(() => {
        if (!ws || ws.readyState === WebSocket.CLOSED) {
            connectWebSocket();
        }
    }, delay);
}

function handleWebSocketMessage(data) {
    if (data.type === "initial_state") {
        rooms.clear();
        data.rooms.forEach((room) => rooms.set(room.room_id, room));
        renderRooms();
        // Load audio status and start polling
        loadAudioStatus();
        startAudioPolling();
    } else if (data.type === "room_update") {
        const room = rooms.get(data.room_id);
        if (room) {
            Object.assign(room, data);
            updateRoomMeta(data.room_id);
        }
    } else if (data.type === "new_message") {
        const room = rooms.get(data.room_id);
        if (room) {
            room.messages.push(data.message);
            // Only count user messages (M, F), not system messages
            if (data.message.from === 'M' || data.message.from === 'F') {
                room.messages_count++;
                // Update the counter badge - use getElementById to avoid CSS selector issues with dots
                const roomCard = document.getElementById(`room-${data.room_id}`);
                if (roomCard) {
                    const msgCountValue = roomCard.querySelector('.msg-count-value');
                    if (msgCountValue) {
                        msgCountValue.textContent = room.messages_count;
                    }
                }
            }
            appendMessage(data.room_id, data.message);
        }
    }
}

// Initialize WebSocket connection
connectWebSocket();

/**
 * Update WebSocket connection status indicator
 */
function updateConnectionStatus(status) {
    const indicator = document.querySelector(".ws-indicator");
    if (!indicator) return;

    indicator.className = `ws-indicator ${status}`;
    indicator.querySelector("span:last-child").textContent =
        status === "connected" ? "Connected" : "Disconnected";
}

// ============================================
// Tab Navigation
// ============================================

function switchTab(tab) {
    // Update tab buttons
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.tab === tab);
    });

    // Update tab content
    document.querySelectorAll(".tab-content").forEach((content) => {
        content.classList.toggle("active", content.id === `tab-${tab}`);
    });

    // Handle audio polling
    if (tab === "dashboard") {
        loadAudioStatus();
        startAudioPolling();
    } else {
        stopAudioPolling();
    }

    // Load content based on tab
    if (tab === "logs") {
        loadLogs();
        loadLogsStats();
    }

    if (tab === "audio-logs") {
        loadAudioLogs();
    }

    refreshIcons();
}

// ============================================
// Initialize
// ============================================

document.addEventListener("DOMContentLoaded", () => {
    refreshIcons();
});
