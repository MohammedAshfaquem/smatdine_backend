# backend/project/smartdine/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Table,MenuItem,Cart,CartItem,Order,OrderItem,Feedback,WaiterRequest,Base,Ingredient,CustomDishIngredient,CustomDish 

User = get_user_model()


class StaffRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ['name', 'email', 'password', 'confirm_password', 'role']

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data

    def validate_role(self, value):
        allowed_roles = ['kitchen', 'waiter']
        if value not in allowed_roles:
            raise serializers.ValidationError(f"Role must be one of {allowed_roles}.")
        return value

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)



class StaffLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        user = User.objects.filter(email=email).first()

        if user and user.check_password(password):
            refresh = RefreshToken.for_user(user)
            return {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': {
                    'id': user.id,
                    'name': user.name,
                    'email': user.email,
                    'role': user.role
                }
            }
        raise serializers.ValidationError("Invalid email or password.")
    
class TableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ['id', 'table_number', 'seats', 'status']
        
class StaffSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'role', 'is_active', 'is_blocked']
        
        
class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = "__all__"






        


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = "__all__"
        
class WaiterRequestSerializer(serializers.ModelSerializer):
    table_number = serializers.IntegerField(source='table.table_number', read_only=True)

    class Meta:
        model = WaiterRequest
        fields = ['id', 'table_number', 'type', 'status', 'created_at', 'updated_at']
        
class BaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Base
        fields = ["id", "name", "price","description"]


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = ["id", "name", "category", "price"]


class CustomDishIngredientSerializer(serializers.ModelSerializer):
    ingredient = IngredientSerializer(read_only=True)
    ingredient_id = serializers.IntegerField(write_only=True, required=True)

    class Meta:
        model = CustomDishIngredient
        fields = ["id", "ingredient", "ingredient_id", "quantity"]


class CustomDishSerializer(serializers.ModelSerializer):
    base = BaseSerializer(read_only=True)
    base_id = serializers.IntegerField(write_only=True, required=True)
    dish_ingredients = CustomDishIngredientSerializer(many=True, read_only=True)
    ingredients = CustomDishIngredientSerializer(many=True, write_only=True, required=False)
    table_number = serializers.IntegerField(source="table.table_number", read_only=True)

    class Meta:
        model = CustomDish
        fields = [
            "id",
            "table_number",
            "name",
            "base",
            "base_id",
            "ingredients",       # write-only payload
            "dish_ingredients",  # read-only representation
            "special_notes",
            "total_price",
            "preparation_time",  # ✅ new field
            "created_at",
        ]
        read_only_fields = [
            "total_price",
            "created_at",
            "dish_ingredients",
            "base",
            "preparation_time",  # ✅ keep read-only
        ]

        
class CartItemSerializer(serializers.ModelSerializer):
    menu_item = MenuItemSerializer(read_only=True)
    custom_dish = CustomDishSerializer(read_only=True)  # 👈 include this
    menu_item_id = serializers.PrimaryKeyRelatedField(
        queryset=MenuItem.objects.all(),
        source='menu_item',
        write_only=True,
        required=False
    )

    class Meta:
        model = CartItem
        fields = [
            'id',
            'menu_item',
            'custom_dish',         # 👈 include this
            'menu_item_id',
            'quantity',
            'special_instructions',
            'subtotal',
        ]
        read_only_fields = ['subtotal']
        
class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_amount = serializers.ReadOnlyField()

    class Meta:
        model = Cart
        fields = ['id', 'table', 'items', 'total_amount', 'created_at', 'updated_at']
        
class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.SerializerMethodField()
    custom_dish = CustomDishSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "menu_item",
            "menu_item_name",
            "custom_dish",
            "quantity",
            "price",
            "subtotal",
        ]

    def get_menu_item_name(self, obj):
        return obj.menu_item.name if obj.menu_item else None



class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    table_number = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "table_number",  # ✅ this now comes from get_table_number()
            "status",
            "total",
            "estimated_time",
            "created_at",
            "updated_at",
            "items",
        ]

    def get_table_number(self, obj):
        """Return table_number from related Table model"""
        return obj.table.table_number if obj.table else None
