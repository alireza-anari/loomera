export function initMap() {

    if (!window.salonLat || !window.salonLng) return;

    const mapContainer = document.getElementById("salonMap");
    if (!mapContainer) return;

    // ساخت نقشه
    const map = L.map("salonMap", {
        center: [window.salonLat, window.salonLng],
        zoom: 16,
        scrollWheelZoom: false,
    });

    // لایه نقشه
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap contributors",
    }).addTo(map);

    // Marker
    const marker = L.marker([window.salonLat, window.salonLng]).addTo(map);

    marker.bindPopup(`<b>${window.salonName}</b>`).openPopup();


    /* دکمه مسیریابی */
    const btn = document.getElementById("navigateBtn");
    if (btn) {
        btn.addEventListener("click", () => {
            const url = `https://www.google.com/maps/dir/?api=1&destination=${window.salonLat},${window.salonLng}`;
            window.open(url, "_blank");
        });
    }
}
