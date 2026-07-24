import { initFadeSlider, initAllUnifiedSliders } from "./unified_sliders.js";

export function initSlider(root) {
  return initFadeSlider(root);
}

export function initAllSliders() {
  return initAllUnifiedSliders();
}

export default initAllSliders;