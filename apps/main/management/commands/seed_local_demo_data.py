from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point, Polygon
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.accounts.models import Customer, CustomUser, SalonManager, Stylist
from apps.locations.models import Neighborhood
from apps.orders.models import Order, OrderDetail, PaymentType
from apps.payments.models import (
    FinancialAccount,
    Payment,
    Wallet,
    WalletTransaction,
)
from apps.salons.models import (
    Salon,
    SalonMembership,
    SalonMembershipStatus,
    SalonOpeningHours,
    SalonsGallery,
    SalonVerificationStatus,
    StaffDashboardPermission,
    SupplementaryInfoView,
)
from apps.services.models import GroupServices, ServicePrice, Services
from apps.stylists.models import StaffLeaveRequest, StylistSchedule, StylistTimeOff

SEED_TAG = "LOOMERA_LOCAL_SEED_V1"
MOBILE_PREFIX = "091770"
DEFAULT_PASSWORD = "LocalTest123!"
LOCAL_BETA_GALLERY_FILE = "images/salon_gallery/loomera-local-beta-placeholder.svg"

LOCAL_BETA_GALLERY_CONTENT = b"""\
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800">
  <rect width="1200" height="800" fill="#f5f1eb"/>
  <rect x="70" y="70" width="1060" height="660" rx="48" fill="#ffffff"/>
  <text
    x="600"
    y="385"
    text-anchor="middle"
    font-family="sans-serif"
    font-size="68"
    fill="#3f3a36"
  >Loomera Local Beta</text>
  <text
    x="600"
    y="465"
    text-anchor="middle"
    font-family="sans-serif"
    font-size="34"
    fill="#77706a"
  >Acceptance Placeholder</text>
</svg>
"""
LOCAL_BETA_NEIGHBORHOOD_NAME = "محله آزمایشی پذیرش بتای لومرا"

LOCAL_BETA_SALON_DESCRIPTION = (
    "این مجموعه یک سالن آزمایشی در دیتاست پذیرش بتای محلی لومرا است. "
    "اطلاعات این پروفایل کاملاً ساختگی بوده و فقط برای اجرای سناریوهای "
    "رزرو مشتری، مدیریت نوبت‌ها، برنامه کاری متخصصان، گزارش‌های عملیاتی، "
    "کنترل دسترسی چندسالنی و ارزیابی آمادگی نسخه بتا استفاده می‌شود. "
    "هیچ‌یک از شماره‌ها، آدرس‌ها، قیمت‌ها یا اطلاعات معرفی‌شده در این "
    "پروفایل متعلق به یک کسب‌وکار واقعی نیست و نباید در محیط Production "
    "یا برای ارتباط با مشتری واقعی استفاده شود."
)


class Command(BaseCommand):
    help = (
        "Create safe fake demo data for local Loomera testing. Never run on production."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete previously created local seed data before creating it again.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow running when DEBUG=False. Use only on disposable local databases.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=14,
            help="How many upcoming days of schedules to create. Default: 14.",
        )
        parser.add_argument(
            "--salons",
            type=int,
            default=5,
            help="How many salons to create. Default: 5.",
        )
        parser.add_argument(
            "--beta-acceptance",
            action="store_true",
            help=(
                "Create a deterministic five-salon Local Beta Acceptance "
                "dataset. Requires --reset and omits unresolved online payments."
            ),
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "This command is blocked because DEBUG=False. "
                "Run it only on local/disposable databases, or pass --force intentionally."
            )
        beta_acceptance = bool(options["beta_acceptance"])

        if beta_acceptance and not settings.DEBUG:
            raise CommandError(
                "--beta-acceptance is strictly local-only and cannot run "
                "when DEBUG=False."
            )

        if beta_acceptance and not options["reset"]:
            raise CommandError(
                "--beta-acceptance requires --reset so the acceptance "
                "dataset is deterministic."
            )

        salons_count = (
            5 if beta_acceptance else max(1, min(int(options["salons"] or 5), 10))
        )
        days_count = max(3, min(int(options["days"] or 14), 45))

        with transaction.atomic():
            if options["reset"]:
                self._reset_seed_data()

            group = self._create_service_group()
            services = self._create_services(group)
            managers = self._create_managers(salons_count)
            stylists = self._create_stylists()
            customers = self._create_customers()
            salons = self._create_salons(
                managers,
                services,
                beta_acceptance=beta_acceptance,
            )
            self._attach_team_members(salons, stylists, services)
            self._create_opening_hours(salons)
            self._create_gallery(salons)

            if beta_acceptance:
                self._create_beta_acceptance_supplementary_info(salons)

            self._create_schedules(salons, stylists, services, days_count)
            self._create_staff_time_off(salons, stylists)
            self._create_wallets(customers)
            orders_created = self._create_orders(
                salons,
                stylists,
                services,
                customers,
                include_unresolved_online=not beta_acceptance,
            )

        self.stdout.write(self.style.SUCCESS("Local Loomera demo data is ready."))
        self.stdout.write(f"Seed tag: {SEED_TAG}")
        self.stdout.write(
            "Profile: " + ("beta-acceptance" if beta_acceptance else "demo")
        )
        self.stdout.write(f"Password for all seed users: {DEFAULT_PASSWORD}")
        self.stdout.write(f"Managers: {MOBILE_PREFIX}10001 ...")
        self.stdout.write(f"Stylists: {MOBILE_PREFIX}20001 ...")
        self.stdout.write(f"Customers: {MOBILE_PREFIX}30001 ...")
        self.stdout.write(
            f"Salons: {len(salons)} | Services: {len(services)} | Orders created/skipped: {orders_created}"
        )

    def _reset_seed_data(self):
        """Remove only Local Seed data, including PROTECT-ed financial artifacts.

        Completed seed appointments may create immutable-looking financial records
        such as LedgerEntry and StaffEarning. Those records intentionally use
        PROTECT in normal product flows, so Local Seed reset must delete their
        dependent graph explicitly before deleting seed users and profiles.
        """

        seed_users = CustomUser.objects.filter(mobile_number__startswith=MOBILE_PREFIX)

        seed_user_ids = list(seed_users.values_list("pk", flat=True))
        seed_customer_ids = list(
            Customer.objects.filter(user_id__in=seed_user_ids).values_list(
                "pk", flat=True
            )
        )
        seed_stylist_ids = list(
            Stylist.objects.filter(user_id__in=seed_user_ids).values_list(
                "pk", flat=True
            )
        )
        seed_manager_ids = list(
            SalonManager.objects.filter(user_id__in=seed_user_ids).values_list(
                "pk", flat=True
            )
        )
        seed_salon_ids = list(
            Salon.objects.filter(slug__startswith="local-seed-salon-").values_list(
                "pk", flat=True
            )
        )

        # Deleting seed users cascades through Customer, Stylist, SalonManager,
        # Salon, Order and OrderDetail. Financial records may protect those rows,
        # so recursively remove only the protecting objects encountered inside
        # this seed-owned graph.
        self._delete_with_protected_dependents(seed_users)

        # FinancialAccount uses GenericForeignKey, so deleting the owner does not
        # automatically delete its accounts. Remove accounts belonging to deleted
        # seed owners, but never remove owner-less platform-wide accounts.
        seed_financial_owners = [
            (Customer, seed_customer_ids),
            (Stylist, seed_stylist_ids),
            (SalonManager, seed_manager_ids),
            (Salon, seed_salon_ids),
            (CustomUser, seed_user_ids),
        ]

        for owner_model, owner_ids in seed_financial_owners:
            if not owner_ids:
                continue

            owner_content_type = ContentType.objects.get_for_model(
                owner_model,
                for_concrete_model=False,
            )

            self._delete_with_protected_dependents(
                FinancialAccount.objects.filter(
                    owner_content_type=owner_content_type,
                    owner_object_id__in=owner_ids,
                )
            )

        self._delete_with_protected_dependents(
            Services.objects.filter(slug__startswith="local-seed-")
        )
        self._delete_with_protected_dependents(
            GroupServices.objects.filter(slug="local-seed-beauty")
        )
        self._delete_with_protected_dependents(
            PaymentType.objects.filter(payment_title__startswith="لوکال تست")
        )
        Neighborhood.objects.filter(name=LOCAL_BETA_NEIGHBORHOOD_NAME).delete()

        self.stdout.write(
            self.style.WARNING(
                "Previous seed data and its protected financial artifacts "
                "were removed."
            )
        )

    def _delete_with_protected_dependents(self, queryset, *, active_deletions=None):
        """Delete a Local Seed queryset and any objects protecting that queryset.

        This helper must only receive querysets already scoped to disposable
        Local Seed data. It does not disable database protections globally.
        """

        model = queryset.model
        primary_keys = list(queryset.values_list("pk", flat=True))

        if not primary_keys:
            return 0

        active_deletions = active_deletions or set()
        deletion_key = (
            model._meta.label_lower,
            tuple(sorted(primary_keys)),
        )

        if deletion_key in active_deletions:
            raise CommandError(
                "A cyclic protected dependency was detected while resetting "
                f"Local Seed data for {model._meta.label}."
            )

        active_deletions.add(deletion_key)

        try:
            while True:
                current_queryset = model._default_manager.filter(pk__in=primary_keys)

                if not current_queryset.exists():
                    return 0

                try:
                    deleted_count, _details = current_queryset.delete()
                    return deleted_count
                except ProtectedError as exc:
                    protected_by_model = {}

                    for protected_object in exc.protected_objects:
                        protected_model = protected_object.__class__
                        protected_by_model.setdefault(
                            protected_model,
                            set(),
                        ).add(protected_object.pk)

                    if not protected_by_model:
                        raise CommandError(
                            "Local Seed reset encountered a protected dependency "
                            f"for {model._meta.label}, but Django did not provide "
                            "the blocking objects."
                        ) from exc

                    for protected_model, protected_ids in protected_by_model.items():
                        self._delete_with_protected_dependents(
                            protected_model._default_manager.filter(
                                pk__in=protected_ids
                            ),
                            active_deletions=active_deletions,
                        )
        finally:
            active_deletions.discard(deletion_key)

    def _create_user(self, *, mobile, name, family, email=""):
        user, _created = CustomUser.objects.get_or_create(
            mobile_number=mobile,
            defaults={
                "name": name,
                "family": family,
                "email": email,
                "is_active": True,
                "active_code": "11111",
            },
        )
        user.name = name
        user.family = family
        user.email = email
        user.is_active = True
        user.active_code = "11111"
        user.set_password(DEFAULT_PASSWORD)
        user.save(
            update_fields=[
                "name",
                "family",
                "email",
                "is_active",
                "active_code",
                "password",
            ]
        )
        return user

    def _create_service_group(self):
        group, _created = GroupServices.objects.update_or_create(
            slug="local-seed-beauty",
            defaults={
                "group_title": "خدمات تست لوکال Loomera",
                "group_image": "images/seed/local-beauty.jpg",
                "descriptions": f"{SEED_TAG} - گروه خدمات فقط برای تست لوکال",
                "is_active": True,
                "allow_indexing": False,
            },
        )
        return group

    def _create_services(self, group):
        specs = [
            ("local-seed-haircut", "کوتاهی مو تست", 45, 350_000, 10),
            ("local-seed-color", "رنگ و مش تست", 120, 1_800_000, 20),
            ("local-seed-nails", "مانیکور تست", 60, 650_000, 10),
            ("local-seed-makeup", "میکاپ تست", 90, 2_400_000, 15),
        ]
        services = []
        for slug, title, duration, price, buffer_minutes in specs:
            service, _created = Services.objects.update_or_create(
                slug=slug,
                defaults={
                    "service_name": title,
                    "summery_description": f"{SEED_TAG} - خدمت ساختگی برای تست رزرو",
                    "description": "این خدمت فقط برای تست لوکال ساخته شده است.",
                    "service_image": "images/seed/local-service.jpg",
                    "is_active": True,
                    "is_platform_catalog": True,
                    "duration_minutes": duration,
                    "base_price": price,
                    "buffer_minutes": buffer_minutes,
                    "allow_indexing": False,
                },
            )
            service.service_group.add(group)
            services.append(service)
        return services

    def _create_managers(self, salons_count):
        names = [
            ("ندا", "مدیر تست"),
            ("سمیرا", "مدیر تست"),
            ("مهسا", "مدیر تست"),
            ("الهام", "مدیر تست"),
            ("رعنا", "مدیر تست"),
            ("لیلا", "مدیر تست"),
            ("ترانه", "مدیر تست"),
            ("سارا", "مدیر تست"),
            ("نازنین", "مدیر تست"),
            ("پرستو", "مدیر تست"),
        ]
        managers = []
        for index in range(salons_count):
            name, family = names[index]
            user = self._create_user(
                mobile=f"{MOBILE_PREFIX}1{index + 1:04d}",
                name=name,
                family=family,
                email=f"local-manager-{index + 1}@loomera.test",
            )
            manager, _created = SalonManager.objects.update_or_create(
                user=user,
                defaults={
                    "address": "آدرس تست لوکال",
                    "salon_number": 2100000000 + index,
                    "is_active": True,
                    "slug": f"local-manager-{index + 1}",
                },
            )
            managers.append(manager)
        return managers

    def _create_stylists(self):
        names = [
            ("آرزو", "متخصص تست", "کوتاهی و براشینگ"),
            ("نگار", "متخصص تست", "رنگ و مش"),
            ("مریم", "متخصص تست", "ناخن"),
            ("شیرین", "متخصص تست", "میکاپ"),
            ("بهار", "متخصص تست", "پوست و مو"),
            ("ترنم", "متخصص تست", "شینیون"),
            ("یاسمن", "متخصص تست", "رنگ مو"),
            ("رها", "متخصص تست", "ناخن"),
        ]
        stylists = []
        for index, (name, family, expert) in enumerate(names, start=1):
            user = self._create_user(
                mobile=f"{MOBILE_PREFIX}2{index:04d}",
                name=name,
                family=family,
                email=f"local-stylist-{index}@loomera.test",
            )
            stylist, _created = Stylist.objects.update_or_create(
                user=user,
                defaults={
                    "description": f"{SEED_TAG} - متخصص ساختگی برای تست لوکال",
                    "address": "آدرس تست متخصص",
                    "is_active": True,
                    "expert": expert,
                    "display_name": f"{name} {family}",
                    "started_working_year": 1398,
                    "public_visibility": Stylist.PublicVisibility.SALON_ONLY,
                    "is_verified_professional": True,
                    "resume_headline": expert,
                    "resume_summary": "پروفایل ساختگی برای سناریوهای رزرو و داشبورد.",
                },
            )
            stylists.append(stylist)
        return stylists

    def _create_customers(self):
        names = [
            ("رها", "مشتری تست", "female"),
            ("کیمیا", "مشتری تست", "female"),
            ("نیلوفر", "مشتری تست", "female"),
            ("آتنا", "مشتری تست", "female"),
            ("مینا", "مشتری تست", "female"),
            ("رضا", "مشتری تست", "male"),
            ("علی", "مشتری تست", "male"),
            ("نگین", "مشتری تست", "female"),
        ]
        customers = []
        for index, (name, family, gender) in enumerate(names, start=1):
            user = self._create_user(
                mobile=f"{MOBILE_PREFIX}3{index:04d}",
                name=name,
                family=family,
                email=f"local-customer-{index}@loomera.test",
            )
            customer, _created = Customer.objects.update_or_create(
                user=user,
                defaults={
                    "address": "آدرس تست مشتری",
                    "gender": gender,
                    "notify_appointment_sms": False,
                    "notify_appointment_whatsapp": False,
                    "notify_appointment_email": False,
                    "notify_marketing_email": False,
                    "notify_marketing_sms": False,
                    "notify_marketing_whatsapp": False,
                },
            )
            customers.append(customer)
        return customers

    def _ensure_local_beta_neighborhood(self):
        polygon = Polygon.from_bbox(
            (
                51.20,
                35.60,
                51.70,
                35.90,
            )
        )
        polygon.srid = 4326

        neighborhood = (
            Neighborhood.objects.filter(name=LOCAL_BETA_NEIGHBORHOOD_NAME)
            .order_by("pk")
            .first()
        )

        if neighborhood is None:
            neighborhood = Neighborhood.objects.create(
                name=LOCAL_BETA_NEIGHBORHOOD_NAME,
                polygon=polygon,
            )
        else:
            neighborhood.polygon = polygon
            neighborhood.save(update_fields=["polygon"])

        return neighborhood

    def _create_salons(
        self,
        managers,
        services,
        *,
        beta_acceptance=False,
    ):
        beta_neighborhood = None

        if beta_acceptance:
            beta_neighborhood = self._ensure_local_beta_neighborhood()
        salon_names = [
            "سالن تست ونک",
            "سالن تست سعادت‌آباد",
            "سالن تست تجریش",
            "سالن تست شهرک غرب",
            "سالن تست یوسف‌آباد",
            "سالن تست پاسداران",
            "سالن تست نیاوران",
            "سالن تست گیشا",
            "سالن تست فرمانیه",
            "سالن تست قیطریه",
        ]
        salons = []
        for index, manager in enumerate(managers):
            salon, _created = Salon.objects.update_or_create(
                slug=f"local-seed-salon-{index + 1}",
                defaults={
                    "salon_name": salon_names[index],
                    "description": (
                        LOCAL_BETA_SALON_DESCRIPTION
                        if beta_acceptance
                        else (f"{SEED_TAG} - سالن ساختگی برای تست لوکال")
                    ),
                    "zone": index + 1,
                    "location": Point(
                        51.35 + (index * 0.01),
                        35.70 + (index * 0.01),
                        srid=4326,
                    ),
                    "neighborhood": (beta_neighborhood if beta_acceptance else None),
                    "address": f"تهران، آدرس تست سالن شماره {index + 1}",
                    "salon_manager": manager,
                    "is_active": True,
                    "verification_status": SalonVerificationStatus.VERIFIED,
                    "phone_number": f"02188{index + 1:06d}",
                    "payout_iban": f"IR82054010268002081790{index + 1:02d}",
                    "payout_account_holder_name": f"مالک سالن تست {index + 1}",
                    "payout_bank_name": "بانک تست",
                    "payout_contact_mobile": manager.user.mobile_number,
                    "cancellation_window_hours": 24,
                    "cancellation_refund_percent": 100,
                    "cancellation_policy_note": "قانون لغو ساختگی برای تست لوکال.",
                    "payout_delay_days": 2,
                    "allow_indexing": False,
                },
            )
            salon.services.set(services)
            salons.append(salon)
        return salons

    def _attach_team_members(self, salons, stylists, services):
        team_plan = {
            0: [stylists[0], stylists[1], stylists[2]],
            1: [stylists[0], stylists[3], stylists[4]],
            2: [stylists[2], stylists[5]],
            3: [stylists[6], stylists[1]],
            4: [stylists[7], stylists[4]],
        }

        for salon_index, salon in enumerate(salons):
            selected = team_plan.get(
                salon_index,
                [stylists[salon_index % len(stylists)]],
            )
            salon.stylists.set(selected)

            for stylist in selected:
                membership, _created = SalonMembership.objects.update_or_create(
                    salon=salon,
                    stylist=stylist,
                    defaults={
                        "invited_phone": stylist.user.mobile_number,
                        "role_title": stylist.expert or "متخصص تست",
                        "status": SalonMembershipStatus.ACTIVE,
                        "invited_by": salon.salon_manager.user,
                        "accepted_at": timezone.now(),
                        "show_on_salon_profile": True,
                        "metadata": {"seed_tag": SEED_TAG},
                    },
                )

                StaffDashboardPermission.objects.update_or_create(
                    membership=membership,
                    defaults={
                        "can_complete_appointments": True,
                        "can_view_own_finance": True,
                        "can_request_payout": True,
                        "can_view_own_clients": True,
                        "can_create_own_bookings": True,
                        "can_view_client_phone": False,
                        "can_manage_own_portfolio": True,
                        "can_submit_posts": False,
                        "can_submit_stories": False,
                        "can_request_leave": True,
                        "can_manage_own_schedule": True,
                    },
                )

                stylist.services_of_stylist.add(*services)

                for service in services:
                    ServicePrice.objects.update_or_create(
                        service=service,
                        stylist=stylist,
                        defaults={"price": int(service.base_price or 0)},
                    )

    def _create_opening_hours(self, salons):
        for salon in salons:
            for day in range(1, 8):
                is_closed = day == 7
                SalonOpeningHours.objects.update_or_create(
                    salon=salon,
                    day_of_week=day,
                    defaults={
                        "open_time": None if is_closed else time(9, 0),
                        "close_time": None if is_closed else time(20, 0),
                        "is_closed": is_closed,
                    },
                )

    def _ensure_local_beta_gallery_file(self) -> str:
        if not default_storage.exists(LOCAL_BETA_GALLERY_FILE):
            default_storage.save(
                LOCAL_BETA_GALLERY_FILE,
                ContentFile(LOCAL_BETA_GALLERY_CONTENT),
            )

        return LOCAL_BETA_GALLERY_FILE

    def _create_gallery(self, salons):
        image_name = self._ensure_local_beta_gallery_file()

        for salon in salons:
            SalonsGallery.objects.update_or_create(
                salon=salon,
                order=0,
                defaults={
                    "salon_image": image_name,
                    "is_cover": True,
                },
            )

    def _create_beta_acceptance_supplementary_info(
        self,
        salons,
    ):
        salon_ids = []

        for salon in salons:
            SupplementaryInfoView.objects.update_or_create(
                salon=salon,
                title="امکانات سالن آزمایشی",
                defaults={
                    "description": ("اطلاعات ساختگی مخصوص پذیرش بتای محلی لومرا"),
                    "icon_class": "fa-solid fa-circle-check",
                    "is_active": True,
                },
            )
            salon_ids.append(salon.pk)

        active_salon_count = (
            SupplementaryInfoView.objects.filter(
                salon_id__in=salon_ids,
                is_active=True,
            )
            .values("salon_id")
            .distinct()
            .count()
        )

        if active_salon_count != len(salon_ids):
            raise CommandError(
                "Local Beta Acceptance supplementary information was not "
                "created for every salon. "
                f"Expected {len(salon_ids)}, found {active_salon_count}."
            )

    def _create_schedules(self, salons, stylists, services, days_count):
        today = timezone.localdate()
        start_offsets_by_salon = [0, 2, 1, 3, 4, 5, 6, 7, 8, 9]

        for day_offset in range(1, days_count + 1):
            schedule_date = today + timedelta(days=day_offset)

            if schedule_date.weekday() == 4:
                continue

            for salon_index, salon in enumerate(salons):
                offset = start_offsets_by_salon[
                    salon_index % len(start_offsets_by_salon)
                ]

                for stylist_index, stylist in enumerate(salon.stylists.all()):
                    service = services[(salon_index + stylist_index) % len(services)]
                    start_hour = 9 + offset + stylist_index

                    if start_hour > 16:
                        start_hour = 16

                    start = time(start_hour, 0)
                    end = time(min(start_hour + 4, 20), 0)

                    StylistSchedule.objects.update_or_create(
                        stylist=stylist,
                        date=schedule_date,
                        start_time=start,
                        defaults={
                            "salon": salon,
                            "service": service,
                            "end_time": end,
                        },
                    )

    def _create_staff_time_off(self, salons, stylists):
        if not salons or not stylists:
            return

        leave_date = timezone.localdate() + timedelta(days=6)
        salon = salons[0]
        stylist = stylists[1]

        StylistTimeOff.objects.update_or_create(
            stylist=stylist,
            date=leave_date,
            start_time=time(12, 0),
            defaults={
                "end_time": time(14, 0),
                "reason": f"{SEED_TAG} - مرخصی ساعتی تست",
            },
        )

        StaffLeaveRequest.objects.update_or_create(
            salon=salon,
            stylist=stylist,
            date=leave_date + timedelta(days=1),
            start_time=time(10, 0),
            defaults={
                "end_time": time(13, 0),
                "reason": f"{SEED_TAG} - درخواست مرخصی تست",
                "status": StaffLeaveRequest.Status.PENDING,
            },
        )

    def _create_wallets(self, customers):
        for customer in customers:
            wallet, _created = Wallet.objects.get_or_create(user=customer.user)
            already_seeded = wallet.transactions.filter(
                description__contains=SEED_TAG
            ).exists()

            if not already_seeded:
                wallet.deposit(
                    2_000_000,
                    description=f"{SEED_TAG} - شارژ اولیه کیف پول تست",
                    transaction_type=WalletTransaction.TransactionType.DEPOSIT,
                )

    def _create_orders(
        self,
        salons,
        stylists,
        services,
        customers,
        *,
        include_unresolved_online=True,
    ):
        payment_type, _created = PaymentType.objects.get_or_create(
            payment_title="لوکال تست - پرداخت در سالن"
        )

        specs = [
            {
                "key": "pending-pay-in-salon",
                "salon": salons[0],
                "stylist": stylists[0],
                "service": services[0],
                "customer": customers[0],
                "days": 1,
                "start": time(10, 0),
                "status": "pending",
                "payment_method": "pay_in_salon",
            },
            {
                "key": "confirmed-pay-in-salon",
                "salon": salons[0],
                "stylist": stylists[1],
                "service": services[1],
                "customer": customers[1],
                "days": 2,
                "start": time(11, 0),
                "status": "confirmed",
                "payment_method": "pay_in_salon",
            },
            {
                "key": "online-pending-payment",
                "salon": salons[1 if len(salons) > 1 else 0],
                "stylist": stylists[0],
                "service": services[2],
                "customer": customers[2],
                "days": 3,
                "start": time(12, 0),
                "status": "pending",
                "payment_method": "online",
                "payment_state": Payment.State.PENDING,
            },
            {
                "key": "completed-manual-payment",
                "salon": salons[2 if len(salons) > 2 else 0],
                "stylist": stylists[5 if len(stylists) > 5 else 0],
                "service": services[0],
                "customer": customers[3],
                "days": -1,
                "start": time(13, 0),
                "status": "completed",
                "payment_method": "pay_in_salon",
                "payment_state": Payment.State.SUCCESS,
            },
            {
                "key": "cancelled-booking",
                "salon": salons[3 if len(salons) > 3 else 0],
                "stylist": stylists[6 if len(stylists) > 6 else 1],
                "service": services[1],
                "customer": customers[4],
                "days": 4,
                "start": time(14, 0),
                "status": "cancelled",
                "payment_method": "pay_in_salon",
            },
            {
                "key": "paid-wallet-booking",
                "salon": salons[4 if len(salons) > 4 else 0],
                "stylist": stylists[7 if len(stylists) > 7 else 2],
                "service": services[3],
                "customer": customers[5],
                "days": 5,
                "start": time(15, 0),
                "status": "paid",
                "payment_method": "wallet",
                "payment_state": Payment.State.SUCCESS,
            },
        ]
        if not include_unresolved_online:
            specs = [spec for spec in specs if spec["key"] != "online-pending-payment"]
        created_or_skipped = 0

        for spec in specs:
            marker = f"{SEED_TAG}:order:{spec['key']}"
            order = Order.objects.filter(description=marker).first()

            if not order:
                self._create_single_order(spec, marker, payment_type)

            created_or_skipped += 1

        return created_or_skipped

    def _create_single_order(self, spec, marker, payment_type):
        service = spec["service"]
        price = int(service.base_price or 0)
        appointment_date = timezone.localdate() + timedelta(days=spec["days"])
        start_time = spec["start"]
        duration = int(service.duration_minutes or 30)
        buffer_minutes = int(service.buffer_minutes or 0)
        end_time = self._add_minutes(start_time, duration)
        occupied_until = self._add_minutes(start_time, duration + buffer_minutes)
        is_final = spec["status"] in {"confirmed", "paid", "completed"}
        is_paid = spec["status"] in {"paid", "completed"}

        order = Order.objects.create(
            customer=spec["customer"],
            salon=spec["salon"],
            status=spec["status"],
            is_finally=is_final,
            is_paid=is_paid,
            description=marker,
            payment_type=payment_type,
            stylist_approved=is_final,
            selected_payment_method=spec["payment_method"],
            requires_online_payment=spec["payment_method"] == "online",
            subtotal_amount=price,
            total_amount=price,
            salon_payout_amount=price,
            booking_source="customer",
            reminder_due_at=self._aware_datetime(appointment_date, start_time)
            - timedelta(hours=24),
            reminder_status="pending",
        )

        detail = OrderDetail.objects.create(
            order=order,
            service=service,
            stylist=spec["stylist"],
            salon=spec["salon"],
            price=price,
            date=appointment_date,
            time=start_time,
            end_time=end_time,
            scheduled_duration_minutes=duration,
            buffer_minutes=buffer_minutes,
            occupied_until=occupied_until,
        )

        if spec["status"] in {"confirmed", "paid", "completed"}:
            detail.mark_confirmed(
                at=self._aware_datetime(appointment_date, start_time),
                save=True,
            )

        if spec["status"] == "completed":
            detail.mark_customer_arrived(
                at=self._aware_datetime(appointment_date, start_time),
                save=True,
            )
            detail.mark_service_started(
                at=self._aware_datetime(appointment_date, start_time),
                save=True,
            )
            detail.mark_service_completed(
                at=self._aware_datetime(appointment_date, end_time),
                save=True,
            )
            order.customer_arrived_at = self._aware_datetime(
                appointment_date,
                start_time,
            )
            order.service_started_at = self._aware_datetime(
                appointment_date,
                start_time,
            )
            order.service_completed_at = self._aware_datetime(
                appointment_date,
                end_time,
            )
            order.save(
                update_fields=[
                    "customer_arrived_at",
                    "service_started_at",
                    "service_completed_at",
                ]
            )

        if spec["status"] == "cancelled":
            order.cancellation_reason = "لغو ساختگی برای تست لوکال"
            order.save(update_fields=["cancellation_reason"])

        payment_state = spec.get("payment_state")

        if payment_state:
            self._create_payment(order, payment_state, marker)

        if spec["payment_method"] == "wallet" and is_paid:
            self._withdraw_from_wallet(order, marker)

        return order

    def _create_payment(self, order, state, marker):
        payment, _created = Payment.objects.get_or_create(
            idempotency_key=f"{marker}:payment",
            defaults={
                "order": order,
                "customer": order.customer,
                "amount": Decimal(order.total_amount or 0),
                "provider": Payment.Provider.MOCK,
                "purpose": Payment.Purpose.APPOINTMENT,
                "state": state,
                "description": f"{marker} - پرداخت ساختگی",
                "gateway_track_id": f"local-track-{order.pk}",
                "callback_token": f"local-callback-{order.pk}",
                "sandbox_mode": True,
                "meta": {
                    "seed_tag": SEED_TAG,
                    "order_marker": marker,
                },
            },
        )

        if state == Payment.State.SUCCESS and not payment.is_finally:
            payment.mark_success(
                ref_id=f"local-ref-{order.pk}",
                track_id=f"local-track-{order.pk}",
                status_code=100,
                meta={"seed_tag": SEED_TAG},
            )

        return payment

    def _withdraw_from_wallet(self, order, marker):
        wallet, _created = Wallet.objects.get_or_create(user=order.customer.user)
        already_withdrawn = wallet.transactions.filter(
            description__contains=marker
        ).exists()

        if already_withdrawn:
            return

        if wallet.balance < order.total_amount:
            wallet.deposit(
                int(order.total_amount or 0),
                description=f"{marker} - شارژ تکمیلی برای خرید تست",
                transaction_type=WalletTransaction.TransactionType.DEPOSIT,
                order=order,
            )

        wallet.withdraw(
            int(order.total_amount or 0),
            description=f"{marker} - برداشت کیف پول برای رزرو تست",
            transaction_type=WalletTransaction.TransactionType.PURCHASE,
            order=order,
        )

    def _aware_datetime(self, date_value, time_value):
        value = datetime.combine(date_value, time_value)

        if timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())

        return value

    def _add_minutes(self, start, minutes):
        value = datetime.combine(timezone.localdate(), start) + timedelta(
            minutes=int(minutes or 0)
        )
        return value.time()
