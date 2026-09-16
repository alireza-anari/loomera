from __future__ import annotations

from typing import Any

from ..context import LumiContext


class StagingLoomeraGateway:
    """Adapter from Lumi's stable domain port to current Loomera services.

    This module is deliberately Django/ORM-free. Current staging implementation
    details live behind `apps.help_center.lumi_domain_service`, so the LLM,
    orchestrator, policies and tools never import Django models.
    """

    @staticmethod
    def _service():
        # Lazy import keeps the Tool Layer importable in isolated unit tests and
        # prevents current Django implementation details from leaking into Lumi.
        from apps.help_center import lumi_domain_service

        return lumi_domain_service

    def get_my_profile(self, *, context: LumiContext) -> dict[str, Any]:
        return self._service().get_lumi_profile(
            actor=context.actor,
            authenticated=context.authenticated,
            primary_role=context.primary_role,
            roles=context.roles,
        )

    def get_services(self, *, salon_id: int | None = None, query: str = "", limit: int = 20) -> dict[str, Any]:
        return self._service().get_services(salon_id=salon_id, query=query, limit=limit)

    def get_service_price(
        self,
        *,
        salon_id: int,
        service_id: int,
        stylist_id: int | None = None,
    ) -> dict[str, Any]:
        return self._service().get_service_price(
            salon_id=salon_id,
            service_id=service_id,
            stylist_id=stylist_id,
        )

    def get_contact(self, *, salon_id: int) -> dict[str, Any]:
        return self._service().get_contact(salon_id=salon_id)

    def get_availability(
        self,
        *,
        salon_id: int,
        service_id: int,
        stylist_id: int | None = None,
        date: str = "",
        period: str = "",
        limit: int = 18,
    ) -> dict[str, Any]:
        return self._service().get_availability(
            salon_id=salon_id,
            service_id=service_id,
            stylist_id=stylist_id,
            date=date,
            period=period,
            limit=limit,
        )

    def prepare_booking(self, *, context: LumiContext, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._service().prepare_booking(request=context.request, arguments=arguments)
