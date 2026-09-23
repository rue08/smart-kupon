from django.contrib import admin

from .models import Category, Coupon, CouponCategory, Merchant

admin.site.register(Merchant)
admin.site.register(Category)
admin.site.register(CouponCategory)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    # `status` is refreshed by coupons.status_refresh on a schedule (or on a
    # single-row API read) rather than on every write, so it can lag the true
    # value by up to COUPON_STATUS_REFRESH_MINUTES here in the admin.
    list_display = ['coupon_code', 'merchant', 'status', 'expiry_date', 'is_low_confidence', 'user']
    list_filter = ['status', 'is_low_confidence']
    search_fields = ['coupon_code', 'merchant__name']
