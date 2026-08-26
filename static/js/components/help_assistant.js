const ROOT_SELECTOR = "[data-help-assistant]";

function csrfToken(root) {
  return (
    root.querySelector("input[name='csrfmiddlewaretoken']")?.value ||
    document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="))
      ?.split("=")[1] ||
    ""
  );
}

function positionKey() {
  return `loomera.help-assistant.position.${matchMedia("(max-width:767px)").matches ? "mobile" : "desktop"}`;
}

function applyPosition(root) {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(positionKey()) || "null"); } catch (_) {}
  if (!saved) return;

  const size = root.offsetWidth || 56;
  const left = saved.side === "right" ? window.innerWidth - size - 14 : 14;
  const minY = 72;
  const bottomReserve = matchMedia("(max-width:767px)").matches ? 100 : 12;
  const maxY = Math.max(minY, window.innerHeight - size - bottomReserve);
  const top = minY + Math.max(0, Math.min(1, Number(saved.ratio) || 0)) * (maxY - minY);

  root.style.left = `${left}px`;
  root.style.top = `${top}px`;
  root.style.right = "auto";
  root.style.bottom = "auto";
}

function savePosition(root) {
  const rect = root.getBoundingClientRect();
  const side = rect.left + rect.width / 2 < window.innerWidth / 2 ? "left" : "right";
  const minY = 72;
  const bottomReserve = matchMedia("(max-width:767px)").matches ? 100 : 12;
  const maxY = Math.max(minY + 1, window.innerHeight - rect.height - bottomReserve);
  const ratio = (Math.max(minY, Math.min(maxY, rect.top)) - minY) / Math.max(1, maxY - minY);
  try { localStorage.setItem(positionKey(), JSON.stringify({ side, ratio })); } catch (_) {}
}

function bindDrag(root, fab) {
  let pointer = null;
  let startX = 0, startY = 0, startLeft = 0, startTop = 0;
  let dragging = false, suppress = false;

  fab.addEventListener("pointerdown", (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    pointer = event.pointerId;
    const rect = root.getBoundingClientRect();
    startX = event.clientX; startY = event.clientY;
    startLeft = rect.left; startTop = rect.top;
    dragging = false;
    try { fab.setPointerCapture(pointer); } catch (_) {}
  });

  fab.addEventListener("pointermove", (event) => {
    if (pointer === null || event.pointerId !== pointer) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < 7) return;
    dragging = true;

    const size = root.offsetWidth || 56;
    const maxX = window.innerWidth - size - 8;
    const maxY = window.innerHeight - size - (matchMedia("(max-width:767px)").matches ? 96 : 8);
    root.style.left = `${Math.max(8, Math.min(maxX, startLeft + dx))}px`;
    root.style.top = `${Math.max(70, Math.min(maxY, startTop + dy))}px`;
    root.style.bottom = "auto";
    root.style.right = "auto";
  });

  const finish = (event) => {
    if (pointer === null || event.pointerId !== pointer) return;
    if (dragging) {
      const rect = root.getBoundingClientRect();
      const size = root.offsetWidth || 56;
      const right = rect.left + rect.width / 2 >= window.innerWidth / 2;
      root.style.left = `${right ? window.innerWidth - size - 14 : 14}px`;
      savePosition(root);
      suppress = true;
      setTimeout(() => { suppress = false; }, 100);
    }
    try { fab.releasePointerCapture(pointer); } catch (_) {}
    pointer = null;
    dragging = false;
  };
  fab.addEventListener("pointerup", finish);
  fab.addEventListener("pointercancel", finish);
  fab.addEventListener("click", (event) => {
    if (suppress) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
}

function feedbackRow(root, messageId) {
  if (!messageId) return null;

  const row = document.createElement("div");
  row.className = "lm-help-assistant__feedback";
  row.innerHTML = `
    <span>این پاسخ مفید بود؟</span>
    <button type="button" data-rating="helpful" aria-label="مفید بود"><i class="fa-regular fa-thumbs-up"></i></button>
    <button type="button" data-rating="not_helpful" aria-label="مفید نبود"><i class="fa-regular fa-thumbs-down"></i></button>
  `;

  row.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const response = await fetch(root.dataset.feedbackUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken(root),
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify({
            message_id: messageId,
            rating: button.dataset.rating,
          }),
        });
        if (!response.ok) throw new Error("feedback");
        row.querySelectorAll("button").forEach((item) => item.classList.remove("is-selected"));
        button.classList.add("is-selected");
        row.querySelector("span").textContent = "ممنون از بازخوردت";
      } catch (_) {
        row.querySelector("span").textContent = "ثبت بازخورد انجام نشد";
      }
    });
  });
  return row;
}

function addMessage(container, role, text, options = {}) {
  const row = document.createElement("div");
  row.className = `lm-help-assistant__message lm-help-assistant__message--${role}`;
  if (options.temporary) row.dataset.temporary = "1";

  const wrap = document.createElement("div");
  const bubble = document.createElement("div");
  bubble.className = "lm-help-assistant__bubble";

  if (options.temporary) {
    bubble.innerHTML = '<span class="lm-help-assistant__typing"><span></span><span></span><span></span></span>';
  } else {
    bubble.textContent = text;
  }

  wrap.appendChild(bubble);
  if (role === "assistant" && options.messageId) {
    const feedback = feedbackRow(options.root, options.messageId);
    if (feedback) wrap.appendChild(feedback);
  }

  row.appendChild(wrap);
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
  return row;
}

function renderSources(box, sources = []) {
  box.innerHTML = "";
  if (!sources.length) {
    box.hidden = true;
    return;
  }
  sources.forEach((source) => {
    const a = document.createElement("a");
    a.href = source.url;
    a.textContent = source.title;
    box.appendChild(a);
  });
  box.hidden = false;
}

async function getContext(root) {
  const url = new URL(root.dataset.contextUrl, window.location.origin);
  url.searchParams.set("path", root.dataset.currentPath || window.location.pathname);
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!response.ok) throw new Error("context");
  return response.json();
}

async function sendChat(root, message, history, conversationId) {
  const response = await fetch(root.dataset.chatUrl, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(root),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({
      message,
      path: root.dataset.currentPath || window.location.pathname,
      history: history.slice(-6),
      conversation_id: conversationId,
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "chat");
  return payload;
}

function autoGrow(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(110, textarea.scrollHeight)}px`;
}

function init() {
  const root = document.querySelector(ROOT_SELECTOR);
  if (!root || root.dataset.bound === "1") return;
  root.dataset.bound = "1";

  if (localStorage.getItem("loomera.help-assistant.hidden") === "1") root.hidden = true;

  const fab = root.querySelector("[data-help-fab]");
  const panel = root.querySelector("[data-help-panel]");
  const close = root.querySelector("[data-help-close]");
  const hide = root.querySelector("[data-help-hide]");
  const form = root.querySelector("[data-help-form]");
  const input = root.querySelector("[data-help-input]");
  const send = root.querySelector("[data-help-send]");
  const messages = root.querySelector("[data-help-messages]");
  const welcome = root.querySelector("[data-help-welcome]");
  const prompts = root.querySelector("[data-help-prompts]");
  const summary = root.querySelector("[data-help-context-summary]");
  const pageLabel = root.querySelector("[data-help-page-label]");
  const sourcesBox = root.querySelector("[data-help-sources]");
  const dot = root.querySelector("[data-help-new-dot]");
  const undo = document.querySelector("[data-help-undo]");
  const handoffBox = root.querySelector("[data-help-handoff-box]");
  const escalate = root.querySelector("[data-help-escalate]");

  let loaded = false;
  let history = [];
  let context = null;
  let conversationId = null;

  applyPosition(root);
  bindDrag(root, fab);

  async function loadContext() {
    if (loaded) return;
    loaded = true;
    try {
      context = await getContext(root);
      pageLabel.textContent = context.title || "راهنمای همین صفحه";
      summary.textContent = context.summary || "درباره استفاده از لومرا از من بپرس.";
      prompts.innerHTML = "";
      (context.quick_prompts || []).slice(0, 4).forEach((text) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = text;
        button.addEventListener("click", () => {
          input.value = text;
          autoGrow(input);
          form.requestSubmit();
        });
        prompts.appendChild(button);
      });

      const seenKey = `loomera.help-assistant.seen.${context.page_key || "general"}.v2`;
      dot.hidden = localStorage.getItem(seenKey) === "1";
    } catch (_) {
      pageLabel.textContent = "راهنمای لومرا";
    }
  }

  async function openPanel() {
    panel.hidden = false;
    fab.setAttribute("aria-expanded", "true");
    await loadContext();
    if (context?.page_key) {
      localStorage.setItem(`loomera.help-assistant.seen.${context.page_key}.v2`, "1");
      dot.hidden = true;
    }
    setTimeout(() => input.focus(), 80);
  }

  function closePanel() {
    panel.hidden = true;
    fab.setAttribute("aria-expanded", "false");
  }

  fab.addEventListener("click", () => panel.hidden ? openPanel() : closePanel());
  close?.addEventListener("click", closePanel);

  hide?.addEventListener("click", () => {
    closePanel();
    root.hidden = true;
    localStorage.setItem("loomera.help-assistant.hidden", "1");
    if (undo) {
      undo.hidden = false;
      clearTimeout(root._undoTimer);
      root._undoTimer = setTimeout(() => { undo.hidden = true; }, 7000);
    }
  });

  undo?.querySelector("button")?.addEventListener("click", () => {
    localStorage.removeItem("loomera.help-assistant.hidden");
    root.hidden = false;
    undo.hidden = true;
  });

  input.addEventListener("input", () => autoGrow(input));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || send.disabled) return;

    welcome.hidden = true;
    renderSources(sourcesBox, []);
    addMessage(messages, "user", text);
    history.push({ role: "user", content: text });

    input.value = "";
    autoGrow(input);
    send.disabled = true;
    const typing = addMessage(messages, "assistant", "", { temporary: true });

    try {
      const payload = await sendChat(root, text, history, conversationId);
      typing.remove();
      conversationId = payload.conversation_id || conversationId;
      addMessage(messages, "assistant", payload.answer || "پاسخی دریافت نشد.", {
        root,
        messageId: payload.assistant_message_id,
      });
      history.push({ role: "assistant", content: payload.answer || "" });
      renderSources(sourcesBox, payload.sources || []);
      handoffBox.hidden = false;
    } catch (error) {
      typing.remove();
      addMessage(
        messages,
        "assistant",
        error.message && error.message !== "chat"
          ? error.message
          : "الان نتونستم پاسخ رو دریافت کنم. از مرکز راهنما یا پشتیبانی استفاده کن."
      );
    } finally {
      send.disabled = false;
      input.focus();
    }
  });

  escalate?.addEventListener("click", async () => {
    if (!conversationId) {
      window.location.href = root.dataset.supportUrl;
      return;
    }

    escalate.disabled = true;
    const original = escalate.textContent;
    escalate.textContent = "در حال انتقال...";

    try {
      const response = await fetch(root.dataset.handoffUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(root),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ conversation_id: conversationId }),
      });
      const payload = await response.json().catch(() => ({}));

      if (response.ok && payload.ticket_url) {
        addMessage(messages, "assistant", "گفتگو به پشتیبانی منتقل شد. صفحه تیکت را باز می‌کنم.");
        setTimeout(() => { window.location.href = payload.ticket_url; }, 700);
        return;
      }

      if (payload.support_url) {
        addMessage(messages, "assistant", payload.error || "برای ادامه فرم پشتیبانی را باز کن.");
        setTimeout(() => { window.location.href = payload.support_url; }, 900);
        return;
      }

      throw new Error(payload.error || "انتقال گفتگو انجام نشد.");
    } catch (error) {
      addMessage(messages, "assistant", error.message || "انتقال گفتگو انجام نشد.");
    } finally {
      escalate.disabled = false;
      escalate.textContent = original;
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) closePanel();
  });

  window.addEventListener("resize", () => applyPosition(root));
  loadContext();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init, { once: true });
} else {
  init();
}
