/**
 * Select Stylist Module - Customer-side synced pricing
 * Phase 09: presentation-safe visual state and summary upgrades.
 */

(function() {
    'use strict';

    const state = {
        salonId: null,
        services: {},
        requiredServices: []
    };

    const STORAGE_KEYS = Object.freeze({
        stylistSelections: Object.freeze({
            key: 'loomera:booking:stylist-selections',
            legacyKeys: Object.freeze(['stylistSelections']),
        }),
        salonId: Object.freeze({
            key: 'loomera:booking:salon-id',
            legacyKeys: Object.freeze(['salonId']),
        }),
        totalPrice: Object.freeze({
            key: 'loomera:booking:total-price',
            legacyKeys: Object.freeze(['totalPrice']),
        }),
    });

    function writeSessionValue(definition, value, { writeLegacy = true } = {}) {
        try {
            sessionStorage.setItem(definition.key, value);
            if (writeLegacy) {
                definition.legacyKeys.forEach((legacyKey) => sessionStorage.setItem(legacyKey, value));
            }
        } catch (error) {
            // Booking can continue with form POST even if sessionStorage is unavailable.
        }
    }

    function parseAmount(value) {
        const normalized = String(value || '')
            .replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d))
            .replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d))
            .replace(/[^\d-]/g, '');
        const amount = parseInt(normalized, 10);
        return Number.isFinite(amount) ? amount : 0;
    }

    function formatAmount(value) {
        return Number(value || 0).toLocaleString('fa-IR');
    }

    function init() {
        try {
            loadPageData();
            setupEventListeners();
            updateContinueButton();
        } catch (error) {
            console.error('❌ Initialization error:', error);
            alert('صفحه به‌درستی بارگذاری نشد. لطفاً دوباره تلاش کنید.');
        }
    }

    function loadPageData() {
        const salonIdElement = document.querySelector('[data-salon-id]');
        if (salonIdElement) {
            state.salonId = parseInt(salonIdElement.dataset.salonId, 10);
        }

        document.querySelectorAll('[data-service-id]').forEach(element => {
            const serviceId = element.dataset.serviceId;
            const serviceName = element.dataset.serviceName;
            const serviceDuration = parseInt(element.dataset.serviceDuration, 10) || 60;

            if (serviceId && !state.requiredServices.find(s => s.id === serviceId)) {
                state.requiredServices.push({
                    id: serviceId,
                    name: serviceName,
                    duration: serviceDuration
                });
            }
        });
    }

    function setupEventListeners() {
        document.querySelectorAll('.stylist-option').forEach(button => {
            button.addEventListener('click', handleStylistSelection);
        });

        const continueBtn = document.getElementById('continueBtn');
        if (continueBtn) {
            continueBtn.addEventListener('click', handleContinue);
        }

        const desktopContinueBtn = document.getElementById('desktopContinueBtn');
        if (desktopContinueBtn) {
            desktopContinueBtn.addEventListener('click', handleContinue);
        }
    }

    function buildSelectionFromButton(button) {
        return {
            serviceId: button.dataset.serviceId,
            serviceName: button.dataset.serviceName,
            serviceDuration: parseInt(button.dataset.serviceDuration, 10) || 60,
            requestedStylistId: button.dataset.stylistId,
            requestedStylistName: button.dataset.stylistName,
            stylistId: button.dataset.stylistId,
            stylistName: button.dataset.stylistName,
            stylistProfileImage: button.dataset.stylistProfileImage || null,
            stylistPrice: parseAmount(button.dataset.stylistPrice || 0)
        };
    }

    function handleStylistSelection(event) {
        const button = event.currentTarget;
        if (button.disabled || button.getAttribute('aria-disabled') === 'true') return;

        const serviceId = button.dataset.serviceId;
        if (!serviceId) return;

        state.services[serviceId] = buildSelectionFromButton(button);
        updateSelectionUI(button);
        updateContinueButton();
    }

    function updateSelectionUI(selectedButton) {
        const serviceCard = selectedButton.closest('[data-staff-service-card]') || selectedButton.closest('.bg-white.rounded-2xl');
        if (!serviceCard) return;

        serviceCard.querySelectorAll('.stylist-option').forEach(btn => {
            btn.classList.remove('is-selected', 'border-loomera-primary', 'bg-loomera-primarySoft');
            btn.classList.add('border-gray-200');
            btn.setAttribute('aria-pressed', 'false');
            btn.setAttribute('aria-selected', 'false');

            const indicator = btn.querySelector('.selection-indicator');
            if (indicator) {
                indicator.classList.add('hidden');
                indicator.classList.remove('scale-100');
            }
        });

        selectedButton.classList.remove('border-gray-200');
        selectedButton.classList.add('is-selected', 'border-loomera-primary', 'bg-loomera-primarySoft');
        selectedButton.setAttribute('aria-pressed', 'true');
        selectedButton.setAttribute('aria-selected', 'true');

        const indicator = selectedButton.querySelector('.selection-indicator');
        if (indicator) {
            indicator.classList.remove('hidden');
            indicator.classList.add('scale-100');
        }

        updateServiceSummaryLabel(selectedButton.dataset.serviceId, selectedButton.dataset.stylistName);
    }

    function updateServiceSummaryLabel(serviceId, stylistName) {
        if (!serviceId) return;
        const escapedServiceId = window.CSS && CSS.escape ? CSS.escape(serviceId) : String(serviceId).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
        const target = document.querySelector(`[data-summary-service-status="${escapedServiceId}"]`);
        if (target) {
            target.textContent = stylistName ? stylistName : 'متخصص انتخاب شد';
            target.classList.remove('text-slate-500');
            target.classList.add('text-loomera-primaryText', 'font-bold');
        }
    }

    function handleContinue() {
        if (!isAllServicesSelected()) {
            alert('لطفاً برای همه خدمات، متخصص را انتخاب کنید.');
            return;
        }

        submitSelections();
    }

    function isAllServicesSelected() {
        return state.requiredServices.every(service => state.services[service.id] !== undefined);
    }

    function getTotalSelectedPrice() {
        return Object.values(state.services).reduce((sum, service) => sum + parseAmount(service.stylistPrice), 0);
    }

    function getSelectedDuration() {
        return Object.values(state.services).reduce((sum, service) => sum + (parseInt(service.serviceDuration, 10) || 0), 0);
    }

    function updateText(id, value) {
        const element = document.getElementById(id);
        if (element) element.textContent = value;
    }

    function updateContinueButton() {
        const btn = document.getElementById('continueBtn');
        const desktopBtn = document.getElementById('desktopContinueBtn');
        const allSelected = isAllServicesSelected();
        const selectedCount = Object.keys(state.services).length;
        const requiredCount = state.requiredServices.length;
        const remaining = Math.max(requiredCount - selectedCount, 0);
        const totalPrice = getTotalSelectedPrice();
        const totalDuration = getSelectedDuration();

        [btn, desktopBtn].forEach((button) => {
            if (!button) return;
            button.disabled = !allSelected;
            button.textContent = allSelected ? 'ادامه انتخاب زمان' : `${formatAmount(remaining)} خدمت باقی مانده`;
        });

        updateText('selectedStaffCount', formatAmount(selectedCount));
        updateText('staffRemainingCount', formatAmount(remaining));
        updateText('staffDesktopTotal', totalPrice > 0 ? `${formatAmount(totalPrice)} تومان` : '—');

        const mobileSummary = document.getElementById('staffMobileSummary');
        if (mobileSummary) {
            if (allSelected) {
                const parts = [`${formatAmount(selectedCount)} متخصص انتخاب شد`];
                if (totalPrice > 0) parts.push(`${formatAmount(totalPrice)} تومان`);
                if (totalDuration > 0) parts.push(`${formatAmount(totalDuration)} دقیقه`);
                mobileSummary.textContent = parts.join(' • ');
            } else {
                mobileSummary.textContent = `${formatAmount(remaining)} خدمت هنوز متخصص ندارد`;
            }
        }
    }

    function submitSelections() {
        const selections = Object.values(state.services);
        const totalPrice = getTotalSelectedPrice();

        const input = document.getElementById('stylistSelectionsInput');
        if (input) {
            input.value = JSON.stringify(selections);
        }

        writeSessionValue(STORAGE_KEYS.stylistSelections, JSON.stringify(selections));
        writeSessionValue(STORAGE_KEYS.salonId, String(state.salonId));
        writeSessionValue(STORAGE_KEYS.totalPrice, String(totalPrice));

        const form = document.getElementById('stylistSelectionForm');
        if (form) {
            form.submit();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.SelectStylist = {
        state: state,
        reload: init
    };
})();
