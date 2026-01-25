// ============================================
// Text Chat Rooms - Rendering and Controls
// ============================================

/**
 * Render all rooms grid
 */
function renderRooms() {
  const grid = document.getElementById("rooms-grid");
  grid.innerHTML = "";

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

/**
 * Re-render a single room
 */
function renderRoom(roomId) {
  const room = rooms.get(roomId);
  const oldCard = document.getElementById(`room-${roomId}`);
  if (oldCard) {
    oldCard.replaceWith(createRoomCard(room));
    refreshIcons();
  }
}

/**
 * Append a message to a room's chat area
 */
function appendMessage(roomId, msg) {
  const chatArea = document.getElementById(`chat-${roomId}`);
  if (!chatArea) return;

  const msgDiv = document.createElement("div");
  if (msg.from === "system") {
    msgDiv.className = "message message-system";
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
        <i data-lucide="user"></i>
        <span>${msg.from}</span>
        ${msg.is_manual ? '<span class="manual-badge"><i data-lucide="hand"></i>manual</span>' : ""}
        <span>${new Date(msg.timestamp).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</span>
      </div>
      <div class="message-bubble">${escapeHtml(msg.message)}</div>
    `;
  }

  const emptyState = chatArea.querySelector(".empty-state");
  if (emptyState) emptyState.remove();

  chatArea.appendChild(msgDiv);
  chatArea.scrollTop = chatArea.scrollHeight;
  refreshIcons();
}

/**
 * Update room metadata (status badges, connection indicators)
 */
function updateRoomMeta(roomId) {
  const room = rooms.get(roomId);
  const card = document.getElementById(`room-${roomId}`);
  if (!card) return;

  const statusClass = room.is_active
    ? "status-active"
    : room.is_paused
      ? "status-paused"
      : room.m_connected && room.f_connected
        ? "status-waiting"
        : "status-offline";
  const statusText = room.is_active
    ? "Active"
    : room.is_paused
      ? "Paused"
      : room.m_connected && room.f_connected
        ? "Searching"
        : "Offline";

  // Update client connection badges
  const clientM = card.querySelector(".client-badge.client-m");
  const clientF = card.querySelector(".client-badge.client-f");
  if (clientM) {
    clientM.className = `client-badge client-m ${room.is_active ? 'active' : room.is_paused ? 'paused' : room.m_connected ? 'connected' : 'offline'}`;
  }
  if (clientF) {
    clientF.className = `client-badge client-f ${room.is_active ? 'active' : room.is_paused ? 'paused' : room.f_connected ? 'connected' : 'offline'}`;
  }

  // Update status pill
  const statusPill = card.querySelector(".status-pill");
  if (statusPill) {
    statusPill.className = `status-pill ${statusClass}`;
    statusPill.innerHTML = `<span class="status-dot"></span>${statusText}`;
  }

  // Update message counter
  const msgCountValue = card.querySelector(".msg-count-value");
  if (msgCountValue) {
    msgCountValue.textContent = room.messages_count;
  }

  const controlPanel = card.querySelector(".control-panel");
  if (controlPanel) {
    controlPanel.innerHTML = createControlPanelHTML(room);
  }

  refreshIcons();
}

/**
 * Generate control panel HTML for a room
 */
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
               ${!room.is_active ? "disabled" : ""}>
        <button class="btn btn-send" 
                onclick="sendMessage('${room.room_id}', '${room.manual_control}')"
                ${!room.is_active ? "disabled" : ""}>
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
      <button class="btn btn-manual btn-control-f" 
              onclick="toggleControl('${room.room_id}', 'F')"
              ${!room.is_active ? "disabled" : ""}>
        <i data-lucide="user"></i>
        Control F
      </button>
      <button class="btn btn-manual btn-control-m" 
              onclick="toggleControl('${room.room_id}', 'M')"
              ${!room.is_active ? "disabled" : ""}>
        <i data-lucide="user"></i>
        Control M
      </button>
    </div>
    <div class="action-buttons">
      <button class="btn ${room.is_paused ? "btn-success" : "btn-pause"}" 
              onclick="togglePause('${room.room_id}')">
        <i data-lucide="${room.is_paused ? "play" : "pause"}"></i>
        ${room.is_paused ? "Resume" : "Pause"}
      </button>
      <button class="btn btn-warning" 
              onclick="restartSearch('${room.room_id}')"
              ${room.is_paused ? "disabled" : ""}>
        <i data-lucide="rotate-ccw"></i>
        Restart
      </button>
      <button class="btn btn-danger" 
              onclick="forceCloseDialog('${room.room_id}')"
              ${!room.is_active ? "disabled" : ""}>
        <i data-lucide="x-circle"></i>
        Close
      </button>
    </div>
  `;
}

/**
 * Create a room card element
 */
function createRoomCard(room) {
  const card = document.createElement("div");
  card.className = "room-card";
  card.id = `room-${room.room_id}`;

  const statusClass = room.is_active
    ? "status-active"
    : room.is_paused
      ? "status-paused"
      : room.m_connected && room.f_connected
        ? "status-waiting"
        : "status-offline";
  const statusText = room.is_active
    ? "Active"
    : room.is_paused
      ? "Paused"
      : room.m_connected && room.f_connected
        ? "Searching"
        : "Offline";

  const chatContent =
    room.messages.length > 0
      ? room.messages
        .map((msg) => {
          if (msg.from === "system") {
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
                ${msg.is_manual ? '<span class="manual-badge"><i data-lucide="hand"></i>manual</span>' : ""}
                <span>${new Date(msg.timestamp).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</span>
              </div>
              <div class="message-bubble">${escapeHtml(msg.message)}</div>
            </div>
          `;
        })
        .join("")
      : `
        <div class="empty-state">
          <div class="empty-icon">
            <i data-lucide="message-circle"></i>
          </div>
          <p>No messages yet</p>
        </div>
      `;

  card.innerHTML = `
    <div class="room-header">
      <div class="room-header-left">
        <span class="room-id">#${room.room_id.slice(-8)}</span>
        <div class="room-clients">
          <span class="client-badge client-m ${room.is_active ? 'active' : room.is_paused ? 'paused' : room.m_connected ? 'connected' : 'offline'}">
            M
          </span>
          <span class="client-badge client-f ${room.is_active ? 'active' : room.is_paused ? 'paused' : room.f_connected ? 'connected' : 'offline'}">
            F
          </span>
        </div>
      </div>
      <div class="room-header-center">
        <span class="status-pill ${statusClass}">
          <span class="status-dot"></span>
          ${statusText}
        </span>
      </div>
      <div class="room-header-right">
        <span class="msg-counter">
          <i data-lucide="message-square"></i>
          <span class="msg-count-value">${room.messages_count}</span>
        </span>
        <button class="btn-icon btn-settings" onclick="openRoomSettings('${room.room_id}')" title="Settings">
          <i data-lucide="settings"></i>
        </button>
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

// ============================================
// Room API Actions
// ============================================

async function toggleControl(roomId, sex) {
  await fetch("/toggle-control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room_id: roomId, sex: sex }),
  });
}

async function sendMessage(roomId, sex) {
  const input = document.getElementById(`input-${roomId}`);
  const message = input.value.trim();

  if (!message) return;

  const response = await fetch("/send-message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room_id: roomId, sex: sex, message: message }),
  });

  if (response.ok) {
    input.value = "";
  }
}

async function forceCloseDialog(roomId) {
  if (!confirm("Are you sure you want to force close this dialog?")) return;

  await fetch("/force-close", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room_id: roomId }),
  });
}

async function restartSearch(roomId) {
  if (!confirm("Restart search for this room? Current dialog/search will be stopped.")) return;

  await fetch("/restart-search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room_id: roomId }),
  });
}

async function togglePause(roomId) {
  await fetch("/toggle-pause", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room_id: roomId }),
  });
}

function handleKeyPress(event, roomId, sex) {
  if (event.key === "Enter") {
    sendMessage(roomId, sex);
  }
}

// ============================================
// Room Settings Modal
// ============================================

let currentSettingsRoom = null;

/**
 * Open room settings modal
 */
function openRoomSettings(roomId) {
  const room = rooms.get(roomId);
  if (!room) return;

  currentSettingsRoom = roomId;

  let overlay = document.getElementById("settings-modal-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "settings-modal-overlay";
    overlay.className = "modal-overlay";
    overlay.onclick = (e) => {
      if (e.target === overlay) closeSettings();
    };
    document.body.appendChild(overlay);
  }

  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <h2>
          <i data-lucide="settings"></i>
          Room Settings
        </h2>
        <button class="modal-close" onclick="closeSettings()">
          <i data-lucide="x"></i>
        </button>
      </div>
      <div class="modal-body">
        <div class="client-tabs">
          <button class="client-tab male active" onclick="showClientTab('M')">Client M</button>
          <button class="client-tab female" onclick="showClientTab('F')">Client F</button>
        </div>
        
        <div id="client-form-M" class="client-form">
          <div class="form-group">
            <label>Token (User ID)</label>
            <input type="text" id="m-token" value="${room.m_token}">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Sex</label>
              <select id="m-sex">
                <option value="M" selected>Male (M)</option>
                <option value="F">Female (F)</option>
              </select>
            </div>
            <div class="form-group">
              <label>Search Sex</label>
              <select id="m-wish-sex">
                <option value="M">Males</option>
                <option value="F" selected>Females</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Age (from,to)</label>
              <input type="text" id="m-age" placeholder="18,24">
            </div>
            <div class="form-group">
              <label>Search Age (ranges)</label>
              <input type="text" id="m-wish-age" placeholder="18,24-25,30">
            </div>
          </div>
        </div>
        
        <div id="client-form-F" class="client-form" style="display:none;">
          <div class="form-group">
            <label>Token (User ID)</label>
            <input type="text" id="f-token" value="${room.f_token}">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Sex</label>
              <select id="f-sex">
                <option value="M">Male (M)</option>
                <option value="F" selected>Female (F)</option>
              </select>
            </div>
            <div class="form-group">
              <label>Search Sex</label>
              <select id="f-wish-sex">
                <option value="M" selected>Males</option>
                <option value="F">Females</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Age (from,to)</label>
              <input type="text" id="f-age" placeholder="18,24">
            </div>
            <div class="form-group">
              <label>Search Age (ranges)</label>
              <input type="text" id="f-wish-age" placeholder="18,24-25,30">
            </div>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeSettings()">
          <i data-lucide="x"></i>
          Cancel
        </button>
        <button class="btn btn-warning" onclick="reloadConfig()">
          <i data-lucide="refresh-cw"></i>
          Reload All
        </button>
      </div>
    </div>
  `;

  overlay.classList.add("active");
  refreshIcons();
}

function closeSettings() {
  const overlay = document.getElementById("settings-modal-overlay");
  if (overlay) {
    overlay.classList.remove("active");
  }
  currentSettingsRoom = null;
}

function showClientTab(sex) {
  document.querySelectorAll(".client-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".client-form").forEach(f => f.style.display = "none");

  document.querySelector(`.client-tab.${sex === 'M' ? 'male' : 'female'}`).classList.add("active");
  document.getElementById(`client-form-${sex}`).style.display = "block";
}

async function reloadConfig() {
  if (!confirm("This will stop all searches and reconnect with new config. Continue?")) return;

  closeSettings();

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
