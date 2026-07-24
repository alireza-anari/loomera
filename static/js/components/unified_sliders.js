function canAutoPlay(root) {
  return root.dataset.autoplay !== "false";
}

function getInterval(root, fallback = 5000) {
  const value = Number(root.dataset.interval || fallback);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

export function initFadeSlider(root) {
  if (!root) return null;
  if (root.__fadeSliderApi) return root.__fadeSliderApi;

  const slides = Array.from(root.querySelectorAll(".slider-slide"));
  const prevBtn = root.querySelector(".slider-prev");
  const nextBtn = root.querySelector(".slider-next");
  const dots = Array.from(root.querySelectorAll("[data-slider-dot]"));

  if (!slides.length) return null;

  let current = 0;
  let timer = null;
  const autoplay = slides.length > 1 && canAutoPlay(root);
  const interval = getInterval(root, 5500);

  const render = () => {
    slides.forEach((slide, index) => {
      slide.classList.toggle("opacity-100", index === current);
      slide.classList.toggle("opacity-0", index !== current);
      slide.classList.toggle("pointer-events-none", index !== current);
      slide.setAttribute("aria-hidden", index === current ? "false" : "true");
    });

    dots.forEach((dot, index) => {
      dot.classList.toggle("bg-white", index === current);
      dot.classList.toggle("bg-white/40", index !== current);
      dot.setAttribute("aria-current", index === current ? "true" : "false");
    });
  };

  const goTo = (index) => {
    current = (index + slides.length) % slides.length;
    render();
  };

  const goNext = () => goTo(current + 1);
  const goPrev = () => goTo(current - 1);

  const stop = () => {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  };

  const start = () => {
    stop();
    if (!autoplay) return;
    timer = window.setInterval(goNext, interval);
  };

  prevBtn?.addEventListener("click", goPrev);
  nextBtn?.addEventListener("click", goNext);
  dots.forEach((dot, index) => dot.addEventListener("click", () => goTo(index)));

  root.addEventListener("mouseenter", stop);
  root.addEventListener("mouseleave", start);
  root.addEventListener("focusin", stop);
  root.addEventListener("focusout", start);

  let touchStartX = 0;
  root.addEventListener(
    "touchstart",
    (event) => {
      touchStartX = event.touches[0]?.clientX || 0;
    },
    { passive: true }
  );

  root.addEventListener(
    "touchend",
    (event) => {
      const touchEndX = event.changedTouches[0]?.clientX || 0;
      const delta = touchEndX - touchStartX;
      if (Math.abs(delta) < 40) return;
      if (delta < 0) goNext();
      else goPrev();
    },
    { passive: true }
  );

  render();
  start();

  root.__fadeSliderApi = { goNext, goPrev, goTo };
  return root.__fadeSliderApi;
}

export function initCarousel(root) {
  if (!root) return null;
  if (root.__carouselApi) return root.__carouselApi;

  const track = root.querySelector("[data-carousel-track]");
  if (!track) return null;

  const scope = root.closest("[data-carousel-scope]") || root.parentElement || root;
  const prevBtn = root.querySelector("[data-carousel-prev]") || scope.querySelector("[data-carousel-prev]");
  const nextBtn = root.querySelector("[data-carousel-next]") || scope.querySelector("[data-carousel-next]");
  const dots = Array.from(
    (root.querySelectorAll("[data-carousel-dot]").length ? root : scope).querySelectorAll("[data-carousel-dot]")
  );
  const items = Array.from(track.children).filter((child) => child instanceof HTMLElement);

  if (!items.length) return null;

  const isRtl = () => (window.getComputedStyle(track).direction || document.dir || "rtl") === "rtl";

  const getVisibleIndex = () => {
    const trackRect = track.getBoundingClientRect();
    const startEdge = isRtl() ? trackRect.right : trackRect.left;

    let bestIndex = 0;
    let bestDistance = Number.POSITIVE_INFINITY;

    items.forEach((item, index) => {
      const rect = item.getBoundingClientRect();
      const itemStart = isRtl() ? rect.right : rect.left;
      const distance = Math.abs(itemStart - startEdge);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    });

    return bestIndex;
  };

  const sync = () => {
    const index = getVisibleIndex();
    prevBtn?.toggleAttribute("disabled", index <= 0);
    nextBtn?.toggleAttribute("disabled", index >= items.length - 1);

    dots.forEach((dot, dotIndex) => {
      dot.classList.toggle("bg-gray-900", dotIndex === index);
      dot.classList.toggle("bg-gray-300", dotIndex !== index);
      dot.setAttribute("aria-current", dotIndex === index ? "true" : "false");
    });
  };

  const scrollToIndex = (index) => {
    const bounded = Math.max(0, Math.min(index, items.length - 1));
    const target = items[bounded];
    if (!target) return;
    target.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
      inline: isRtl() ? "end" : "start",
    });
    window.setTimeout(sync, 260);
  };

  const scrollPrev = () => scrollToIndex(getVisibleIndex() - 1);
  const scrollNext = () => scrollToIndex(getVisibleIndex() + 1);

  prevBtn?.addEventListener("click", (event) => {
    event.preventDefault();
    scrollPrev();
  });
  nextBtn?.addEventListener("click", (event) => {
    event.preventDefault();
    scrollNext();
  });
  dots.forEach((dot, index) => dot.addEventListener("click", () => scrollToIndex(index)));

  let isPointerDown = false;
  let startX = 0;
  let startScrollLeft = 0;

  track.addEventListener("pointerdown", (event) => {
    isPointerDown = true;
    startX = event.clientX;
    startScrollLeft = track.scrollLeft;
    track.classList.add("cursor-grabbing");
  });

  track.addEventListener("pointermove", (event) => {
    if (!isPointerDown) return;
    const delta = event.clientX - startX;
    track.scrollLeft = startScrollLeft - delta;
  });

  const releasePointer = () => {
    if (!isPointerDown) return;
    isPointerDown = false;
    track.classList.remove("cursor-grabbing");
    sync();
  };

  track.addEventListener("pointerup", releasePointer);
  track.addEventListener("pointerleave", releasePointer);
  track.addEventListener("pointercancel", releasePointer);

  track.addEventListener("scroll", sync, { passive: true });
  window.addEventListener("resize", sync);
  sync();

  root.__carouselApi = { scrollPrev, scrollNext, scrollToIndex, sync };
  return root.__carouselApi;
}

export function initAllUnifiedSliders() {
  document.querySelectorAll("[data-slider-id]").forEach((root) => initFadeSlider(root));
  document.querySelectorAll("[data-carousel]").forEach((root) => initCarousel(root));
}

export default initAllUnifiedSliders;
