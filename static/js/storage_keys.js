const STORAGE_TYPE = Object.freeze({
  LOCAL: "local",
  SESSION: "session",
});

export const STORAGE_KEYS = Object.freeze({
  dashboardSidebarCollapsed: Object.freeze({
    storage: STORAGE_TYPE.LOCAL,
    key: "loomera:dashboard:sidebar:collapsed",
    legacyKeys: Object.freeze([
      "loomera.dashboard.sidebar.collapsed",
      "salonify.dashboard.sidebar.collapsed",
    ]),
  }),
  bookingSelectionDraft: Object.freeze({
    storage: STORAGE_TYPE.SESSION,
    key: "loomera:booking:selection-draft",
    legacyKeys: Object.freeze(["selected_services"]),
  }),
  bookingSelectedServices: Object.freeze({
    storage: STORAGE_TYPE.SESSION,
    key: "loomera:booking:selected-services",
    legacyKeys: Object.freeze(["selectedServices"]),
  }),
  bookingSelectedServicesData: Object.freeze({
    storage: STORAGE_TYPE.SESSION,
    key: "loomera:booking:selected-services:data",
    legacyKeys: Object.freeze(["selectedServicesData"]),
  }),
  bookingStylistSelections: Object.freeze({
    storage: STORAGE_TYPE.SESSION,
    key: "loomera:booking:stylist-selections",
    legacyKeys: Object.freeze(["stylistSelections"]),
  }),
  bookingSalonId: Object.freeze({
    storage: STORAGE_TYPE.SESSION,
    key: "loomera:booking:salon-id",
    legacyKeys: Object.freeze(["salonId"]),
  }),
  bookingTotalPrice: Object.freeze({
    storage: STORAGE_TYPE.SESSION,
    key: "loomera:booking:total-price",
    legacyKeys: Object.freeze(["totalPrice"]),
  }),
});

function resolveStorage(storageType) {
  if (typeof window === "undefined") return null;

  try {
    return storageType === STORAGE_TYPE.SESSION ? window.sessionStorage : window.localStorage;
  } catch (error) {
    return null;
  }
}

function safeGet(storage, key) {
  try {
    return storage?.getItem(key) ?? null;
  } catch (error) {
    return null;
  }
}

function safeSet(storage, key, value) {
  try {
    storage?.setItem(key, value);
    return true;
  } catch (error) {
    return false;
  }
}

function safeRemove(storage, key) {
  try {
    storage?.removeItem(key);
  } catch (error) {
    // Storage cleanup should never block the user flow.
  }
}

export function readStorageValue(definition, options = {}) {
  const {
    migrate = true,
    removeLegacy = true,
    validate = (value) => value !== null,
  } = options;

  const storage = resolveStorage(definition.storage);
  if (!storage) return null;

  const canonical = safeGet(storage, definition.key);
  if (validate(canonical)) return canonical;

  for (const legacyKey of definition.legacyKeys || []) {
    const legacyValue = safeGet(storage, legacyKey);
    if (!validate(legacyValue)) continue;

    if (migrate) {
      safeSet(storage, definition.key, legacyValue);
      if (removeLegacy) safeRemove(storage, legacyKey);
    }

    return legacyValue;
  }

  return null;
}

export function writeStorageValue(definition, value, options = {}) {
  const { writeLegacy = false, removeLegacy = !writeLegacy } = options;
  const storage = resolveStorage(definition.storage);
  if (!storage) return false;

  const written = safeSet(storage, definition.key, value);

  for (const legacyKey of definition.legacyKeys || []) {
    if (writeLegacy) safeSet(storage, legacyKey, value);
    else if (removeLegacy) safeRemove(storage, legacyKey);
  }

  return written;
}


export function migrateKnownStorageKeys() {
  Object.values(STORAGE_KEYS).forEach((definition) => {
    readStorageValue(definition, { migrate: true, removeLegacy: true });
  });
}

if (typeof window !== "undefined") {
  try {
    migrateKnownStorageKeys();
  } catch (error) {
    // Storage migration must never block the app bootstrap.
  }
}
