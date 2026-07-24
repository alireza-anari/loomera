// static/js/components/modal.js

export function openModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.remove("hidden");
}

export function closeModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.add("hidden");
}

export default function initModals() {
    // دکمه‌هایی که مودال را باز می‌کنند
    document.querySelectorAll("[data-modal-open]").forEach(btn => {
        btn.addEventListener("click", () => {
            const id = btn.getAttribute("data-modal-open");
            const modal = document.getElementById(id);
            if (modal) modal.classList.remove("hidden");
        });
    });

    document.querySelectorAll("[data-modal-close]").forEach(btn => {
        btn.addEventListener("click", () => {
            const id = btn.getAttribute("data-modal-close");
            const modal = document.getElementById(id);
            if (modal) modal.classList.add("hidden");
        });
    });

    

    // کلیک روی پس‌زمینه برای بستن
    document.querySelectorAll(".modal-overlay").forEach(overlay => {
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) {
                overlay.classList.add("hidden");
            }
        });
    });

    
}
