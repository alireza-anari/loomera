# Help Docs RAG v1.3 — Support conversation UX

This is a cumulative update. If v1.2 was not applied, do not apply it separately.

No new database migration is required.

## What changed

Backend:
- v1.2 grounding hardening is included
- support-like Persian answer style
- the assistant does not claim to be a human or to have live account access
- more natural fallback wording
- conversation history read API for continuity across page navigation

Frontend:
- renamed UI to «دستیار پشتیبانی لومرا»
- cleaner 430px desktop panel
- full-screen chat on mobile
- assistant avatar and support-style message layout
- typing state: «دارم راهنماهای مرتبط رو بررسی می‌کنم…»
- citations become compact clickable source badges
- sources are attached to each answer in a collapsible section
- old global sources panel removed
- conversation continues after refresh/navigation in the same browser tab
- «گفتگوی جدید» action added
- support escalation is compact and clearer
- composer redesigned for Enter / Shift+Enter

## Apply

Because this cumulative package contains corrected v1.2 production documents, run:

```powershell
python manage.py seed_help_center --refresh-defaults
python manage.py rebuild_help_chunks
python manage.py audit_help_coverage
python manage.py test apps.help_center.tests
python manage.py check
```

Then:

```powershell
python manage.py runserver
```

Expected test count is at least 10.

## UX test

Ask these in different pages:

```text
چطور متخصص جدید اضافه کنم؟
چرا متخصص برای رزرو نمایش داده نمی‌شه؟
چطور کد تخفیف بسازم؟
چطور شیفت ثابت برای متخصص بگذارم؟
متخصص رو اضافه کردم و براش شیفت گذاشتم ولی هنوز قابل رزرو نیست، چی رو چک کنم؟
بهترین مدل گوشی امسال چیه؟
```

Also:
1. send 2 messages
2. navigate to another Loomera page in the same tab
3. open the assistant
4. the recent conversation should be restored
5. start «گفتگوی جدید» and verify the UI returns to the welcome state
