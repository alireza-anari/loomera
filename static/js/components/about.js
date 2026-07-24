export function initAboutSection() {
    const desc = document.getElementById("salonDescription");
    const button = document.getElementById("toggleDescriptionBtn");

    if (!desc || !button) return;

    // اگر متن کوتاه بود دکمه نمایش بیشتر نمایش داده نشود
    if (desc.scrollHeight <= desc.clientHeight + 10) {
        button.classList.add("hidden");
        return;
    }

    button.classList.remove("hidden");

    let expanded = false;

    button.addEventListener("click", () => {
        expanded = !expanded;

        if (expanded) {
            desc.classList.remove("max-h-24", "max-h-28");
            button.textContent = "نمایش کمتر";
        } else {
            desc.classList.add("max-h-28");
            button.textContent = "نمایش بیشتر";
        }
    });
}
