export function initReviews() {

    /* 1) باز/بستن فرم ثبت نظر */
    const formContainer = document.getElementById("reviewFormContainer");
    const openFormBtn = document.getElementById("openReviewFormBtn");
    const cancelFormBtn = document.getElementById("cancelReviewFormBtn");

    openFormBtn?.addEventListener("click", () => {
        formContainer.classList.remove("hidden");
    });

    cancelFormBtn?.addEventListener("click", () => {
        formContainer.classList.add("hidden");
    });


    /* 2) شمارش کاراکتر textarea */
    const textarea = document.querySelector("textarea[name='comment_text']");
    const counter = document.getElementById("charCounter");

    if (textarea && counter) {
        textarea.addEventListener("input", () => {
            const len = textarea.value.length;
            counter.textContent = `${len}/500`;
        });
    }


    /* 3) مودال همه دیدگاه‌ها */
    document.querySelectorAll("[data-modal-open='reviewsModal']").forEach(btn => {
        btn.addEventListener("click", () => {
            loadReviews();
            document.getElementById("reviewsModal").classList.remove("hidden");
        });
    });

    document.querySelectorAll("[data-modal-close='reviewsModal']").forEach(btn => {
        btn.addEventListener("click", () => {
            document.getElementById("reviewsModal").classList.add("hidden");
        });
    });


    /* 4) فیلتر دیدگاه‌ها بر اساس ستاره */
    const filters = document.querySelectorAll(".review-filter-star");
    filters.forEach(f => f.addEventListener("change", loadReviews));


    /* 5) ساخت HTML برای هر دیدگاه */
    function renderReview(item) {
        return `
        <div class="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
            <div class="flex items-center gap-3 mb-2">
                <img src="${item.avatar_url || '/static/images/default-avatar.png'}"
                     class="w-10 h-10 rounded-full object-cover">
                <div>
                    <p class="text-sm font-semibold text-gray-800">${item.user_full_name}</p>
                    <p class="text-xs text-gray-500">${item.date}</p>
                </div>
            </div>

            <div class="flex items-center text-yellow-400 mb-2">
                ${"★".repeat(item.score)}${"☆".repeat(5 - item.score)}
            </div>

            <p class="text-sm text-gray-800">${item.comment_text}</p>
        </div>
        `;
    }


    /* 6) لود دیدگاه‌ها */
    function loadReviews() {
        const container = document.getElementById("allReviewsContainer");
        const activeStars = [...document.querySelectorAll(".review-filter-star:checked")].map(i => parseInt(i.value));

        const list = (window.allReviews || []).filter(r => activeStars.includes(r.score));

        container.innerHTML = list.map(renderReview).join("");

        document.getElementById("reviewsCountDisplay").textContent =
            `${list.length} دیدگاه`;
    }

}
