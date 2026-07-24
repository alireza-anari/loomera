// static/js/components/stylistCard.js

/**
 * کامپوننت StylistCard
 * برای نمایش کارت آرایشگر در صفحات مختلف
 */

export const StylistCard = (() => {
    /**
     * ساخت HTML کارت آرایشگر
     * @param {Object} stylist - اطلاعات آرایشگر
     * @param {Object} options - تنظیمات اضافی
     * @returns {string} HTML string
     */
    function render(stylist, options = {}) {
        const {
            showSelectButton = true,
            showProfile = true,
            showRating = true,
            isSelected = false,
            onSelect = null,
            cssClass = ''
        } = options;

        const hasImage = stylist.profile_image && stylist.profile_image !== '';
        const displayName = stylist.full_name || `${stylist.first_name} ${stylist.last_name}`;
        const firstLetter = stylist.first_name ? stylist.first_name.charAt(0) : 'A';
        const avgScore = stylist.avg_score || stylist.rating;

        return `
            <div class="stylist-card ${cssClass} ${isSelected ? 'selected' : ''}" 
                 data-stylist-id="${stylist.id}">
                <div class="flex items-center justify-between gap-3">
                    <!-- Avatar -->
                    <div class="flex items-center gap-3 flex-1 min-w-0">
                        ${renderAvatar(hasImage, stylist.profile_image, displayName, firstLetter)}
                        
                        <!-- Info -->
                        <div class="flex-1 min-w-0">
                            <h3 class="text-sm font-semibold text-gray-900 truncate">
                                ${displayName}
                            </h3>
                            
                            ${showRating && avgScore ? renderRating(avgScore) : ''}
                            
                            ${showProfile ? `
                                <button class="text-xs text-indigo-600 hover:underline mt-0.5"
                                        onclick="event.stopPropagation(); showStylistProfile(${stylist.id}, event)">
                                    مشاهده پروفایل
                                </button>
                            ` : ''}
                        </div>
                    </div>

                    <!-- Select Button or Checkmark -->
                    ${showSelectButton ? renderSelectButton(isSelected) : renderCheckmark(isSelected)}
                </div>
            </div>
        `;
    }

    /**
     * رندر آواتار
     */
    function renderAvatar(hasImage, imageUrl, displayName, firstLetter) {
        if (hasImage) {
            return `
                <img src="${imageUrl}" 
                     alt="${displayName}"
                     class="w-12 h-12 rounded-full object-cover shrink-0 border-2 border-gray-200">
            `;
        } else {
            return `
                <div class="w-12 h-12 rounded-full bg-gradient-to-br from-loomera-secondary to-pink-400 
                            flex items-center justify-center shrink-0 border-2 border-gray-200">
                    <span class="text-white text-lg font-bold">
                        ${firstLetter}
                    </span>
                </div>
            `;
        }
    }

    /**
     * رندر امتیاز
     */
    function renderRating(score) {
        return `
            <div class="flex items-center gap-1 mt-0.5">
                <i class="fas fa-star text-yellow-400 text-xs"></i>
                <span class="text-xs text-gray-600">${score.toFixed(1)}</span>
            </div>
        `;
    }

    /**
     * رندر دکمه انتخاب
     */
    function renderSelectButton(isSelected) {
        return `
            <button class="select-btn px-4 py-1.5 rounded-full border ${
                isSelected 
                    ? 'border-indigo-600 bg-indigo-600 text-white' 
                    : 'border-gray-300 text-gray-700 hover:border-indigo-600 hover:text-indigo-600'
            } text-sm transition-colors shrink-0 whitespace-nowrap">
                ${isSelected ? 'انتخاب شده' : 'انتخاب'}
            </button>
        `;
    }

    /**
     * رندر علامت چک
     */
    function renderCheckmark(isSelected) {
        return `
            <div class="checkmark-circle w-6 h-6 rounded-full border-2 ${
                isSelected 
                    ? 'border-indigo-600 bg-indigo-600' 
                    : 'border-gray-300'
            } flex items-center justify-center transition-all shrink-0">
                <i class="fas fa-check text-white text-xs ${isSelected ? '' : 'hidden'}"></i>
            </div>
        `;
    }

    /**
     * کارت "هر متخصصی"
     */
    function renderAnyProfessional(options = {}) {
        const {
            isSelected = false,
            cssClass = ''
        } = options;

        return `
            <div class="stylist-card any-professional ${cssClass} ${isSelected ? 'selected' : ''}"
                 data-stylist-id="any">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        <div class="w-12 h-12 rounded-full bg-indigo-50 flex items-center justify-center shrink-0">
                            <i class="fas fa-users text-indigo-600 text-lg"></i>
                        </div>
                        
                        <div class="flex-1">
                            <h3 class="text-sm font-semibold text-gray-900">هر متخصصی</h3>
                            <p class="text-xs text-gray-500 mt-0.5">برای حداکثر در دسترس بودن</p>
                        </div>
                    </div>

                    ${renderCheckmark(isSelected)}
                </div>
            </div>
        `;
    }

    /**
     * ساخت المنت DOM از HTML string
     */
    function createElement(htmlString) {
        const template = document.createElement('template');
        template.innerHTML = htmlString.trim();
        return template.content.firstChild;
    }

    /**
     * رندر کارت در یک container
     */
    function renderTo(container, stylist, options = {}) {
        if (!container) return null;

        const html = render(stylist, options);
        const element = createElement(html);
        
        container.appendChild(element);
        
        return element;
    }

    /**
     * رندر لیستی از آرایشگران
     */
    function renderList(container, stylists, options = {}) {
        if (!container || !Array.isArray(stylists)) return;

        const {
            includeAnyOption = true,
            ...restOptions
        } = options;

        // پاک کردن محتوای قبلی
        container.innerHTML = '';

        // افزودن گزینه "هر متخصصی"
        if (includeAnyOption) {
            const anyHtml = renderAnyProfessional(restOptions);
            const anyElement = createElement(anyHtml);
            container.appendChild(anyElement);
        }

        // افزودن آرایشگران
        stylists.forEach(stylist => {
            renderTo(container, stylist, restOptions);
        });
    }

    // Public API
    return {
        render,
        renderTo,
        renderList,
        renderAnyProfessional,
        createElement
    };
})();

// Export for use in other modules
export default StylistCard;