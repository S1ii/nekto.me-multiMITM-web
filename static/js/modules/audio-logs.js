// ============================================
// Audio Logs Viewer
// ============================================

let audioLogs = [];
let currentAudioFilename = null;
let audioSearchTimeout = null;
let audioLiveRooms = [];
let currentLiveRoomId = null;
let audioLiveInterval = null;

/**
 * Debounce audio search
 */
function debounceAudioSearch() {
    clearTimeout(audioSearchTimeout);
    audioSearchTimeout = setTimeout(loadAudioLogs, 350);
}

/**
 * Clear audio search
 */
function clearAudioSearch() {
    document.getElementById("audio-logs-search").value = "";
    document.getElementById("clear-audio-search-btn").style.display = "none";
    loadAudioLogs();
}

/**
 * Load audio logs list
 */
async function loadAudioLogs() {
    const sidebar = document.getElementById("audio-logs-sidebar");
    const searchQuery = document.getElementById("audio-logs-search").value.toLowerCase();

    document.getElementById("clear-audio-search-btn").style.display = searchQuery ? "flex" : "none";

    sidebar.innerHTML = `
    <div class="loading-state">
      <div class="loading-spinner">
        <i data-lucide="loader-2" class="spin"></i>
      </div>
      <p>Loading audio logs...</p>
    </div>
  `;
    refreshIcons();

    try {
        const response = await fetch("/api/audio/logs");
        audioLogs = await response.json();
        if (searchQuery) {
            audioLogs = audioLogs.filter((log) =>
                log.filename.toLowerCase().includes(searchQuery)
            );
        }
        renderAudioLogsList();
    } catch (e) {
        sidebar.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <i data-lucide="alert-circle"></i>
        </div>
        <p>Failed to load audio logs</p>
      </div>
    `;
        refreshIcons();
    }
}

/**
 * Render audio logs list
 */
function renderAudioLogsList() {
    const sidebar = document.getElementById("audio-logs-sidebar");

    if (audioLogs.length === 0) {
        sidebar.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <i data-lucide="inbox"></i>
        </div>
        <p>No audio logs found</p>
      </div>
    `;
        refreshIcons();
        return;
    }

    sidebar.innerHTML = audioLogs
        .map((log) => {
            const createdAt = log.created_at ? new Date(log.created_at) : null;
            return `
        <div class="log-item ${currentAudioFilename === log.filename ? "active" : ""}"
             onclick="loadAudioLogDetail('${log.filename}')">
          <div class="log-item-header">
            <span class="log-date">
              <i data-lucide="calendar"></i>
              ${createdAt ? createdAt.toLocaleDateString("ru-RU") : "Unknown"}
            </span>
            <span class="log-time">
              ${createdAt ? createdAt.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : ""}
            </span>
          </div>
          <div class="log-item-body">
            <span class="log-room-id">
              <i data-lucide="file-audio"></i>
              ${escapeHtml(log.filename)}
            </span>
          </div>
          <div class="log-item-footer">
            <span class="log-size">
              ${formatFileSize(log.file_size)}
            </span>
          </div>
        </div>
      `;
        })
        .join("");

    refreshIcons();
}

/**
 * Load audio log detail (player)
 */
async function loadAudioLogDetail(filename) {
    currentAudioFilename = filename;
    renderAudioLogsList();

    const detail = document.getElementById("audio-log-detail");
    const audioUrl = `/api/audio/logs/${encodeURIComponent(filename)}`;

    detail.innerHTML = `
    <div class="log-detail-header">
      <div class="log-detail-info">
        <h2>
          <i data-lucide="file-audio"></i>
          ${escapeHtml(filename)}
        </h2>
      </div>
      <div class="log-detail-actions">
        <a class="btn btn-secondary" href="${audioUrl}" download="${filename}">
          <i data-lucide="download"></i>
          Download
        </a>
      </div>
    </div>
    <div class="audio-player">
      <audio controls src="${audioUrl}"></audio>
    </div>
  `;

    refreshIcons();
}

// ============================================
// Live Audio Viewer
// ============================================

/**
 * Load live audio rooms
 */
async function loadAudioLive() {
    const list = document.getElementById("audio-live-list");
    const player = document.getElementById("audio-live-player");

    if (!list) return;

    list.innerHTML = `
    <div class="loading-state">
      <div class="loading-spinner">
        <i data-lucide="loader-2" class="spin"></i>
      </div>
      <p>Loading live rooms...</p>
    </div>
  `;
    refreshIcons();

    try {
        const response = await fetch("/api/audio/live");
        audioLiveRooms = await response.json();
        renderAudioLiveList();

        if (!currentLiveRoomId && audioLiveRooms.length > 0) {
            loadAudioLivePlayer(audioLiveRooms[0].room_id);
        }
    } catch (e) {
        list.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <i data-lucide="alert-circle"></i>
        </div>
        <p>Failed to load live rooms</p>
      </div>
    `;
        if (!currentLiveRoomId && player) {
            player.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">
            <i data-lucide="volume-2"></i>
          </div>
          <p>Live stream unavailable</p>
        </div>
      `;
        }
        refreshIcons();
    }
}

/**
 * Render live audio rooms list
 */
function renderAudioLiveList() {
    const list = document.getElementById("audio-live-list");
    if (!list) return;

    if (audioLiveRooms.length === 0) {
        list.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <i data-lucide="headphones"></i>
        </div>
        <p>No live rooms yet</p>
      </div>
    `;
        refreshIcons();
        return;
    }

    list.innerHTML = audioLiveRooms
        .map((room) => {
            const startedAt = room.started_at ? new Date(room.started_at) : null;
            return `
        <div class="log-item ${currentLiveRoomId === room.room_id ? "active" : ""}"
             onclick="loadAudioLivePlayer('${room.room_id}')">
          <div class="log-item-header">
            <span class="log-date">
              <i data-lucide="radio"></i>
              ${room.room_id.slice(-10)}
            </span>
            <span class="log-time">
              ${startedAt ? startedAt.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : ""}
            </span>
          </div>
          <div class="log-item-body">
            <span class="log-room-id">
              <i data-lucide="headphones"></i>
              Live stream
            </span>
          </div>
        </div>
      `;
        })
        .join("");

    refreshIcons();
}

/**
 * Load live audio player
 */
function loadAudioLivePlayer(roomId) {
    currentLiveRoomId = roomId;
    renderAudioLiveList();

    const player = document.getElementById("audio-live-player");
    if (!player) return;

    const liveUrl = `/api/audio/live/${encodeURIComponent(roomId)}`;

    player.innerHTML = `
    <div class="log-detail-header">
      <div class="log-detail-info">
        <h2>
          <i data-lucide="radio"></i>
          Live Audio Room
        </h2>
        <div class="log-meta">
          <span><i data-lucide="hash"></i>${roomId}</span>
        </div>
      </div>
      <div class="log-detail-actions">
        <button class="btn btn-refresh" onclick="loadAudioLive()">
          <i data-lucide="refresh-cw"></i>
          Refresh
        </button>
      </div>
    </div>
    <div class="audio-player">
      <audio controls autoplay src="${liveUrl}"></audio>
      <p class="audio-live-hint">Если поток не запускается, подождите пару секунд — данные появятся после подключения собеседников.</p>
    </div>
  `;
    refreshIcons();
}
