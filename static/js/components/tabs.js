export function initTabsBehavior() {
    const topbar = document.getElementById("detail_topbar");
    const tabsNav = document.querySelector("nav.sticky");

    if (!topbar || !tabsNav) return;

    const links = Array.from(tabsNav.querySelectorAll("a[href^='#']"));
    const sections = links
        .map(a => document.getElementById(a.getAttribute("href").substring(1)))
        .filter(Boolean);

    function updateSticky() {
        const topbarHeight = topbar.offsetHeight;

        if (window.scrollY > topbarHeight) {
            tabsNav.classList.add("fixed", "top-0", "left-0", "right-0", "z-40", "bg-white", "shadow-md");
            tabsNav.style.top = `${topbarHeight}px`;
        } else {
            tabsNav.classList.remove("fixed", "shadow-md", "bg-white");
            tabsNav.style.top = `auto`;
        }

        const offset = topbarHeight + tabsNav.offsetHeight + 20;

        sections.forEach((sec, i) => {
            const rect = sec.getBoundingClientRect();
            if (rect.top <= offset && rect.bottom > offset) {
                links.forEach(l => l.classList.remove("text-loomera-primaryText", "font-bold"));
                links[i].classList.add("text-loomera-primaryText", "font-bold");
            }
        });
    }

    window.addEventListener("scroll", updateSticky);
    updateSticky();

    links.forEach(link => {
        link.addEventListener("click", e => {
            e.preventDefault();
            const id = link.getAttribute("href").substring(1);
            const sec = document.getElementById(id);
            if (!sec) return;

            const topbarHeight = topbar.offsetHeight;
            const tabsHeight = tabsNav.offsetHeight;
            const target = sec.offsetTop - (topbarHeight + tabsHeight + 10);

            window.scrollTo({ top: target, behavior: "smooth" });
        });
    });
}
