import { STORAGE_KEYS, readStorageValue, writeStorageValue } from "../storage_keys.js";

let dashboardLayoutBound = false;

function setupDashboardLayout() {
  if (dashboardLayoutBound) return;
  dashboardLayoutBound = true;

  const SIDEBAR_EXPANDED_WIDTH = "lg:w-[22rem]";
  const SIDEBAR_COLLAPSED_WIDTH = "lg:w-24";

  const CONTENT_EXPANDED_OFFSET = "lg:pr-[22rem]";
  const CONTENT_COLLAPSED_OFFSET = "lg:pr-24";

  const TOPBAR_EXPANDED_OFFSET = "lg:right-[22rem]";
  const TOPBAR_COLLAPSED_OFFSET = "lg:right-24";

  const readCollapsedPreference = () => {
    const stored = readStorageValue(STORAGE_KEYS.dashboardSidebarCollapsed, {
      validate: (value) => value === "1" || value === "0",
    });

    return stored === "1";
  };

  const sidebar = document.querySelector("[data-dashboard-sidebar]");
  const overlay = document.querySelector("[data-dashboard-overlay]");
  const content = document.querySelector("[data-dashboard-content]");
  const topbar = document.querySelector("[data-dashboard-topbar]");

  const openButton = document.querySelector("[data-sidebar-open]");
  const closeButton = document.querySelector("[data-sidebar-close]");
  const collapseButton = document.querySelector("[data-sidebar-collapse]");
  const collapseIcon = document.querySelector("[data-sidebar-collapse-icon]");

  const labels = document.querySelectorAll("[data-sidebar-label]");
  const sidebarItems = document.querySelectorAll(".lm-dashboard-sidebar-item");
  const collapsedOnlyElements = document.querySelectorAll("[data-sidebar-collapsed-only]");
  const expandedOnlyElements = document.querySelectorAll("[data-sidebar-expanded-only]");

  const notificationRoot = document.querySelector("[data-notification-root]");
  const notificationToggle = document.querySelector("[data-notification-toggle]");
  const notificationPanel = document.querySelector("[data-notification-panel]");

  const mobileCreateRoot = document.querySelector("[data-mobile-create-root]");
  const mobileCreateToggle = document.querySelector("[data-mobile-create-toggle]");
  const mobileCreatePanel = document.querySelector("[data-mobile-create-panel]");

  const mobileManagementRoot = document.querySelector("[data-mobile-management-root]");
  const mobileManagementToggle = document.querySelector("[data-mobile-management-toggle]");
  const mobileManagementPanel = document.querySelector("[data-mobile-management-panel]");
  const mobileManagementClose = document.querySelector("[data-mobile-management-close]");

  let comingSoonToastTimer = null;

  const showComingSoonToast = (message = "به‌زودی فعال می‌شود") => {
    document.querySelector("[data-dashboard-coming-soon-toast]")?.remove();

    const toast = document.createElement("div");
    toast.className = "lm-dashboard-coming-soon-toast";
    toast.dataset.dashboardComingSoonToast = "true";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    toast.textContent = message;
    document.body.appendChild(toast);

    window.requestAnimationFrame(() => {
      toast.classList.add("is-visible");
    });

    if (comingSoonToastTimer) window.clearTimeout(comingSoonToastTimer);
    comingSoonToastTimer = window.setTimeout(() => {
      toast.classList.remove("is-visible");
      window.setTimeout(() => toast.remove(), 220);
    }, 2400);
  };

  if (!sidebar || !overlay || !content) return;

  const isDesktop = () => window.matchMedia("(min-width: 1024px)").matches;

  const setExpanded = (control, expanded) => {
    if (!control) return;
    control.setAttribute("aria-expanded", expanded ? "true" : "false");
  };

  const setPressed = (control, pressed) => {
    if (!control) return;
    control.setAttribute("aria-pressed", pressed ? "true" : "false");
  };

  const syncTopbarOffset = (collapsed) => {
    if (!topbar) return;

    topbar.classList.toggle(TOPBAR_EXPANDED_OFFSET, !collapsed);
    topbar.classList.toggle(TOPBAR_COLLAPSED_OFFSET, collapsed);
  };

  const resetTopbarForMobile = () => {
    if (!topbar) return;

    topbar.classList.remove(TOPBAR_COLLAPSED_OFFSET);
    topbar.classList.add(TOPBAR_EXPANDED_OFFSET);
  };

  const setSidebarVisualState = (collapsed) => {
    labels.forEach((label) => label.classList.toggle("hidden", collapsed));
    collapsedOnlyElements.forEach((element) => element.classList.toggle("hidden", !collapsed));
    expandedOnlyElements.forEach((element) => element.classList.toggle("hidden", collapsed));

    sidebar.dataset.sidebarState = collapsed ? "collapsed" : "expanded";
    sidebarItems.forEach((item) => {
      item.dataset.sidebarCollapsed = collapsed ? "true" : "false";
    });

    collapseIcon?.classList.toggle("fa-angles-right", !collapsed);
    collapseIcon?.classList.toggle("fa-angles-left", collapsed);

    setPressed(collapseButton, collapsed);
  };

  const setCollapsedState = (collapsed, persist = true) => {
    if (!isDesktop()) {
      sidebar.classList.remove(SIDEBAR_COLLAPSED_WIDTH);
      sidebar.classList.add(SIDEBAR_EXPANDED_WIDTH);

      content.classList.remove(CONTENT_COLLAPSED_OFFSET);
      content.classList.add(CONTENT_EXPANDED_OFFSET);

      resetTopbarForMobile();

      labels.forEach((label) => label.classList.remove("hidden"));
      collapsedOnlyElements.forEach((element) => element.classList.add("hidden"));
      expandedOnlyElements.forEach((element) => element.classList.remove("hidden"));
      sidebar.dataset.sidebarState = "expanded";
      sidebarItems.forEach((item) => {
        item.dataset.sidebarCollapsed = "false";
      });

      setPressed(collapseButton, false);
      collapseIcon?.classList.remove("fa-angles-left");
      collapseIcon?.classList.add("fa-angles-right");

      return;
    }

    sidebar.classList.toggle(SIDEBAR_EXPANDED_WIDTH, !collapsed);
    sidebar.classList.toggle(SIDEBAR_COLLAPSED_WIDTH, collapsed);

    content.classList.toggle(CONTENT_EXPANDED_OFFSET, !collapsed);
    content.classList.toggle(CONTENT_COLLAPSED_OFFSET, collapsed);

    syncTopbarOffset(collapsed);
    setSidebarVisualState(collapsed);

    if (persist) {
      writeStorageValue(STORAGE_KEYS.dashboardSidebarCollapsed, collapsed ? "1" : "0");
    }
  };

  const closeNotificationPanel = () => {
    if (!notificationPanel) return;
    notificationPanel.classList.add("hidden");
    setExpanded(notificationToggle, false);
  };

  const closeMobileCreatePanel = () => {
    if (!mobileCreatePanel) return;
    mobileCreatePanel.classList.add("hidden");
    setExpanded(mobileCreateToggle, false);
  };

  const closeMobileManagementPanel = () => {
    if (!mobileManagementPanel) return;
    mobileManagementPanel.classList.add("hidden");
    setExpanded(mobileManagementToggle, false);
  };

  function closeFloatingPanels() {
    closeNotificationPanel();
    closeMobileCreatePanel();
    closeMobileManagementPanel();
  }

  const openMobileSidebar = () => {
    if (isDesktop()) return;

    closeFloatingPanels();

    sidebar.classList.remove("translate-x-full");
    sidebar.classList.add("translate-x-0");

    overlay.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");

    setExpanded(openButton, true);
  };

  const closeMobileSidebar = () => {
    if (isDesktop()) {
      overlay.classList.add("hidden");
      document.body.classList.remove("overflow-hidden");
      setExpanded(openButton, false);
      return;
    }

    sidebar.classList.remove("translate-x-0");
    sidebar.classList.add("translate-x-full");

    overlay.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");

    setExpanded(openButton, false);
  };

  const collapseDesktopSidebar = () => {
    if (!isDesktop()) return;

    const isCollapsed = sidebar.classList.contains(SIDEBAR_COLLAPSED_WIDTH);
    setCollapsedState(!isCollapsed);
  };

  const setupNotificationTabs = () => {
    if (!notificationPanel) return;

    const tabButtons = Array.from(notificationPanel.querySelectorAll("[data-notification-tab]"));
    const items = Array.from(notificationPanel.querySelectorAll("[data-notification-item]"));
    const emptyState = notificationPanel.querySelector("[data-notification-empty]");

    if (!tabButtons.length) return;

    const activeClasses = ["bg-loomera-primary", "text-white", "border-loomera-primary"];
    const inactiveClasses = ["bg-white", "text-loomera-textSecondary", "border-loomera-borderSoft"];

    const activateTab = (key) => {
      let visibleItems = 0;

      tabButtons.forEach((button) => {
        const active = button.dataset.notificationTab === key;

        button.classList.toggle(activeClasses[0], active);
        button.classList.toggle(activeClasses[1], active);
        button.classList.toggle(activeClasses[2], active);

        button.classList.toggle(inactiveClasses[0], !active);
        button.classList.toggle(inactiveClasses[1], !active);
        button.classList.toggle(inactiveClasses[2], !active);

        button.setAttribute("aria-selected", active ? "true" : "false");
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });

      items.forEach((item) => {
        const matches = key === "all" || item.dataset.notificationCategory === key;
        item.classList.toggle("hidden", !matches);

        if (matches) visibleItems += 1;
      });

      if (emptyState && items.length) {
        emptyState.classList.toggle("hidden", visibleItems !== 0);

        if (visibleItems === 0) {
          emptyState.textContent = "در این تب اعلان فعالی وجود ندارد.";
        }
      }
    };

    tabButtons.forEach((button) => {
      if (button.dataset.bound === "true") return;

      button.dataset.bound = "true";
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();

        activateTab(button.dataset.notificationTab || "all");
      });
    });

    const initiallyActive = tabButtons.find((button) => button.getAttribute("aria-selected") === "true");
    activateTab(initiallyActive?.dataset.notificationTab || tabButtons[0]?.dataset.notificationTab || "all");
  };


  const setupNotificationReadActions = () => {
    if (!notificationPanel) return;

    const csrfToken = () => {
      const cookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrftoken="));
      return cookie ? decodeURIComponent(cookie.slice("csrftoken=".length)) : "";
    };

    notificationPanel.querySelectorAll("[data-notification-item]").forEach((item) => {
      if (item.dataset.readBound === "true") return;
      item.dataset.readBound = "true";

      item.addEventListener("click", async (event) => {
        if (
          event.defaultPrevented
          || event.button !== 0
          || event.metaKey
          || event.ctrlKey
          || event.shiftKey
          || event.altKey
        ) {
          return;
        }

        const readUrl = item.dataset.notificationReadUrl || "";
        const isUnread = item.dataset.notificationUnread === "true";
        if (!isUnread || !readUrl) return;

        event.preventDefault();
        const destination = item.href;

        try {
          await fetch(readUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: {
              "X-CSRFToken": csrfToken(),
              "X-Requested-With": "XMLHttpRequest",
              "Accept": "application/json",
            },
          });
        } catch (error) {
          console.warn("Unable to mark dashboard notification as read.", error);
        } finally {
          window.location.assign(destination);
        }
      });
    });
  };


  const openNotificationPanel = () => {
    if (!notificationPanel) return;

    closeMobileCreatePanel();
    closeMobileManagementPanel();

    notificationPanel.classList.remove("hidden");
    setExpanded(notificationToggle, true);
    setupNotificationTabs();
    setupNotificationReadActions();
  };

  const openMobileCreatePanel = () => {
    if (!mobileCreatePanel) return;

    closeNotificationPanel();
    closeMobileManagementPanel();

    mobileCreatePanel.classList.remove("hidden");
    setExpanded(mobileCreateToggle, true);
  };

  const openMobileManagementPanel = () => {
    if (!mobileManagementPanel) return;

    closeNotificationPanel();
    closeMobileCreatePanel();

    mobileManagementPanel.classList.remove("hidden");
    setExpanded(mobileManagementToggle, true);
  };

  notificationToggle?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();

    if (!notificationPanel) return;

    if (notificationPanel.classList.contains("hidden")) {
      openNotificationPanel();
    } else {
      closeNotificationPanel();
    }
  });

  mobileCreateToggle?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();

    if (!mobileCreatePanel) return;

    if (mobileCreatePanel.classList.contains("hidden")) {
      openMobileCreatePanel();
    } else {
      closeMobileCreatePanel();
    }
  });

  mobileManagementToggle?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();

    if (!mobileManagementPanel) return;

    if (mobileManagementPanel.classList.contains("hidden")) {
      openMobileManagementPanel();
    } else {
      closeMobileManagementPanel();
    }
  });

  mobileManagementClose?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    closeMobileManagementPanel();
  });

  notificationPanel?.addEventListener("click", (event) => event.stopPropagation());
  mobileCreatePanel?.addEventListener("click", (event) => event.stopPropagation());
  mobileManagementPanel?.addEventListener("click", (event) => event.stopPropagation());

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Node)) return;

    const comingSoonTrigger = target instanceof Element
      ? target.closest("[data-dashboard-coming-soon]")
      : null;

    if (comingSoonTrigger) {
      event.preventDefault();
      event.stopPropagation();
      showComingSoonToast(
        comingSoonTrigger.dataset.dashboardComingSoonMessage || "به‌زودی فعال می‌شود",
      );
      return;
    }

    if (notificationRoot && !notificationRoot.contains(target)) {
      closeNotificationPanel();
    }

    if (mobileCreateRoot && !mobileCreateRoot.contains(target)) {
      closeMobileCreatePanel();
    }

    if (mobileManagementRoot && !mobileManagementRoot.contains(target)) {
      closeMobileManagementPanel();
    }
  });

  openButton?.addEventListener("click", openMobileSidebar);
  closeButton?.addEventListener("click", closeMobileSidebar);
  collapseButton?.addEventListener("click", collapseDesktopSidebar);

  overlay.addEventListener("click", () => {
    closeMobileSidebar();
    closeFloatingPanels();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeMobileSidebar();
      closeFloatingPanels();
    }
  });

  window.addEventListener("resize", () => {
    if (isDesktop()) {
      overlay.classList.add("hidden");
      document.body.classList.remove("overflow-hidden");

      sidebar.classList.remove("translate-x-full");
      sidebar.classList.add("translate-x-0");

      setExpanded(openButton, false);
      setCollapsedState(readCollapsedPreference(), false);
      closeMobileCreatePanel();
      closeMobileManagementPanel();

      return;
    }

    setCollapsedState(false, false);

    if (!sidebar.classList.contains("translate-x-full")) {
      closeMobileSidebar();
    }
  });

  if (isDesktop()) {
    sidebar.classList.remove("translate-x-full");
    sidebar.classList.add("translate-x-0");
  }

  setCollapsedState(readCollapsedPreference(), false);
  setupNotificationTabs();
}

export default function initDashboardLayout() {
  setupDashboardLayout();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", setupDashboardLayout, { once: true });
} else {
  setupDashboardLayout();
}