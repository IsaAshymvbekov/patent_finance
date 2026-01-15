# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import PatentViewSet, BankCallbackView

router = DefaultRouter()
router.register("patents", PatentViewSet, basename="patent")

urlpatterns = [
    path("api/", include(router.urls)),
    path("api/bank/callback/", BankCallbackView.as_view(), name="bank-callback"),
]
