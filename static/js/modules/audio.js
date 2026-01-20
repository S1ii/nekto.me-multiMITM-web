// ============================================
// Audio Rooms - Rendering and Controls
// ============================================

// Audio state
let audioClientsStatus = { clients: [], rooms: [] };
let audioStatusInterval = null;

/**
 * Load audio status from API
 */
async function loadAudioStatus() {
    const grid = document.getElementById("audio-rooms-grid");
    if (!grid) return;

    try {
        const response = await fetch("/api/audio/status");
        audioClientsStatus = await response.json();
        renderAudioRooms();
    } catch (e) {
        grid.innerHTML = `
      <div class="audio-empty-state">
        <div class="empty-icon">
          <i data-lucide="alert-circle"></i>
        </div>
        <h3>Failed to load audio status</h3>
        <p>Check server connection</p>
      </div>
    `;
        refreshIcons();
    }
}

/**
 * Force close audio dialog
 */
async function forceCloseAudio(roomId) {
    if (!confirm('Force close this audio dialog? This will restart the search.')) return;

    try {
        const response = await fetch('/api/audio/force-close', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ room_id: roomId })
        });

        if (response.ok) {
            loadAudioStatus();
        }
    } catch (e) {
        console.error('Failed to force close audio:', e);
    }
}

/**
 * Toggle audio pause
 */
async function toggleAudioPause(roomId) {
    try {
        const response = await fetch('/api/audio/toggle-pause', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ room_id: roomId })
        });

        if (response.ok) {
            loadAudioStatus();
        }
    } catch (e) {
        console.error('Failed to toggle audio pause:', e);
    }
}

/**
 * Render audio rooms on dashboard
 */
function renderAudioRooms() {
    const grid = document.getElementById("audio-rooms-grid");
    if (!grid) return;

    const rooms = audioClientsStatus.rooms || [];
    const clients = audioClientsStatus.clients || [];

    // Update counters
    const clientsCountEl = document.getElementById("audio-clients-count");
    const activeRoomsEl = document.getElementById("audio-active-rooms");
    if (clientsCountEl) clientsCountEl.textContent = clients.length;
    if (activeRoomsEl) activeRoomsEl.textContent = rooms.filter(r => r.is_recording).length;

    if (rooms.length === 0 && clients.length === 0) {
        grid.innerHTML = `
      <div class="audio-empty-state">
        <div class="empty-icon">
          <i data-lucide="headphones"></i>
        </div>
        <h3>No audio clients configured</h3>
        <p>Add [audio] section to config.ini to enable audio chat monitoring</p>
      </div>
    `;
        refreshIcons();
        return;
    }

    // Render rooms if available
    if (rooms.length > 0) {
        grid.innerHTML = rooms.map((room, idx) => {
            const startTime = room.start_time ? new Date(room.start_time) : null;
            const members = room.members || [];
            const isPaused = room.is_paused || false;

            // Determine room status
            let roomStatus = 'waiting';
            let roomStatusIcon = 'loader-2';
            let roomStatusText = 'Searching';

            if (isPaused) {
                roomStatus = 'paused';
                roomStatusIcon = 'pause-circle';
                roomStatusText = 'Paused';
            } else if (room.is_recording) {
                roomStatus = 'recording';
                roomStatusIcon = 'circle-dot';
                roomStatusText = 'Recording';
            }

            return `
        <div class="audio-room-card ${room.is_recording ? 'recording' : ''} ${isPaused ? 'paused' : ''}">
          <div class="audio-room-header">
            <div class="audio-room-info">
              <div class="audio-room-id">
                <i data-lucide="radio"></i>
                Room ${idx + 1}
              </div>
              <div class="audio-room-time">
                <i data-lucide="clock"></i>
                ${startTime ? startTime.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : '-'}
              </div>
            </div>
            <div class="audio-room-header-right">
              <button class="btn-settings" onclick="openAudioSettings('${room.room_id}')" title="Audio Room Settings">
                <i data-lucide="settings"></i>
              </button>
              <div class="audio-room-status ${roomStatus}">
                <i data-lucide="${roomStatusIcon}"></i>
                ${roomStatusText}
              </div>
            </div>
          </div>
          <div class="audio-room-members">
            ${members.map((member, mIdx) => {
                const statusLabels = {
                    'disconnected': 'Offline',
                    'connecting': 'Connecting',
                    'connected': 'Connected',
                    'registering': 'Registering',
                    'searching': 'Searching',
                    'in_call': 'In Call',
                    'error': 'Error'
                };
                return `
                <div class="audio-member">
                  <div class="audio-member-info">
                    <div class="audio-member-avatar member-${mIdx + 1}">
                      <i data-lucide="user"></i>
                    </div>
                    <div class="audio-member-details">
                      <span class="audio-member-name">${escapeHtml(member.name)}</span>
                      <span class="audio-member-user-id">${escapeHtml(member.user_id)}</span>
                    </div>
                  </div>
                  <span class="audio-member-status ${member.status}">
                    ${statusLabels[member.status] || member.status}
                  </span>
                </div>
              `;
            }).join('')}
          </div>
          <div class="audio-room-controls">
            <button class="btn btn-primary" 
                    onclick="listenToAudio('${room.room_id}')"
                    ${!room.is_recording ? 'disabled' : ''}>
              <i data-lucide="headphones"></i>
              Listen
            </button>
            <button class="btn ${isPaused ? 'btn-success' : 'btn-pause'}" 
                    onclick="toggleAudioPause('${room.room_id}')">
              <i data-lucide="${isPaused ? 'play' : 'pause'}"></i>
              ${isPaused ? 'Resume' : 'Pause'}
            </button>
            <button class="btn btn-danger" 
                    onclick="forceCloseAudio('${room.room_id}')"
                    ${isPaused ? 'disabled' : ''}>
              <i data-lucide="x-circle"></i>
              Force Close
            </button>
          </div>
        </div>
      `;
        }).join('');
    } else {
        // Only clients without rooms
        grid.innerHTML = clients.map((client, idx) => `
      <div class="audio-room-card">
        <div class="audio-member">
          <div class="audio-member-info">
            <div class="audio-member-avatar member-${(idx % 2) + 1}">
              <i data-lucide="user"></i>
            </div>
            <div class="audio-member-details">
              <span class="audio-member-name">${escapeHtml(client.name)}</span>
              <span class="audio-member-user-id">${escapeHtml(client.user_id)}</span>
            </div>
          </div>
          <span class="audio-member-status ${client.status}">
            ${client.status}
          </span>
        </div>
      </div>
    `).join('');
    }

    refreshIcons();
}

/**
 * Start audio status polling
 */
function startAudioPolling() {
    if (!audioStatusInterval) {
        audioStatusInterval = setInterval(() => {
            loadAudioStatus();
        }, 3000);
    }
}

/**
 * Stop audio status polling
 */
function stopAudioPolling() {
    if (audioStatusInterval) {
        clearInterval(audioStatusInterval);
        audioStatusInterval = null;
    }
}

/**
 * Open audio settings modal with config reload option
 */
function openAudioSettings(roomId) {
    let overlay = document.getElementById("audio-settings-modal-overlay");
    if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "audio-settings-modal-overlay";
        overlay.className = "modal-overlay";
        overlay.onclick = (e) => {
            if (e.target === overlay) closeAudioSettings();
        };
        document.body.appendChild(overlay);
    }

    // Find room info
    const rooms = audioClientsStatus.rooms || [];
    const room = rooms.find(r => r.room_id === roomId) || {};
    const members = room.members || [];

    const clientsHtml = members.map((m, idx) => `
        <div class="form-group">
            <label>Client ${idx + 1}: ${escapeHtml(m.name)}</label>
            <input type="text" value="${escapeHtml(m.user_id || '')}" readonly>
            <small style="color: var(--text-tertiary);">Status: ${m.status}</small>
        </div>
    `).join('') || '<p style="color: var(--text-tertiary);">No clients in this room</p>';

    overlay.innerHTML = `
        <div class="modal">
            <div class="modal-header">
                <h2>
                    <i data-lucide="headphones"></i>
                    Audio Room Settings
                </h2>
                <button class="modal-close" onclick="closeAudioSettings()">
                    <i data-lucide="x"></i>
                </button>
            </div>
            <div class="modal-body">
                <p style="margin-bottom: 16px; color: var(--text-secondary);">
                    Audio client configuration is managed through <code>config.ini</code>.<br>
                    Edit the <code>[audio]</code> section and reload to apply changes.
                </p>
                ${clientsHtml}
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeAudioSettings()">
                    <i data-lucide="x"></i>
                    Cancel
                </button>
                <button class="btn btn-warning" onclick="reloadAudioConfig()">
                    <i data-lucide="refresh-cw"></i>
                    Reload All Configs
                </button>
            </div>
        </div>
    `;

    overlay.classList.add("active");
    refreshIcons();
}

function closeAudioSettings() {
    const overlay = document.getElementById("audio-settings-modal-overlay");
    if (overlay) {
        overlay.classList.remove("active");
    }
}

async function reloadAudioConfig() {
    if (!confirm("This will stop all audio connections and reconnect with new config. Continue?")) return;

    closeAudioSettings();

    try {
        const response = await fetch("/api/config/reload", { method: "POST" });
        const result = await response.json();

        if (result.status === "ok") {
            setTimeout(() => location.reload(), 1500);
        } else {
            alert("Failed to reload config: " + (result.message || "Unknown error"));
        }
    } catch (e) {
        console.error("Failed to reload config:", e);
        alert("Failed to reload config: " + e.message);
    }
}

/**
 * Listen to audio room in real-time
 */
let currentAudioPlayer = null;

function listenToAudio(roomId) {
    // Create or get audio player modal
    let overlay = document.getElementById("audio-player-modal");
    if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "audio-player-modal";
        overlay.className = "modal-overlay";
        overlay.onclick = (e) => {
            if (e.target === overlay) closeAudioPlayer();
        };
        document.body.appendChild(overlay);
    }

    // Generate unique timestamp to avoid caching
    const timestamp = Date.now();
    const audioUrl = `/api/audio/stream/${roomId}?t=${timestamp}`;

    overlay.innerHTML = `
        <div class="modal" style="max-width: 400px;">
            <div class="modal-header">
                <h2>
                    <i data-lucide="headphones"></i>
                    Live Audio
                </h2>
                <button class="modal-close" onclick="closeAudioPlayer()">
                    <i data-lucide="x"></i>
                </button>
            </div>
            <div class="modal-body" style="text-align: center;">
                <div class="audio-player-container">
                    <audio id="live-audio-player" controls autoplay style="width: 100%;">
                        <source src="${audioUrl}" type="audio/webm">
                        Your browser does not support audio playback.
                    </audio>
                    <p style="margin-top: 16px; color: var(--text-tertiary); font-size: 13px;">
                        <i data-lucide="info" style="width: 14px; height: 14px; vertical-align: middle;"></i>
                        Audio may have a slight delay
                    </p>
                    <button class="btn btn-secondary" style="margin-top: 12px;" onclick="refreshAudioStream('${roomId}')">
                        <i data-lucide="refresh-cw"></i>
                        Refresh Stream
                    </button>
                </div>
            </div>
        </div>
    `;

    overlay.classList.add("active");
    refreshIcons();

    // Store current player reference
    currentAudioPlayer = document.getElementById("live-audio-player");
}

function closeAudioPlayer() {
    const overlay = document.getElementById("audio-player-modal");
    if (overlay) {
        overlay.classList.remove("active");
    }

    // Stop the audio
    if (currentAudioPlayer) {
        currentAudioPlayer.pause();
        currentAudioPlayer.src = "";
        currentAudioPlayer = null;
    }
}

function refreshAudioStream(roomId) {
    if (currentAudioPlayer) {
        const timestamp = Date.now();
        currentAudioPlayer.src = `/api/audio/stream/${roomId}?t=${timestamp}`;
        currentAudioPlayer.load();
        currentAudioPlayer.play();
    }
}
