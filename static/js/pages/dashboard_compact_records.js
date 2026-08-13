function closeSiblingRecords(record) {
  const group = record.dataset.lmCompactGroup;
  if (!group) return;
  const scope = record.closest("[data-lm-task-panel], [data-dashboard-page], [data-dashboard-workspace-root]") || document;
  scope.querySelectorAll(`[data-lm-compact-record][data-lm-compact-group="${CSS.escape(group)}"]`).forEach((candidate) => {
    if (candidate !== record && candidate instanceof HTMLDetailsElement) candidate.open = false;
  });
}

function initRecord(record) {
  if (!(record instanceof HTMLDetailsElement) || record.dataset.lmCompactReady === "true") return;
  record.dataset.lmCompactReady = "true";
  record.addEventListener("toggle", () => {
    if (!record.open) return;
    closeSiblingRecords(record);
    window.requestAnimationFrame(() => {
      const summary = record.querySelector(":scope > summary");
      summary?.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  });
}

function hydrate(root = document) {
  root.querySelectorAll("details[data-lm-compact-record]").forEach(initRecord);
}

export default function initDashboardCompactRecords(root = document) {
  hydrate(root);
  if (document.documentElement.dataset.lmCompactRecordsObserver === "true") return;
  document.documentElement.dataset.lmCompactRecordsObserver = "true";
  const observer = new MutationObserver((mutations) => {
    if (mutations.some((mutation) => Array.from(mutation.addedNodes).some((node) =>
      node instanceof Element && (node.matches?.("details[data-lm-compact-record]") || node.querySelector?.("details[data-lm-compact-record]"))
    ))) hydrate(document);
  });
  observer.observe(document.body, { childList: true, subtree: true });
}
