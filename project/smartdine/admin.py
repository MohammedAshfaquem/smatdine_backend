from django.contrib import admin
from django.utils.html import format_html
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
    Ingredient,
    Base,
    CustomDish,
    CustomDishIngredient,
    TableHistory
)

# -------------------------
# User Admin
# -------------------------
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "id", "name", "email", "role", "is_active",
        "is_blocked", "is_email_verified", "is_approved_by_admin"
    )
    list_filter = (
        "role", "is_active", "is_blocked",
        "is_email_verified", "is_approved_by_admin"
    )
    search_fields = ("name", "email")
    ordering = ("id",)


# -------------------------
# Menu Item Admin
# -------------------------
@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "category",
        "type",
        "price",
        "stock",
        "availability",
        "preparation_time",
        "created_at",
        "updated_at",
    )
    list_filter = ("category", "type", "availability")
    search_fields = ("name",)
    list_editable = ("price", "stock", "availability")


# -------------------------
# Cart & CartItem Admin
# -------------------------
class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("subtotal",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "created_at", "updated_at")
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "cart", "menu_item", "custom_dish", "quantity", "subtotal")
    readonly_fields = ("subtotal",)


# -------------------------
# Order & OrderItem Admin
# -------------------------
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("subtotal",)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "table",
        "total",
        "status",
        "chef",
        "waiter",
        "estimated_time",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "chef", "waiter")
    search_fields = ("table__table_number", "chef__email", "waiter__email")
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "menu_item", "custom_dish", "quantity", "price", "subtotal")
    readonly_fields = ("subtotal",)


# -------------------------
# WaiterRequest Admin
# -------------------------
@admin.register(WaiterRequest)
class WaiterRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "type", "status", "created_at", "updated_at")
    list_filter = ("type", "status")
    search_fields = ("table__table_number", "description")


# -------------------------
# Table Admin
# -------------------------
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


# -------------------------
# Feedback Admin
# -------------------------
@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'food_rating', 'service_rating', 'comments', 'created_at')
    list_filter = ('food_rating', 'service_rating', 'created_at')
    search_fields = ('order__id', 'comments')
    ordering = ('-created_at',)


# -------------------------
# Base & Ingredient Admin
# -------------------------
@admin.register(Base)
class BaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'price')
    search_fields = ('name',)


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price')
    list_filter = ('category',)
    search_fields = ('name',)


# -------------------------
# Custom Dish & Ingredients Admin
# -------------------------
class CustomDishIngredientInline(admin.TabularInline):
    model = CustomDishIngredient
    extra = 1


@admin.register(CustomDish)
class CustomDishAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'base', 'get_ingredients', 'total_price', 'created_at']
    inlines = [CustomDishIngredientInline]

    def get_ingredients(self, obj):
        return ", ".join([i.ingredient.name for i in obj.dish_ingredients.all()])
    get_ingredients.short_description = "Ingredients"


@admin.register(CustomDishIngredient)
class CustomDishIngredientAdmin(admin.ModelAdmin):
    list_display = ('custom_dish', 'ingredient', 'quantity')
    

@admin.register(TableHistory)
class TableHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "status", "changed_by", "timestamp")
    readonly_fields = ("snapshot", "timestamp")
    search_fields = ("table__table_number",)
    list_filter = ("status", "timestamp")
