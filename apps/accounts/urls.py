from django.urls import path
from django.views.generic import TemplateView

from .views import (
    CustomerSignupView,
    StylistSignupView,
    RegisterUserView,
    VerifyRegisterView,
    LoginUserView,
    LogoutUserView,
    ChangePasswordView,
    RememberPasswordView,
    CustomerUpdateProfileView,
    CustomerPanelPageView,
    CustomerProfilePageView,
    CustomerAddressListView,
    CustomerAddressCreateView,
    CustomerAddressUpdateView,
    customer_address_delete,
    customer_address_set_default,
    customer_update_profile_image,
    add_customer,
    DetailCustomerView,
    delete_customer_note,
    CustomerSettingsView,
    NotificationSettingsView,
    update_notification_settings,
    DeleteAccountView,
    CustomerNotificationsView,
    customer_notifications_summary,
    mark_customer_notification_read,
    mark_all_customer_notifications_read,
)

# ----------------------------------------------------------------
app_name = "accounts"
urlpatterns = [
    path("customer-signup/", CustomerSignupView.as_view(), name="customer_signup"),
    path("stylist-signup/", StylistSignupView.as_view(), name="stylist_signup"),
    path("register/", RegisterUserView.as_view(), name="register"),
    path("verify/", VerifyRegisterView.as_view(), name="verify"),
    path("login/", LoginUserView.as_view(), name="login"),
    path("logout/", LogoutUserView.as_view(), name="logout"),
    path("change_password/", ChangePasswordView.as_view(), name="change_password"),
    path(
        "remember_password/", RememberPasswordView.as_view(), name="remember_password"
    ),
    path(
        "customerUpdateProfile",
        CustomerUpdateProfileView.as_view(),
        name="customer_update_profile",
    ),
    path("customerPanel", CustomerPanelPageView.as_view(), name="customer_panel"),
    path("customerProfile", CustomerProfilePageView.as_view(), name="customerProfile"),
    path(
        "update-profile-image/",
        customer_update_profile_image,
        name="customer_update_profile_image",
    ),
    path("addresses/", CustomerAddressListView.as_view(), name="customer_addresses"),
    path(
        "addresses/add/",
        CustomerAddressCreateView.as_view(),
        name="customer_address_add",
    ),
    path(
        "addresses/<int:address_id>/edit/",
        CustomerAddressUpdateView.as_view(),
        name="customer_address_edit",
    ),
    path(
        "addresses/<int:address_id>/delete/",
        customer_address_delete,
        name="customer_address_delete",
    ),
    path(
        "addresses/<int:address_id>/default/",
        customer_address_set_default,
        name="customer_address_set_default",
    ),
    path("add_customer/<int:salon_id>/", add_customer, name="add_customer"),
    path(
        "detail_customer/<int:customer_id>/",
        DetailCustomerView.as_view(),
        name="detail_customer",
    ),
    path(
        "customer/<int:customer_id>/note/<int:note_id>/delete/",
        delete_customer_note,
        name="delete_customer_note",
    ),
    path(
        "customer_settings/", CustomerSettingsView.as_view(), name="customer_settings"
    ),
    path(
        "notification_settings/",
        NotificationSettingsView.as_view(),
        name="notification_settings",
    ),
    path(
        "api/update-notification-settings/",
        update_notification_settings,
        name="update_notification_settings",
    ),
    path(
        "notifications/",
        CustomerNotificationsView.as_view(),
        name="notifications",
    ),
    path(
        "api/notifications/summary/",
        customer_notifications_summary,
        name="notifications_summary",
    ),
    path(
        "api/notifications/<int:notification_id>/read/",
        mark_customer_notification_read,
        name="notification_read",
    ),
    path(
        "api/notifications/read-all/",
        mark_all_customer_notifications_read,
        name="notifications_read_all",
    ),
    path(
        "delete-account/",
        DeleteAccountView.as_view(),
        name="delete_account",
    ),
    path(
        "privacy-policy/",
        TemplateView.as_view(template_name="accounts/privacy_policy.html"),
        name="privacy_policy",
    ),
    path(
        "terms-of-use/",
        TemplateView.as_view(template_name="accounts/terms_of_use.html"),
        name="terms_of_use",
    ),
    path(
        "social-login-info/",
        TemplateView.as_view(template_name="accounts/social_login_info.html"),
        name="social_login_info",
    ),
]
