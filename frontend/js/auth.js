/**
 * Authentication and Session Management for Frontend Portals
 */
import { apiRequest } from "./api.js";
import { showToast, escapeHTML, formatDate, formatTime } from "./ui.js";

export async function getCurrentUser() {
  try {
    return await apiRequest("/api/auth/me");
  } catch {
    return null;
  }
}

export async function requireAuth(expectedRole = null) {
  const user = await getCurrentUser();
  if (!user) {
    redirectToLogin(expectedRole);
    return null;
  }

  if (expectedRole && user.role !== expectedRole) {
    showToast(`Access restricted: expected role '${expectedRole}'`, "error");
    redirectToLogin(expectedRole);
    return null;
  }

  return user;
}

export function redirectToLogin(role = null) {
  if (role === "admin") window.location.href = "/admin/login.html";
  else if (role === "officer") window.location.href = "/officer/login.html";
  else if (role === "scanner") window.location.href = "/scanner/login.html";
  else window.location.href = "/login.html";
}

export async function logoutUser() {
  try {
    await apiRequest("/api/auth/logout", { method: "POST" });
  } catch {
    // Continue even if logout API had issue
  }
  const path = window.location.pathname;
  if (path.includes("/admin/")) window.location.href = "/admin/login.html";
  else if (path.includes("/officer/")) window.location.href = "/officer/login.html";
  else if (path.includes("/scanner/")) window.location.href = "/scanner/login.html";
  else window.location.href = "/login.html";
}

export function setupHeader(user, portalName) {
  const nameEl = document.getElementById("header-user-name");
  if (nameEl) nameEl.textContent = user.full_name;

  const roleEl = document.getElementById("header-role-badge");
  if (roleEl) roleEl.textContent = portalName || user.role.toUpperCase();

  const logoutBtn = document.getElementById("header-logout-btn");
  if (logoutBtn) {
    logoutBtn.onclick = logoutUser;
  }

  // Setup notification bell if present (Customer portal)
  setupNotificationBell();
}

export function setupNotificationBell() {
  const notifBtn = document.getElementById("notif-btn");
  const notifDropdown = document.getElementById("notif-dropdown");
  const notifBadge = document.getElementById("notif-badge");
  const notifList = document.getElementById("notif-list");
  const markAllBtn = document.getElementById("notif-mark-all");

  if (!notifBtn || !notifDropdown) return;

  async function updateUnreadCount() {
    try {
      const data = await apiRequest("/api/notifications/unread-count");
      const count = data.unread_count || 0;
      if (notifBadge) {
        if (count > 0) {
          notifBadge.textContent = count > 9 ? "9+" : count;
          notifBadge.style.display = "flex";
        } else {
          notifBadge.style.display = "none";
        }
      }
    } catch {
      // Ignore background notification fetch errors
    }
  }

  async function loadNotifications() {
    if (!notifList) return;
    try {
      const items = await apiRequest("/api/notifications");
      if (items.length === 0) {
        notifList.innerHTML = `<li class="notif-item" style="color:var(--muted);text-align:center;padding:20px;">No notifications</li>`;
        return;
      }
      notifList.innerHTML = items.map(n => `
        <li class="notif-item ${!n.is_read ? "unread" : ""}">
          <div style="font-weight:600;color:var(--green-900);">${escapeHTML(n.title)}</div>
          <div style="font-size:0.85rem;margin:2px 0;">${escapeHTML(n.message)}</div>
          <div class="notif-time">${formatDate(n.created_at)} ${formatTime(n.created_at)}</div>
        </li>
      `).join("");
    } catch (e) {
      console.warn("Could not load notifications", e);
    }
  }

  notifBtn.onclick = (e) => {
    e.stopPropagation();
    const isOpen = notifDropdown.classList.toggle("open");
    if (isOpen) {
      loadNotifications();
    }
  };

  document.addEventListener("click", (e) => {
    if (!notifDropdown.contains(e.target) && e.target !== notifBtn) {
      notifDropdown.classList.remove("open");
    }
  });

  if (markAllBtn) {
    markAllBtn.onclick = async () => {
      try {
        await apiRequest("/api/notifications/read-all", { method: "POST" });
        await updateUnreadCount();
        await loadNotifications();
        showToast("Marked all as read", "success");
      } catch (e) {
        showToast(e.message, "error");
      }
    };
  }

  // Initial count
  updateUnreadCount();
  // Refresh count every 15s
  setInterval(updateUnreadCount, 15000);
}

