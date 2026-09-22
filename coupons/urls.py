from django.urls import path

app_name = 'coupons'

urlpatterns = [
    # GET               /api/v1/coupons           -- list coupons (search, category, source, status, sort)
    # GET               /api/v1/coupons/{id}      -- retrieve a single coupon's detail
    # PATCH             /api/v1/coupons/{id}      -- update a coupon (mark used, change category)
    # DELETE            /api/v1/coupons/{id}      -- delete a coupon owned by the user
    # GET               /api/v1/coupons/expiring  -- list coupons expiring within a configurable window (FR-6.2)
]
