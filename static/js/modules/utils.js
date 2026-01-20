// ============================================
// Utility Functions
// ============================================

/**
 * Format file sizes
 */
function formatFileSize(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
}

/**
 * Format duration in seconds
 */
function formatDuration(seconds) {
    if (!seconds || seconds < 0) return "0s";

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

/**
 * Format date from ISO string to localized date
 */
function formatDate(isoString) {
    if (!isoString) return "Unknown";
    try {
        const date = new Date(isoString);
        return date.toLocaleDateString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric"
        });
    } catch (e) {
        return "Invalid Date";
    }
}

/**
 * Format date and time from ISO string
 */
function formatDateTime(isoString) {
    if (!isoString) return "Unknown";
    try {
        const date = new Date(isoString);
        return date.toLocaleString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit"
        });
    } catch (e) {
        return "Invalid Date";
    }
}

/**
 * Format time from ISO string
 */
function formatTime(isoString) {
    if (!isoString) return "";
    try {
        const date = new Date(isoString);
        return date.toLocaleTimeString("ru-RU", {
            hour: "2-digit",
            minute: "2-digit"
        });
    } catch (e) {
        return "";
    }
}

/**
 * Escape HTML special characters
 */
function escapeHtml(text) {
    const map = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
    };
    return text.replace(/[&<>"']/g, (m) => map[m]);
}

/**
 * Copy text to clipboard
 */
function copyMessage(text) {
    navigator.clipboard
        .writeText(text)
        .then(() => {
            console.log("Message copied to clipboard");
        })
        .catch((err) => {
            console.error("Failed to copy:", err);
        });
}

/**
 * Refresh Lucide icons
 */
function refreshIcons() {
    if (typeof lucide !== "undefined") {
        lucide.createIcons();
    }
}
