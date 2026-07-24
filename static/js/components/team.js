// مدیریت مودال آرایشگران
export function initTeam() {

    /* نمایش همه آرایشگران */
    document.querySelectorAll("[data-modal-open='stylistsModal']").forEach(btn => {
        btn.addEventListener("click", () => {
            document.getElementById("stylistsModal").classList.remove("hidden");
        });
    });

    /* بستن مودال */
    document.querySelectorAll("[data-modal-close='stylistsModal']").forEach(btn => {
        btn.addEventListener("click", () => {
            document.getElementById("stylistsModal").classList.add("hidden");
        });
    });
}
