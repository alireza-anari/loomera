from __future__ import annotations

from typing import Any, Protocol

from ..context import LumiContext


class LoomeraDomainGateway(Protocol):
    """Port used by tools. Tool handlers never import/read Django models directly."""

    def get_my_profile(self, *, context: LumiContext) -> dict[str, Any]: ...

    def get_services(self, *, salon_id: int | None = None, query: str = "", limit: int = 20) -> dict[str, Any]: ...

    def get_service_price(
        self,
        *,
        salon_id: int,
        service_id: int,
        stylist_id: int | None = None,
    ) -> dict[str, Any]: ...

    def get_contact(self, *, salon_id: int) -> dict[str, Any]: ...

    def get_availability(
        self,
        *,
        salon_id: int,
        service_id: int,
        stylist_id: int | None = None,
        date: str = "",
        period: str = "",
        limit: int = 18,
    ) -> dict[str, Any]: ...

    def prepare_booking(self, *, context: LumiContext, arguments: dict[str, Any]) -> dict[str, Any]: ...
