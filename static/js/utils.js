// static/js/utils.js
/**
 * ماژول توابع کمکی عمومی
 */

/**
 * دریافت مقدار CSRF Token
 */
export function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

/**
 * فرمت کردن عدد با جداکننده هزارگان
 */
export function formatNumber(number) {
    if (!number && number !== 0) return '0';
    return number.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * نمایش Toast Notification
 */
export function showToast(message, type = 'info', duration = 3000) {
    if (window.LoomeraFeedback?.show) {
        return window.LoomeraFeedback.show(message, type, { duration });
    }
    return null;
}

/**
 * Debounce function
 */
export function debounce(func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

export default {
    getCookie,
    formatNumber,
    showToast,
    debounce
};