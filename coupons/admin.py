from django.contrib import admin

from .models import Category, Coupon, CouponCategory, Merchant

admin.site.register(Merchant)
admin.site.register(Category)
admin.site.register(Coupon)
admin.site.register(CouponCategory)
