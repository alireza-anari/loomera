// static/js/components/services.js

import initBookingBar from "./bookingBar.js";
import { STORAGE_KEYS, writeStorageValue } from "../storage_keys.js";

export function initServices() {

    /* ------------------------- */
    /* 1) مدیریت گروه‌بندی      */
    /* ------------------------- */

    const groupButtons = document.querySelectorAll(".service-group-btn");
    const serviceItems = document.querySelectorAll(".service-item");

    groupButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const group = btn.dataset.group;

            // دکمه فعال
            groupButtons.forEach(b => b.classList.remove("bg-loomera-primary", "text-white", "border-loomera-primary"));
            groupButtons.forEach(b => b.classList.add("bg-white", "text-gray-700", "border-gray-300"));

            btn.classList.remove("bg-white", "text-gray-700", "border-gray-300");
            btn.classList.add("bg-loomera-primary", "text-white", "border-loomera-primary");

            // نمایش خدمات
            serviceItems.forEach(item => {
                if (item.classList.contains(group)) item.classList.remove("hidden");
                else item.classList.add("hidden");
            });
        });
    });


    /* ------------------------- */
    /* 2) مدیریت افزودن خدمات به رزرو */
    /* ------------------------- */

    // ذخیره خدمات انتخاب شده
    const selectedServices = new Set();
    const selectedServicesData = {};

    const booking = initBookingBar({
        onSubmit: ({ count, price, duration }) => {
            if (selectedServices.size === 0) {
                alert("لطفاً حداقل یک خدمت انتخاب کنید.");
                return;
            }

            // ذخیره انتخاب‌های رزرو با namespace جدید Loomera و aliasهای موقت برای compatibility
            const servicesArray = Array.from(selectedServices);
            writeStorageValue(
                STORAGE_KEYS.bookingSelectedServices,
                JSON.stringify(servicesArray),
                { writeLegacy: true }
            );
            writeStorageValue(
                STORAGE_KEYS.bookingSelectedServicesData,
                JSON.stringify(selectedServicesData),
                { writeLegacy: true }
            );

            // انتقال به صفحه انتخاب آرایشگر
            const submitBtn = document.getElementById("bookingSubmitBtn");
            const salonId = submitBtn.dataset.salonId;
            const bookingUrl = submitBtn.dataset.bookingUrl;
            
            window.location.href = `${bookingUrl}?salon_id=${salonId}&selected_services=${servicesArray.join(',')}`;
        }
    });

    document.querySelectorAll(".add-service-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            
            const parent = e.target.closest(".service-item");
            if (!parent) return;

            const serviceId = parent.dataset.serviceId;
            const serviceName = parent.dataset.serviceName;
            const price = parseInt(parent.dataset.servicePrice.replace(/,/g, "")) || 0;
            const duration = parseInt(parent.dataset.serviceDuration) || 0;

            // اگر قبلاً انتخاب شده بود، حذف می‌کنیم
            if (selectedServices.has(serviceId)) {
                selectedServices.delete(serviceId);
                delete selectedServicesData[serviceId];
                parent.classList.remove("border-loomera-primary", "bg-loomera-primarySoft");
                parent.classList.add("border-loomera-primary/25");
                btn.innerHTML = '<i class="fa-solid fa-plus"></i>';
                btn.classList.remove("bg-red-500");
                btn.classList.add("bg-loomera-primary");
                
                // کم کردن از booking bar
                booking.addService(-price, -duration);
            } else {
                // اضافه کردن
                selectedServices.add(serviceId);
                selectedServicesData[serviceId] = {
                    id: serviceId,
                    name: serviceName,
                    price: price,
                    duration: duration
                };
                parent.classList.add("border-loomera-primary", "bg-loomera-primarySoft");
                parent.classList.remove("border-loomera-primary/25");
                btn.innerHTML = '<i class="fa-solid fa-check"></i>';
                btn.classList.remove("bg-loomera-primary");
                btn.classList.add("bg-red-500");
                
                // اضافه کردن به booking bar
                booking.addService(price, duration);
            }
        });
    });

}