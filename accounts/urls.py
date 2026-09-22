from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('firebase/login', views.FirebaseLoginView.as_view(), name='firebase-login'),
    path('me', views.MeView.as_view(), name='me'),
]
