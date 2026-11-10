/**
 * UI Utilities: Toasts, Modals, Formatters, and Feedback components
 */

// Toast notification container
function getOrCreateToastContainer() {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    document.body.appendChild(container);
  }
  return container;
}

export function showToast(message, type = "success", durationMs = 3500) {
  const container = getOrCreateToastContainer();
  const toast = document.createElement("div");
  toast.className = `toast ${type === "error" ? "toast-error" : type === "warning" ? "toast-warning" : ""}`;

  const icon = type === "error" ? "❌" : type === "warning" ? "⚠️" : "✅";
  
  const content = document.createElement("div");
  content.style.display = "flex";
  content.style.alignItems = "center";
  content.style.gap = "8px";
  
  const iconSpan = document.createElement("span");
  iconSpan.textContent = icon;
  
  const textSpan = document.createElement("span");
  textSpan.textContent = message;
  
  content.appendChild(iconSpan);
  content.appendChild(textSpan);
  toast.appendChild(content);

  const closeBtn = document.createElement("button");
  closeBtn.textContent = "✕";
  closeBtn.style.background = "none";
  closeBtn.style.border = "none";
  closeBtn.style.cursor = "pointer";
  closeBtn.style.color = "var(--muted)";
  closeBtn.style.fontSize = "14px";
  closeBtn.onclick = () => toast.remove();
  toast.appendChild(closeBtn);

  container.appendChild(toast);

  setTimeout(() => {
    if (toast.parentElement) {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(50px)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }
  }, durationMs);
}

export function formatCurrency(amount) {
  if (amount === null || amount === undefined || isNaN(amount)) return "₹0.00";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(amount);
}

export function formatDate(dateStr) {
  if (!dateStr) return "-";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatTime(timeStr) {
  if (!timeStr) return "-";
  if (timeStr.includes("T")) {
    const d = new Date(timeStr);
    return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
  }
  return timeStr.slice(0, 5);
}

export function showConfirmModal(title, message, onConfirm, confirmText = "Confirm", isDanger = false) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay open";

  const modal = document.createElement("div");
  modal.className = "modal";

  modal.innerHTML = `
    <div class="modal-header">
      <h3 class="modal-title">${escapeHTML(title)}</h3>
      <button type="button" class="btn btn-sm" id="modal-close-x">✕</button>
    </div>
    <div class="modal-body">
      <p>${escapeHTML(message)}</p>
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" id="modal-cancel-btn">Cancel</button>
      <button type="button" class="btn ${isDanger ? "btn-danger" : "btn-primary"}" id="modal-confirm-btn">${escapeHTML(confirmText)}</button>
    </div>
  `;

  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  const cleanup = () => {
    overlay.classList.remove("open");
    setTimeout(() => overlay.remove(), 250);
  };

  overlay.querySelector("#modal-close-x").onclick = cleanup;
  overlay.querySelector("#modal-cancel-btn").onclick = cleanup;
  overlay.querySelector("#modal-confirm-btn").onclick = async () => {
    cleanup();
    await onConfirm();
  };
}

export function escapeHTML(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

