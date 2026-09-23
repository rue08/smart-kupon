from rest_framework import serializers

from .models import Category, Coupon, Merchant


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['category_id', 'name']


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ['merchant_id', 'name']


class CouponSerializer(serializers.ModelSerializer):
    merchant = MerchantSerializer(read_only=True)
    categories = CategorySerializer(many=True, read_only=True)
    source = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            'coupon_id', 'merchant', 'categories', 'coupon_code', 'discount_value',
            'expiry_date', 'status', 'is_low_confidence', 'source', 'created_at',
        ]

    def get_source(self, obj):
        return obj.message.source_type if obj.message_id else None


class CouponUpdateSerializer(serializers.ModelSerializer):
    """PATCH /api/v1/coupons/{id} -- FR-4.4 manual actions.

    `status` may only be set to `used` here: active/expiring_soon/expired are
    derived from expiry_date (Coupon.compute_status), not client-settable.
    """

    category_ids = serializers.PrimaryKeyRelatedField(
        source='categories', queryset=Category.objects.all(), many=True, required=False,
    )

    class Meta:
        model = Coupon
        fields = ['status', 'category_ids']

    def validate_status(self, value):
        if value != Coupon.Status.USED:
            raise serializers.ValidationError('status can only be set to "used" via this endpoint.')
        return value
