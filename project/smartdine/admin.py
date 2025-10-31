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
from django.utils.html import format_html



@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "email", "role", "is_active", "is_blocked", "is_email_verified", "is_approved_by_admin")
    list_filter = ("role", "is_active", "is_blocked", "is_email_verified", "is_approved_by_admin")
    search_fields = ("name", "email")
    ordering = ("id",)






@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "category", "price", "availability", "created_at", "updated_at")
    list_filter = ("category", "availability")
    search_fields = ("name",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "created_at", "updated_at")


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "cart", "menu_item", "quantity")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "total", "status", "created_at", "updated_at")
    list_filter = ("status",)
    search_fields = ("table__table_number",)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "menu_item", "quantity", "price")


@admin.register(WaiterRequest)
class WaiterRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "type", "status", "created_at", "updated_at")
    list_filter = ("type", "status")


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "order", "rating", "comment", "created_at", "updated_at")
    list_filter = ("rating",)


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('id', 'table_number', 'seats', 'status', 'qr_code_preview', 'created_at', 'updated_at')
    list_filter = ('status',)

    def qr_code_preview(self, obj):
        if obj.qr_code:
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" width="80" height="80" style="border-radius:8px;"/></a>',
                obj.qr_code.url,
                obj.qr_code.url
            )
        return "No QR Code"

    qr_code_preview.short_description = "QR Code"