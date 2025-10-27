from django.urls import path
from .views import (
    StaffRegisterView,
    StaffLoginView,
    verify_staff_email,
    RequestPasswordResetView,
    PasswordResetConfirmView,

)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


urlpatterns = [
    # Staff endpoints
    path('auth/staff/register/', StaffRegisterView.as_view(), name='staff-register'),
    path('auth/staff/login/', StaffLoginView.as_view(), name='staff-login'),
    path('auth/staff/verify-email/<str:token>/', verify_staff_email, name='verify-email'),
    path('auth/staff/request-password-reset/', RequestPasswordResetView.as_view(), name='request-password-reset'),
    path('auth/staff/reset-password/<int:user_id>/<str:token>/', PasswordResetConfirmView.as_view(), name='reset-password'),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

]
