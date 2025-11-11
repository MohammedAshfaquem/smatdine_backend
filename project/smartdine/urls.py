from django.urls import path
from .views import (
    # --- Auth Views ---
    StaffRegisterView, StaffLoginView, VerifyStaffEmailView,
    RequestPasswordResetView, PasswordResetConfirmView, ValidateResetTokenView,
    # --- Admin / Staff Management ---
    PendingUsersView, ApproveUserView, PendingRequestsCountView,
    StaffListView, StaffActionView,
    # --- Table Views ---
    table_redirect_view, get_table, occupy_table, release_table, TableListAPIView,
    # --- Menu & Cart ---
    MenuItemAPIView, MenuItemDetailAPIView, CartAPIView,
    CartItemQuantityAPIView, CartCountView,
    # --- Orders ---
    OrderAPIView, TableOrdersAPIView, OrderDetailAPIView,OrdersListAPIView,
    # --- Feedback ---
    FeedbackAPIView,
    # --- Waiter Features ---
    WaiterRequestAPIView, WaiterRequestListAPIView, WaiterRequestUpdateAPIView,
    WaiterRequestsByTableAPIView, MarkOrderServedAPIView,ClearTableDataAPIView,
    # --- Kitchen ---
    KitchenOrdersAPIView, UpdateOrderStatusAPIView,
    # --- Custom Dish (AI / Builder Section) ---
    BaseListView, IngredientListView, CreateCustomDishView,
    CustomDishListByTableView, CustomDishListAllView, ReorderCustomDishView,
    
    
    ServiceRequestAPIView,
    
    
    
    chat_with_gemini
)

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


urlpatterns = [
    # ==========================
    # 🔐 AUTHENTICATION
    # ==========================
    path('auth/staff/register/', StaffRegisterView.as_view(), name='staff-register'),
    path('auth/staff/login/', StaffLoginView.as_view(), name='staff-login'),
    path('auth/staff/verify-email/<uuid:token>/', VerifyStaffEmailView.as_view(), name='verify-email'),
    path('auth/staff/forget-password/', RequestPasswordResetView.as_view(), name='request-password-reset'),
    path('auth/staff/reset-password/<int:user_id>/<str:token>/', PasswordResetConfirmView.as_view(), name='reset-password'),
    path('auth/staff/validate-reset-token/<int:user_id>/<uuid:token>/', ValidateResetTokenView.as_view(), name='validate-reset-token'),

    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # ==========================
    # 👥 ADMIN / STAFF MANAGEMENT
    # ==========================
    path('test/pending-users/', PendingUsersView.as_view(), name='pending-users'),
    path('api/admin/approve-user/<int:pk>/', ApproveUserView.as_view(), name='approve-user'),
    path('api/admin/pending-count/', PendingRequestsCountView.as_view(), name='pending_count'),
    path('api/admin/staffs/', StaffListView.as_view(), name='staff-list'),
    path('api/admin/staffs/<int:pk>/action/', StaffActionView.as_view(), name='staff-action'),

    # ==========================
    # 🍽 TABLES
    # ==========================
    path('table/<int:table_number>/', table_redirect_view, name='table_redirect'),
    path('tables/<int:table_number>/', get_table, name='get_table'),
    path('api/tables/', TableListAPIView.as_view(), name='table-list'),
    path('tables/<int:table_number>/occupy/', occupy_table, name='occupy-table'),
    path('tables/<int:table_number>/release/', release_table, name='release-table'),

    # ==========================
    # 📜 MENU & CART (Customer Side)
    # ==========================
    path('menu/', MenuItemAPIView.as_view(), name='menu-list-create'),
    path('menu/<int:pk>/', MenuItemDetailAPIView.as_view(), name='menu-detail'),

    path('cart/<int:table_number>/', CartAPIView.as_view(), name='get_cart'),
    path('cart/add/', CartAPIView.as_view(), name='cart-add'),
    path('cart/update/', CartAPIView.as_view(), name='cart-update'),
    path('cart/remove/<int:item_id>/', CartAPIView.as_view(), name='cart-remove'),
    path('cart/item-quantity/<int:table_number>/', CartItemQuantityAPIView.as_view(), name='cart-item-quantity'),
    path('cart/count/<int:table_number>/', CartCountView.as_view(), name='cart-count'),

    # ==========================
    # 🧾 ORDERS
    # ==========================
    path('order/place/', OrderAPIView.as_view(), name='place-order'),
    path('orders/<int:table_id>/', TableOrdersAPIView.as_view(), name='table-orders'),
    path('order/<int:order_id>/', OrderDetailAPIView.as_view(), name='order-detail'),
    path("orders/<int:order_id>/status/", UpdateOrderStatusAPIView.as_view(), name="update-order-status"),
    path("orders/filter/", OrdersListAPIView.as_view(), name="orders-filter"),


    # ==========================
    # 💬 FEEDBACK
    # ==========================
    path('feedback/<int:order_id>/', FeedbackAPIView.as_view(), name='feedback'),

    # ==========================
    # 🧑‍🍳 KITCHEN
    # ==========================
    path('kitchen/orders/', KitchenOrdersAPIView.as_view(), name='kitchen-orders'),
    path('kitchen/orders/<int:order_id>/update-status/', UpdateOrderStatusAPIView.as_view(), name='update-order-status'),

    # ==========================
    # 🧑‍💼 WAITER
    # ==========================
    path('waiter-request/<int:table_id>/', WaiterRequestAPIView.as_view(), name='create_waiter_request'),
    path('waiter-requests/', WaiterRequestListAPIView.as_view(), name='list_waiter_requests'),
    path('waiter-requests/<int:pk>/', WaiterRequestUpdateAPIView.as_view(), name='update_waiter_request'),
    path('waiter/orders/<int:order_id>/served/', MarkOrderServedAPIView.as_view(), name='waiter-mark-served'),
    path('waiter/requests/<int:table_number>/', WaiterRequestsByTableAPIView.as_view(), name='waiter-requests-by-table'),
    path('waiter/tables/clear/<int:table_number>/', ClearTableDataAPIView.as_view(), name='clear-table'),
    
    path("service-requests/", ServiceRequestAPIView.as_view(), name="service-requests"),



    # ==========================
    # 🧠 CUSTOM DISH BUILDER
    # ==========================
    path('custom-bases/', BaseListView.as_view(), name='custom-bases'),
    path('custom-ingredients/', IngredientListView.as_view(), name='custom-ingredients'),
    path('custom-dish/create/<int:table_id>/', CreateCustomDishView.as_view(), name='custom-dish-create'),
    path('custom-dishes/<int:table_id>/', CustomDishListByTableView.as_view(), name='custom-dish-list-by-table'),
    path('custom-dishes/', CustomDishListAllView.as_view(), name='custom-dish-list-all'),
    path('custom-dish/<int:custom_dish_id>/reorder/', ReorderCustomDishView.as_view(), name='custom-dish-reorder'),
    
    
    
    path("api/chat/", chat_with_gemini, name="chat_with_gemini"),
]
