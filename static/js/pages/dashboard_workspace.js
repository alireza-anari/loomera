let dashboardWorkspaceBound = false;
let workspaceScrollRaf = null;
let workspaceResizeRaf = null;

const DESKTOP_QUERY = "(min-width: 1024px)";
const ACTIVE_TAB_CLASSES = [
  "border-loomera-primary/20",
  "bg-loomera-primarySoft",
  "text-loomera-primaryText",
  "shadow-sm",
];
const INACTIVE_TAB_CLASSES = [
  "border-loomera-borderSoft",
  "bg-white",
  "text-loomera-textSecondary",
];
const ACTIVE_BADGE_CLASSES = ["bg-white/80", "text-loomera-primaryText"];
const INACTIVE_BADGE_CLASSES = ["bg-loomera-bgSubtle", "text-loomera-textMuted"];

const getDesktopMedia = () => window.matchMedia(DESKTOP_QUERY);
const isDesktop = () => getDesktopMedia().matches;

const toggleClasses = (element, classes, enabled) => {
  if (!element) return;
  classes.forEach((className) => element.classList.toggle(className, enabled));
};

const getTopbar = () => document.querySelector("[data-dashboard-topbar]");

const readTopbarBottom = () => {
  const topbar = getTopbar();
  if (!topbar) return 0;

  const rect = topbar.getBoundingClientRect();
  const fallbackHeight = topbar.offsetHeight || 72;
  return Math.ceil(rect.bottom || fallbackHeight);
};

const getTargetElement = (tab, root) => {
  const targetSelector =
    tab.dataset.target || tab.dataset.dashboardWorkspaceTarget || tab.getAttribute("href");

  if (!targetSelector) return null;

  if (targetSelector.startsWith("#")) {
    return root.querySelector(targetSelector) || document.querySelector(targetSelector);
  }

  return (
    root.querySelector(`#${CSS.escape(targetSelector)}`) ||
    document.getElementById(targetSelector)
  );
};

const collectPanels = (root, tabs) => {
  const explicitPanels = Array.from(
    root.querySelectorAll("[data-dashboard-workspace-panel]")
  );

  if (explicitPanels.length) return explicitPanels;

  return tabs
    .map((tab) => getTargetElement(tab, root))
    .filter((panel, index, panels) => panel && panels.indexOf(panel) === index);
};

const getPanelId = (panel) => (panel ? panel.id || panel.dataset.dashboardWorkspacePanel : "");

const tabMatchesPanel = (tab, panel, root) => getTargetElement(tab, root) === panel;

const setTabActiveState = (tabs, activeTab, shouldScrollIntoView = true) => {
  tabs.forEach((tab) => {
    const active = tab === activeTab;
    const badge = tab.querySelector("[data-dashboard-workspace-tab-badge]");

    tab.classList.toggle("border", true);
    toggleClasses(tab, ACTIVE_TAB_CLASSES, active);
    toggleClasses(tab, INACTIVE_TAB_CLASSES, !active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
    tab.setAttribute("aria-pressed", active ? "true" : "false");

    toggleClasses(badge, ACTIVE_BADGE_CLASSES, active);
    toggleClasses(badge, INACTIVE_BADGE_CLASSES, !active);
  });

  if (activeTab && shouldScrollIntoView) {
    activeTab.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }
};

const getShellState = (shell, nav) => {
  if (!shell.__loomeraWorkspaceState) {
    shell.__loomeraWorkspaceState = {
      shellPageTop: 0,
      shellLeft: 0,
      shellWidth: 0,
      clickedNavigationAt: 0,
      resizeObserver: null,
    };
  }

  if (!shell.__loomeraWorkspaceState.resizeObserver && "ResizeObserver" in window) {
    shell.__loomeraWorkspaceState.resizeObserver = new ResizeObserver(() => {
      syncWorkspaceTabs(shell, nav);
    });
    shell.__loomeraWorkspaceState.resizeObserver.observe(shell);
    shell.__loomeraWorkspaceState.resizeObserver.observe(nav);
  }

  return shell.__loomeraWorkspaceState;
};

const measureShell = (shell, nav) => {
  const state = getShellState(shell, nav);
  const rect = shell.getBoundingClientRect();

  state.shellPageTop = window.scrollY + rect.top;
  state.shellLeft = rect.left;
  state.shellWidth = rect.width;

  const navHeight = Math.ceil(nav.offsetHeight || 56);
  shell.style.minHeight = `${navHeight}px`;

  return state;
};

const unpinTabs = (nav) => {
  nav.removeAttribute("data-dashboard-workspace-tabs-pinned");
  nav.style.position = "";
  nav.style.top = "";
  nav.style.left = "";
  nav.style.width = "";
  nav.style.zIndex = "";
};

const pinTabs = (nav, top, left, width) => {
  nav.setAttribute("data-dashboard-workspace-tabs-pinned", "true");
  nav.style.position = "fixed";
  nav.style.top = `${top}px`;
  nav.style.left = `${Math.round(left)}px`;
  nav.style.width = `${Math.round(width)}px`;
  nav.style.zIndex = "40";
};

function syncWorkspaceTabs(shell, nav) {
  if (!shell || !nav || !document.body.contains(shell)) return;

  const topbarBottom = readTopbarBottom();
  const gap = Number.parseInt(shell.dataset.dashboardWorkspaceTabsGap || "0", 10) || 0;
  const pinnedTop = Math.max(topbarBottom + gap, 0);
  const isPinned = nav.hasAttribute("data-dashboard-workspace-tabs-pinned");
  const state = isPinned ? getShellState(shell, nav) : measureShell(shell, nav);

  if (isPinned) {
    const rect = shell.getBoundingClientRect();
    state.shellLeft = rect.left;
    state.shellWidth = rect.width;
  }

  const alwaysFixed = shell.dataset.dashboardWorkspaceTabsMode === "always";
  const shouldPin = alwaysFixed || window.scrollY + pinnedTop >= state.shellPageTop;
  const offset = pinnedTop + Math.ceil(nav.offsetHeight || 56) + 12;

  document.documentElement.style.setProperty("--lm-dashboard-workspace-offset", `${offset}px`);

  if (shouldPin) {
    pinTabs(nav, pinnedTop, state.shellLeft, state.shellWidth);
  } else {
    unpinTabs(nav);
  }
}

const getScrollOffset = (shell, nav) => {
  syncWorkspaceTabs(shell, nav);
  const value = Number.parseInt(
    getComputedStyle(document.documentElement).getPropertyValue("--lm-dashboard-workspace-offset"),
    10
  );

  return Number.isFinite(value) ? value : readTopbarBottom() + Math.ceil(nav.offsetHeight || 56) + 12;
};

const closeOtherPanels = (panels, activePanel) => {
  if (isDesktop() || !activePanel) return;

  panels.forEach((panel) => {
    if (panel !== activePanel && panel.tagName === "DETAILS") {
      panel.open = false;
    }
  });
};

const enforcePanelState = (panels, preferredPanel = null) => {
  if (!panels.length) return;

  if (isDesktop()) {
    panels.forEach((panel) => {
      if (panel.tagName === "DETAILS") panel.open = true;
    });
    return;
  }

  const explicitPanel = panels.find((panel) => panel.dataset.dashboardWorkspaceOpenMobile === "true");
  const activePanel =
    preferredPanel || panels.find((panel) => panel.tagName !== "DETAILS" || panel.open) || explicitPanel || panels[0];

  if (activePanel?.tagName === "DETAILS") activePanel.open = true;
  closeOtherPanels(panels, activePanel);
};

const updateActiveTabFromScroll = (root, shell, nav, tabs, panels) => {
  const state = getShellState(shell, nav);
  if (Date.now() - state.clickedNavigationAt < 650) return;

  const offset = getScrollOffset(shell, nav);
  let activePanel = null;
  let activeDistance = Number.POSITIVE_INFINITY;

  panels.forEach((panel) => {
    const rect = panel.getBoundingClientRect();
    const distance = Math.abs(rect.top - offset);
    const visibleEnough = rect.bottom > offset + 80 && rect.top < window.innerHeight * 0.68;

    if (visibleEnough && distance < activeDistance) {
      activeDistance = distance;
      activePanel = panel;
    }
  });

  if (!activePanel) return;
  const activeTab = tabs.find((tab) => tabMatchesPanel(tab, activePanel, root));
  if (activeTab) setTabActiveState(tabs, activeTab, false);
};

const bindWorkspaceGroup = (shell) => {
  const root = shell.closest("[data-dashboard-workspace-root]") || shell.closest("[data-dashboard-workspace-frame]") || document;
  const nav = shell.querySelector("[data-dashboard-workspace-tabs]");
  const tabs = Array.from(shell.querySelectorAll("[data-dashboard-workspace-tab]"));
  const panels = collectPanels(root, tabs);

  if (!nav || !tabs.length || !panels.length) return;

  const state = getShellState(shell, nav);

  if (nav.dataset.dashboardWorkspaceReady !== "true") {
    nav.dataset.dashboardWorkspaceReady = "true";

    tabs.forEach((tab) => {
      tab.setAttribute("type", tab.getAttribute("type") || "button");
      tab.addEventListener("click", (event) => {
        event.preventDefault();

        const target = getTargetElement(tab, root);
        if (!target) return;

        if (target.tagName === "DETAILS") {
          target.open = true;
          closeOtherPanels(panels, target);
        }

        state.clickedNavigationAt = Date.now();
        const top = target.getBoundingClientRect().top + window.scrollY - getScrollOffset(shell, nav);
        window.scrollTo({ top, behavior: "smooth" });
        setTabActiveState(tabs, tab);
      });
    });

    panels.forEach((panel) => {
      if (panel.tagName !== "DETAILS") return;

      panel.addEventListener("toggle", () => {
        if (!panel.open) return;

        closeOtherPanels(panels, panel);
        const relatedTab = tabs.find((tab) => tabMatchesPanel(tab, panel, root));
        if (relatedTab) setTabActiveState(tabs, relatedTab, false);
        window.setTimeout(() => syncWorkspaceTabs(shell, nav), 40);
      });
    });
  }

  enforcePanelState(panels);
  measureShell(shell, nav);
  syncWorkspaceTabs(shell, nav);

  const selectedTab = tabs.find((tab) => tab.getAttribute("aria-selected") === "true") || tabs[0];
  if (selectedTab) setTabActiveState(tabs, selectedTab, false);
  updateActiveTabFromScroll(root, shell, nav, tabs, panels);
};

const refreshWorkspace = (root = document) => {
  const shells = Array.from(root.querySelectorAll("[data-dashboard-workspace-tabs-shell]"));
  shells.forEach(bindWorkspaceGroup);
};

const refreshAll = () => {
  refreshWorkspace(document);
};

const onScroll = () => {
  if (workspaceScrollRaf) return;

  workspaceScrollRaf = window.requestAnimationFrame(() => {
    workspaceScrollRaf = null;

    const shells = Array.from(document.querySelectorAll("[data-dashboard-workspace-tabs-shell]"));
    shells.forEach((shell) => {
      const root = shell.closest("[data-dashboard-workspace-root]") || shell.closest("[data-dashboard-workspace-frame]") || document;
      const nav = shell.querySelector("[data-dashboard-workspace-tabs]");
      const tabs = Array.from(shell.querySelectorAll("[data-dashboard-workspace-tab]"));
      const panels = collectPanels(root, tabs);
      if (!nav || !tabs.length || !panels.length) return;

      syncWorkspaceTabs(shell, nav);
      updateActiveTabFromScroll(root, shell, nav, tabs, panels);
    });
  });
};

const onResize = () => {
  if (workspaceResizeRaf) return;

  workspaceResizeRaf = window.requestAnimationFrame(() => {
    workspaceResizeRaf = null;

    const shells = Array.from(document.querySelectorAll("[data-dashboard-workspace-tabs-shell]"));
    shells.forEach((shell) => {
      const nav = shell.querySelector("[data-dashboard-workspace-tabs]");
      const root = shell.closest("[data-dashboard-workspace-root]") || shell.closest("[data-dashboard-workspace-frame]") || document;
      const tabs = Array.from(shell.querySelectorAll("[data-dashboard-workspace-tab]"));
      const panels = collectPanels(root, tabs);

      if (nav) {
        unpinTabs(nav);
        measureShell(shell, nav);
        syncWorkspaceTabs(shell, nav);
      }

      enforcePanelState(panels);
    });
  });
};

export default function initDashboardWorkspace() {
  refreshAll();

  if (dashboardWorkspaceBound) return;
  dashboardWorkspaceBound = true;

  window.LoomeraDashboardWorkspace = {
    refresh: refreshWorkspace,
    refreshAll,
  };

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onResize, { passive: true });
  window.addEventListener("orientationchange", () => window.setTimeout(onResize, 160));

  document.addEventListener("loomera:workspace-refresh", (event) => {
    refreshWorkspace(event.target instanceof Element ? event.target : document);
  });

  document.addEventListener("htmx:afterSwap", (event) => {
    refreshWorkspace(event.target instanceof Element ? event.target : document);
  });

  if ("MutationObserver" in window) {
    const observer = new MutationObserver((mutations) => {
      const shouldRefresh = mutations.some((mutation) =>
        Array.from(mutation.addedNodes).some(
          (node) =>
            node instanceof Element &&
            (node.matches?.("[data-dashboard-workspace-tabs-shell]") ||
              node.querySelector?.("[data-dashboard-workspace-tabs-shell]"))
        )
      );

      if (shouldRefresh) window.setTimeout(refreshAll, 40);
    });

    observer.observe(document.body, { childList: true, subtree: true });
  }

  window.setTimeout(refreshAll, 80);
  window.setTimeout(refreshAll, 280);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initDashboardWorkspace, { once: true });
} else {
  initDashboardWorkspace();
}


// Finance Hub UX stage 2: tab interaction shell.
// Existing routes and financial calculations remain unchanged.
document.addEventListener("DOMContentLoaded", () => {
  const buttons = document.querySelectorAll("[data-finance-tab]");
  if (!buttons.length) return;

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      buttons.forEach((item) => {
        item.classList.remove("bg-loomera-primary", "text-white");
        item.classList.add("bg-loomera-bgSubtle", "text-loomera-textSecondary");
      });
      button.classList.add("bg-loomera-primary", "text-white");
      button.classList.remove("bg-loomera-bgSubtle", "text-loomera-textSecondary");
    });
  });
});
