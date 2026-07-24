function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return decodeURIComponent(parts.pop().split(";").shift());
  return "";
}

function normalizeStoriesData(value) {
  if (Array.isArray(value)) return value;

  if (value && Array.isArray(value.stories)) {
    return value.stories;
  }

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return [];

    try {
      return normalizeStoriesData(JSON.parse(trimmed));
    } catch (error) {
      console.warn("[magazine] invalid nested stories data");
      return [];
    }
  }

  return [];
}

function readStoriesData() {
  const script =
    document.getElementById("magazineStoriesData") ||
    document.getElementById("salonStoriesData");

  if (!script) return [];

  try {
    return normalizeStoriesData(JSON.parse(script.textContent || "[]"));
  } catch (error) {
    console.warn("[magazine] invalid stories data");
    return [];
  }
}

function postStoryEvent(url, payload = {}) {
  if (!url) return Promise.resolve();

  const formData = new FormData();

  Object.entries(payload).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      formData.append(key, String(value));
    }
  });

  return fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCookie("csrftoken"),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: formData,
  }).catch((error) => {
    console.warn("[magazine] story event request failed");
  });
}

function initStoryViewer() {
  const stories = readStoriesData();
  if (!stories.length) return;

  const viewer = document.querySelector("[data-story-viewer]");
  if (!viewer) return;

  const progressRoot = viewer.querySelector("[data-story-progress]");
  const imageEl = viewer.querySelector("[data-story-image]");
  const videoEl = viewer.querySelector("[data-story-video]");
  const captionEl = viewer.querySelector("[data-story-caption]");
  const salonEl = viewer.querySelector("[data-story-salon]");
  const titleEl = viewer.querySelector("[data-story-title]");
  const closeBtn = viewer.querySelector("[data-story-close]");
  const prevBtn = viewer.querySelector("[data-story-prev]");
  const nextBtn = viewer.querySelector("[data-story-next]");
  const cta = viewer.querySelector("[data-story-cta]");
  const ctaLabel = viewer.querySelector("[data-story-cta-label]");
  const reportOpen = viewer.querySelector("[data-story-report-open]");
  const reportForm = viewer.querySelector("[data-story-report-form]");
  const reportCancel = viewer.querySelector("[data-story-report-cancel]");
  const reportMessage = viewer.querySelector("[data-story-report-message]");

  let activeStoryIndex = 0;
  let activeItemIndex = 0;
  let timer = null;

  const clearTimer = () => {
    if (timer) window.clearTimeout(timer);
    timer = null;
  };

  const activeStory = () => stories[activeStoryIndex];
  const activeItem = () => {
    const story = activeStory();
    const item = story?.items?.[activeItemIndex];

    if (item) return item;

    if (story?.coverUrl) {
      return {
        id: "",
        mediaType: "image",
        mediaUrl: story.coverUrl,
        caption: story.summary || "",
        duration: 5,
      };
    }

    return null;
  };

  const closeViewer = () => {
    clearTimer();
    viewer.classList.add("hidden");
    viewer.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";

    if (videoEl) {
      videoEl.pause();
      videoEl.removeAttribute("src");
      videoEl.load();
    }
  };

  const renderProgress = () => {
    if (!progressRoot) return;

    const story = activeStory();
    const items = story?.items || [];
    progressRoot.innerHTML = "";

    items.forEach((_, index) => {
      const bar = document.createElement("span");
      bar.className = "h-1 flex-1 overflow-hidden rounded-full bg-white/25";

      const fill = document.createElement("span");
      fill.className = "block h-full rounded-full bg-white transition-all duration-300";
      fill.style.width = index < activeItemIndex ? "100%" : index === activeItemIndex ? "40%" : "0%";

      bar.appendChild(fill);
      progressRoot.appendChild(bar);
    });
  };

  const markCurrentItemViewed = (completed = false) => {
    const story = activeStory();
    const item = activeItem();

    if (!story || !item) return;

    postStoryEvent(story.viewUrl, {
      item_id: item.id,
      completed: completed ? "1" : "0",
    });
  };

  const goNext = () => {
    const story = activeStory();
    if (!story) return;

    const items = story.items || [];

    if (activeItemIndex < items.length - 1) {
      activeItemIndex += 1;
      renderCurrent();
      return;
    }

    markCurrentItemViewed(true);

    if (activeStoryIndex < stories.length - 1) {
      activeStoryIndex += 1;
      activeItemIndex = 0;
      renderCurrent();
      return;
    }

    closeViewer();
  };

  const goPrev = () => {
    if (activeItemIndex > 0) {
      activeItemIndex -= 1;
      renderCurrent();
      return;
    }

    if (activeStoryIndex > 0) {
      activeStoryIndex -= 1;
      const items = stories[activeStoryIndex]?.items || [];
      activeItemIndex = Math.max(0, items.length - 1);
      renderCurrent();
    }
  };

  function renderCurrent() {
    clearTimer();

    const story = activeStory();
    const item = activeItem();

    if (!story || !item) {
      closeViewer();
      return;
    }

    if (salonEl) salonEl.textContent = story.salonName || "";
    if (titleEl) titleEl.textContent = story.title || "";
    if (captionEl) captionEl.textContent = item.caption || "";
    if (reportForm) reportForm.classList.add("hidden");
    if (reportOpen) reportOpen.classList.toggle("hidden", !story.reportUrl);
    if (reportMessage) reportMessage.classList.add("hidden");

    if (imageEl) {
      imageEl.classList.add("hidden");
      imageEl.removeAttribute("src");
    }

    if (videoEl) {
      videoEl.classList.add("hidden");
      videoEl.pause();
      videoEl.removeAttribute("src");
      videoEl.load();
    }

    if (item.mediaType === "video" && item.mediaUrl && videoEl) {
      videoEl.src = item.mediaUrl;
      videoEl.classList.remove("hidden");
      videoEl.play().catch(() => {});
    } else if (imageEl) {
      imageEl.src = item.mediaUrl || story.coverUrl || "";
      imageEl.alt = story.title || "";
      imageEl.classList.remove("hidden");
    }

    if (cta) {
      const itemButtonUrl = item.buttonUrl || "";
      const itemButtonLabel = item.buttonLabel || "";
      const targetUrl = itemButtonUrl || story.ctaUrl || "#";
      cta.href = targetUrl;
      cta.classList.toggle("hidden", !targetUrl || targetUrl === "#");

      if (ctaLabel) {
        ctaLabel.textContent = itemButtonLabel || story.ctaLabel || "مشاهده";
      }
    }

    renderProgress();
    markCurrentItemViewed(false);

    const duration = Math.max(3, Number(item.duration || 5)) * 1000;
    timer = window.setTimeout(goNext, duration);
  }

  function openViewer(storyId) {
    const index = stories.findIndex((story) => String(story.id) === String(storyId));
    if (index < 0) return;

    activeStoryIndex = index;
    activeItemIndex = 0;

    viewer.classList.remove("hidden");
    viewer.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";

    renderCurrent();
  }

  document.querySelectorAll("[data-story-open]").forEach((button) => {
    button.addEventListener("click", () => {
      openViewer(button.dataset.storyId);
    });
  });

  closeBtn?.addEventListener("click", closeViewer);
  nextBtn?.addEventListener("click", goNext);
  prevBtn?.addEventListener("click", goPrev);

  cta?.addEventListener("click", () => {
    const story = activeStory();
    if (!story) return;
    postStoryEvent(story.clickUrl, {});
  });

  reportOpen?.addEventListener("click", () => {
    if (!reportForm) return;
    reportForm.classList.remove("hidden");
    reportMessage?.classList.add("hidden");
  });

  reportCancel?.addEventListener("click", () => {
    reportForm?.classList.add("hidden");
  });

  reportForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const story = activeStory();
    if (!story?.reportUrl) return;
    const button = reportForm.querySelector("button[type='submit']");
    if (button) {
      button.disabled = true;
      button.textContent = "در حال ثبت...";
    }
    fetch(story.reportUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {"X-Requested-With": "XMLHttpRequest"},
      body: new FormData(reportForm),
    })
      .then((response) => {
        if (!response.ok) throw new Error("report_failed");
        return response.json();
      })
      .then(() => {
        if (reportMessage) {
          reportMessage.textContent = "گزارش ثبت شد.";
          reportMessage.className = "mt-2 text-xs font-black text-emerald-300";
        }
        reportForm.reset();
        window.setTimeout(() => reportForm.classList.add("hidden"), 1200);
      })
      .catch(() => {
        if (reportMessage) {
          reportMessage.textContent = "ثبت گزارش انجام نشد. دوباره تلاش کن.";
          reportMessage.className = "mt-2 text-xs font-black text-rose-300";
        }
      })
      .finally(() => {
        if (button) {
          button.disabled = false;
          button.textContent = "ثبت گزارش";
        }
      });
  });

  document.addEventListener("keydown", (event) => {
    if (viewer.classList.contains("hidden")) return;

    if (event.key === "Escape") closeViewer();
    if (event.key === "ArrowLeft") goNext();
    if (event.key === "ArrowRight") goPrev();
  });
  const initialStoryId = new URLSearchParams(window.location.search).get("story") || new URLSearchParams(window.location.search).get("story_id");
  if (initialStoryId) {
    window.setTimeout(() => openViewer(initialStoryId), 150);
  }

}

function initSalonArticlesSlider() {
  document.querySelectorAll("[data-salon-articles-slider]").forEach((scope) => {
    const rail = scope.querySelector("[data-salon-articles-rail]");
    const prev = scope.querySelector("[data-salon-articles-prev]");
    const next = scope.querySelector("[data-salon-articles-next]");

    if (!rail) return;

    const getAmount = () => Math.max(280, Math.floor(rail.clientWidth * 0.72));

    prev?.addEventListener("click", () => {
      rail.scrollBy({ left: getAmount(), behavior: "smooth" });
    });

    next?.addEventListener("click", () => {
      rail.scrollBy({ left: -getAmount(), behavior: "smooth" });
    });
  });
}

function initMagazineHorizontalRails() {
  document.querySelectorAll("[data-magazine-rail]").forEach((rail) => {
    if (rail.dataset.magazineRailBound === "1") return;
    rail.dataset.magazineRailBound = "1";

    let isDown = false;
    let startX = 0;
    let scrollLeft = 0;

    rail.addEventListener("pointerdown", (event) => {
      isDown = true;
      startX = event.pageX;
      scrollLeft = rail.scrollLeft;
      rail.setPointerCapture?.(event.pointerId);
    });

    rail.addEventListener("pointermove", (event) => {
      if (!isDown) return;
      const dx = event.pageX - startX;
      if (Math.abs(dx) > 6) {
        rail.scrollLeft = scrollLeft - dx;
      }
    });

    ["pointerup", "pointercancel", "pointerleave"].forEach((eventName) => {
      rail.addEventListener(eventName, () => {
        isDown = false;
      });
    });
  });

  document.querySelectorAll("[data-magazine-rail-prev], [data-magazine-rail-next]").forEach((button) => {
    if (button.dataset.magazineRailButtonBound === "1") return;
    button.dataset.magazineRailButtonBound = "1";

    button.addEventListener("click", () => {
      const scope = button.closest("[data-magazine-rail-scope]");
      const rail = scope?.querySelector("[data-magazine-rail]");
      if (!rail) return;
      const amount = Math.max(260, Math.floor(rail.clientWidth * 0.72));
      rail.scrollBy({
        left: button.hasAttribute("data-magazine-rail-prev") ? amount : -amount,
        behavior: "smooth",
      });
    });
  });
}

export function initMagazinePage() {
  if (document.body.dataset.magazinePageBound === "1") return;
  document.body.dataset.magazinePageBound = "1";

  initStoryViewer();
  initSalonArticlesSlider();
  initMagazineHorizontalRails();
}
