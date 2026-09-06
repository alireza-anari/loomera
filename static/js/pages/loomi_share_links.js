import { copyText, showToast } from '../utils.js';

document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-loomi-copy]');
    if (!button || button.disabled) return;
    const input = button.closest('[data-loomi-share-link]')?.querySelector('[data-loomi-link-value]');
    if (!input?.value) return;
    button.disabled = true;
    try {
        if (await copyText(input.value)) {
            showToast('لینک لومی کپی شد.', 'success');
        } else {
            input.focus();
            input.select();
            input.setSelectionRange(0, input.value.length);
            showToast('کپی خودکار در دسترس نیست؛ لینک را انتخاب و کپی کن.', 'info');
        }
    } finally {
        button.disabled = false;
    }
});
