from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable



class BotRoleKey:
    CUSTOMER = "customer"
    STYLIST = "stylist"
    MANAGER = "manager"


ROLE_LABELS = {
    BotRoleKey.CUSTOMER: "مشتری",
    BotRoleKey.STYLIST: "متخصص",
    BotRoleKey.MANAGER: "مدیر سالن",
}


@dataclass(frozen=True)
class UserBotRole:
    key: str
    label: str
    is_active: bool = True
    object_id: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class UserBotRoleContext:
    user: object
    roles: tuple[UserBotRole, ...]

    @property
    def has_roles(self) -> bool:
        return bool(self.roles)

    @property
    def is_multi_role(self) -> bool:
        return len(self.roles) > 1

    def has_role(self, role_key: str) -> bool:
        return any(role.key == role_key for role in self.roles)

    def get_role(self, role_key: str) -> UserBotRole | None:
        return next((role for role in self.roles if role.key == role_key), None)

    @property
    def primary_role_key(self) -> str:
        return self.roles[0].key if self.roles else ""

    @property
    def role_labels_text(self) -> str:
        return "، ".join(role.label for role in self.roles)


def _has_related(user, attr_name: str) -> bool:
    try:
        return getattr(user, attr_name) is not None
    except Exception:
        return False


def _safe_count(queryset) -> int:
    try:
        return int(queryset.count())
    except Exception:
        return 0


def detect_user_bot_roles(user) -> UserBotRoleContext:
    """
    Resolve Loomera product roles for a connected messaging user.

    This function intentionally reads the same role objects used by the site:
    Customer, Stylist and SalonManager. It does not grant any permission by
    itself; operational permissions must still be checked in action handlers.
    """
    roles: list[UserBotRole] = []
    if not user or getattr(user, "is_anonymous", False):
        return UserBotRoleContext(user=user, roles=())

    if _has_related(user, "customer_profile"):
        roles.append(
            UserBotRole(
                key=BotRoleKey.CUSTOMER,
                label=ROLE_LABELS[BotRoleKey.CUSTOMER],
                object_id=getattr(getattr(user, "customer_profile", None), "pk", None),
            )
        )

    if _has_related(user, "stylist"):
        stylist = getattr(user, "stylist", None)
        metadata = {}
        try:
            from apps.salons.models import SalonMembership, SalonMembershipStatus

            active_memberships = SalonMembership.objects.filter(
                stylist=stylist,
                status=SalonMembershipStatus.ACTIVE,
            )
            pending_memberships = SalonMembership.objects.filter(
                stylist=stylist,
                status__in=[
                    SalonMembershipStatus.INVITED,
                    SalonMembershipStatus.PENDING_ACCEPTANCE,
                ],
            )
            metadata = {
                "active_salon_count": _safe_count(active_memberships),
                "pending_invite_count": _safe_count(pending_memberships),
            }
            try:
                from django.utils import timezone
                from django.db.models import Q
                from apps.orders.models import OrderDetail

                today = timezone.localdate()
                all_today_items = OrderDetail.objects.filter(
                    stylist=stylist,
                    date=today,
                )
                today_items = all_today_items.filter(
                    Q(order__status__in=["pending", "confirmed", "paid"])
                    | Q(
                        order__status="completed",
                        order__selected_payment_method="pay_in_salon",
                        order__is_paid=False,
                    )
                )
                metadata.update(
                    {
                        "today_appointment_count": _safe_count(all_today_items),
                        "today_ready_count": _safe_count(
                            today_items.filter(
                                service_started_at__isnull=True,
                                service_completed_at__isnull=True,
                                no_show_pending_at__isnull=True,
                                no_show_confirmed_at__isnull=True,
                            )
                        ),
                        "today_in_progress_count": _safe_count(
                            today_items.filter(
                                service_started_at__isnull=False,
                                service_completed_at__isnull=True,
                            )
                        ),
                        "today_cash_pending_count": _safe_count(
                            today_items.filter(
                                order__status="completed",
                                order__selected_payment_method="pay_in_salon",
                                order__is_paid=False,
                            )
                        ),
                    }
                )
            except Exception:
                metadata.update(
                    {
                        "today_appointment_count": 0,
                        "today_ready_count": 0,
                        "today_in_progress_count": 0,
                        "today_cash_pending_count": 0,
                    }
                )
        except Exception:
            metadata = {"active_salon_count": 0, "pending_invite_count": 0}
        roles.append(
            UserBotRole(
                key=BotRoleKey.STYLIST,
                label=ROLE_LABELS[BotRoleKey.STYLIST],
                is_active=bool(getattr(stylist, "is_active", True)),
                object_id=getattr(stylist, "pk", None),
                metadata=metadata,
            )
        )

    if _has_related(user, "salon_manager_profile"):
        manager = getattr(user, "salon_manager_profile", None)
        metadata = {}
        try:
            from apps.salons.models import Salon

            salons = Salon.objects.filter(salon_manager=manager)
            ordered_salons = list(
                salons.order_by("-is_active", "salon_name", "id").values(
                    "id", "salon_name", "is_active"
                )
            )
            salon_ids = [item["id"] for item in ordered_salons]
            metadata = {
                "salon_count": len(ordered_salons),
                "active_salon_count": sum(1 for item in ordered_salons if item["is_active"]),
                "first_salon_id": ordered_salons[0]["id"] if ordered_salons else None,
                "salons": [
                    {
                        "id": item["id"],
                        "name": item["salon_name"],
                        "is_active": bool(item["is_active"]),
                    }
                    for item in ordered_salons
                ],
            }
            try:
                from django.utils import timezone
                from apps.orders.models import OrderDetail
                from apps.stylists.models import StaffLeaveRequest, StaffScheduleRequest
                from apps.salons.models import SalonMembership, SalonMembershipStatus

                today = timezone.localdate()
                today_items = OrderDetail.objects.filter(
                    salon_id__in=salon_ids,
                    date=today,
                )
                membership_pending = SalonMembership.objects.filter(
                    salon_id__in=salon_ids,
                    status=SalonMembershipStatus.PENDING_ACCEPTANCE,
                    stylist__isnull=False,
                )
                leave_pending = StaffLeaveRequest.objects.filter(
                    salon_id__in=salon_ids,
                    status=StaffLeaveRequest.Status.PENDING,
                )
                schedule_pending = StaffScheduleRequest.objects.filter(
                    salon_id__in=salon_ids,
                    status=StaffScheduleRequest.Status.PENDING,
                )
                metadata.update(
                    {
                        "today_appointment_count": _safe_count(today_items),
                        "open_staff_request_count": (
                            _safe_count(membership_pending)
                            + _safe_count(leave_pending)
                            + _safe_count(schedule_pending)
                        ),
                    }
                )
            except Exception:
                metadata.update(
                    {
                        "today_appointment_count": 0,
                        "open_staff_request_count": 0,
                    }
                )
        except Exception:
            metadata = {"salon_count": 0, "active_salon_count": 0, "first_salon_id": None, "salons": [], "today_appointment_count": 0, "open_staff_request_count": 0}
        roles.append(
            UserBotRole(
                key=BotRoleKey.MANAGER,
                label=ROLE_LABELS[BotRoleKey.MANAGER],
                is_active=bool(getattr(manager, "is_active", True)),
                object_id=getattr(manager, "pk", None),
                metadata=metadata,
            )
        )

    return UserBotRoleContext(user=user, roles=tuple(roles))


def role_keys(context: UserBotRoleContext | Iterable[UserBotRole]) -> list[str]:
    if isinstance(context, UserBotRoleContext):
        return [role.key for role in context.roles]
    return [role.key for role in context]
