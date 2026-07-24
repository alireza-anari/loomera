from __future__ import annotations

from itertools import count

from django.utils import timezone

from apps.accounts.models import CustomUser, Customer, SalonManager, Stylist
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon
from apps.services.models import GroupServices, ServicePrice, Services
from apps.stylists.models import StaffLeaveRequest, StylistSchedule


class Stage1DomainFactoryMixin:
    _counter = count(1)

    def _next(self) -> int:
        return next(self._counter)

    def make_user(self, *, password="pass12345", is_active=True, **kwargs):
        index = self._next()
        defaults = {
            "mobile_number": f"0912{index:07d}"[:11],
            "email": f"user{index}@example.com",
            "name": f"User{index}",
            "family": "Test",
            "is_active": is_active,
        }
        defaults.update(kwargs)

        user = CustomUser.objects.create_user(
            mobile_number=defaults.pop("mobile_number"),
            email=defaults.pop("email"),
            name=defaults.pop("name"),
            family=defaults.pop("family"),
            password=password,
        )

        changed_fields = []
        for field, value in defaults.items():
            setattr(user, field, value)
            changed_fields.append(field)

        if changed_fields:
            user.save(update_fields=changed_fields)

        return user

    def make_customer(self, *, password="pass12345", is_active=True, **kwargs):
        user_kwargs = kwargs.pop("user_kwargs", {})
        user = self.make_user(password=password, is_active=is_active, **user_kwargs)
        return Customer.objects.create(user=user, **kwargs)

    def make_salon_manager(self, *, password="pass12345", is_active=True, **kwargs):
        user_kwargs = kwargs.pop("user_kwargs", {})
        user = self.make_user(password=password, is_active=is_active, **user_kwargs)
        return SalonManager.objects.create(user=user, is_active=True, **kwargs)

    def make_stylist(self, *, password="pass12345", is_active=True, **kwargs):
        user_kwargs = kwargs.pop("user_kwargs", {})
        user = self.make_user(password=password, is_active=is_active, **user_kwargs)
        defaults = {
            "expert": "زیبایی",
            "is_active": True,
        }
        defaults.update(kwargs)
        return Stylist.objects.create(user=user, **defaults)

    def make_service(
        self, *, name=None, duration_minutes=30, base_price=120_000, **kwargs
    ):
        index = self._next()
        group = GroupServices.objects.create(group_title=f"گروه تست {index}")

        defaults = {
            "service_name": name or f"خدمت تست {index}",
            "duration_minutes": duration_minutes,
            "base_price": base_price,
            "is_active": True,
        }
        defaults.update(kwargs)

        service = Services.objects.create(**defaults)
        service.service_group.add(group)
        return service

    def make_salon(self, *, manager, **kwargs):
        index = self._next()
        defaults = {
            "salon_name": f"سالن تست {index}",
            "salon_manager": manager,
            "description": "سالن تست",
            "address": "آدرس تست",
            "is_active": True,
        }
        defaults.update(kwargs)
        return Salon.objects.create(**defaults)

    def connect_service(self, *, salon, stylist, service, price=120_000):
        salon.services.add(service)
        salon.stylists.add(stylist)
        service.stylists.add(stylist)
        ServicePrice.objects.update_or_create(
            stylist=stylist,
            service=service,
            defaults={"price": price},
        )
        return service


    def add_schedule(self, *, stylist, salon, service, date_value, start, end):
        existing = StylistSchedule.objects.filter(
            stylist=stylist,
            date=date_value,
            start_time=start,
        ).first()

        if existing:
            changed_fields = []

            if existing.salon_id != salon.id:
                existing.salon = salon
                changed_fields.append("salon")

            if existing.end_time != end:
                existing.end_time = end
                changed_fields.append("end_time")

            # مدل فعلی روی stylist/date/start_time محدودیت unique دارد.
            # وقتی تست برای دو خدمت در یک بازه یکسان schedule می‌سازد،
            # برنامه را عمومی می‌کنیم تا برای هر دو خدمت معتبر باشد.
            if existing.service_id != getattr(service, "id", None):
                existing.service = None
                changed_fields.append("service")

            if changed_fields:
                existing.save(update_fields=changed_fields)

            return existing

        return StylistSchedule.objects.create(
            stylist=stylist,
            salon=salon,
            service=service,
            date=date_value,
            start_time=start,
            end_time=end,
        )

    def add_time_off(self, *, stylist, date_value, start=None, end=None, reason="تست", salon=None):
        target_salon = salon or getattr(self, "salon", None)
        if target_salon is None:
            raise ValueError("برای ساخت مرخصی تستی، salon لازم است.")

        return StaffLeaveRequest.objects.create(
            salon=target_salon,
            stylist=stylist,
            date=date_value,
            start_time=start,
            end_time=end,
            reason=reason,
            status=StaffLeaveRequest.Status.APPROVED,
        )

    def make_order(self, *, customer, salon, **kwargs):
        defaults = {
            "customer": customer,
            "salon": salon,
            "selected_payment_method": "pay_in_salon",
            "status": "confirmed",
            "is_paid": False,
            "is_finally": True,
            "subtotal_amount": 120_000,
            "total_amount": 120_000,
            "salon_payout_amount": 120_000,
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def make_order_detail(
        self,
        *,
        order,
        service,
        stylist,
        salon,
        date_value,
        start,
        end,
        price=120_000,
        **kwargs,
    ):
        duration = int(
            (
                timezone.datetime.combine(date_value, end)
                - timezone.datetime.combine(date_value, start)
            ).total_seconds()
            // 60
        )
        defaults = {
            "order": order,
            "service": service,
            "stylist": stylist,
            "salon": salon,
            "price": price,
            "date": date_value,
            "time": start,
            "end_time": end,
            "scheduled_duration_minutes": max(duration, 0),
            "buffer_minutes": getattr(service, "buffer_minutes", 0) or 0,
            "occupied_until": end,
        }
        defaults.update(kwargs)
        return OrderDetail.objects.create(**defaults)
