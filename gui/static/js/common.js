// =============================================================================
// common.js — Shared utilities for all pages
// =============================================================================

const WS_BASE = `ws://${location.host}`;
const API_BASE = `${location.origin}/api`;

// --- Status polling (nav bar status pill) ---

async function pollStatus() {
  try {
    const res = await fetch(`${API_BASE}/status`);
    const data = await res.json();
    updateStatusUI(data);
  } catch (e) { /* Silently skip */ }
}

function updateStatusUI(data) {
  const pill = document.getElementById('status-pill');
  if (!pill) return;

  const containers = data.containers || data;
  const statuses = Object.values(containers);
  const running = statuses.filter(s => s === 'running').length;
  const total = statuses.length;

  if (total === 0) {
    pill.textContent = 'No containers';
    pill.className = 'status-pill pill-down';
  } else if (running === total) {
    pill.textContent = `${running}/${total} Ready`;
    pill.className = 'status-pill pill-ready';
  } else if (running > 0) {
    pill.textContent = `${running}/${total} Partial`;
    pill.className = 'status-pill pill-partial';
  } else {
    pill.textContent = `${running}/${total} Down`;
    pill.className = 'status-pill pill-down';
  }
}

// --- Utilities ---

function escapeHtml(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatMetricName(key) {
  return key.replace(/_/g, ' ').replace(/fivegs\s.*?\s/, '');
}

function formatMetricValue(v) {
  if (typeof v !== 'number') return v;
  if (Number.isInteger(v)) return v.toLocaleString();
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1) + 'K';
  return v.toFixed(2);
}

function renderSparkline(values, w, h) {
  if (!values || values.length < 2) return '';
  const max = Math.max(...values, 1);
  const step = w / (values.length - 1);
  const pts = values.map((v, i) => `${i * step},${h - (v / max) * h}`).join(' ');
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="1.5" />
  </svg>`;
}

// --- Nav bar active page highlighting ---

// Runs after DOM is ready — highlights the current page in the nav bar
document.addEventListener('DOMContentLoaded', function() {
  const path = location.pathname;
  document.querySelectorAll('nav a').forEach(a => {
    const href = a.getAttribute('href');
    if (href === path || (href === '/' && path === '/')) {
      a.classList.add('active');
    }
  });

  // Start status polling on every page
  pollStatus();
  setInterval(pollStatus, 5000);
});
