from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from sources.models import SourceMessage

from . import dedup, extraction
from .models import Category, Coupon, Merchant
from .pipeline import process_message
from .status_refresh import refresh_statuses
from .views import CouponDetailView, CouponExpiringView, CouponListView


class ExtractionTests(TestCase):
    def test_code_via_keyword(self):
        result = extraction.extract('From: AD-AMAZNIN\nUse code SAVE20 to get 20% off, valid till 25/12.')
        self.assertEqual(result.coupon_code, 'SAVE20')

    def test_code_standalone_fallback(self):
        result = extraction.extract('From: FLPKRT\nFLAT50 on your next order at Flipkart!')
        self.assertEqual(result.coupon_code, 'FLAT50')

    def test_discount_extracted(self):
        result = extraction.extract('Use code SAVE20 for 20% off at Amazon.')
        self.assertEqual(result.discount_value.replace(' ', ''), '20%off')

    def test_relative_weekday_expiry_is_in_the_future(self):
        result = extraction.extract('Use code SAVE20 at Amazon, valid till Sunday!')
        self.assertIsNotNone(result.expiry_date)
        self.assertGreater(result.expiry_date, timezone.localdate())
        self.assertEqual(result.expiry_date.weekday(), 6)  # Sunday

    def test_relative_days_expiry(self):
        result = extraction.extract('Use code SAVE20 at Amazon, expires in 5 days.')
        self.assertEqual(result.expiry_date, timezone.localdate() + timedelta(days=5))

    def test_absolute_date_expiry(self):
        result = extraction.extract('Use code SAVE20 at Amazon, valid till 25/12/2026.')
        self.assertEqual(result.expiry_date, timezone.datetime(2026, 12, 25).date())

    def test_no_code_returns_none(self):
        self.assertIsNone(extraction.extract('Your OTP for login is 483920. Do not share it.'))

    def test_low_confidence_when_merchant_and_expiry_missing(self):
        result = extraction.extract('Use code SAVE20 for a discount.')
        self.assertTrue(result.is_low_confidence)

    def test_high_confidence_when_everything_resolves(self):
        result = extraction.extract('From: AD-AMAZNIN\nUse code SAVE20 for 20% off at Amazon, valid till 25/12/2026.')
        self.assertFalse(result.is_low_confidence)


class DedupTests(TestCase):
    def test_normalize_collapses_variants(self):
        # Domain/case noise ("amazon.in" -> "Amazon") is merchants.resolve_merchant's
        # job; normalize() only case-folds and strips punctuation/whitespace.
        self.assertEqual(dedup.normalize('Amazon'), dedup.normalize('AMAZON'))
        self.assertEqual(dedup.normalize('SAVE-20'), dedup.normalize('save 20'))
        self.assertEqual(dedup.normalize('AMAZON'), 'amazon')

    def test_build_dedup_key_combines_merchant_and_code(self):
        self.assertEqual(dedup.build_dedup_key('Amazon', 'SAVE20'), 'amazon:save20')
        self.assertEqual(dedup.build_dedup_key(None, 'SAVE20'), ':save20')


class PipelineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(name='Test User', email='t@example.com', auth_provider_ref='uid-1')

    def _sms(self, body, sender='AD-AMAZNIN'):
        return SourceMessage.objects.create(
            user=self.user, source_type=SourceMessage.SourceType.SMS,
            raw_ref=f'From: {sender}\n{body}',
        )

    def test_creates_coupon_and_clears_raw_ref(self):
        message = self._sms('Use code SAVE20 for 20% off at Amazon, valid till 25/12/2026.')
        coupon = process_message(message)

        message.refresh_from_db()
        self.assertIsNone(message.raw_ref)
        self.assertIsNotNone(coupon)
        self.assertEqual(coupon.coupon_code, 'SAVE20')
        self.assertEqual(coupon.merchant.name, 'Amazon')
        self.assertEqual(coupon.user, self.user)

    def test_no_coupon_data_clears_raw_ref_without_creating_coupon(self):
        message = self._sms('Your OTP is 483920.', sender='VM-OTPSVC')
        coupon = process_message(message)

        message.refresh_from_db()
        self.assertIsNone(message.raw_ref)
        self.assertIsNone(coupon)
        self.assertEqual(Coupon.objects.count(), 0)

    def test_resync_same_offer_merges_instead_of_duplicating(self):
        process_message(self._sms('Use code SAVE20 for 20% off at Amazon.'))
        process_message(self._sms('Use code SAVE20 at Amazon, valid till 25/12/2026.'))

        self.assertEqual(Coupon.objects.count(), 1)
        coupon = Coupon.objects.get()
        # First message had no expiry; the second fills it in (FR-4.2 merge).
        self.assertEqual(coupon.expiry_date, timezone.datetime(2026, 12, 25).date())

    def test_auto_categorization_for_known_merchant(self):
        process_message(self._sms('Use code SAVE20 for 20% off at Amazon.'))
        coupon = Coupon.objects.get()
        self.assertEqual(list(coupon.categories.values_list('name', flat=True)), ['Shopping'])


class StatusComputationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(name='Test User', email='t2@example.com', auth_provider_ref='uid-2')

    def _coupon(self, expiry_date, status=Coupon.Status.ACTIVE):
        return Coupon.objects.create(
            user=self.user, coupon_code='X', dedup_key=f'x{expiry_date}{status}', expiry_date=expiry_date,
            status=status,
        )

    def test_far_future_is_active(self):
        coupon = self._coupon(timezone.localdate() + timedelta(days=30))
        self.assertEqual(coupon.compute_status(), Coupon.Status.ACTIVE)

    def test_within_window_is_expiring_soon(self):
        coupon = self._coupon(timezone.localdate() + timedelta(days=2))
        self.assertEqual(coupon.compute_status(), Coupon.Status.EXPIRING_SOON)

    def test_today_is_expiring_soon_not_expired(self):
        coupon = self._coupon(timezone.localdate())
        self.assertEqual(coupon.compute_status(), Coupon.Status.EXPIRING_SOON)

    def test_past_is_expired(self):
        coupon = self._coupon(timezone.localdate() - timedelta(days=1))
        self.assertEqual(coupon.compute_status(), Coupon.Status.EXPIRED)

    def test_used_overrides_date(self):
        coupon = self._coupon(timezone.localdate() - timedelta(days=1), status=Coupon.Status.USED)
        self.assertEqual(coupon.compute_status(), Coupon.Status.USED)

    def test_null_expiry_is_active(self):
        coupon = Coupon.objects.create(user=self.user, coupon_code='Y', dedup_key='y', expiry_date=None)
        self.assertEqual(coupon.compute_status(), Coupon.Status.ACTIVE)

    def test_refresh_statuses_bulk_updates_without_touching_used(self):
        expired = self._coupon(timezone.localdate() - timedelta(days=1))
        used = self._coupon(timezone.localdate() - timedelta(days=1), status=Coupon.Status.USED)

        refresh_statuses()

        expired.refresh_from_db()
        used.refresh_from_db()
        self.assertEqual(expired.status, Coupon.Status.EXPIRED)
        self.assertEqual(used.status, Coupon.Status.USED)


class CouponViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create(name='Test User', email='t3@example.com', auth_provider_ref='uid-3')
        self.merchant = Merchant.objects.create(name='Amazon')
        self.category = Category.objects.create(name='Shopping')

        self.active = Coupon.objects.create(
            user=self.user, merchant=self.merchant, coupon_code='SAVE20', dedup_key='amazon:save20',
            expiry_date=timezone.localdate() + timedelta(days=30), status=Coupon.Status.ACTIVE,
        )
        self.active.categories.add(self.category)
        self.expiring = Coupon.objects.create(
            user=self.user, merchant=self.merchant, coupon_code='FLASH10', dedup_key='amazon:flash10',
            expiry_date=timezone.localdate() + timedelta(days=1), status=Coupon.Status.EXPIRING_SOON,
        )

    def test_list_returns_only_own_coupons(self):
        other_user = User.objects.create(name='Other', email='other@example.com', auth_provider_ref='uid-x')
        Coupon.objects.create(user=other_user, coupon_code='NOTMINE', dedup_key='x:notmine')

        request = self.factory.get('/api/v1/coupons')
        force_authenticate(request, user=self.user)
        response = CouponListView.as_view()(request)

        codes = [c['coupon_code'] for c in response.data['results']]
        self.assertEqual(set(codes), {'SAVE20', 'FLASH10'})

    def test_search_by_coupon_code(self):
        request = self.factory.get('/api/v1/coupons?search=FLASH')
        force_authenticate(request, user=self.user)
        response = CouponListView.as_view()(request)
        self.assertEqual([c['coupon_code'] for c in response.data['results']], ['FLASH10'])

    def test_filter_by_status(self):
        request = self.factory.get('/api/v1/coupons?status=expiring_soon')
        force_authenticate(request, user=self.user)
        response = CouponListView.as_view()(request)
        self.assertEqual([c['coupon_code'] for c in response.data['results']], ['FLASH10'])

    def test_expiring_view(self):
        request = self.factory.get('/api/v1/coupons/expiring')
        force_authenticate(request, user=self.user)
        response = CouponExpiringView.as_view()(request)
        self.assertEqual([c['coupon_code'] for c in response.data['results']], ['FLASH10'])

    def test_patch_marks_used(self):
        request = self.factory.patch(f'/api/v1/coupons/{self.active.coupon_id}', {'status': 'used'}, format='json')
        force_authenticate(request, user=self.user)
        response = CouponDetailView.as_view()(request, coupon_id=self.active.coupon_id)

        self.assertEqual(response.data['status'], 'used')
        self.active.refresh_from_db()
        self.assertEqual(self.active.status, Coupon.Status.USED)

    def test_patch_rejects_direct_active_status(self):
        request = self.factory.patch(f'/api/v1/coupons/{self.active.coupon_id}', {'status': 'active'}, format='json')
        force_authenticate(request, user=self.user)
        response = CouponDetailView.as_view()(request, coupon_id=self.active.coupon_id)
        self.assertEqual(response.status_code, 400)

    def test_delete_removes_coupon(self):
        request = self.factory.delete(f'/api/v1/coupons/{self.expiring.coupon_id}')
        force_authenticate(request, user=self.user)
        response = CouponDetailView.as_view()(request, coupon_id=self.expiring.coupon_id)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Coupon.objects.filter(coupon_id=self.expiring.coupon_id).exists())

    def test_detail_self_heals_stale_status(self):
        stale = Coupon.objects.create(
            user=self.user, coupon_code='STALE1', dedup_key='x:stale1',
            expiry_date=timezone.localdate() - timedelta(days=5), status=Coupon.Status.ACTIVE,
        )
        request = self.factory.get(f'/api/v1/coupons/{stale.coupon_id}')
        force_authenticate(request, user=self.user)
        response = CouponDetailView.as_view()(request, coupon_id=stale.coupon_id)

        self.assertEqual(response.data['status'], 'expired')
        stale.refresh_from_db()
        self.assertEqual(stale.status, Coupon.Status.EXPIRED)
