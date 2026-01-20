// ============================================
// NektoMe Chat Manager - Main Entry Point
// ============================================

// Global state
const ws = new WebSocket(`ws://${window.location.host}/ws`);
const rooms = new Map();

// ============================================
// WebSocket Handlers
// ============================================

ws.onopen = () => {
    updateConnectionStatus("connected");
};

ws.onclose = () => {
    updateConnectionStatus("disconnected");
};

ws.onerror = () => {
    updateConnectionStatus("disconnected");
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "initial_state") {
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
            room.messages_count++;
            appendMessage(data.room_id, data.message);
        }
    }
};

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
