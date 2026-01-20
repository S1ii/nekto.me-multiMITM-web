// ============================================
// Chat Logs Viewer with Pagination & Full-text Search
// ============================================

let currentLogs = [];
let currentLogFilename = null;
let searchTimeout = null;
let isSearchMode = false;

// Pagination state
let currentPage = 1;
let totalPages = 1;
let totalLogs = 0;
const PAGE_LIMIT = 50;

/**
 * Load logs statistics
 */
async function loadLogsStats() {
  try {
    const response = await fetch("/api/logs/stats");
    const stats = await response.json();

    document.getElementById("stat-total-logs").textContent = stats.total_logs || 0;
    document.getElementById("stat-total-messages").textContent = stats.total_messages || 0;
    document.getElementById("stat-total-size").textContent = formatFileSize(stats.total_size || 0);
    document.getElementById("stat-date-range").textContent = stats.date_range || "-";
  } catch (e) {
    console.error("Failed to load logs stats:", e);
  }
}

/**
 * Load logs list with pagination
 */
async function loadLogs(page = 1) {
  const sidebar = document.getElementById("logs-sidebar");
  const searchQuery = document.getElementById("logs-search").value.trim();
  const sortBy = document.getElementById("logs-sort").value;

  document.getElementById("clear-search-btn").style.display = searchQuery ? "flex" : "none";

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
    let data;

    if (searchQuery) {
      // Use Whoosh full-text search
      isSearchMode = true;
      const response = await fetch(`/api/logs/search?q=${encodeURIComponent(searchQuery)}&page=${page}&limit=${PAGE_LIMIT}`);
      data = await response.json();
      currentLogs = data.results || [];
    } else {
      // Use paginated listing
      isSearchMode = false;
      const response = await fetch(`/api/logs?page=${page}&limit=${PAGE_LIMIT}&sort=${sortBy}`);
      data = await response.json();
      currentLogs = data.logs || [];
    }

    // Update pagination state
    currentPage = data.page || 1;
    totalPages = data.totalPages || 1;
    totalLogs = data.total || 0;

    renderLogsList();
    renderPagination();
  } catch (e) {
    console.error("Failed to load logs:", e);
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

/**
 * Render pagination controls
 */
function renderPagination() {
  let paginationEl = document.getElementById("logs-pagination");

  if (!paginationEl) {
    // Create pagination container if it doesn't exist
    const toolbar = document.querySelector(".logs-toolbar");
    paginationEl = document.createElement("div");
    paginationEl.id = "logs-pagination";
    paginationEl.className = "pagination";
    toolbar.appendChild(paginationEl);
  }

  if (totalPages <= 1) {
    paginationEl.innerHTML = `<span class="pagination-info">${totalLogs} logs</span>`;
    return;
  }

  let html = `
        <button class="pagination-btn" onclick="goToPage(${currentPage - 1})" ${currentPage <= 1 ? 'disabled' : ''}>
            <i data-lucide="chevron-left"></i>
        </button>
    `;

  // Page numbers
  const maxVisible = 5;
  let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
  let endPage = Math.min(totalPages, startPage + maxVisible - 1);

  if (endPage - startPage < maxVisible - 1) {
    startPage = Math.max(1, endPage - maxVisible + 1);
  }

  if (startPage > 1) {
    html += `<button class="pagination-btn" onclick="goToPage(1)">1</button>`;
    if (startPage > 2) {
      html += `<span class="pagination-ellipsis">...</span>`;
    }
  }

  for (let i = startPage; i <= endPage; i++) {
    html += `<button class="pagination-btn ${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
  }

  if (endPage < totalPages) {
    if (endPage < totalPages - 1) {
      html += `<span class="pagination-ellipsis">...</span>`;
    }
    html += `<button class="pagination-btn" onclick="goToPage(${totalPages})">${totalPages}</button>`;
  }

  html += `
        <button class="pagination-btn" onclick="goToPage(${currentPage + 1})" ${currentPage >= totalPages ? 'disabled' : ''}>
            <i data-lucide="chevron-right"></i>
        </button>
        <span class="pagination-info">${totalLogs} logs</span>
    `;

  paginationEl.innerHTML = html;
  refreshIcons();
}

/**
 * Go to specific page
 */
function goToPage(page) {
  if (page < 1 || page > totalPages) return;
  loadLogs(page);
}

/**
 * Render logs list in sidebar
 */
function renderLogsList() {
  const sidebar = document.getElementById("logs-sidebar");

  if (currentLogs.length === 0) {
    const message = isSearchMode ? "No results found" : "No logs found";
    sidebar.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <i data-lucide="${isSearchMode ? 'search-x' : 'inbox'}"></i>
        </div>
        <p>${message}</p>
      </div>
    `;
    refreshIcons();
    return;
  }

  sidebar.innerHTML = currentLogs
    .map((log) => {
      return `
        <div class="log-item ${currentLogFilename === log.filename ? "active" : ""}"
             onclick="loadLogDetail('${log.filename}')">
          <div class="log-item-header">
            <span class="log-date">
              <i data-lucide="calendar"></i>
              ${formatDate(log.start_time)}
            </span>
            <span class="log-time">
              ${formatTime(log.start_time)}
            </span>
          </div>
          <div class="log-item-body">
            <span class="log-room-id">
              <i data-lucide="hash"></i>
              ${log.room_id ? log.room_id.slice(-12) : log.filename}
            </span>
          </div>
          <div class="log-item-footer">
            <span class="log-messages">
              <i data-lucide="message-square"></i>
              ${log.messages_count} messages
            </span>
            <span class="log-duration">
              <i data-lucide="clock"></i>
              ${formatDuration(log.duration)}
            </span>
          </div>
        </div>
      `;
    })
    .join("");

  refreshIcons();
}

/**
 * Load log detail
 */
async function loadLogDetail(filename) {
  currentLogFilename = filename;
  renderLogsList();

  const detail = document.getElementById("log-detail");
  detail.innerHTML = `
    <div class="loading-state">
      <div class="loading-spinner">
        <i data-lucide="loader-2" class="spin"></i>
      </div>
      <p>Loading log...</p>
    </div>
  `;
  refreshIcons();

  try {
    const response = await fetch(`/api/logs/${encodeURIComponent(filename)}`);
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

/**
 * Render log detail view
 */
function renderLogDetail(log, filename) {
  const detail = document.getElementById("log-detail");
  const searchQuery = document.getElementById("logs-search").value.trim().toLowerCase();

  const messagesHtml = log.messages
    .map((msg) => {
      let messageText = escapeHtml(msg.message);

      // Highlight search matches
      if (searchQuery && searchQuery.length >= 2) {
        const regex = new RegExp(`(${escapeRegex(searchQuery)})`, 'gi');
        messageText = messageText.replace(regex, '<mark class="search-highlight">$1</mark>');
      }

      if (msg.from === "system") {
        return `
          <div class="log-message log-message-system">
            <div class="log-message-bubble">
              <i data-lucide="info"></i>
              ${messageText}
            </div>
          </div>
        `;
      }
      return `
        <div class="log-message log-message-${msg.from.toLowerCase()}">
          <div class="log-message-header">
            <i data-lucide="user"></i>
            <span class="log-message-sender">${msg.from}</span>
            ${msg.is_manual ? '<span class="manual-badge"><i data-lucide="hand"></i>manual</span>' : ""}
            <span class="log-message-time">
              ${new Date(msg.timestamp).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
            <button class="log-message-copy" onclick="copyMessage('${escapeHtml(msg.message).replace(/'/g, "\\'")}')">
              <i data-lucide="copy"></i>
            </button>
          </div>
          <div class="log-message-bubble">${messageText}</div>
        </div>
      `;
    })
    .join("");

  detail.innerHTML = `
    <div class="log-detail-header">
      <div class="log-detail-info">
        <h2>
          <i data-lucide="file-text"></i>
          ${log.room_id ? log.room_id.slice(-12) : filename}
        </h2>
        <div class="log-meta">
          <span><i data-lucide="calendar"></i>${formatDateTime(log.start_time)}</span>
          <span><i data-lucide="message-square"></i>${log.messages.length} messages</span>
          <span><i data-lucide="clock"></i>${formatDuration(log.duration)}</span>
        </div>
      </div>
      <div class="log-detail-actions">
        <button class="btn btn-secondary" onclick="exportLog('${filename}', 'txt')">
          <i data-lucide="file-text"></i>
          Export TXT
        </button>
        <button class="btn btn-secondary" onclick="exportLog('${filename}', 'json')">
          <i data-lucide="file-json"></i>
          Export JSON
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
}

/**
 * Escape regex special characters
 */
function escapeRegex(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Debounce search input
 */
function debounceSearch() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => loadLogs(1), 350);
}

/**
 * Clear search input
 */
function clearSearch() {
  document.getElementById("logs-search").value = "";
  loadLogs(1);
}

/**
 * Delete a log file
 */
async function deleteLog(filename) {
  if (!confirm(`Delete log "${filename}"? This action cannot be undone.`)) return;

  try {
    const response = await fetch(`/api/logs/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    });

    if (response.ok) {
      currentLogFilename = null;
      loadLogs(currentPage);
      loadLogsStats();

      document.getElementById("log-detail").innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">
            <i data-lucide="check-circle"></i>
          </div>
          <p>Log deleted successfully</p>
        </div>
      `;
      refreshIcons();
    }
  } catch (e) {
    console.error("Failed to delete log:", e);
  }
}

/**
 * Export log file
 */
async function exportLog(filename, format) {
  try {
    const response = await fetch(`/api/logs/${encodeURIComponent(filename)}`);
    const log = await response.json();

    let content;
    let mimeType;
    let extension;

    if (format === "json") {
      content = JSON.stringify(log, null, 2);
      mimeType = "application/json";
      extension = "json";
    } else {
      const lines = [];
      lines.push(`Room ID: ${log.room_id}`);
      lines.push(`Start: ${log.start_time}`);
      lines.push(`End: ${log.end_time}`);
      lines.push(`Duration: ${formatDuration(log.duration)}`);
      lines.push("");
      lines.push("=".repeat(50));
      lines.push("");

      log.messages.forEach((msg) => {
        const time = new Date(msg.timestamp).toLocaleTimeString("ru-RU");
        if (msg.from === "system") {
          lines.push(`[${time}] --- ${msg.message} ---`);
        } else {
          lines.push(`[${time}] ${msg.from}: ${msg.message}`);
        }
      });

      content = lines.join("\n");
      mimeType = "text/plain";
      extension = "txt";
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${filename.replace(".json", "")}.${extension}`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error("Failed to export log:", e);
  }
}
