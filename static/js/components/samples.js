import { initCarousel } from "./unified_sliders.js";

export function initSamples() {
  const samplesCarousel = document.querySelector('[data-carousel="samples"]');
  if (samplesCarousel) {
    initCarousel(samplesCarousel);
  }

  const fullscreen = document.getElementById("sampleFullscreen");
  const fullscreenImg = document.getElementById("sampleFullscreenImage");
  const fullscreenInfo = document.getElementById("sampleFullscreenInfo");
  const closeBtn = document.getElementById("sampleFullscreenClose");

  function openFullscreen(image, stylist, service) {
    if (!fullscreen || !fullscreenImg || !fullscreenInfo) return;

    fullscreenImg.src = image;
    fullscreenInfo.innerHTML = `
      <div>${stylist}</div>
      <div class="text-gray-300">${service || ""}</div>
    `;
    fullscreen.classList.remove("hidden");
  }

  closeBtn?.addEventListener("click", () => {
    fullscreen?.classList.add("hidden");
  });

  document.querySelectorAll("[data-sample-image]").forEach((item) => {
    item.addEventListener("click", () => {
      openFullscreen(
        item.dataset.sampleImage,
        item.dataset.sampleStylist,
        item.dataset.sampleService
      );
    });
  });
}

export default initSamples;