from django.urls import path

from . import views

app_name = 'sources'

urlpatterns = [
    # included under /api/v1/ in smartkupon/urls.py
    path('sources/gmail/authorize', views.GmailAuthorizeView.as_view(), name='gmail-authorize'),
    path('sources/gmail/callback', views.GmailCallbackView.as_view(), name='gmail-callback'),
    path('sync/gmail/trigger', views.GmailSyncTriggerView.as_view(), name='gmail-sync-trigger'),
    path('sources/sms/sync', views.SMSSyncView.as_view(), name='sms-sync'),
]
