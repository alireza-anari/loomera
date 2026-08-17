from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.dashboards.views import _stylist_detail_status_meta


class _ConfirmationStatus:
    REJECTED = "rejected"


class _ServiceLifecycleStatus:
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    ARRIVED = "arrived"
    IN_SERVICE = "in_service"
    COMPLETED = "completed"
    DISPUTED = "disputed"


def _detail(*, order_status="confirmed", lifecycle_status="confirmed"):
    return SimpleNamespace(
        order=SimpleNamespace(status=order_status, is_finally=True),
        confirmation_status="confirmed",
        lifecycle_status=lifecycle_status,
        ConfirmationStatus=_ConfirmationStatus,
        ServiceLifecycleStatus=_ServiceLifecycleStatus,
    )


class StylistNoShowStatusUxTests(SimpleTestCase):
    def test_final_no_show_has_explicit_status(self):
        meta = _stylist_detail_status_meta(
            _detail(order_status="no_show", lifecycle_status="no_show_confirmed")
        )
        self.assertEqual(meta["label"], "عدم حضور تأیید شد")

    def test_pending_no_show_is_not_mislabelled_as_waiting_for_confirmation(self):
        meta = _stylist_detail_status_meta(
            _detail(lifecycle_status="no_show_pending_review")
        )
        self.assertEqual(meta["label"], "عدم حضور در انتظار بررسی")

    def test_service_overrun_has_explicit_status(self):
        meta = _stylist_detail_status_meta(
            _detail(lifecycle_status="service_overrun")
        )
        self.assertEqual(meta["label"], "زمان خدمت بیشتر شد")
