from django.test import SimpleTestCase, override_settings
from django.test import TestCase
from django.core.cache import cache
from unittest.mock import Mock, patch

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.services.models import Services
from apps.bale_bot.parser import parse_bale_update
from apps.bale_bot.handlers import handle_bale_update_stage11
from apps.messaging.models import MessagingConversationContext
from apps.messaging.services import ensure_default_providers, get_or_create_identity, connect_identity_to_user
from apps.messaging.loomi import answer_loomi_message, try_apply_loomi_start_context

from apps.messaging.links import build_loomi_provider_start_url, build_loomi_start_payload
from apps.messaging.loomi import loomi_messaging_enabled, parse_loomi_start_payload


class LoomiPayloadTests(SimpleTestCase):
    def test_compact_salon_payload(self):
        parsed = parse_loomi_start_payload("loomi_s_125")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.scope_type, "salon")
        self.assertEqual(parsed.object_id, 125)

    def test_compact_stylist_payload(self):
        parsed = parse_loomi_start_payload("loomi_p_44")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.scope_type, "stylist")
        self.assertEqual(parsed.object_id, 44)

    def test_existing_connect_payload_is_not_claimed(self):
        self.assertIsNone(parse_loomi_start_payload("connect_abc123"))

    def test_invalid_payload_is_not_claimed(self):
        self.assertIsNone(parse_loomi_start_payload("loomi_s_0"))
        self.assertIsNone(parse_loomi_start_payload("something_else"))


class LoomiFeatureFlagTests(SimpleTestCase):
    @override_settings(LOOMI_MESSAGING_ENABLED=False)
    def test_disabled_by_default_path(self):
        self.assertFalse(loomi_messaging_enabled("telegram"))

    @override_settings(
        LOOMI_MESSAGING_ENABLED=True,
        LOOMI_MESSAGING_ALLOWED_PROVIDERS=["telegram", "bale"],
    )
    def test_enabled_for_allowed_provider(self):
        self.assertTrue(loomi_messaging_enabled("telegram"))
        self.assertTrue(loomi_messaging_enabled("bale"))
        self.assertFalse(loomi_messaging_enabled("whatsapp"))


class LoomiLinkTests(SimpleTestCase):
    @override_settings(TELEGRAM_BOT_USERNAME="LoomiBot")
    def test_telegram_salon_link(self):
        self.assertEqual(build_loomi_start_payload("salon", 125), "loomi_s_125")
        self.assertEqual(
            build_loomi_provider_start_url("telegram", "salon", 125),
            "https://t.me/LoomiBot?start=loomi_s_125",
        )

    @override_settings(BALE_BOT_USERNAME="LoomiBot", BALE_BOT_START_URL_TEMPLATE="")
    def test_bale_stylist_link(self):
        self.assertEqual(build_loomi_start_payload("stylist", 44), "loomi_p_44")
        self.assertEqual(
            build_loomi_provider_start_url("bale", "stylist", 44),
            "https://ble.ir/LoomiBot?start=loomi_p_44",
        )


@override_settings(
    LOOMI_MESSAGING_ENABLED=True,
    LOOMI_MESSAGING_ALLOWED_PROVIDERS=["telegram", "bale"],
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class LoomiConversationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.providers = ensure_default_providers()
        self.provider = self.providers["telegram"]
        self.identity, _ = get_or_create_identity(provider=self.provider, provider_user_id="801", chat_id="801")
        self.manager_user = CustomUser.objects.create(mobile_number="09121110001", name="مدیر", is_active=True)
        manager = SalonManager.objects.create(user=self.manager_user, is_active=True)
        self.salon = Salon.objects.create(salon_name="سالن آزمایش", salon_manager=manager, is_active=True, address="تهران، خیابان تست", mobile_phone="09121112222")
        self.stylist_user = CustomUser.objects.create(mobile_number="09121110002", name="متخصص", is_active=True)
        self.stylist = Stylist.objects.create(user=self.stylist_user, is_active=True, public_visibility="salon_only")
        self.salon.stylists.add(self.stylist)
        self.service = Services.objects.create(service_name="رنگ مو", slug="loomi-color", is_active=True, base_price=250000)
        self.salon.services.add(self.service)
        self.service.stylists.add(self.stylist)

    def start(self, payload=None):
        return try_apply_loomi_start_context(identity=self.identity, provider=self.provider,
            payload=payload or f"loomi_s_{self.salon.pk}", base_url="https://loomera.test")

    def answer(self, question):
        return answer_loomi_message(identity=self.identity, provider=self.provider,
            text=question, base_url="https://loomera.test")

    def update(self, text, **extra):
        return {"update_id": 1, "message": {"message_id": 1,
            "from": {"id": 801}, "chat": {"id": 801, "type": "private"}, "text": text}, **extra}

    def dispatch(self, text):
        client = Mock()
        result = handle_bale_update_stage11(parsed=parse_bale_update(self.update(text)),
            identity=self.identity, provider=self.provider, base_url="https://loomera.test", client=client)
        return result, client

    def test_both_provider_start_links_through_webhook_services(self):
        from apps.telegram_bot.services import record_telegram_webhook_update
        from apps.bale_bot.services import record_bale_webhook_update
        with override_settings(MESSAGING_ENABLED=True, MESSAGING_ALLOWED_PROVIDERS=["telegram", "bale"], TELEGRAM_BOT_ENABLED=True, BALE_BOT_ENABLED=True):
            for key, recorder, client_path in [
                ("telegram", record_telegram_webhook_update, "apps.telegram_bot.services.TelegramBotClient"),
                ("bale", record_bale_webhook_update, "apps.bale_bot.handlers.BaleBotClient"),
            ]:
                with self.subTest(provider=key), patch(client_path) as client:
                    result = recorder(payload=self.update(f"/start loomi_s_{self.salon.pk}"), base_url="https://loomera.test")
                    self.assertEqual(result["handler_result"], "loomi_context_started")
                    self.assertEqual(result["identity"].loomi_context.scope_object_id, self.salon.pk)
                    self.assertIn("سالن آزمایش", client.return_value.send_message.call_args.kwargs["text"])
                    duplicate = recorder(payload=self.update(f"/start loomi_s_{self.salon.pk}"))
                    self.assertTrue(duplicate["duplicate"])
                    self.assertEqual(client.return_value.send_message.call_count, 1)

    def test_salon_prices_and_contact_are_database_backed(self):
        self.start()
        self.assertIn("250,000", self.answer("قیمت رنگ مو چنده؟")["text"])
        self.assertIn(self.salon.address, self.answer("آدرس کجاست؟")["text"])
        self.assertIn(self.salon.mobile_phone, self.answer("شماره تماس؟")["text"])
        self.assertNotIn(self.manager_user.mobile_number, self.answer("شماره تماس؟")["text"])

    def test_stylist_price_override_and_hidden_price_filter(self):
        from apps.services.models import ServicePrice
        ServicePrice.objects.create(service=self.service, stylist=self.stylist, price=320000)
        self.start(f"loomi_p_{self.stylist.pk}")
        self.assertIn("320,000", self.answer("قیمت رنگ مو؟")["text"])
        self.start()
        self.assertIn("320,000", self.answer("قیمت رنگ مو؟")["text"])
        self.stylist.public_visibility = "hidden"
        self.stylist.save(update_fields=["public_visibility"])
        reply = self.answer("قیمت رنگ مو؟")["text"]
        self.assertNotIn("320,000", reply)
        self.assertIn("250,000", reply)

    def test_price_range_includes_base_price_for_stylist_without_override(self):
        from apps.services.models import ServicePrice
        other_user = CustomUser.objects.create(mobile_number="09121110003", name="متخصص دوم", is_active=True)
        other = Stylist.objects.create(user=other_user, is_active=True)
        self.salon.stylists.add(other)
        self.service.stylists.add(other)
        ServicePrice.objects.create(service=self.service, stylist=self.stylist, price=320000)
        self.start()
        reply = self.answer("قیمت رنگ مو؟")["text"]
        self.assertIn("250,000", reply)
        self.assertIn("320,000", reply)

    def test_stylist_services_exclude_unpublished_salon_services(self):
        private = Services.objects.create(service_name="خدمت خصوصی", slug="loomi-private", base_price=999)
        private.stylists.add(self.stylist)
        self.start(f"loomi_p_{self.stylist.pk}")
        answer = self.answer("چه خدماتی انجام میدی؟")["text"]
        self.assertIn("رنگ مو", answer)
        self.assertNotIn("خصوصی", answer)

    def test_inactive_services_hidden(self):
        self.start()
        self.service.is_active = False
        self.service.save(update_fields=["is_active"])
        self.assertNotIn("رنگ مو", self.answer("خدمات؟")["text"])

    def test_invalid_link_clears_previous_scope(self):
        self.start()
        for payload in ["loomi_s_0", "loomi_p_9999999", "loomi_s_" + "9" * 5000]:
            with self.subTest(payload=payload[:30]):
                self.assertIn("معتبر نیست", self.start(payload)["text"])
                self.assertFalse(MessagingConversationContext.objects.filter(identity=self.identity).exists())

    def test_inactive_salon_and_stale_context_hidden(self):
        self.start()
        self.salon.is_active = False
        self.salon.save(update_fields=["is_active"])
        self.assertIn("در دسترس نیست", self.answer("خدمات؟")["text"])
        self.assertIn("معتبر نیست", self.start()["text"])

    def test_hidden_and_inactive_stylists_rejected(self):
        for visibility, active in [("hidden", True), ("resume_only", True), ("public", False)]:
            self.stylist.public_visibility = visibility
            self.stylist.is_active = active
            self.stylist.save()
            self.assertIn("معتبر نیست", self.start(f"loomi_p_{self.stylist.pk}")["text"])

    def test_hidden_membership_rejected(self):
        SalonMembership.objects.create(salon=self.salon, stylist=self.stylist,
            status=SalonMembershipStatus.ACTIVE, show_on_salon_profile=False)
        self.assertIn("معتبر نیست", self.start(f"loomi_p_{self.stylist.pk}")["text"])

    def test_booking_only_links_and_never_creates_order(self):
        from apps.orders.models import Order
        self.start()
        before = Order.objects.count()
        answer = self.answer("برای فردا نوبت رزرو کن")
        self.assertIn("مسیر رزرو", answer["text"])
        self.assertTrue(answer["reply_markup"]["inline_keyboard"][0][0]["url"].startswith("https://loomera.test/"))
        self.assertEqual(Order.objects.count(), before)

    @override_settings(LOOMI_MESSAGING_GUEST_LIMIT=1)
    def test_rate_limit_and_menu_remains_available(self):
        self.start()
        self.assertIn("رنگ مو", self.answer("خدمات؟")["text"])
        self.assertIn("سقف", self.answer("خدمات؟")["text"])
        self.assertEqual(self.dispatch("/help")[0], "help_menu")

    def test_cache_outage_safely_limits_assistant(self):
        with patch("apps.messaging.loomi.cache.add", side_effect=RuntimeError("cache unavailable")):
            self.assertEqual(self.dispatch("سؤال؟")[0], "unknown_guest_message_menu")

    @override_settings(LOOMI_MESSAGING_ENABLED=False)
    def test_disabled_preserves_original_fallback(self):
        self.assertIsNone(self.start())
        self.assertEqual(self.dispatch("سؤال جدید؟")[0], "unknown_guest_message_menu")

    def test_existing_commands_and_menus_bypass_loomi(self):
        with patch("apps.bale_bot.handlers.answer_loomi_message") as answer:
            for text, expected in [("/help", "help_menu"), ("راهنما", "help_menu"), ("/menu", "guest_menu"), ("نوبت‌های من", "appointments_requires_connection")]:
                self.assertEqual(self.dispatch(text)[0], expected)
            answer.assert_not_called()
        self.assertIsNone(self.answer("/unknown"))

    def test_callback_bypasses_loomi(self):
        payload = {"update_id": 2, "callback_query": {"id": "cb", "from": {"id": 801},
            "data": "menu:help", "message": {"chat": {"id": 801, "type": "private"}}}}
        with patch("apps.bale_bot.handlers.answer_loomi_message") as answer:
            result = handle_bale_update_stage11(parsed=parse_bale_update(payload), identity=self.identity,
                provider=self.provider, client=Mock(), base_url="https://loomera.test")
            self.assertEqual(result, "help_menu")
            answer.assert_not_called()

    def test_manager_guidance_requires_active_connection(self):
        connect_identity_to_user(self.identity, self.manager_user)
        reply = self.answer("چطور برنامه کاری تیم را مدیریت کنم؟")
        self.assertIn("داشبورد", reply["text"])
        self.assertIsNotNone(reply["reply_markup"])

    def test_stylist_schedule_guidance(self):
        connect_identity_to_user(self.identity, self.stylist_user)
        reply = self.answer("برنامه فردای من چطور است؟")
        self.assertIn("تقویم", reply["text"])
        self.assertIsNotNone(reply["reply_markup"])

    def test_stale_user_does_not_receive_authenticated_role(self):
        self.identity.user = self.manager_user
        self.identity.save(update_fields=["user"])
        with patch("apps.help_center.services.answer_help_question", return_value={"answer": "راهنمای عمومی"}) as help_answer:
            self.answer("چطور حساب بسازم؟")
            self.assertEqual(help_answer.call_args.kwargs["role"], "guest")
            self.assertEqual(help_answer.call_args.kwargs["history"], [])

    def test_scoped_unknown_does_not_call_ai(self):
        self.start()
        with patch("apps.help_center.services.answer_help_question") as help_answer:
            self.assertIn("اطلاعات تأییدشده", self.answer("مدیر اینجا چند سالشه؟")["text"])
            help_answer.assert_not_called()

    def test_help_failure_returns_old_friendly_menu(self):
        with patch("apps.help_center.services.answer_help_question", side_effect=RuntimeError("offline")):
            result, client = self.dispatch("چطور حساب بسازم؟")
            self.assertEqual(result, "unknown_guest_message_menu")
            self.assertIn("گزینه‌های زیر", client.send_message.call_args.kwargs["text"])

    def test_service_lookup_failure_returns_menu_instead_of_missing_data_claim(self):
        self.start()
        with patch("apps.messaging.loomi._scope_services", side_effect=RuntimeError("lookup failed")):
            result, client = self.dispatch("خدمات؟")
            self.assertEqual(result, "unknown_guest_message_menu")
            self.assertIn("گزینه‌های زیر", client.send_message.call_args.kwargs["text"])

    def test_database_failure_does_not_poison_webhook_transaction(self):
        from django.db import connection
        def broken(*args, **kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM loomi_missing_table_for_test")
        with patch("apps.messaging.loomi._resolve_target", side_effect=broken):
            self.assertIsNone(self.start())
        self.assertTrue(Salon.objects.filter(pk=self.salon.pk).exists())

    def test_group_messages_do_not_use_private_context(self):
        payload = self.update("قیمت؟")
        payload["message"]["chat"]["type"] = "group"
        with patch("apps.bale_bot.handlers.answer_loomi_message") as answer:
            handle_bale_update_stage11(parsed=parse_bale_update(payload), identity=self.identity,
                provider=self.provider, client=Mock(), base_url="https://loomera.test")
            answer.assert_not_called()

    def test_unscoped_booking_does_not_call_help_ai(self):
        with patch("apps.help_center.services.answer_help_question") as help_answer:
            self.assertIn("مسیر سایت", self.answer("برای فردا رزرو کن")["text"])
            help_answer.assert_not_called()

    def test_direct_bot_public_questions_and_greeting_use_existing_search(self):
        for provider_key in ("telegram", "bale"):
            self.provider = self.providers[provider_key]
            for question, expected in [
                ("قیمت رنگ مو چنده؟", "کدوم سالن"),
                ("قیمت رنگساژ چنده؟", "کدوم سالن"),
                ("چه خدماتی دارید؟", "کدوم سالن"),
                ("آدرس و شماره تماس؟", "کدوم سالن"),
                ("این متخصص چه کاری انجام میده؟", "کدوم سالن"),
                ("برای فردا وقت دارید؟", "اول سالن"),
                ("سلام", "سلام 🌱"),
            ]:
                cache.clear()
                with self.subTest(provider=provider_key, question=question), patch(
                    "apps.help_center.services.answer_help_question"
                ) as help_answer, patch("apps.orders.booking_utils.get_available_slots_for_service") as slots:
                    result, client = self.dispatch(question)
                    self.assertEqual(result, "loomi_message")
                    sent = client.send_message.call_args.kwargs
                    self.assertIn(expected, sent["text"])
                    rows = sent["reply_markup"]["inline_keyboard"]
                    self.assertEqual(rows[0][0]["callback_data"], "menu:customer_search")
                    self.assertEqual(rows[-1][0]["callback_data"], "menu:guest")
                    help_answer.assert_not_called()
                    slots.assert_not_called()

    def test_general_help_including_cancellation_bypasses_selection(self):
        for question in ["لومرا چیه؟", "چطور حساب کاربری بسازم؟", "چطور نوبتم رو لغو کنم؟", "قوانین پرداخت چیه؟"]:
            with self.subTest(question=question), patch("apps.help_center.services.answer_help_question",
                return_value={"answer": "راهنمای عمومی لومرا"}) as help_answer:
                self.assertEqual(self.answer(question)["text"], "راهنمای عمومی لومرا")
                help_answer.assert_called_once()

    def test_context_lookup_failure_uses_old_safe_menu(self):
        with patch("apps.messaging.loomi._current_context", side_effect=RuntimeError("lookup failed")):
            self.assertEqual(self.dispatch("خدمات؟")[0], "unknown_guest_message_menu")

    def test_manager_question_with_customer_context_keeps_operator_guidance(self):
        self.start()
        connect_identity_to_user(self.identity, self.manager_user)
        self.assertIn("تقویم", self.answer("برنامه فردای تیم را چطور ببینم؟")["text"])

    @override_settings(MESSAGING_ENABLED=True, MESSAGING_ALLOWED_PROVIDERS=["telegram", "bale"],
        TELEGRAM_BOT_ENABLED=True, BALE_BOT_ENABLED=True, TELEGRAM_BOT_USERNAME="LoomiBot",
        BALE_BOT_USERNAME="LoomiBot", BALE_BOT_START_URL_TEMPLATE="")
    def test_public_profile_entry_points_render_and_respect_flag(self):
        from django.template import Context, Template
        template = Template('{% load messaging_connect %}{% loomi_links "salon" salon %}')
        html = template.render(Context({"salon": self.salon}))
        self.assertIn(f"https://t.me/LoomiBot?start=loomi_s_{self.salon.pk}", html)
        self.assertIn(f"https://ble.ir/LoomiBot?start=loomi_s_{self.salon.pk}", html)
        with override_settings(LOOMI_MESSAGING_ENABLED=False):
            self.assertEqual(template.render(Context({"salon": self.salon})).strip(), "")
