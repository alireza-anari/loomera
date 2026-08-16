from pathlib import Path

ROOT = Path(".")


def replace_exact(path_str: str, old: str, new: str):
    path = ROOT / path_str
    content = path.read_text(encoding="utf-8")
    if old not in content:
        raise SystemExit(f"ERROR: exact snippet not found in {path_str}")
    content = content.replace(old, new, 1)
    path.write_text(content, encoding="utf-8")
    print(f"UPDATED: {path_str}")


# 1) Persian digits in shared mobile booking header
replace_exact(
    "templates/orders/_booking_step_header.html",
    '<p class="text-xs font-black text-loomera-primary">مرحله {{ step_current }} از ۴</p>',
    """<p class="text-xs font-black text-loomera-primary">
        مرحله
        {% if step_current == '1' %}۱{% elif step_current == '2' %}۲{% elif step_current == '3' %}۳{% elif step_current == '4' %}۴{% else %}{{ step_current }}{% endif %}
        از ۴
      </p>""",
)

# 2) Make mobile sticky CTA in stylist selection smaller
replace_exact(
    "templates/orders/select_stylists.html",
    """  <div class="mx-auto flex w-full max-w-md flex-col gap-3">
    <div class="rounded-2xl border border-loomera-borderSoft bg-loomera-bgSubtle px-4 py-3">
      <p class="text-xs font-bold text-loomera-textMuted">انتخاب متخصص</p>
      <p id="staffMobileSummary" class="mt-1 truncate text-sm font-black text-loomera-textPrimary">برای هر خدمت، یک متخصص انتخاب کن</p>
    </div>
    <button
      id="continueBtn"
      type="button"
      class="inline-flex w-full items-center justify-center rounded-full bg-loomera-primary px-5 py-4 text-sm font-black text-white shadow-lm-soft transition hover:bg-loomera-primaryHover disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-loomera-focusRing/35"
      disabled
    >
      ادامه انتخاب زمان
    </button>
  </div>""",
    """  <div class="mx-auto w-full max-w-md">
    <p id="staffMobileSummary" class="mb-2 text-center text-xs font-black text-loomera-textSecondary" aria-live="polite">برای هر خدمت، یک متخصص انتخاب کن</p>
    <button
      id="continueBtn"
      type="button"
      class="inline-flex w-full items-center justify-center rounded-full bg-loomera-primary px-5 py-3 text-sm font-black text-white shadow-lm-soft transition hover:bg-loomera-primaryHover disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-loomera-focusRing/35"
      disabled
    >
      ادامه انتخاب زمان
    </button>
  </div>""",
)

# 3) Hide the duplicated large current-service block on mobile in select datetime
replace_exact(
    "templates/orders/select_datetime.html",
    '<section class="rounded-[28px] border border-loomera-borderSoft bg-loomera-surface p-4 shadow-lm-card lg:p-5" aria-labelledby="currentServiceTitle">',
    '<section class="hidden rounded-[28px] border border-loomera-borderSoft bg-loomera-surface p-4 shadow-lm-card lg:block lg:p-5" aria-labelledby="currentServiceTitle">',
)

# 4) Smaller/shorter title in reservation preview hero card
replace_exact(
    "templates/orders/reservation_preview.html",
    '<h1 id="checkout-heading" class="text-xl font-black leading-9 text-loomera-textPrimary lg:text-3xl">جزئیات رزرو را بررسی کن</h1>',
    '<h1 id="checkout-heading" class="text-base font-black leading-8 text-loomera-textPrimary sm:text-lg lg:text-3xl">بررسی جزئیات رزرو</h1>',
)

print("\\nStage 4 booking mobile polish applied successfully.")
