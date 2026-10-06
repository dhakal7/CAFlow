/**
 * CAFlow - Vanilla JavaScript Client Utilities
 * Modern, robust, zero-dependency client helper.
 */

(function (window, document) {
  'use strict';

  const CAFlow = {
    // -------------------------------------------------------------
    // Initialization
    // -------------------------------------------------------------
    init() {
      this.initMobileSidebar();
      this.initModals();
      this.initDrawers();
      this.initDropdowns();
      this.initKeyboardShortcuts();
      this.initAutoFormLoading();
      this.initToastsContainer();
      this.initSortableTables();
    },

    // -------------------------------------------------------------
    // 1. Mobile Sidebar & Drawer
    // -------------------------------------------------------------
    initMobileSidebar() {
      const toggleBtn = document.getElementById('cf-sidebar-toggle');
      const sidebar = document.getElementById('cf-sidebar');
      const overlay = document.getElementById('cf-sidebar-overlay');
      const closeBtn = document.getElementById('cf-sidebar-close');

      const openSidebar = () => {
        if (sidebar) sidebar.classList.add('is-open');
        if (overlay) overlay.classList.add('is-open');
        document.body.style.overflow = 'hidden';
      };

      const closeSidebar = () => {
        if (sidebar) sidebar.classList.remove('is-open');
        if (overlay) overlay.classList.remove('is-open');
        document.body.style.overflow = '';
      };

      if (toggleBtn) {
        toggleBtn.addEventListener('click', (e) => {
          e.preventDefault();
          openSidebar();
        });
      }

      if (overlay) {
        overlay.addEventListener('click', closeSidebar);
      }

      if (closeBtn) {
        closeBtn.addEventListener('click', closeSidebar);
      }

      // Close on escape
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && sidebar && sidebar.classList.contains('is-open')) {
          closeSidebar();
        }
      });
    },

    // -------------------------------------------------------------
    // 2. Modal Controller
    // -------------------------------------------------------------
    initModals() {
      // Data attribute triggers: data-cf-modal-target="#modalId" or data-cf-modal-trigger="modalId"
      document.addEventListener('click', (e) => {
        const trigger = e.target.closest('[data-cf-modal-target], [data-cf-modal-trigger]');
        if (trigger) {
          e.preventDefault();
          let targetSelector = trigger.getAttribute('data-cf-modal-target') || trigger.getAttribute('data-cf-modal-trigger');
          if (targetSelector && !targetSelector.startsWith('#') && !targetSelector.startsWith('.')) {
            targetSelector = '#' + targetSelector;
          }
          this.openModal(targetSelector);
        }

        // Close triggers: data-cf-modal-close
        const closeBtn = e.target.closest('[data-cf-modal-close]');
        if (closeBtn) {
          e.preventDefault();
          const modalBackdrop = closeBtn.closest('.cf-modal-backdrop');
          if (modalBackdrop) {
            this.closeModal(modalBackdrop);
          }
        }
      });

      // Close on backdrop click
      document.addEventListener('click', (e) => {
        if (e.target.classList.contains('cf-modal-backdrop')) {
          this.closeModal(e.target);
        }
      });

      // Close on ESC
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          const openModal = document.querySelector('.cf-modal-backdrop.is-open, .cf-modal-backdrop.active');
          if (openModal) {
            this.closeModal(openModal);
          }
        }
      });
    },

    openModal(modalElementOrSelector) {
      const modal = typeof modalElementOrSelector === 'string'
        ? document.querySelector(modalElementOrSelector)
        : modalElementOrSelector;

      if (!modal) return;
      modal.classList.add('is-open');
      modal.classList.add('active');
      document.body.style.overflow = 'hidden';

      // Autofocus first input if any
      const input = modal.querySelector('input:not([type=hidden]), textarea, select');
      if (input) {
        setTimeout(() => input.focus(), 100);
      }
    },

    closeModal(modalElementOrSelector) {
      const modal = typeof modalElementOrSelector === 'string'
        ? document.querySelector(modalElementOrSelector)
        : modalElementOrSelector;

      if (!modal) return;
      modal.classList.remove('is-open');
      modal.classList.remove('active');
      if (!document.querySelector('.cf-modal-backdrop.is-open') && !document.querySelector('.cf-drawer-backdrop.is-open')) {
        document.body.style.overflow = '';
      }
    },

    // -------------------------------------------------------------
    // 2.1. Drawer / Slide-Over Controller
    // -------------------------------------------------------------
    initDrawers() {
      // Data attribute triggers: data-cf-drawer-target="#drawerId"
      document.addEventListener('click', (e) => {
        const trigger = e.target.closest('[data-cf-drawer-target]');
        if (trigger) {
          e.preventDefault();
          const targetSelector = trigger.getAttribute('data-cf-drawer-target');
          this.openDrawer(targetSelector);
        }

        // Close triggers: data-cf-drawer-close
        const closeBtn = e.target.closest('[data-cf-drawer-close]');
        if (closeBtn) {
          e.preventDefault();
          const drawerBackdrop = closeBtn.closest('.cf-drawer-backdrop');
          if (drawerBackdrop) {
            this.closeDrawer(drawerBackdrop);
          }
        }
      });

      // Close on backdrop click (outside drawer panel)
      document.addEventListener('click', (e) => {
        if (e.target.classList.contains('cf-drawer-backdrop')) {
          this.closeDrawer(e.target);
        }
      });

      // Close on ESC
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          const openDrawer = document.querySelector('.cf-drawer-backdrop.is-open');
          if (openDrawer) {
            this.closeDrawer(openDrawer);
          }
        }
      });
    },

    openDrawer(drawerElementOrSelector) {
      const drawer = typeof drawerElementOrSelector === 'string'
        ? document.querySelector(drawerElementOrSelector)
        : drawerElementOrSelector;

      if (!drawer) return;
      drawer.classList.add('is-open');
      document.body.style.overflow = 'hidden';

      const input = drawer.querySelector('input:not([type=hidden]), textarea, select');
      if (input) {
        setTimeout(() => input.focus(), 150);
      }
    },

    closeDrawer(drawerElementOrSelector) {
      const drawer = typeof drawerElementOrSelector === 'string'
        ? document.querySelector(drawerElementOrSelector)
        : drawerElementOrSelector;

      if (!drawer) return;
      drawer.classList.remove('is-open');
      if (!document.querySelector('.cf-modal-backdrop.is-open') && !document.querySelector('.cf-drawer-backdrop.is-open')) {
        document.body.style.overflow = '';
      }
    },

    // -------------------------------------------------------------
    // 3. Confirmation Dialog Helper
    // -------------------------------------------------------------
    confirm({
      title = 'Confirm Action',
      message = 'Are you sure you want to proceed?',
      confirmText = 'Confirm',
      cancelText = 'Cancel',
      variant = 'primary', // 'primary', 'danger', 'warning'
      onConfirm = null,
      onCancel = null,
    }) {
      let confirmModal = document.getElementById('cf-global-confirm-modal');
      if (!confirmModal) {
        confirmModal = document.createElement('div');
        confirmModal.id = 'cf-global-confirm-modal';
        confirmModal.className = 'cf-modal-backdrop';
        confirmModal.innerHTML = `
          <div class="cf-modal-dialog" style="max-width: 440px;">
            <div class="cf-modal-header">
              <h3 class="cf-modal-title" id="cf-confirm-title"></h3>
              <button type="button" class="cf-modal-close-btn" data-cf-modal-close>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>
            <div class="cf-modal-body">
              <p id="cf-confirm-message" style="margin: 0; color: var(--cf-text-secondary);"></p>
            </div>
            <div class="cf-modal-footer">
              <button type="button" class="cf-btn cf-btn-outline" id="cf-confirm-cancel-btn"></button>
              <button type="button" class="cf-btn" id="cf-confirm-ok-btn"></button>
            </div>
          </div>
        `;
        document.body.appendChild(confirmModal);
      }

      document.getElementById('cf-confirm-title').textContent = title;
      document.getElementById('cf-confirm-message').textContent = message;

      const cancelBtn = document.getElementById('cf-confirm-cancel-btn');
      cancelBtn.textContent = cancelText;

      const okBtn = document.getElementById('cf-confirm-ok-btn');
      okBtn.textContent = confirmText;
      okBtn.className = `cf-btn cf-btn-${variant}`;

      const handleOk = () => {
        this.closeModal(confirmModal);
        cleanup();
        if (typeof onConfirm === 'function') onConfirm();
      };

      const handleCancel = () => {
        this.closeModal(confirmModal);
        cleanup();
        if (typeof onCancel === 'function') onCancel();
      };

      const cleanup = () => {
        okBtn.removeEventListener('click', handleOk);
        cancelBtn.removeEventListener('click', handleCancel);
      };

      okBtn.addEventListener('click', handleOk);
      cancelBtn.addEventListener('click', handleCancel);

      this.openModal(confirmModal);
    },

    // -------------------------------------------------------------
    // 4. Toast Notification Dispatcher
    // -------------------------------------------------------------
    initToastsContainer() {
      if (!document.getElementById('cf-toast-container')) {
        const container = document.createElement('div');
        container.id = 'cf-toast-container';
        container.className = 'cf-toast-container';
        document.body.appendChild(container);
      }
    },

    toast(message, type = 'info', durationMs = 4000) {
      this.initToastsContainer();
      const container = document.getElementById('cf-toast-container');
      const toast = document.createElement('div');
      toast.className = `cf-toast cf-toast-${type}`;

      const icons = {
        success: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--cf-success)" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`,
        warning: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--cf-warning)" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
        danger: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--cf-danger)" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
        info: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--cf-info)" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
      };

      toast.innerHTML = `
        <span style="display: flex; align-items: center;">${icons[type] || icons.info}</span>
        <span style="flex: 1; font-size: 0.875rem; font-weight: 500;">${message}</span>
        <button type="button" style="background:none; border:none; color:var(--cf-text-muted); cursor:pointer; padding:2px;" onclick="this.parentElement.remove()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      `;

      container.appendChild(toast);

      if (durationMs > 0) {
        setTimeout(() => {
          toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
          toast.style.opacity = '0';
          toast.style.transform = 'translateY(10px)';
          setTimeout(() => toast.remove(), 300);
        }, durationMs);
      }
    },

    // -------------------------------------------------------------
    // 5. Dropdown Menus
    // -------------------------------------------------------------
    initDropdowns() {
      document.addEventListener('click', (e) => {
        const toggle = e.target.closest('[data-cf-dropdown-toggle]');
        const openMenus = document.querySelectorAll('.cf-dropdown-menu.show');

        if (toggle) {
          e.preventDefault();
          const parent = toggle.closest('.cf-dropdown') || toggle.parentElement;
          const menu = parent.querySelector('.cf-dropdown-menu');

          if (menu) {
            const isShown = menu.classList.contains('show');
            openMenus.forEach((m) => m.classList.remove('show'));
            if (!isShown) menu.classList.add('show');
          }
        } else if (!e.target.closest('.cf-dropdown-menu')) {
          openMenus.forEach((m) => m.classList.remove('show'));
        }
      });
    },

    // -------------------------------------------------------------
    // 6. Keyboard Shortcuts (Cmd+K / Ctrl+K)
    // -------------------------------------------------------------
    initKeyboardShortcuts() {
      document.addEventListener('keydown', (e) => {
        // Cmd+K or Ctrl+K or '/' to focus search
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
          e.preventDefault();
          const searchInput = document.querySelector('.cf-global-search-input');
          if (searchInput) searchInput.focus();
        }
      });
    },

    // -------------------------------------------------------------
    // 7. Auto Form Loading States
    // -------------------------------------------------------------
    initAutoFormLoading() {
      document.addEventListener('submit', (e) => {
        const form = e.target;
        if (form.hasAttribute('data-cf-no-loader')) return;

        const submitBtn = form.querySelector('button[type="submit"]:not(.cf-no-spinner)');
        if (submitBtn) {
          const originalText = submitBtn.innerHTML;
          submitBtn.disabled = true;
          submitBtn.innerHTML = `<span class="cf-spinner"></span> <span>Processing...</span>`;
          
          // Fallback timeout in case of aborted submission
          setTimeout(() => {
            if (submitBtn.disabled) {
              submitBtn.disabled = false;
              submitBtn.innerHTML = originalText;
            }
          }, 8000);
        }
      });
    },

    // -------------------------------------------------------------
    // 8. Reusable Table Search Filter
    // -------------------------------------------------------------
    filterTable(tableId, query) {
      const table = document.getElementById(tableId);
      if (!table) return;

      const q = (query || '').toLowerCase().trim();
      const rows = table.querySelectorAll('tbody tr');

      rows.forEach((row) => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(q) ? '' : 'none';
      });
    },

    // -------------------------------------------------------------
    // 9. Interactive Table Column Sorting
    // -------------------------------------------------------------
    initSortableTables() {
      document.addEventListener('click', (e) => {
        const th = e.target.closest('th.is-sortable');
        if (!th) return;

        const table = th.closest('table');
        if (!table) return;

        const tbody = table.querySelector('tbody');
        if (!tbody) return;

        const colIndex = Array.from(th.parentNode.children).indexOf(th);
        const isAsc = !th.classList.contains('is-sorted-asc');

        table.querySelectorAll('th.is-sortable').forEach((h) => {
          h.classList.remove('is-sorted', 'is-sorted-asc', 'is-sorted-desc');
        });

        th.classList.add('is-sorted', isAsc ? 'is-sorted-asc' : 'is-sorted-desc');

        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a, b) => {
          const aText = (a.children[colIndex]?.innerText || '').trim();
          const bText = (b.children[colIndex]?.innerText || '').trim();

          const aNum = parseFloat(aText.replace(/[^0-9.-]/g, ''));
          const bNum = parseFloat(bText.replace(/[^0-9.-]/g, ''));

          if (!isNaN(aNum) && !isNaN(bNum)) {
            return isAsc ? aNum - bNum : bNum - aNum;
          }
          return isAsc ? aText.localeCompare(bText) : bText.localeCompare(aText);
        });

        rows.forEach((r) => tbody.appendChild(r));
      });
    },
  };

  // Expose to global window
  window.CAFlow = CAFlow;

  // Auto init on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => CAFlow.init());
  } else {
    CAFlow.init();
  }
})(window, document);
