from django.urls import path

from . import views

app_name = 'coupons'

urlpatterns = [
    path('', views.CouponListView.as_view(), name='coupon-list'),
    path('expiring', views.CouponExpiringView.as_view(), name='coupon-expiring'),
    path('<uuid:coupon_id>', views.CouponDetailView.as_view(), name='coupon-detail'),
]
