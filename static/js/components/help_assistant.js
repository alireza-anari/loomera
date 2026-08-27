const ROOT_SELECTOR = "[data-help-assistant]";
const CONVERSATION_STORAGE_KEY = "loomera.help-assistant.conversation.v3";

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

function getStoredConversationId() {
  try { return sessionStorage.getItem(CONVERSATION_STORAGE_KEY) || null; } catch (_) { return null; }
}

function setStoredConversationId(value) {
  try {
    if (value) sessionStorage.setItem(CONVERSATION_STORAGE_KEY, value);
    else sessionStorage.removeItem(CONVERSATION_STORAGE_KEY);
  } catch (_) {}
}

function positionKey() {
  return `loomera.help-assistant.position.${matchMedia("(max-width:767px)").matches ? "mobile" : "desktop"}`;
}

function applyPosition(root) {
  if (matchMedia("(max-width:767px)").matches) {
    root.style.left = "";
    root.style.top = "";
    root.style.right = "";
    root.style.bottom = "";
    return;
  }

  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(positionKey()) || "null"); } catch (_) {}
  if (!saved) return;

  const size = root.offsetWidth || 60;
  const left = saved.side === "right" ? window.innerWidth - size - 20 : 20;
  const minY = 72;
  const maxY = Math.max(minY, window.innerHeight - size - 20);
  const top = minY + Math.max(0, Math.min(1, Number(saved.ratio) || 0)) * (maxY - minY);

  root.style.left = `${left}px`;
  root.style.top = `${top}px`;
  root.style.right = "auto";
  root.style.bottom = "auto";
}

function savePosition(root) {
  if (matchMedia("(max-width:767px)").matches) return;
  const rect = root.getBoundingClientRect();
  const side = rect.left + rect.width / 2 < window.innerWidth / 2 ? "left" : "right";
  const minY = 72;
  const maxY = Math.max(minY + 1, window.innerHeight - rect.height - 20);
  const ratio = (Math.max(minY, Math.min(maxY, rect.top)) - minY) / Math.max(1, maxY - minY);
  try { localStorage.setItem(positionKey(), JSON.stringify({ side, ratio })); } catch (_) {}
}

function bindDrag(root, fab) {
  if (matchMedia("(max-width:767px)").matches) return;

  let pointer = null;
  let startX = 0, startY = 0, startLeft = 0, startTop = 0;
  let dragging = false, suppress = false;

  fab.addEventListener("pointerdown", (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    pointer = event.pointerId;
    const rect = root.getBoundingClientRect();
    startX = event.clientX;
    startY = event.clientY;
    startLeft = rect.left;
    startTop = rect.top;
    dragging = false;
    try { fab.setPointerCapture(pointer); } catch (_) {}
  });

  fab.addEventListener("pointermove", (event) => {
    if (pointer === null || event.pointerId !== pointer) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < 7) return;
    dragging = true;

    const size = root.offsetWidth || 60;
    root.style.left = `${Math.max(10, Math.min(window.innerWidth - size - 10, startLeft + dx))}px`;
    root.style.top = `${Math.max(70, Math.min(window.innerHeight - size - 10, startTop + dy))}px`;
    root.style.bottom = "auto";
    root.style.right = "auto";
  });

  const finish = (event) => {
    if (pointer === null || event.pointerId !== pointer) return;
    if (dragging) {
      const rect = root.getBoundingClientRect();
      const right = rect.left + rect.width / 2 >= window.innerWidth / 2;
      const size = root.offsetWidth || 60;
      root.style.left = `${right ? window.innerWidth - size - 20 : 20}px`;
      savePosition(root);
      suppress = true;
      setTimeout(() => { suppress = false; }, 120);
    }
    try { fab.releasePointerCapture(pointer); } catch (_) {}
    pointer = null;
    dragging = false;
  };

  fab.addEventListener("pointerup", finish);
  fab.addEventListener("pointercancel", finish);
  fab.addEventListener("click", (event) => {
    if (!suppress) return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);
}

function autoGrow(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(128, textarea.scrollHeight)}px`;
}

function appendTextWithCitations(container, text, sources = []) {
  const value = String(text || "");
  const pattern = /\[(\d{1,2})\]/g;
  let cursor = 0;
  let match;

  while ((match = pattern.exec(value)) !== null) {
    if (match.index > cursor) {
      container.append(document.createTextNode(value.slice(cursor, match.index)));
    }

    const number = Number(match[1]);
    const source = sources[number - 1];
    if (source?.url) {
      const citation = document.createElement("a");
      citation.className = "lm-help-assistant__citation";
      citation.href = source.url;
      citation.title = source.title || `منبع ${number}`;
      citation.textContent = String(number);
      citation.setAttribute("aria-label", `منبع ${number}: ${source.title || "راهنمای لومرا"}`);
      container.appendChild(citation);
    } else {
      container.append(document.createTextNode(match[0]));
    }
    cursor = pattern.lastIndex;
  }

  if (cursor < value.length) {
    container.append(document.createTextNode(value.slice(cursor)));
  }
}

function feedbackRow(root, messageId) {
  if (!messageId) return null;

  const row = document.createElement("div");
  row.className = "lm-help-assistant__feedback";

  const label = document.createElement("span");
  label.textContent = "پاسخ مفید بود؟";
  row.appendChild(label);

  [
    ["helpful", "fa-regular fa-thumbs-up", "بله، مفید بود"],
    ["not_helpful", "fa-regular fa-thumbs-down", "نه، مفید نبود"],
  ].forEach(([rating, icon, aria]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.rating = rating;
    button.setAttribute("aria-label", aria);
    button.innerHTML = `<i class="${icon}" aria-hidden="true"></i>`;
    row.appendChild(button);
  });

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
        label.textContent = "ممنون، ثبت شد";
      } catch (_) {
        label.textContent = "ثبت بازخورد انجام نشد";
      }
    });
  });

  return row;
}

function sourceDetails(sources = []) {
  if (!sources.length) return null;

  const details = document.createElement("details");
  details.className = "lm-help-assistant__message-sources";

  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span><i class="fa-regular fa-book-open" aria-hidden="true"></i> منابع این پاسخ</span>
    <span class="lm-help-assistant__source-count">${sources.length}</span>
  `;
  details.appendChild(summary);

  const list = document.createElement("div");
  list.className = "lm-help-assistant__source-list";

  sources.forEach((source, index) => {
    const link = document.createElement("a");
    link.href = source.url;
    link.className = "lm-help-assistant__source-link";

    const number = document.createElement("span");
    number.className = "lm-help-assistant__source-number";
    number.textContent = String(index + 1);

    const copy = document.createElement("span");
    copy.className = "lm-help-assistant__source-copy";

    const title = document.createElement("strong");
    title.textContent = source.title || "راهنمای لومرا";
    copy.appendChild(title);

    if (source.heading && source.heading !== source.title) {
      const heading = document.createElement("small");
      heading.textContent = source.heading;
      copy.appendChild(heading);
    }

    const arrow = document.createElement("i");
    arrow.className = "fa-solid fa-chevron-left";
    arrow.setAttribute("aria-hidden", "true");

    link.append(number, copy, arrow);
    list.appendChild(link);
  });

  details.appendChild(list);
  return details;
}

function addMessage(container, role, text, options = {}) {
  const row = document.createElement("div");
  row.className = `lm-help-assistant__message lm-help-assistant__message--${role}`;
  if (options.temporary) row.dataset.temporary = "1";

  if (role === "assistant") {
    const avatar = document.createElement("span");
    avatar.className = "lm-help-assistant__message-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.innerHTML = '<i class="fa-solid fa-sparkles"></i>';
    row.appendChild(avatar);
  }

  const stack = document.createElement("div");
  stack.className = "lm-help-assistant__message-stack";

  if (role === "assistant") {
    const name = document.createElement("span");
    name.className = "lm-help-assistant__message-name";
    name.textContent = "دستیار پشتیبانی";
    stack.appendChild(name);
  }

  const bubble = document.createElement("div");
  bubble.className = "lm-help-assistant__bubble";

  if (options.temporary) {
    const typing = document.createElement("div");
    typing.className = "lm-help-assistant__typing-wrap";
    typing.innerHTML = `
      <span class="lm-help-assistant__typing"><span></span><span></span><span></span></span>
      <span>دارم راهنماهای مرتبط رو بررسی می‌کنم…</span>
    `;
    bubble.appendChild(typing);
  } else if (role === "assistant") {
    appendTextWithCitations(bubble, text, options.sources || []);
  } else {
    bubble.textContent = text;
  }

  stack.appendChild(bubble);

  if (role === "assistant" && !options.temporary) {
    const details = sourceDetails(options.sources || []);
    if (details) stack.appendChild(details);

    const feedback = feedbackRow(options.root, options.messageId);
    if (feedback) stack.appendChild(feedback);
  }

  row.appendChild(stack);
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
  return row;
}

async function getContext(root) {
  const url = new URL(root.dataset.contextUrl, window.location.origin);
  url.searchParams.set("path", root.dataset.currentPath || window.location.pathname);
  url.searchParams.set("route", root.dataset.currentRoute || "");

  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!response.ok) throw new Error("context");
  return response.json();
}

async function getConversation(root, conversationId) {
  if (!conversationId) return null;
  const url = new URL(root.dataset.conversationUrl, window.location.origin);
  url.searchParams.set("conversation_id", conversationId);

  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("conversation");
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
      route_name: root.dataset.currentRoute || "",
      history: history.slice(-6),
      conversation_id: conversationId,
    }),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "chat");
  return payload;
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
  const newChat = root.querySelector("[data-help-new-chat]");
  const form = root.querySelector("[data-help-form]");
  const input = root.querySelector("[data-help-input]");
  const send = root.querySelector("[data-help-send]");
  const messages = root.querySelector("[data-help-messages]");
  const welcome = root.querySelector("[data-help-welcome]");
  const prompts = root.querySelector("[data-help-prompts]");
  const summary = root.querySelector("[data-help-context-summary]");
  const pageLabel = root.querySelector("[data-help-page-label]");
  const dot = root.querySelector("[data-help-new-dot]");
  const undo = document.querySelector("[data-help-undo]");
  const handoffBox = root.querySelector("[data-help-handoff-box]");
  const escalate = root.querySelector("[data-help-escalate]");

  let contextLoaded = false;
  let conversationHydrated = false;
  let history = [];
  let context = null;
  let conversationId = getStoredConversationId();

  applyPosition(root);
  bindDrag(root, fab);

  function resetConversationUi() {
    history = [];
    conversationId = null;
    setStoredConversationId(null);
    conversationHydrated = true;

    messages.querySelectorAll(".lm-help-assistant__message").forEach((item) => item.remove());
    welcome.hidden = false;
    handoffBox.hidden = true;
    input.value = "";
    autoGrow(input);
  }

  async function loadContext() {
    if (contextLoaded) return;
    contextLoaded = true;

    try {
      context = await getContext(root);
      pageLabel.innerHTML = "";
      const online = document.createElement("span");
      online.className = "lm-help-assistant__online-dot";
      pageLabel.appendChild(online);
      pageLabel.append(document.createTextNode(context.title || "آنلاین · پاسخ براساس راهنمای لومرا"));

      summary.textContent =
        context.summary ||
        "هر سؤالی درباره کار با لومرا داری بپرس. جواب رو از راهنماهای رسمی پیدا می‌کنم.";

      prompts.innerHTML = "";
      (context.quick_prompts || []).slice(0, 3).forEach((text) => {
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

      const seenKey = `loomera.help-assistant.seen.${context.page_key || "general"}.v3`;
      dot.hidden = localStorage.getItem(seenKey) === "1";
    } catch (_) {
      pageLabel.textContent = "دستیار پشتیبانی لومرا";
    }
  }

  async function hydrateConversation() {
    if (conversationHydrated) return;
    conversationHydrated = true;
    if (!conversationId) return;

    try {
      const payload = await getConversation(root, conversationId);
      if (!payload?.messages?.length) {
        if (!payload) {
          conversationId = null;
          setStoredConversationId(null);
        }
        return;
      }

      welcome.hidden = true;
      history = [];

      payload.messages.forEach((item) => {
        addMessage(messages, item.role, item.content, {
          root,
          messageId: item.message_id,
          sources: item.sources || [],
        });
        history.push({ role: item.role, content: item.content });
      });

      handoffBox.hidden = false;
    } catch (_) {
      conversationId = null;
      setStoredConversationId(null);
    }
  }

  async function openPanel() {
    panel.hidden = false;
    fab.setAttribute("aria-expanded", "true");
    await Promise.all([loadContext(), hydrateConversation()]);

    if (context?.page_key) {
      localStorage.setItem(`loomera.help-assistant.seen.${context.page_key}.v3`, "1");
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

  newChat?.addEventListener("click", () => {
    if (history.length && !window.confirm("گفتگوی جدید شروع بشه؟ گفتگوی فعلی در سوابق پشتیبانی باقی می‌مونه.")) {
      return;
    }
    resetConversationUi();
    input.focus();
  });

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
      setStoredConversationId(conversationId);

      const answer = payload.answer || "الان جواب قابل اتکایی پیدا نکردم.";
      addMessage(messages, "assistant", answer, {
        root,
        messageId: payload.assistant_message_id,
        sources: payload.sources || [],
      });
      history.push({ role: "assistant", content: answer });
      handoffBox.hidden = false;
    } catch (error) {
      typing.remove();
      addMessage(
        messages,
        "assistant",
        error.message && error.message !== "chat"
          ? error.message
          : "الان نتونستم پاسخ رو دریافت کنم. یک‌بار دیگه امتحان کن؛ اگر ادامه داشت، همین گفتگو رو برای پشتیبانی بفرست.",
        { root }
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
    const original = escalate.innerHTML;
    escalate.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> در حال ارجاع…';

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
        addMessage(
          messages,
          "assistant",
          "گفتگو برای پشتیبانی ارسال شد. الان صفحه پیگیری درخواست رو باز می‌کنم.",
          { root }
        );
        setTimeout(() => { window.location.href = payload.ticket_url; }, 650);
        return;
      }

      if (payload.support_url) {
        addMessage(
          messages,
          "assistant",
          payload.error || "برای ادامه، فرم پشتیبانی رو باز می‌کنم.",
          { root }
        );
        setTimeout(() => { window.location.href = payload.support_url; }, 850);
        return;
      }

      throw new Error(payload.error || "ارجاع گفتگو انجام نشد.");
    } catch (error) {
      addMessage(messages, "assistant", error.message || "ارجاع گفتگو انجام نشد.", { root });
    } finally {
      escalate.disabled = false;
      escalate.innerHTML = original;
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
