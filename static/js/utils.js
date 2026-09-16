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

/** Copy text with a fallback for older/mobile browsers and denied permissions. */
export async function copyText(text) {
    try {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
            return true;
        }
    } catch (_error) {
        // Try the legacy copy path before asking for manual selection.
    }
    const previousFocus = document.activeElement;
    const helper = document.createElement('textarea');
    helper.value = text;
    helper.setAttribute('readonly', '');
    helper.style.position = 'fixed';
    helper.style.opacity = '0';
    document.body.appendChild(helper);
    try {
        helper.focus();
        helper.select();
        helper.setSelectionRange(0, text.length);
        return Boolean(document.execCommand('copy'));
    } catch (_error) {
        return false;
    } finally {
        helper.remove();
        previousFocus?.focus();
    }
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
    copyText,
    debounce
};
