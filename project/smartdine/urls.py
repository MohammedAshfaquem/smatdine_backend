from django.urls import path
from .views import (
    StaffRegisterView,
    StaffLoginView,
    VerifyStaffEmailView,
    RequestPasswordResetView,
    PasswordResetConfirmView,
    PendingUsersView,
    ApproveUserView,
    PendingRequestsCountView,
    table_redirect_view,
    get_table,
    StaffListView,
    StaffActionView,
    ValidateResetTokenView
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


urlpatterns = [
    path('auth/staff/register/', StaffRegisterView.as_view(), name='staff-register'),
    path('auth/staff/login/', StaffLoginView.as_view(), name='staff-login'),
    path('auth/staff/verify-email/<uuid:token>/', VerifyStaffEmailView.as_view(), name='verify-email'),
    path('auth/staff/forget-password/', RequestPasswordResetView.as_view(), name='request-password-reset'),
    path('auth/staff/reset-password/<int:user_id>/<str:token>/', PasswordResetConfirmView.as_view(), name='reset-password'),
    path("auth/staff/validate-reset-token/<int:user_id>/<uuid:token>/",ValidateResetTokenView.as_view(), name="validate-reset-token"),
    path("api/admin/staffs/", StaffListView.as_view(), name="staff-list"),
    path("api/admin/staffs/<int:pk>/action/", StaffActionView.as_view(), name="staff-action"),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path('test/pending-users/',PendingUsersView.as_view(),name="pending-users"),
    path("api/admin/approve-user/<int:pk>/", ApproveUserView.as_view(), name="approve-user"),
    path("api/admin/pending-count/", PendingRequestsCountView.as_view(), name="pending_count"),
    path('table/<int:table_number>/', table_redirect_view, name='table_redirect'),
    path('tables/<int:table_number>/', get_table, name='get_table'),


]
