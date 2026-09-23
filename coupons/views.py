from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status as http_status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Coupon
from .serializers import CouponSerializer, CouponUpdateSerializer


class CouponPagination(PageNumberPagination):
    page_size = 20


def _base_queryset(user):
    return Coupon.objects.filter(user=user).select_related('merchant', 'message').prefetch_related('categories')


def _apply_filters(queryset, params):
    """FR-5.2 search, FR-5.3 filtering."""
    search = params.get('search')
    if search:
        queryset = queryset.filter(Q(coupon_code__icontains=search) | Q(merchant__name__icontains=search))

    category = params.get('category')
    if category:
        queryset = queryset.filter(categories__name__iexact=category)

    source = params.get('source')
    if source:
        queryset = queryset.filter(message__source_type=source)

    status_param = params.get('status')
    if status_param:
        queryset = queryset.filter(status=status_param)

    return queryset


def _apply_sort(queryset, params):
    """FR-5.4 sorting."""
    sort = params.get('sort')
    if sort == 'expiry_date':
        return queryset.order_by('expiry_date')
    if sort == 'discount_value':
        return queryset.order_by('discount_value')
    return queryset.order_by('-created_at')


def _paginated_response(queryset, request):
    paginator = CouponPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = CouponSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


class CouponListView(APIView):
    """GET /api/v1/coupons -- FR-5.1 dashboard, with search/category/source/status/sort."""

    def get(self, request):
        queryset = _base_queryset(request.user)
        queryset = _apply_filters(queryset, request.query_params)
        queryset = _apply_sort(queryset, request.query_params)
        return _paginated_response(queryset, request)


class CouponExpiringView(APIView):
    """GET /api/v1/coupons/expiring -- FR-6.2, a focused expiring_soon view."""

    def get(self, request):
        queryset = _base_queryset(request.user).filter(status=Coupon.Status.EXPIRING_SOON).order_by('expiry_date')
        return _paginated_response(queryset, request)


class CouponDetailView(APIView):
    """GET/PATCH/DELETE /api/v1/coupons/{id}."""

    def _get_object(self, request, coupon_id):
        coupon = get_object_or_404(_base_queryset(request.user), coupon_id=coupon_id)
        # Self-heal: a single-row read is cheap, so always show the accurate
        # status here even if the scheduled bulk refresh (coupons.status_refresh)
        # hasn't caught this row yet.
        computed = coupon.compute_status()
        if computed != coupon.status:
            coupon.status = computed
            coupon.save(update_fields=['status'])
        return coupon

    def get(self, request, coupon_id):
        coupon = self._get_object(request, coupon_id)
        return Response(CouponSerializer(coupon).data)

    def patch(self, request, coupon_id):
        coupon = self._get_object(request, coupon_id)
        serializer = CouponUpdateSerializer(coupon, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(CouponSerializer(coupon).data)

    def delete(self, request, coupon_id):
        coupon = get_object_or_404(Coupon, coupon_id=coupon_id, user=request.user)
        coupon.delete()
        return Response(status=http_status.HTTP_204_NO_CONTENT)
