from django import template

from apps.dashboards.layout import build_dashboard_context

register = template.Library()


DEFAULT_HEADER = {
    "salon_name": "سالن شما",
    "manager_name": "مدیر سالن",
    "working_hours": "ساعت کاری ثبت نشده",
    "notifications_count": 0,
    "pending_approvals": 0,
    "team_count": 0,
    "is_active": False,
}


DEFAULT_PAGE_META = {
    "title": "داشبورد",
    "description": "نمای عملیاتی بخش مدیریت سالن.",
    "icon": "fa-solid fa-grid-2",
    "badges": [],
    "primary_action": None,
}


def _resolve_shell_context(context):
    cached = context.get("_dashboard_shell_context")
    if cached:
        return cached

    request = context.get("request")
    if request is None:
        shell = {
            "dashboard_nav_items": context.get("dashboard_nav_items", []),
            "dashboard_sidebar_sections": context.get("dashboard_sidebar_sections", []),
            "dashboard_sidebar_items": context.get("dashboard_sidebar_items", []),
            "dashboard_mobile_nav_items": context.get("dashboard_mobile_nav_items", []),
            "dashboard_quick_actions": context.get("dashboard_quick_actions", []),
            "dashboard_header": context.get("dashboard_header", DEFAULT_HEADER),
            "page_meta": context.get("page_meta", DEFAULT_PAGE_META),
            "salon": context.get("salon"),
            "page_title": context.get("page_title", "داشبورد"),
        }
    else:
        shell = build_dashboard_context(
            request.user,
            nav_active=context.get("nav_active", "home"),
            sidebar_active=context.get("sidebar_active", "overview"),
            page_title=context.get("page_title", "داشبورد"),
            request_path=request.path,
        )
        request = context.get("request")
        dashboard_current_path = ""

        if request is not None:
            try:
                dashboard_current_path = request.get_full_path()
            except Exception:
                dashboard_current_path = getattr(request, "path", "") or ""
        else:
            dashboard_current_path = (
                context.get("dashboard_current_path")
                or context.get("dashboard_request_path")
                or ""
            )
        shell.update(
            {
                "dashboard_nav_items": context.get(
                    "dashboard_nav_items", shell.get("dashboard_nav_items", [])
                ),
                "dashboard_sidebar_sections": context.get(
                    "dashboard_sidebar_sections",
                    shell.get("dashboard_sidebar_sections", []),
                ),
                "dashboard_sidebar_items": context.get(
                    "dashboard_sidebar_items", shell.get("dashboard_sidebar_items", [])
                ),
                "dashboard_mobile_nav_items": context.get(
                    "dashboard_mobile_nav_items",
                    shell.get("dashboard_mobile_nav_items", []),
                ),
                "dashboard_quick_actions": context.get(
                    "dashboard_quick_actions", shell.get("dashboard_quick_actions", [])
                ),
                "dashboard_header": context.get(
                    "dashboard_header", shell.get("dashboard_header", DEFAULT_HEADER)
                ),
                "page_meta": context.get(
                    "page_meta", shell.get("page_meta", DEFAULT_PAGE_META)
                ),
                "salon": context.get("salon", shell.get("salon")),
                "page_title": context.get(
                    "page_title", shell.get("page_title", "داشبورد")
                ),
                "stylist_active_memberships": context.get(
                    "stylist_active_memberships",
                    shell.get("stylist_active_memberships", []),
                ),
                "stylist_salon": context.get(
                    "stylist_salon",
                    shell.get("stylist_salon"),
                ),
                "request": request,
                "dashboard_current_path": dashboard_current_path,
            }
        )

    context["_dashboard_shell_context"] = shell
    return shell


@register.inclusion_tag("partials/dashboard/sidebar.html", takes_context=True)
def dashboard_sidebar(context):
    return _resolve_shell_context(context)


@register.inclusion_tag("partials/dashboard/navbar.html", takes_context=True)
def dashboard_navbar(context):
    return _resolve_shell_context(context)


@register.inclusion_tag("partials/dashboard/header.html", takes_context=True)
def dashboard_header(context):
    return _resolve_shell_context(context)


@register.inclusion_tag("partials/dashboard/mobile_nav.html", takes_context=True)
def dashboard_mobile_nav(context):
    return _resolve_shell_context(context)
