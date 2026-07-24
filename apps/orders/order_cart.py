from apps.accounts.models import Stylist
from apps.salons.models import Salon
from apps.services.models import Services


# -----------------------------------------------------------------------------------------------------
class OrderCart:
    def __init__(self, request):
        self.session = request.session
        temp = self.session.get("order_cart")
        if not temp:
            temp = self.session["order_cart"] = {}
        self.order_cart = temp
        self.count = len(self.order_cart.keys())

    def add_to_order_cart(self, service, stylist, salon, date, time):
        service_id = str(service.id)
        if service_id not in self.order_cart:
            self.order_cart[service_id] = {
                "service_id": service.id,
                "stylist_id": stylist.user_id if stylist else None,
                "salon_id": salon.id if salon else None,
                "date": date,
                "time": time,
                "price": stylist.get_price_for_service(service),
                "final_price": stylist.get_price_by_discount(service),
            }
            # پیام موفقیت را در سشن ذخیره کنید
            self.session["order_cart_message"] = (
                "خدمت به سبد سفارش شما اضافه شد.",
                "success",
            )
        else:
            # پیام اخطار را در سشن ذخیره کنید
            self.session["order_cart_message"] = (
                "این خدمت در سبد سفارش شما قرار دارد.",
                "warning",
            )

        self.save()

    def delete_from_order_cart(self, service):
        service_id = str(service.id)
        if service_id in self.order_cart:
            del self.order_cart[service_id]
        self.save()

    def __iter__(self):
        service_ids = self.order_cart.keys()
        services = Services.objects.filter(id__in=service_ids)
        temp_order_cart = self.order_cart.copy()

        for service in services:
            service_id = str(service.id)  # type: ignore
            item = temp_order_cart[service_id]
            # بازیابی آرایشگر و سالن برای هر آیتم
            stylist = (
                Stylist.objects.filter(user_id=item["stylist_id"]).first()
                if item["stylist_id"]
                else None
            )
            salon = Salon.objects.filter(id=item["salon_id"]).first() if item["salon_id"] else None
            item["service"] = service
            item["stylist"] = stylist
            item["salon"] = salon
            yield item

    def update(
        self,
        service_id_list,
        stylist_id_list,
        salon_id_list,
        date_value_list,
        time_value_list,
    ):
        if salon_id_list or stylist_id_list:
            i = 0
            for service_id in service_id_list:
                self.order_cart[service_id]["stylist_id"] = stylist_id_list[i]
                self.order_cart[service_id]["salon_id"] = salon_id_list[i]
                i += 1
            self.save()
        elif date_value_list or time_value_list:
            i = 0
            for service_id in service_id_list:
                self.order_cart[service_id]["date"] = date_value_list[i]
                self.order_cart[service_id]["time"] = time_value_list[i]
                i += 1
            self.save()

    def save(self):
        self.session.modified = True

    def calc_total_price(self):
        sum = 0
        for item in self.order_cart.values():
            sum += int(item["final_price"])
        return sum


# from apps.services.models import Services
# from apps.accounts.models import Stylist
# from apps.salons.models import Salon


# class OrderCart:
#     def __init__(self, request):
#         self.session = request.session
#         temp = self.session.get("order_cart")
#         if not temp:
#             temp = self.session["order_cart"] = {}
#         self.order_cart = temp

#     @property
#     def count(self):
#         """Calculate the number of items in the order cart."""
#         return sum(len(item) for item in self.order_cart.values())

#     def add_to_order_cart(
#         self, service=None, stylist=None, salon=None, date=None, time=None
#     ):
#         cart_item = {}
#         item_id = len(self.order_cart) + 1

#         # افزودن مقادیر اختیاری به آیتم
#         if service:
#             cart_item["service"] = service
#         if stylist:
#             cart_item["stylist"] = stylist.user.id
#         if salon:
#             cart_item["salon"] = salon.id
#         if date:
#             cart_item["date"] = date
#         if time:
#             cart_item["time"] = time

#         self.order_cart[item_id] = cart_item
#         self.save()

#     def save(self):
#         """ذخیره‌ی سبد خرید در جلسه"""
#         self.session.modified = True

#     def delete(self, item_id):
#         """حذف یک آیتم از سبد سفارش"""
#         if str(item_id) in self.order_cart:
#             del self.order_cart[str(item_id)]
#             self.save()

#     def update(
#         self, item_id, service=None, stylist=None, salon=None, date=None, time=None
#     ):
#         """به‌روزرسانی یک آیتم در سبد سفارش"""
#         if str(item_id) in self.order_cart:
#             cart_item = self.order_cart[str(item_id)]

#             # به‌روزرسانی مقادیر در صورت وجود
#             if service:
#                 cart_item["service"] = service
#             if stylist:
#                 cart_item["stylist"] = stylist.user.id
#             if salon:
#                 cart_item["salon"] = salon.id
#             if date:
#                 cart_item["date"] = date
#             if time:
#                 cart_item["time"] = time

#             self.order_cart[str(item_id)] = cart_item
#             self.save()

#     def __iter__(self):
#         """آیتم‌های سبد سفارش برای نمایش"""
#         service_ids = [
#             item.get("service")
#             for item in self.order_cart.values()
#             if item.get("service")
#         ]
#         services = Services.objects.filter(id__in=service_ids)
#         cart_copy = self.order_cart.copy()
#         for service in services:
#             cart_copy[str(service.pk)]["service"] = service

#         for item in cart_copy.values():
#             stylist_id = item.get("stylist")
#             salon_id = item.get("salon")
#             if stylist_id:
#                 try:
#                     item["stylist"] = Stylist.objects.get(user__id=stylist_id)
#                 except Stylist.DoesNotExist:
#                     item["stylist"] = None
#             if salon_id:
#                 try:
#                     item["salon"] = Salon.objects.get(id=salon_id)
#                 except Salon.DoesNotExist:
#                     item["salon"] = None
#             item["price"] = item["service"].service_prices if "service" in item else 0
#             item["total_price"] = item["price"]
#             yield item

#     def calc_total_price(self):
#         """محاسبه‌ی قیمت نهایی سبد سفارش"""
#         total = sum(
#             int(item["price"]) for item in self.order_cart.values() if "price" in item
#         )
#         return total
