// Study Rescue – Main JavaScript
// Provides toast notifications, loading states, dark mode toggle, and auth error handling.

(function () {
  'use strict';

  // ── Dark Mode Toggle ───────────────────────────────────────────────
  const htmlEl = document.documentElement;
  const savedTheme = localStorage.getItem('studyrescue-theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

  if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
    htmlEl.classList.add('dark');
  }

  window.toggleDarkMode = function () {
    const isDark = htmlEl.classList.toggle('dark');
    localStorage.setItem('studyrescue-theme', isDark ? 'dark' : 'light');
  };

  // ── Mobile Sidebar ─────────────────────────────────────────────────
  window.toggleMobileSidebar = function () {
    const sidebar = document.querySelector('aside.sr-sidebar');
    const overlay = document.getElementById('mobile-sidebar-overlay');
    if (!sidebar || !overlay) return;
    const isHidden = sidebar.classList.contains('hidden');
    if (isHidden) {
      sidebar.classList.remove('hidden');
      overlay.classList.remove('hidden');
    } else {
      sidebar.classList.add('hidden');
      overlay.classList.add('hidden');
    }
  };

  // ── Toast Notifications ────────────────────────────────────────────
  const toastContainer = document.getElementById('toast-container');
  let toastIdCounter = 0;

  window.showToast = function (message, type = 'info', duration = 5000) {
    if (!toastContainer) return;

    const id = 'toast-' + ++toastIdCounter;
    const typeConfig = {
      success: { icon: '✅', border: 'border-l-4 border-emerald-400', bg: 'bg-[#111827]', text: 'text-[#34d399]' },
      error:   { icon: '❌', border: 'border-l-4 border-red-400', bg: 'bg-[#111827]', text: 'text-[#f87171]' },
      warning: { icon: '⚠️', border: 'border-l-4 border-amber-400', bg: 'bg-[#111827]', text: 'text-[#fbbf24]' },
      info:    { icon: 'ℹ️', border: 'border-l-4 border-indigo-400', bg: 'bg-[#111827]', text: 'text-[#a5b4fc]' },
    }[type] || typeConfig.info;

    const dark = document.documentElement.classList.contains('dark');
    const toast = document.createElement('div');
    toast.id = id;
    toast.className = 'sr-toast ' + typeConfig.border + ' ' + typeConfig.bg + ' ' + typeConfig.text;
    toast.innerHTML = `
      <span class="text-lg">${typeConfig.icon}</span>
      <div class="flex-1 min-w-0">
        <p class="text-sm font-medium leading-tight">${escapeHtml(message)}</p>
      </div>
      <button class="sr-toast-close" onclick="dismissToast('${id}')" aria-label="Dismiss">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
      </button>
    `;

    toastContainer.appendChild(toast);

    // Auto-dismiss
    const timer = setTimeout(() => dismissToast(id), duration);
    toast.dataset.timer = timer;

    // Hover to pause auto-dismiss
    toast.addEventListener('mouseenter', () => clearTimeout(parseInt(toast.dataset.timer, 10)));
    toast.addEventListener('mouseleave', () => {
      toast.dataset.timer = setTimeout(() => dismissToast(id), duration / 2);
    });
  };

  window.dismissToast = function (id) {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.dataset.timer) clearTimeout(parseInt(el.dataset.timer, 10));
    el.style.opacity = '0';
    el.style.transform = 'translateX(20px)';
    el.style.transition = 'all 0.2s ease';
    setTimeout(() => el.remove(), 200);
  };

  // ── Escape HTML helper ─────────────────────────────────────────────
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // ── Loading Button States ──────────────────────────────────────────
  window.setButtonLoading = function (btn, loading) {
    if (!btn) return;
    if (loading) {
      btn.dataset.originalText = btn.innerHTML;
      btn.disabled = true;
      btn.classList.add('opacity-70', 'cursor-not-allowed');
      btn.innerHTML = '<span class="flex items-center gap-1"><span class="animate-spin rounded-full h-4 w-4 border-b-2 border-current"></span> Working...</span>';
    } else {
      btn.disabled = false;
      btn.classList.remove('opacity-70', 'cursor-not-allowed');
      btn.innerHTML = btn.dataset.originalText || btn.innerHTML;
    }
  };

  // ── Auto-dismiss server-rendered alerts after 8 seconds ────────────
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.sr-alert, .alert').forEach(function (alert) {
      setTimeout(() => {
        alert.style.opacity = '0';
        alert.style.transition = 'opacity 0.4s ease';
        setTimeout(() => alert.remove(), 400);
      }, 8000);
    });
  });

  // ── Extract form_data from template (for toast on auth errors) ─────
  // This reads a JSON payload injected by the template if present
  const serverMsgEl = document.getElementById('server-message');
  if (serverMsgEl) {
    try {
      const data = JSON.parse(serverMsgEl.textContent);
      if (data.message) {
        showToast(data.message, data.type || 'info', 6000);
      }
    } catch (e) {
      // ignore
    }
  }

  // ── Auth Token Helpers ─────────────────────────────────────────────
  window.setAuthToken = function (token) {
    if (token) {
      localStorage.setItem('studyrescue-token', token);
      localStorage.setItem('token', token);
    }
  };

  window.getAuthToken = function () {
    return localStorage.getItem('studyrescue-token') || localStorage.getItem('token') || '';
  };

  window.clearAuthToken = function () {
    localStorage.removeItem('studyrescue-token');
    localStorage.removeItem('token');
  };

  // ── Global AJAX error handler & Bearer Token Interceptor (fetch) ───
  const originalFetch = window.fetch;
  window.fetch = function (input, init = {}) {
    init = Object.assign({}, init);
    const headers = init.headers ? new Headers(init.headers) : new Headers();
    const token = window.getAuthToken();
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    init.headers = headers;
    if (!init.credentials) {
      init.credentials = 'include';
    }

    return originalFetch(input, init)
      .then(function (res) {
        // Backup token extraction if server returns token header or JSON
        const authHeader = res.headers.get('Authorization') || res.headers.get('X-Session-Token');
        if (authHeader && authHeader.startsWith('Bearer ')) {
          window.setAuthToken(authHeader.slice(7));
        }
        return res;
      })
      .catch(function (err) {
        showToast('Network error: unable to reach the server. Please check your connection.', 'error', 8000);
        throw err;
      });
  };

})();