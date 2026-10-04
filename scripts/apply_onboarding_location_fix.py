from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def write(path, text):
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path, old, new):
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}: {old[:90]!r}")
    write(path, text.replace(old, new, 1))


def regex_once(path, pattern, replacement):
    text = read(path)
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{path}: regex expected exactly one match, found {count}")
    write(path, updated)


# Salon persistence: keep legacy numeric `zone`, add nationwide city + textual area.
replace_once(
    "apps/salons/models.py",
    '    zone = models.PositiveIntegerField(verbose_name="منطقه ", null=True, blank=True)\n',
    '    zone = models.PositiveIntegerField(verbose_name="منطقه ", null=True, blank=True)\n'
    '    city = models.CharField(max_length=100, blank=True, default="", db_index=True, verbose_name="شهر")\n'
    '    zone_label = models.CharField(max_length=100, blank=True, default="", verbose_name="منطقه / ناحیه")\n',
)

# Form carries city/zone label as hidden geocoder metadata and writes it onto Salon.
replace_once(
    "apps/salons/forms.py",
    '    longitude = forms.FloatField(required=False, widget=forms.HiddenInput())\n'
    '    neighborhood_name = forms.CharField(required=False, widget=forms.HiddenInput())\n',
    '    longitude = forms.FloatField(required=False, widget=forms.HiddenInput())\n'
    '    city = forms.CharField(required=False, max_length=100, widget=forms.HiddenInput())\n'
    '    neighborhood_name = forms.CharField(required=False, widget=forms.HiddenInput())\n',
)
replace_once(
    "apps/salons/forms.py",
    '        if instance and getattr(instance, "pk", None):\n'
    '            if getattr(instance, "neighborhood_id", None):\n'
    '                self.fields["neighborhood_name"].initial = instance.neighborhood.name\n'
    '            if getattr(instance, "zone", None):\n'
    '                self.fields["zone_label"].initial = f"منطقه {instance.zone}"\n',
    '        if instance and getattr(instance, "pk", None):\n'
    '            if getattr(instance, "neighborhood_id", None):\n'
    '                self.fields["neighborhood_name"].initial = instance.neighborhood.name\n'
    '            self.fields["city"].initial = getattr(instance, "city", "") or ""\n'
    '            stored_zone_label = getattr(instance, "zone_label", "") or ""\n'
    '            if stored_zone_label:\n'
    '                self.fields["zone_label"].initial = stored_zone_label\n'
    '            elif getattr(instance, "zone", None):\n'
    '                self.fields["zone_label"].initial = f"منطقه {instance.zone}"\n',
)
replace_once(
    "apps/salons/forms.py",
    '    def clean_neighborhood_name(self):\n'
    '        return (self.cleaned_data.get("neighborhood_name") or "").strip()\n\n'
    '    def clean_zone_label(self):\n',
    '    def clean_city(self):\n'
    '        return (self.cleaned_data.get("city") or "").strip()\n\n'
    '    def clean_neighborhood_name(self):\n'
    '        return (self.cleaned_data.get("neighborhood_name") or "").strip()\n\n'
    '    def clean_zone_label(self):\n',
)
replace_once(
    "apps/salons/forms.py",
    '    def clean(self):\n'
    '        cleaned_data = super().clean()\n'
    '        latitude = cleaned_data.get("latitude")\n'
    '        longitude = cleaned_data.get("longitude")\n\n'
    '        if latitude is None or longitude is None:\n'
    '            raise forms.ValidationError("لطفاً موقعیت مجموعه را روی نقشه انتخاب کنید.")\n\n'
    '        return cleaned_data\n\n\n# -----------------------------------------------------------------\nclass SalonOpeningHoursForm',
    '    def clean(self):\n'
    '        cleaned_data = super().clean()\n'
    '        latitude = cleaned_data.get("latitude")\n'
    '        longitude = cleaned_data.get("longitude")\n\n'
    '        if latitude is None or longitude is None:\n'
    '            raise forms.ValidationError("لطفاً موقعیت مجموعه را روی نقشه انتخاب کنید.")\n\n'
    '        return cleaned_data\n\n'
    '    def save(self, commit=True):\n'
    '        salon = super().save(commit=False)\n'
    '        salon.city = self.cleaned_data.get("city") or ""\n'
    '        salon.zone_label = self.cleaned_data.get("zone_label") or ""\n'
    '        if commit:\n'
    '            salon.save()\n'
    '            self.save_m2m()\n'
    '        return salon\n\n\n# -----------------------------------------------------------------\nclass SalonOpeningHoursForm',
)

# Never reuse a same-name neighborhood polygon from another city just by name.
regex_once(
    "apps/dashboards/views.py",
    r'def _get_or_create_auto_neighborhood\(name, \*, latitude=None, longitude=None\):.*?\n\n\ndef _parse_zone_number',
    '''def _get_or_create_auto_neighborhood(name, *, latitude=None, longitude=None):
    name = (name or "").strip()
    if not name:
        return None

    candidates = list(Neighborhood.objects.filter(name__iexact=name).order_by("pk"))
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return candidates[0] if candidates else None

    point = Point(lon, lat, srid=4326)
    for neighborhood in candidates:
        polygon = getattr(neighborhood, "polygon", None)
        if polygon is not None:
            try:
                if polygon.contains(point) or polygon.touches(point):
                    return neighborhood
            except Exception:
                continue

    delta = 0.002
    polygon = Polygon(
        (
            (lon - delta, lat - delta),
            (lon + delta, lat - delta),
            (lon + delta, lat + delta),
            (lon - delta, lat + delta),
            (lon - delta, lat - delta),
        ),
        srid=4326,
    )
    return Neighborhood.objects.create(name=name, polygon=polygon)


def _parse_zone_number''',
)

# Re-export the hardened nationwide parsers/proxies from the existing views module.
views_path = "apps/search/views.py"
views = read(views_path)
marker = "# Nationwide onboarding location overrides"
if marker not in views:
    views += '''\n\n# Nationwide onboarding location overrides\nfrom apps.search.location_geo import (\n    _extract_reverse_geocode_city as _nationwide_extract_city,\n    _extract_reverse_geocode_neighborhood as _nationwide_extract_neighborhood,\n    _extract_reverse_geocode_zone as _nationwide_extract_zone,\n    city_search_proxy,\n    reverse_geocode_proxy as _nationwide_reverse_geocode_proxy,\n)\n\n_extract_reverse_geocode_city = _nationwide_extract_city\n_extract_reverse_geocode_neighborhood = _nationwide_extract_neighborhood\n_extract_reverse_geocode_zone = _nationwide_extract_zone\nreverse_geocode_proxy = _nationwide_reverse_geocode_proxy\n'''
    write(views_path, views)
else:
    raise RuntimeError("apps/search/views.py already contains nationwide override marker")

# City-search route.
replace_once(
    "apps/search/urls.py",
    '    reverse_geocode_proxy,\n    search_suggestions,\n',
    '    reverse_geocode_proxy,\n    city_search_proxy,\n    search_suggestions,\n',
)
replace_once(
    "apps/search/urls.py",
    '    path("reverse-geocode/", reverse_geocode_proxy, name="reverse_geocode_proxy"),\n',
    '    path("reverse-geocode/", reverse_geocode_proxy, name="reverse_geocode_proxy"),\n'
    '    path("city-search/", city_search_proxy, name="city_search_proxy"),\n',
)

# Map.ir forward-search configuration.
replace_once(
    "loomera/settings/base.py",
    'MAPIR_REVERSE_BASE_URL = env(\n'
    '    "MAPIR_REVERSE_BASE_URL", default="https://map.ir/reverse/no"\n'
    ')\n',
    'MAPIR_REVERSE_BASE_URL = env(\n'
    '    "MAPIR_REVERSE_BASE_URL", default="https://map.ir/reverse/no"\n'
    ')\n'
    'MAPIR_SEARCH_BASE_URL = env(\n'
    '    "MAPIR_SEARCH_BASE_URL", default="https://map.ir/search/v2"\n'
    ')\n'
    'CITY_SEARCH_QUERY_MAX_CHARS = env.int("CITY_SEARCH_QUERY_MAX_CHARS", default=80)\n',
)

# Template: city chooser first, then map; persist hidden city field.
replace_once(
    "templates/dashboards/salon_profile_creator_step2.html",
    'data-reverse-geocode-url="{% url \'search:reverse_geocode_proxy\' %}"\n',
    'data-reverse-geocode-url="{% url \'search:reverse_geocode_proxy\' %}"\n'
    'data-city-search-url="{% url \'search:city_search_proxy\' %}"\n',
)
replace_once(
    "templates/dashboards/salon_profile_creator_step2.html",
    '      {{ form.longitude }}\n      {{ form.zone }}\n',
    '      {{ form.longitude }}\n      {{ form.city }}\n      {{ form.zone }}\n',
)
replace_once(
    "templates/dashboards/salon_profile_creator_step2.html",
    '            <h2 class="text-base font-black text-loomera-textPrimary sm:text-lg">موقعیت مکانی روی نقشه</h2>\n'
    '            <p class="mt-1 text-xs leading-6 text-loomera-textMuted">روی نقشه بزن یا از موقعیت فعلی استفاده کن.</p>\n',
    '            <h2 class="text-base font-black text-loomera-textPrimary sm:text-lg">موقعیت مکانی روی نقشه</h2>\n'
    '            <p class="mt-1 text-xs leading-6 text-loomera-textMuted">اول شهر را انتخاب کن؛ سپس محل دقیق مجموعه را روی نقشه مشخص کن.</p>\n',
)
replace_once(
    "templates/dashboards/salon_profile_creator_step2.html",
    '        <div id="mapWarning" class="mb-4 hidden rounded-2xl border border-loomera-danger/20 bg-loomera-dangerSoft px-4 py-3 text-sm font-bold leading-7 text-loomera-danger"></div>\n'
    '        <div class="overflow-hidden rounded-[24px] border border-loomera-borderSoft bg-loomera-bgSubtle">\n',
    '        <div class="mb-4">\n'
    '          <label for="id_city_search" class="mb-2 block text-xs font-black text-loomera-textMuted">شهر</label>\n'
    '          <div class="relative">\n'
    '            <input id="id_city_search" type="search" value="{{ form.city.value|default:\'\' }}" autocomplete="off" class="w-full rounded-[20px] border border-loomera-borderSoft bg-loomera-bgSubtle/70 px-4 py-3.5 text-sm font-bold text-loomera-textPrimary outline-none transition focus:border-loomera-primary/40 focus:bg-white focus:ring-4 focus:ring-loomera-primary/10" placeholder="نام شهر را بنویس؛ مثلاً اصفهان">\n'
    '            <div id="citySearchResults" class="absolute inset-x-0 top-[calc(100%+0.5rem)] z-30 hidden max-h-64 overflow-y-auto rounded-[20px] border border-loomera-borderSoft bg-white p-2 shadow-lm-elevated" role="listbox" aria-label="نتایج جستجوی شهر"></div>\n'
    '          </div>\n'
    '          <p class="mt-2 text-xs leading-6 text-loomera-textMuted">با انتخاب شهر، نقشه روی همان شهر زوم می‌شود؛ انتخاب شهر به‌تنهایی محل مجموعه را ثبت نمی‌کند.</p>\n'
    '        </div>\n\n'
    '        <div id="mapWarning" class="mb-4 hidden rounded-2xl border border-loomera-danger/20 bg-loomera-dangerSoft px-4 py-3 text-sm font-bold leading-7 text-loomera-danger"></div>\n'
    '        <div class="overflow-hidden rounded-[24px] border border-loomera-borderSoft bg-loomera-bgSubtle">\n',
)
replace_once(
    "templates/dashboards/salon_profile_creator_step2.html",
    '<label for="id_zone_display" class="mb-2 block text-xs font-black text-loomera-textMuted">منطقه</label>\n'
    '            <input id="id_zone_display" type="text" value="{% if form.zone.value %}منطقه {{ form.zone.value }}{% endif %}" readonly',
    '<label for="id_zone_display" class="mb-2 block text-xs font-black text-loomera-textMuted">منطقه / ناحیه</label>\n'
    '            <input id="id_zone_display" type="text" value="{% if form.zone_label.value %}{{ form.zone_label.value }}{% elif form.zone.value %}منطقه {{ form.zone.value }}{% endif %}" readonly',
)

# JS: city search/zoom + textual area handling + nationwide default map extent.
replace_once(
    "static/js/pages/salon_location_step.js",
    '  const reverseGeocodeUrl = body.dataset.reverseGeocodeUrl || "";\n',
    '  const reverseGeocodeUrl = body.dataset.reverseGeocodeUrl || "";\n'
    '  const citySearchUrl = body.dataset.citySearchUrl || "";\n',
)
replace_once(
    "static/js/pages/salon_location_step.js",
    '  const mapRoot = document.getElementById("salon-location-map");\n'
    '  const form = document.getElementById("salonLocationForm");\n',
    '  const mapRoot = document.getElementById("salon-location-map");\n'
    '  const form = document.getElementById("salonLocationForm");\n'
    '  const cityInput = document.getElementById("id_city");\n'
    '  const citySearchInput = document.getElementById("id_city_search");\n'
    '  const citySearchResults = document.getElementById("citySearchResults");\n',
)
regex_once(
    "static/js/pages/salon_location_step.js",
    r'  function applyReverseArea\(data = \{\}\) \{.*?\n  \}\n\n  async function reverseGeocode',
    '''  function applyReverseArea(data = {}) {
    const zoneValue = normalizeDigits(data.zone || "").replace(/[^0-9]/g, "");
    const zoneLabel = normalizeText(data.zone_label) || (zoneValue ? `منطقه ${zoneValue}` : "");
    const neighborhood = normalizeText(data.neighborhood);
    const city = normalizeText(data.city);

    if (city && cityInput) cityInput.value = city;
    if (city && citySearchInput) citySearchInput.value = city;

    if (zoneInput) zoneInput.value = zoneValue;
    if (zoneLabelInput) zoneLabelInput.value = zoneLabel;
    if (zoneDisplayInput) zoneDisplayInput.value = zoneLabel;

    if (neighborhoodInput) neighborhoodInput.value = "";
    if (neighborhoodNameInput) neighborhoodNameInput.value = neighborhood;
    if (neighborhoodDisplayInput) neighborhoodDisplayInput.value = neighborhood;
  }

  async function reverseGeocode''',
)
replace_once(
    "static/js/pages/salon_location_step.js",
    '        const missingArea = !normalizeText(data.neighborhood) || !normalizeText(data.zone);\n',
    '        const missingArea = !normalizeText(data.neighborhood) || !(normalizeText(data.zone_label) || normalizeText(data.zone));\n',
)
replace_once(
    "static/js/pages/salon_location_step.js",
    '      }).setView([35.699739, 51.338097], 12);\n',
    '      }).setView([32.4279, 53.6880], 5);\n',
)
# Insert city behavior before map initialization.
replace_once(
    "static/js/pages/salon_location_step.js",
    '  async function initMap() {\n',
    '''  let citySearchTimer = null;
  let cityLookupCounter = 0;

  function hideCityResults() {
    if (!citySearchResults) return;
    citySearchResults.classList.add("hidden");
    citySearchResults.replaceChildren();
  }

  function focusCityOnMap(lat, lon, city) {
    const latitude = Number(lat);
    const longitude = Number(lon);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;

    const cityName = normalizeText(city);
    if (cityInput) cityInput.value = cityName;
    if (citySearchInput) citySearchInput.value = cityName;
    hideCityResults();

    if (mapInstance) {
      mapInstance.setView([latitude, longitude], 12);
    }
  }

  async function searchCities(query, { autoFocusFirst = false } = {}) {
    const normalizedQuery = normalizeText(query);
    if (!citySearchUrl || normalizedQuery.length < 2) {
      hideCityResults();
      return;
    }

    const requestId = ++cityLookupCounter;
    try {
      const url = new URL(citySearchUrl, window.location.origin);
      url.searchParams.set("q", normalizedQuery);
      const response = await fetch(url.toString(), {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const payload = await response.json();
      if (requestId !== cityLookupCounter) return;

      const results = response.ok && payload.ok && Array.isArray(payload.results)
        ? payload.results
        : [];

      if (autoFocusFirst && results.length) {
        const first = results[0];
        focusCityOnMap(first.lat, first.lon, first.city || first.label || normalizedQuery);
        return;
      }

      if (!citySearchResults) return;
      citySearchResults.replaceChildren();
      if (!results.length) {
        citySearchResults.classList.add("hidden");
        return;
      }

      results.forEach((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "flex w-full items-center justify-between gap-3 rounded-2xl px-3 py-2.5 text-right text-sm font-bold text-loomera-textPrimary transition hover:bg-loomera-primarySoft";
        button.setAttribute("role", "option");
        const title = document.createElement("span");
        title.textContent = item.label || item.city || normalizedQuery;
        const meta = document.createElement("span");
        meta.className = "text-[11px] font-bold text-loomera-textMuted";
        meta.textContent = item.province || "";
        button.append(title, meta);
        button.addEventListener("click", () => {
          focusCityOnMap(item.lat, item.lon, item.city || item.label || normalizedQuery);
        });
        citySearchResults.appendChild(button);
      });
      citySearchResults.classList.remove("hidden");
    } catch (error) {
      if (requestId === cityLookupCounter) hideCityResults();
    }
  }

  citySearchInput?.addEventListener("input", () => {
    if (cityInput) cityInput.value = "";
    window.clearTimeout(citySearchTimer);
    citySearchTimer = window.setTimeout(() => searchCities(citySearchInput.value), 300);
  });

  citySearchInput?.addEventListener("focus", () => {
    if (normalizeText(citySearchInput.value).length >= 2) {
      searchCities(citySearchInput.value);
    }
  });

  document.addEventListener("click", (event) => {
    if (!citySearchResults || !citySearchInput) return;
    if (!citySearchResults.contains(event.target) && event.target !== citySearchInput) {
      hideCityResults();
    }
  });

  async function initMap() {
''',
)
# If an old salon has city metadata but no coordinates, center it when the map starts.
replace_once(
    "static/js/pages/salon_location_step.js",
    '      if (!Number.isNaN(initialLat) && !Number.isNaN(initialLng)) {\n'
    '        setLocation(initialLat, initialLng, true, false);\n',
    '      if (!Number.isNaN(initialLat) && !Number.isNaN(initialLng)) {\n'
    '        setLocation(initialLat, initialLng, true, false);\n',
)
# Add city fallback after the saved-location block without changing saved-location behavior.
needle = '''      if (!Number.isNaN(initialLat) && !Number.isNaN(initialLng)) {
        setLocation(initialLat, initialLng, true, false);
        if (addressInput.value.trim()) {
          setMessageState(
            addressMessageBox,
            "success",
            '<i class="fa-solid fa-check ml-1"></i> آدرس ذخیره‌شده قبلی نمایش داده شده است.'
          );
        }
      }
'''
replacement = needle + '''      else if (cityInput && normalizeText(cityInput.value)) {
        searchCities(cityInput.value, { autoFocusFirst: true });
      }
'''
replace_once("static/js/pages/salon_location_step.js", needle, replacement)

print("Nationwide onboarding location patch applied successfully.")
