from django.contrib import admin
from .models import (
    User,
    Table,
    MenuItem,
    Cart,
    CartItem,
    Order,
    OrderItem,
    WaiterRequest,
    Feedback,
)

# ---------------------------
# User (Staff) Admin
# ---------------------------
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "email", "role", "is_active", "isBlocked", "is_email_verified", "is_approved_by_admin")
    list_filter = ("role", "is_active", "isBlocked", "is_email_verified", "is_approved_by_admin")
    search_fields = ("name", "email")
    ordering = ("id",)


# ---------------------------
# Table Admin
# ---------------------------
@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ("id", "table_number", "seats", "status", "created_at", "updated_at")
    list_filter = ("status",)
    search_fields = ("table_number",)


# ---------------------------
# MenuItem Admin
# ---------------------------
@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "category", "price", "availability", "created_at", "updated_at")
    list_filter = ("category", "availability")
    search_fields = ("name",)


# ---------------------------
# Cart & CartItem Admin
# ---------------------------
@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "created_at", "updated_at")


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "cart", "menu_item", "quantity")


# ---------------------------
# Order & OrderItem Admin
# ---------------------------
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "total", "status", "created_at", "updated_at")
    list_filter = ("status",)
    search_fields = ("table__table_number",)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "menu_item", "quantity", "price")


# ---------------------------
# WaiterRequest Admin
# ---------------------------
@admin.register(WaiterRequest)
class WaiterRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "type", "status", "created_at", "updated_at")
    list_filter = ("type", "status")


# ---------------------------
# Feedback Admin
# ---------------------------
@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "order", "rating", "comment", "created_at", "updated_at")
    list_filter = ("rating",)
