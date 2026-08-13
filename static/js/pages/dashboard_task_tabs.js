const STORAGE_PREFIX = "loomera:dashboard-task-tab";


function syncStickyTabsOffset() {
  const topbar = document.querySelector("[data-dashboard-topbar]");
  const top = topbar ? Math.ceil(topbar.getBoundingClientRect().height) : 76;
  document.documentElement.style.setProperty("--lm-dashboard-sticky-tabs-top", `${top}px`);
}

function syncStickyTabsState() {
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--lm-dashboard-sticky-tabs-top");
  const top = Number.parseFloat(raw) || 76;
  document.querySelectorAll(".lm-task-tabs-anchor").forEach((anchor) => {
    const stuck = anchor.getBoundingClientRect().top <= top + 1 && window.scrollY > 0;
    anchor.classList.toggle("is-stuck", stuck);
  });
}

function initStickyTabsRuntime() {
  if (document.documentElement.dataset.lmStickyTabsRuntime === "true") return;
  document.documentElement.dataset.lmStickyTabsRuntime = "true";
  const sync = () => {
    syncStickyTabsOffset();
    syncStickyTabsState();
  };
  sync();
  window.addEventListener("resize", sync, { passive: true });
  window.addEventListener("orientationchange", sync, { passive: true });
  window.addEventListener("scroll", syncStickyTabsState, { passive: true });
}

function safeStorageGet(key) {
  try { return window.sessionStorage.getItem(key); } catch (_) { return null; }
}

function safeStorageSet(key, value) {
  try { window.sessionStorage.setItem(key, value); } catch (_) { /* noop */ }
}

function directSummary(panel) {
  if (!(panel instanceof HTMLDetailsElement)) return null;
  return Array.from(panel.children).find((child) => child.tagName === "SUMMARY") || null;
}

function lockDetailsPanel(panel) {
  if (!(panel instanceof HTMLDetailsElement)) return;
  panel.open = true;
  panel.dataset.lmTaskLockedDetail = "true";
  const summary = directSummary(panel);
  if (!summary || summary.dataset.lmTaskLocked === "true") return;
  summary.dataset.lmTaskLocked = "true";
  summary.setAttribute("aria-disabled", "true");
  summary.addEventListener("click", (event) => event.preventDefault());
  panel.addEventListener("toggle", () => {
    if (!panel.hidden && !panel.open) panel.open = true;
  });
}

function panelContainsHashTarget(panel) {
  const hash = window.location.hash;
  if (!hash || hash.length < 2) return false;
  const target = document.getElementById(decodeURIComponent(hash.slice(1)));
  return Boolean(target && panel.contains(target));
}

function initGroup(groupName, panels, anchor, anchorScope = null) {
  if (!panels.length) return;

  panels = [...panels].sort((a, b) => {
    const orderA = Number.parseInt(a.dataset.lmTaskOrder || "999", 10);
    const orderB = Number.parseInt(b.dataset.lmTaskOrder || "999", 10);
    if (orderA !== orderB) return orderA - orderB;
    return 0;
  });

  const pageKey = `${window.location.pathname}:${groupName}`;
  const storageKey = `${STORAGE_PREFIX}:${pageKey}`;
  const keys = [];
  const labels = new Map();
  const groupedPanels = new Map();

  panels.forEach((panel) => {
    panel.dataset.lmTaskReady = "true";
    const key = panel.dataset.lmTaskKey || panel.id || `panel-${keys.length + 1}`;
    const label = panel.dataset.lmTaskLabel || key;
    panel.dataset.lmTaskKey = key;
    panel.dataset.lmTaskGroup = groupName;
    if (!groupedPanels.has(key)) {
      groupedPanels.set(key, []);
      keys.push(key);
      labels.set(key, label);
    }
    groupedPanels.get(key).push(panel);
    lockDetailsPanel(panel);
  });

  if (keys.length < 2) return;

  const nav = document.createElement("div");
  nav.className = "lm-task-tabs";
  nav.setAttribute("role", "tablist");
  nav.setAttribute("aria-label", anchor?.dataset.lmTaskTabsLabel || "بخش‌های صفحه");
  nav.dataset.lmTaskTabsGenerated = groupName;

  const buttons = new Map();
  keys.forEach((key, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lm-task-tab";
    button.dataset.lmTaskTab = key;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", "false");
    button.setAttribute("tabindex", index === 0 ? "0" : "-1");
    const token = `${groupName}-${key}`.replace(/[^a-zA-Z0-9_-]+/g, "-");
    button.id = `lm-task-tab-${token}`;
    const firstPanel = groupedPanels.get(key)[0];
    if (!firstPanel.id) firstPanel.id = `lm-task-panel-${token}`;
    button.setAttribute("aria-controls", firstPanel.id);
    groupedPanels.get(key).forEach((panel) => panel.setAttribute("aria-labelledby", button.id));
    button.textContent = labels.get(key);
    nav.appendChild(button);
    buttons.set(key, button);
  });

  if (anchor) {
    anchor.replaceChildren(nav);
    anchor.classList.add("lm-task-tabs-anchor");
  } else {
    const generatedAnchor = document.createElement("div");
    generatedAnchor.className = "lm-task-tabs-anchor";
    generatedAnchor.dataset.lmTaskTabsAnchorGenerated = groupName;
    generatedAnchor.appendChild(nav);

    // Keep the sticky bar inside the common task-page scope, not inside the
    // first grid/section that happens to contain a panel. A sticky element is
    // bounded by its containing block; inserting it into a short first grid
    // makes it stop sticking before later task panels are reached.
    if (anchorScope instanceof HTMLElement) {
      const firstPanel = panels[0];
      const directChild = Array.from(anchorScope.children).find(
        (child) => child === firstPanel || child.contains(firstPanel)
      );
      if (directChild) anchorScope.insertBefore(generatedAnchor, directChild);
      else anchorScope.prepend(generatedAnchor);
    } else {
      panels[0].parentNode?.insertBefore(generatedAnchor, panels[0]);
    }
    anchor = generatedAnchor;
  }

  const setActive = (key, { persist = true, focus = false } = {}) => {
    if (!groupedPanels.has(key)) return;

    keys.forEach((candidate) => {
      const active = candidate === key;
      const button = buttons.get(candidate);
      button?.setAttribute("aria-selected", active ? "true" : "false");
      button?.setAttribute("tabindex", active ? "0" : "-1");
      groupedPanels.get(candidate).forEach((panel) => {
        panel.hidden = !active;
        panel.setAttribute("role", "tabpanel");
        if (active) lockDetailsPanel(panel);
      });
    });

    if (persist) safeStorageSet(storageKey, key);
    const activeButton = buttons.get(key);
    if (focus) activeButton?.focus({ preventScroll: true });
    if (activeButton && nav.scrollWidth > nav.clientWidth) {
      window.requestAnimationFrame(() => {
        activeButton.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
      });
    }
    window.dispatchEvent(new CustomEvent("loomera:task-tab-change", { detail: { group: groupName, key } }));
  };

  const params = new URLSearchParams(window.location.search);
  const explicitTab = params.get("tab");
  const editKey = params.has("edit") && groupedPanels.has("form") ? "form" : null;
  const errorPanel = panels.find((panel) =>
    panel.querySelector(
      ".errorlist, [aria-invalid=\"true\"], .text-loomera-danger, .text-loomera-warning, .text-rose-600, .text-red-600"
    )
  );
  const errorKey = errorPanel?.dataset.lmTaskKey;
  const hashPanel = panels.find(panelContainsHashTarget);
  const hashKey = hashPanel?.dataset.lmTaskKey;
  const defaultPanel = panels.find((panel) => panel.hasAttribute("data-lm-task-default"));
  const defaultKey = defaultPanel?.dataset.lmTaskKey || keys[0];
  const storedKey = safeStorageGet(storageKey);
  const initialKey =
    (explicitTab && groupedPanels.has(explicitTab) ? explicitTab : null) ||
    editKey ||
    errorKey ||
    hashKey ||
    (storedKey && groupedPanels.has(storedKey) ? storedKey : defaultKey);
  setActive(initialKey, { persist: false });

  keys.forEach((key, index) => {
    const button = buttons.get(key);
    button?.addEventListener("click", () => setActive(key));
    button?.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      let nextIndex = index;
      if (event.key === "Home") nextIndex = 0;
      else if (event.key === "End") nextIndex = keys.length - 1;
      else if (event.key === "ArrowLeft") nextIndex = (index + 1) % keys.length;
      else if (event.key === "ArrowRight") nextIndex = (index - 1 + keys.length) % keys.length;
      setActive(keys[nextIndex], { focus: true });
    });
  });

  document.addEventListener("click", (event) => {
    const link = event.target.closest('a[href^="#"]');
    if (!link) return;
    const id = decodeURIComponent(link.getAttribute("href").slice(1));
    if (!id) return;
    const target = document.getElementById(id);
    if (!target) return;
    const owner = panels.find((panel) => panel.contains(target));
    if (!owner) return;
    setActive(owner.dataset.lmTaskKey);
  });
}

function hydrateTaskTabs(root = document) {
  const panels = Array.from(root.querySelectorAll("[data-lm-task-panel]:not([data-lm-task-ready=\"true\"])"));
  if (!panels.length) return;

  const groups = new Map();
  panels.forEach((panel) => {
    const group = panel.dataset.lmTaskPanel;
    if (!group) return;
    const scope = panel.closest("[data-dashboard-page], [data-appointments-workspace], [data-dashboard-workspace-root]") || document;
    const scopeDataset = scope instanceof HTMLElement ? scope.dataset : {};
    const scopeKey = scope.id || scopeDataset.dashboardPage || scopeDataset.page || "dashboard";
    const compound = `${scopeKey}::${group}`;
    if (!groups.has(compound)) groups.set(compound, { group, scope, panels: [] });
    groups.get(compound).panels.push(panel);
  });

  groups.forEach(({ group, scope, panels: groupPanels }) => {
    const allPanels = Array.from(scope.querySelectorAll(`[data-lm-task-panel="${group}"]`));
    const anchor = scope.querySelector(`[data-lm-task-tabs-anchor="${group}"]`);
    initGroup(group, allPanels.length ? allPanels : groupPanels, anchor, scope);
  });
}

export default function initDashboardTaskTabs(root = document) {
  initStickyTabsRuntime();
  hydrateTaskTabs(root);
  if (document.documentElement.dataset.lmTaskTabsObserver === "true") return;
  document.documentElement.dataset.lmTaskTabsObserver = "true";
  const observer = new MutationObserver((mutations) => {
    const shouldRefresh = mutations.some((mutation) =>
      Array.from(mutation.addedNodes).some((node) =>
        node instanceof Element && (node.matches?.("[data-lm-task-panel]") || node.querySelector?.("[data-lm-task-panel]"))
      )
    );
    if (shouldRefresh) hydrateTaskTabs(document);
  });
  observer.observe(document.body, { childList: true, subtree: true });
}
