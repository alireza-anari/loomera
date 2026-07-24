export default function initBookingBar(options = {}) {

    let totalCount = 0;
    let totalPrice = 0;
    let totalDuration = 0;

    const elCount = document.getElementById("bookingCount");
    const elPrice = document.getElementById("bookingPrice");
    const elDuration = document.getElementById("bookingDuration");

    const submitBtn = document.getElementById("bookingSubmitBtn");


    /* ---------------------------- */
    /*   به‌روزرسانی UI             */
    /* ---------------------------- */
    function updateUI() {
        elCount.textContent = `${totalCount} خدمت`;
        elPrice.textContent = `${totalPrice.toLocaleString()} تومان`;
        elDuration.textContent = `${totalDuration} دقیقه`;
    }


    /* ---------------------------- */
    /*   افزودن/حذف یک خدمت         */
    /* ---------------------------- */
    function addService(price, duration) {
        totalCount += (price > 0 ? 1 : -1);
        totalPrice += price;
        totalDuration += duration;

        // جلوگیری از منفی شدن
        if (totalCount < 0) totalCount = 0;
        if (totalPrice < 0) totalPrice = 0;
        if (totalDuration < 0) totalDuration = 0;

        updateUI();
    }


    /* ---------------------------- */
    /*   دکمه رزرو نهایی            */
    /* ---------------------------- */
    submitBtn?.addEventListener("click", () => {

        if (totalCount === 0) {
            alert("لطفاً حداقل یک خدمت انتخاب کنید.");
            return;
        }

        const salonId = submitBtn.dataset.salonId;
        const bookingUrl = submitBtn.dataset.bookingUrl;

        // قبل از رفتن به صفحه انتخاب آرایشگر:
        if (options.onSubmit) {
            options.onSubmit({
                count: totalCount,
                price: totalPrice,
                duration: totalDuration
            });
        }

        // انتقال به صفحه انتخاب آرایشگر
        window.location.href = `${bookingUrl}?salon_id=${salonId}`;
    });


    /* ---------------------------- */
    /* خروجی کامپوننت               */
    /* ---------------------------- */
    return {
        addService,
    };
}