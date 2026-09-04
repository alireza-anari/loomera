document.addEventListener("DOMContentLoaded", function () {
  const root = document.querySelector("[data-lm-home]");

  if (!root) {
    return;
  }

  const reduceMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  const finePointer = window.matchMedia("(pointer: fine)").matches;
  const sections = Array.from(root.querySelectorAll(".lm-reveal"));
  const hero = root.querySelector(".lm-home-hero");
  const productCards = Array.from(root.querySelectorAll(".lm-product-showcase"));

  root.classList.add("lm-motion-ready");

  /* Product stories enter from alternating directions on desktop. */
  productCards.forEach(function (card, index) {
    card.classList.add(
      index % 2 === 0 ? "lm-enter-inline-start" : "lm-enter-inline-end"
    );
  });

  const staggerSelectors = [
    ".lm-audience-card",
    ".lm-flow article",
    ".lm-final-option"
  ];

  const staggerItems = [];

  staggerSelectors.forEach(function (selector) {
    Array.from(root.querySelectorAll(selector)).forEach(function (item, index) {
      item.classList.add("lm-stagger-item");
      item.style.setProperty("--lm-delay", index * 70 + "ms");
      staggerItems.push(item);
    });
  });

  /* Product internals animate after the card itself enters. */
  productCards.forEach(function (card) {
    const copy = card.querySelector(".lm-product-copy");
    const screen = card.querySelector(".lm-product-screen");

    if (copy) {
      copy.classList.add("lm-product-copy-motion");
    }

    if (screen) {
      screen.classList.add("lm-product-screen-motion");
    }
  });

  if (reduceMotion) {
    root.classList.add("lm-reduced-motion");

    sections.forEach(function (section) {
      section.classList.add("is-visible");
    });

    staggerItems.forEach(function (item) {
      item.classList.add("lm-inview");
    });

    productCards.forEach(function (card) {
      card.classList.add("lm-product-visible");
    });

    if (hero) {
      hero.classList.add("lm-hero-ready");
    }

    return;
  }

  /* Slim brand progress indicator. */
  const progressBar = document.createElement("div");
  progressBar.className = "lm-scroll-progress";
  progressBar.setAttribute("aria-hidden", "true");
  progressBar.innerHTML = "<span></span>";
  document.body.appendChild(progressBar);

  requestAnimationFrame(function () {
    if (hero) {
      hero.classList.add("lm-hero-ready");
    }
  });

  if (!("IntersectionObserver" in window)) {
    sections.forEach(function (section) {
      section.classList.add("is-visible");
    });

    staggerItems.forEach(function (item) {
      item.classList.add("lm-inview");
    });

    productCards.forEach(function (card) {
      card.classList.add("lm-product-visible");
    });

    return;
  }

  const sectionObserver = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) {
          return;
        }

        entry.target.classList.add("is-visible");
        sectionObserver.unobserve(entry.target);
      });
    },
    {
      threshold: 0.11,
      rootMargin: "0px 0px -8% 0px"
    }
  );

  sections.forEach(function (section) {
    sectionObserver.observe(section);
  });

  const itemObserver = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) {
          return;
        }

        entry.target.classList.add("lm-inview");
        itemObserver.unobserve(entry.target);
      });
    },
    {
      threshold: 0.18,
      rootMargin: "0px 0px -8% 0px"
    }
  );

  staggerItems.forEach(function (item) {
    itemObserver.observe(item);
  });

  const productObserver = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) {
          return;
        }

        entry.target.classList.add("lm-product-visible");
        productObserver.unobserve(entry.target);
      });
    },
    {
      threshold: 0.18,
      rootMargin: "0px 0px -10% 0px"
    }
  );

  productCards.forEach(function (card) {
    productObserver.observe(card);
  });

  if (sections[0]) {
    sections[0].classList.add("is-visible");
  }

  const parallaxTargets = [
    root.querySelector(".lm-hero-phone"),
    ...Array.from(root.querySelectorAll(".lm-product-screen"))
  ].filter(Boolean);

  let ticking = false;

  const updateScrollEffects = function () {
    ticking = false;

    const scrollTop = window.scrollY || window.pageYOffset;
    const doc = document.documentElement;
    const maxScroll = Math.max(doc.scrollHeight - window.innerHeight, 1);
    const percent = Math.min(Math.max((scrollTop / maxScroll) * 100, 0), 100);

    document.documentElement.style.setProperty(
      "--lm-scroll-percent",
      percent.toFixed(2)
    );

    /*
     * Parallax is deliberately desktop/tablet only.
     * Mobile gets transform-free layout to avoid image overlap/jank.
     */
    if (!finePointer || window.innerWidth <= 900) {
      parallaxTargets.forEach(function (target) {
        target.style.removeProperty("--lm-scroll-shift");
      });
      return;
    }

    parallaxTargets.forEach(function (target) {
      const rect = target.getBoundingClientRect();
      const viewportCenter = window.innerHeight * 0.5;
      const distance = rect.top + rect.height * 0.5 - viewportCenter;
      const shift = Math.max(Math.min(distance * -0.028, 10), -10);

      target.style.setProperty(
        "--lm-scroll-shift",
        shift.toFixed(2) + "px"
      );
    });
  };

  const requestTick = function () {
    if (ticking) {
      return;
    }

    ticking = true;
    window.requestAnimationFrame(updateScrollEffects);
  };

  updateScrollEffects();

  window.addEventListener("scroll", requestTick, { passive: true });
  window.addEventListener("resize", requestTick);
});
