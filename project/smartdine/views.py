from http import client
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404,redirect
from rest_framework import status, permissions,parsers,viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny,IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import (StaffRegisterSerializer,
                          StaffLoginSerializer,WaiterRequestSerializer,IngredientSerializer,CustomDishSerializer,
                          TableSerializer,StaffSerializer,MenuItemSerializer,CartSerializer,CartItemSerializer,
                          OrderSerializer,FeedbackSerializer,BaseSerializer
)
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .utils import send_verification_email,get_unsplash_image
from .models import (Table,MenuItem,CartItem,Cart,OrderItem,Order,
                     Feedback,WaiterRequest,Base,CustomDish,
                     CustomDishIngredient,Ingredient,TableHistory)
from django.conf import settings
from datetime import timedelta
from django.utils import timezone
import datetime
from decimal import Decimal
from django.db import transaction
from google import genai
import re
import os
import difflib


User = get_user_model()

class StaffRegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = StaffRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            try:
                send_verification_email(user)
            except Exception as e:
                print(f"Email sending failed: {e}")
            return Response({"success": True, "message": "Registered successfully! Please verify your email."}, status=201)
        return Response(serializer.errors, status=400)
    
class VerifyStaffEmailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        print(f"📩 Received token: {token}")

        try:
            user = get_object_or_404(User, email_verification_token=token)
            print(f"✅ Found user: {user.email}")

            if user.is_email_verified:
                return Response({"message": "Email already verified!"})
            user.is_email_verified = True
            user.is_active = True
            user.save()
            return Response({"message": "Email verified successfully!"})
        except Exception as e:
            print(f"❌ Verification error: {e}")
            return Response({"message": "Invalid or expired token."}, status=400)

class StaffLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = StaffLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.get(id=data['user']['id'])

        if not user.is_email_verified:
            return Response({"error": "Email not verified."}, status=401)
        if user.role != "admin" and not user.is_approved_by_admin:
            return Response({"error": "Admin has not approved your account yet."}, status=401)
        if user.is_blocked:
            return Response({"error": "Your account is blocked."}, status=401)

        return Response(data, status=200)

class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, user_id, token):
        password = request.data.get("password")
        confirm_password = request.data.get("confirm_password")

        if not password or not confirm_password:
            return Response({"error": "Both password fields are required."}, status=400)

        if password != confirm_password:
            return Response({"error": "Passwords do not match."}, status=400)

        user = get_object_or_404(User, id=user_id)

        # ✅ Check if token is valid first
        if not user.is_reset_token_valid(token):
            return Response({"error": "Invalid or expired token."}, status=400)

        # ✅ Reset password and clear token (so link can’t be reused)
        user.set_password(password)
        user.clear_reset_token()
        user.save()

        return Response({"message": "Password reset successful."}, status=200)

class RequestPasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"error": "Email is required."}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "User does not exist."}, status=404)

        # ✅ Clear any existing token before creating a new one
        user.clear_reset_token()

        token = user.create_reset_token()
        reset_link = f"{settings.FRONTEND_URL}/reset-password/{user.id}/{token}/"

        subject = "SmartDine - Password Reset Request"
        message = f"Click this link to reset your password: {reset_link}"
        html_message = f"""
            <p>Hello {user.name},</p>
            <p>Click <a href="{reset_link}">here</a> to reset your password.</p>
            <p>This link expires in 10 minutes and can only be used once.</p>
            <p>– SmartDine Team</p>
        """

        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
        )

        return Response({"message": "Password reset link sent to your email."}, status=200)

class ValidateResetTokenView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id, token):
        user = get_object_or_404(User, id=user_id)

        if not user.is_reset_token_valid(token):
            return Response({"valid": False}, status=400)

        return Response({"valid": True}, status=200)

class PendingUsersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != "admin":
            return Response({"error": "Only admins can view pending users."}, status=403)

        pending_users = User.objects.filter(is_email_verified=True, is_approved_by_admin=False)

        data = [
            {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": user.role,
                "is_email_verified": user.is_email_verified,
                "is_approved_by_admin": user.is_approved_by_admin,
            }
            for user in pending_users
        ]

        return Response(data, status=200)

@method_decorator(csrf_exempt, name='dispatch')
class ApproveUserView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if request.user.role != "admin":
            return Response({"detail": "Only admins can approve users."}, status=status.HTTP_403_FORBIDDEN)

        user = get_object_or_404(User, pk=pk)
        if user.is_approved_by_admin:
            return Response({"detail": "User is already approved."}, status=status.HTTP_200_OK)

        user.is_approved_by_admin = True
        user.save()
        return Response({"detail": f"{user.name} approved successfully!"}, status=status.HTTP_200_OK)
    
class PendingRequestsCountView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):

        count = User.objects.filter(
            is_approved_by_admin=False,
            is_superuser=False
        ).count()
        return Response({"pending_count": count})
       
def table_redirect_view(request, table_number):
    table = get_object_or_404(Table, table_number=table_number)
    frontend_url = f"http://localhost:3001/customer/dashboard?table={table.table_number}"
    return redirect(frontend_url)

@api_view(['GET'])
@permission_classes([AllowAny])  
def get_table(request, table_number):
    try:
        table = Table.objects.get(table_number=table_number)
        serializer = TableSerializer(table)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Table.DoesNotExist:
        return Response({"error": "Table not found"}, status=status.HTTP_404_NOT_FOUND)
    
class StaffListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        staff = User.objects.filter(role__in=['kitchen', 'waiter'], is_approved_by_admin=True)
        serializer = StaffSerializer(staff, many=True)
        return Response(serializer.data)
    
class StaffActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        user = User.objects.filter(id=pk, role__in=['kitchen', 'waiter'], is_approved_by_admin=True).first()
        if not user:
            return Response({"error": "Approved staff not found"}, status=status.HTTP_404_NOT_FOUND)
        action = request.data.get("action")
        if action == "block":
            user.is_blocked = True
            user.save()
            return Response({"message": f"{user.name} has been blocked."})

        elif action == "unblock":
            user.is_blocked = False
            user.save()
            return Response({"message": f"{user.name} has been unblocked."})

        elif action == "delete":
            user.delete()
            return Response({"message": "User deleted successfully."})

        return Response({"error": "Invalid action."}, status=status.HTTP_400_BAD_REQUEST)
    
class MenuItemAPIView(APIView):
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get(self, request):
        queryset = MenuItem.objects.all()
        category = request.query_params.get("category")
        item_type = request.query_params.get("type")
        available = request.query_params.get("available")
        low_stock = request.query_params.get("low_stock")

        if category:
            queryset = queryset.filter(category__iexact=category)
        if item_type:
            queryset = queryset.filter(type__iexact=item_type)
        if available:
            queryset = queryset.filter(availability=(available.lower() == "true"))
        if low_stock and low_stock.lower() == "true":
            queryset = queryset.filter(stock__lte=F('min_stock'))

        # Order by stock (low first) then created_at (oldest first)
        queryset = queryset.order_by('stock', 'created_at')

        serializer = MenuItemSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = MenuItemSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Menu item created successfully", "data": serializer.data},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        serializer = MenuItemSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Menu item created successfully", "data": serializer.data},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class MenuItemDetailAPIView(APIView):
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get(self, request, pk):
        item = get_object_or_404(MenuItem, pk=pk)
        serializer = MenuItemSerializer(item)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        item = get_object_or_404(MenuItem, pk=pk)
        serializer = MenuItemSerializer(item, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Menu item updated successfully", "data": serializer.data},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        item = get_object_or_404(MenuItem, pk=pk)
        serializer = MenuItemSerializer(item, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Menu item partially updated", "data": serializer.data},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        item = get_object_or_404(MenuItem, pk=pk)
        item.delete()
        return Response(
            {"message": "Menu item deleted successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )

class CartAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    def get_cart(self, table_number):
        """Ensure every table has its own cart."""
        table = get_object_or_404(Table, table_number=table_number)
        cart, _ = Cart.objects.get_or_create(table=table)
        return cart
    def get(self, request, table_number):
        cart = self.get_cart(table_number)
        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        table_number = request.data.get("table_number")
        menu_item_id = request.data.get("menu_item_id")
        custom_dish_id = request.data.get("custom_dish_id")
        is_custom = request.data.get("is_custom", False)
        quantity = int(request.data.get("quantity", 1))
        special_instructions = request.data.get("special_instructions", "")

        if not table_number:
            return Response({"error": "Missing table_number"}, status=status.HTTP_400_BAD_REQUEST)

        cart = self.get_cart(table_number)

        if is_custom:
            if not custom_dish_id:
                return Response({"error": "Missing custom_dish_id"}, status=status.HTTP_400_BAD_REQUEST)

            custom_dish = get_object_or_404(CustomDish, id=custom_dish_id)
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                custom_dish=custom_dish,
                defaults={
                    "quantity": quantity,
                    "special_instructions": special_instructions,
                    "is_custom": True,
                    "menu_item": None,
                },
            )
        else:
            if not menu_item_id:
                return Response({"error": "Missing menu_item_id"}, status=status.HTTP_400_BAD_REQUEST)

            menu_item = get_object_or_404(MenuItem, id=menu_item_id)
            existing_cart_item = CartItem.objects.filter(cart=cart, menu_item=menu_item).first()
            existing_quantity = existing_cart_item.quantity if existing_cart_item else 0

            if menu_item.stock is not None and (existing_quantity + quantity) > menu_item.stock:
                return Response(
                    {"error": f"Only {menu_item.stock - existing_quantity} item(s) available in your cart"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                menu_item=menu_item,
                defaults={
                    "quantity": quantity,
                    "special_instructions": special_instructions,
                    "is_custom": False,
                },
            )

        if not created:
            new_quantity = cart_item.quantity + quantity
            if cart_item.menu_item and cart_item.menu_item.stock is not None:
                if new_quantity > cart_item.menu_item.stock:
                    return Response(
                        {"error": f"Only {cart_item.menu_item.stock - cart_item.quantity} more item(s) can be added"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            cart_item.quantity = new_quantity
            if special_instructions:
                cart_item.special_instructions = special_instructions
            cart_item.save()

        name = cart_item.custom_dish.name if cart_item.is_custom else cart_item.menu_item.name

        return Response(
            {
                "message": f"Item added to cart for Table {cart.table.table_number}",
                "item": name,
                "quantity": cart_item.quantity,
            },
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request):
        table_number = request.data.get("table_number")
        item_id = request.data.get("item_id")
        quantity = int(request.data.get("quantity"))

        if not table_number or not item_id:
            return Response({"error": "Missing table_number or item_id"}, status=status.HTTP_400_BAD_REQUEST)

        cart = self.get_cart(table_number)
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)

        if cart_item.menu_item and cart_item.menu_item.stock is not None:
            if quantity > cart_item.menu_item.stock:
                return Response(
                    {"error": f"Only {cart_item.menu_item.stock} item(s) available in stock"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        cart_item.quantity = quantity
        cart_item.save()
        return Response({"message": f"Quantity updated for Table {cart.table.table_number}"}, status=status.HTTP_200_OK)

    def delete(self, request, item_id):
        table_number = request.query_params.get("table_number")
        if not table_number:
            return Response({"error": "Missing table_number in query params"}, status=status.HTTP_400_BAD_REQUEST)

        cart = self.get_cart(table_number)
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        cart_item.delete()
        return Response({"message": f"Item removed from Table {cart.table.table_number}"}, status=status.HTTP_204_NO_CONTENT)

    def get_item_quantity(self, request, table_number, menu_item_id=None, custom_dish_id=None):
        cart = self.get_cart(table_number)
        if menu_item_id:
            cart_item = CartItem.objects.filter(cart=cart, menu_item_id=menu_item_id).first()
        elif custom_dish_id:
            cart_item = CartItem.objects.filter(cart=cart, custom_dish_id=custom_dish_id).first()
        else:
            return Response({"quantity": 0})
        return Response({"quantity": cart_item.quantity if cart_item else 0})

class CartItemQuantityAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, table_number):
        menu_item_id = request.query_params.get("menu_item_id")
        cart = get_object_or_404(Cart, table__table_number=table_number)
        quantity = 0
        if menu_item_id:
            cart_item = CartItem.objects.filter(cart=cart, menu_item_id=menu_item_id).first()
            if cart_item:
                quantity = cart_item.quantity
        return Response({"quantity": quantity}, status=status.HTTP_200_OK) 

class CartCountView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, table_number):
        try:
            cart = Cart.objects.filter(table__table_number=table_number).first()
            count = 0
            if cart and hasattr(cart, 'items'):
                count = cart.items.count()
            return Response({"count": count})
        except Exception as e:
            return Response({"count": 0, "error": str(e)}, status=500)

                
@api_view(['GET'])
@permission_classes([AllowAny])
def get_cart(request, table_number):
    try:
        table = Table.objects.get(table_number=table_number)
    except Table.DoesNotExist:
        return Response({"detail": "No Table matches the given number."}, status=status.HTTP_404_NOT_FOUND)

    cart, created = Cart.objects.get_or_create(table=table)
    items = cart.items.all()
    data = {
        "table": table.table_number,
        "items": [
            {
                "menu_item": item.menu_item.name,
                "quantity": item.quantity,
                "special_instructions": getattr(item, "special_instructions", "")
            }
            for item in items
        ]
    }
    return Response(data, status=status.HTTP_200_OK)

class OrderAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """
        Convert Cart → Order and decrease stock for menu items.
        Checks stock availability before placing the order.
        """
        table_number = request.data.get("table_number")
        if not table_number:
            return Response(
                {"error": "Missing table_number"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        table = get_object_or_404(Table, table_number=table_number)
        cart = get_object_or_404(Cart, table=table)
        cart_items = CartItem.objects.filter(cart=cart)

        if not cart_items.exists():
            return Response(
                {"error": "Cart is empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ✅ Check stock availability first
        for item in cart_items:
            if item.menu_item and item.menu_item.stock is not None:
                if item.menu_item.stock < item.quantity:
                    return Response(
                        {
                            "error": f"Not enough stock for '{item.menu_item.name}'. Only {item.menu_item.stock} left."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # ✅ Create a new pending order (countdown starts when it becomes 'preparing')
        order = Order.objects.create(
            table=table,
            status="pending",
        )

        total = Decimal("0.00")

        # ✅ Move all cart items into the order
        for item in cart_items:
            if item.menu_item:
                menu_item = item.menu_item
                subtotal = Decimal(menu_item.price) * item.quantity

                if menu_item.stock is not None:
                    menu_item.stock -= item.quantity
                    menu_item.save()

                OrderItem.objects.create(
                    order=order,
                    menu_item=menu_item,
                    quantity=item.quantity,
                    price=menu_item.price,
                    subtotal=subtotal,
                )
                total += subtotal

            elif item.custom_dish:
                subtotal = Decimal(item.custom_dish.total_price) * item.quantity
                OrderItem.objects.create(
                    order=order,
                    custom_dish=item.custom_dish,
                    quantity=item.quantity,
                    price=item.custom_dish.total_price,
                    subtotal=subtotal,
                )
                total += subtotal

        # ✅ Update total and estimated time (via model logic)
        order.total = total
        order.update_total_and_eta()

        # Calculate expected ready time for display
        expected_ready_time = timezone.now() + timedelta(minutes=order.estimated_time)

        # ✅ Clear cart after placing order
        cart_items.delete()

        serializer = OrderSerializer(order)

        return Response(
            {
                "message": f"Order placed successfully for Table {table_number}",
                "order": {
                    **serializer.data,
                    "expected_ready_time": expected_ready_time.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                },
            },
            status=status.HTTP_201_CREATED,
        )

class UpdateOrderStatusAPIView(APIView):
    def patch(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("status")
        if not new_status:
            return Response({"error": "Missing status field"}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Record preparation start time
        if new_status == "preparing" and not order.started_preparing_at:
            order.started_preparing_at = timezone.now()

        order.status = new_status
        order.save()

        return Response(
            {"message": f"Order {order.id} status updated to {new_status}"},
            status=status.HTTP_200_OK,
        )
class TableOrdersAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, table_id):
        try:
            orders = Order.objects.filter(table__table_number=table_id).order_by('-created_at')

            if not orders.exists():
                return Response({"message": "No orders for this table"}, status=404)

            data = []
            for order in orders:
                estimated_minutes = order.estimated_time or 0
                expected_ready_time = order.created_at + timedelta(minutes=estimated_minutes)

                now = timezone.now()
                remaining = expected_ready_time - now
                minutes_left = max(int(remaining.total_seconds() // 60), 0)
                time_remaining = (
                    f"{minutes_left} minutes left" if minutes_left > 0 else "Ready"
                )

                items = []
                for item in OrderItem.objects.filter(order=order):
                    if item.menu_item:  
                        items.append({
                            "type": "menu_item",
                            "name": item.menu_item.name,
                            "image": item.menu_item.image.url if item.menu_item.image else None,
                            "quantity": item.quantity,
                            "subtotal": str(item.subtotal),
                            "preparation_time": getattr(item.menu_item, 'preparation_time', None),
                            "spice_level": getattr(item.menu_item, 'spice_level', None),
                        })
                    elif item.custom_dish:  
                        items.append({
                            "type": "custom_dish",
                            "name": item.custom_dish.name,
                            "image": item.custom_dish.image_url,  
                            "ingredients": [
                                {
                                    "name": di.ingredient.name,
                                    "quantity": di.quantity
                                } for di in item.custom_dish.dish_ingredients.all()
                            ],
                            "base": item.custom_dish.base.name if getattr(item.custom_dish, 'base', None) else None,
                            "preparation_time": getattr(item.custom_dish, 'preparation_time', None),
                            "quantity": item.quantity,
                            "subtotal": str(item.subtotal),
                        })

                data.append({
                    "id": order.id,
                    "table_number": order.table.table_number,
                    "status": order.status,
                    "total": str(order.total),
                    "estimated_time": f"{estimated_minutes} minutes",
                    "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "expected_ready_time": expected_ready_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "time_remaining": time_remaining,
                    "items": items,
                })

            return Response({"orders": data}, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)
         
class OrderDetailAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    def get(self, request, order_id):
        try:
            order = get_object_or_404(Order, id=order_id)
            estimated_minutes = order.estimated_time or 0
            expected_ready_time = order.created_at + timedelta(minutes=estimated_minutes)

            now = timezone.now()
            remaining = expected_ready_time - now
            minutes_left = max(int(remaining.total_seconds() // 60), 0)
            time_remaining = f"{minutes_left} minutes left" if minutes_left > 0 else "Ready"
            items = []
            for item in OrderItem.objects.filter(order=order):
                if item.menu_item:
                    items.append({
                        "type": "menu_item",
                        "name": item.menu_item.name,
                        "image": item.menu_item.image.url if item.menu_item.image else None,
                        "quantity": item.quantity,
                        "subtotal": str(item.subtotal),
                        "preparation_time": getattr(item.menu_item, "preparation_time", None),
                    })
                elif item.custom_dish:
                    items.append({
                        "type": "custom_dish",
                        "name": item.custom_dish.name,
                        "image": item.custom_dish.image_url,  
                        "ingredients": [
                            {
                                "name": di.ingredient.name,
                                "quantity": di.quantity
                            } for di in item.custom_dish.dish_ingredients.all()
                        ],
                        "preparation_time": getattr(item.custom_dish, "preparation_time", None),
                        "quantity": item.quantity,
                        "subtotal": str(item.subtotal),
                    })

            data = {
                "id": order.id,
                "table_number": order.table.table_number,
                "status": order.status,
                "total": str(order.total),
                "estimated_time": f"{estimated_minutes} minutes",
                "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "expected_ready_time": expected_ready_time.strftime("%Y-%m-%d %H:%M:%S"),
                "time_remaining": time_remaining,
                "items": items,
            }

            return Response(data, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)
  
class FeedbackAPIView(APIView):
    permission_classes = [permissions.AllowAny]  

    def get(self, request, order_id):
        """Check if feedback exists for this order"""
        exists = Feedback.objects.filter(order_id=order_id).exists()
        return Response({"exists": exists})

    def post(self, request, order_id):
        """Submit feedback for an order"""
        order = get_object_or_404(Order, id=order_id)

        if Feedback.objects.filter(order=order).exists():
            return Response(
                {"message": "Feedback already exists"},
                status=status.HTTP_409_CONFLICT
            )

        Feedback.objects.create(
            order=order,
            food_rating=request.data.get("food_rating", 0),
            service_rating=request.data.get("service_rating", 0),
            comments=request.data.get("comments", ""),
        )
        return Response({"message": "Feedback submitted successfully"}, status=status.HTTP_201_CREATED)
    
class WaiterRequestAPIView(APIView):
    """
    Customer creates a waiter request (e.g., need water, need bill, clean table, general)
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, table_id):
        table = get_object_or_404(Table, table_number=table_id)

        req_type = request.data.get("type")
        valid_types = ['need water', 'need bill', 'clean table', 'general']

        if req_type not in valid_types:
            return Response(
                {"error": f"Invalid request type. Must be one of {valid_types}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        description = request.data.get("description", "") if req_type == "general" else ""

        WaiterRequest.objects.create(table=table, type=req_type, description=description)

        msg = f"Waiter request '{req_type}' sent for Table {table.table_number}"
        if req_type == "general" and description:
            msg += f": {description}"

        return Response({"message": msg}, status=status.HTTP_201_CREATED)

class WaiterRequestListAPIView(APIView):
    """
    Waiter views all requests (sorted by latest first)
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        requests = WaiterRequest.objects.all().order_by('-created_at')
        data = [
            {
                "id": r.id,
                "table_number": r.table.table_number,
                "type": r.type,
                "status": r.status,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for r in requests
        ]
        return Response(data, status=status.HTTP_200_OK)

class WaiterRequestUpdateAPIView(APIView):
    """
    Waiter updates a specific request’s status
    """
    permission_classes = [permissions.AllowAny]

    def patch(self, request, pk):
        waiter_request = get_object_or_404(WaiterRequest, pk=pk)
        new_status = request.data.get("status")

        valid_statuses = ['pending', 'in-progress', 'completed']
        if new_status not in valid_statuses:
            return Response(
                {"error": f"Invalid status. Must be one of {valid_statuses}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        waiter_request.status = new_status
        waiter_request.save()

        return Response(
            {
                "message": f"Status updated to '{new_status}' for Table {waiter_request.table.table_number}",
                "id": waiter_request.id,
                "table_number": waiter_request.table.table_number,
                "type": waiter_request.type,
                "status": waiter_request.status,
            },
            status=status.HTTP_200_OK,
        )
        
class KitchenOrdersAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        Fetch all active orders for the kitchen dashboard.
        Show only 'pending' and 'preparing' orders.
        """
        orders = Order.objects.filter(status__in=["pending", "preparing"]).order_by("-created_at")
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class UpdateOrderStatusAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, order_id):
        """
        Update order status — example:
        PATCH /api/kitchen/orders/5/update-status/
        { "status": "preparing" }
        """
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("status")
        valid_statuses = ["pending", "preparing", "ready", "completed"]

        if new_status not in valid_statuses:
            return Response({"error": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)

        order.status = new_status
        order.save()

        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class ReadyOrdersAPIView(APIView):
    """List all ready orders for waiters to serve."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        ready_orders = Order.objects.filter(status="ready").prefetch_related("items", "table")
        serializer = OrderSerializer(ready_orders, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class MarkOrderServedAPIView(APIView):
    """Mark an order as served by the waiter."""
    permission_classes = [permissions.AllowAny]

    def patch(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        order.status = "served"
        order.save()
        return Response({"message": f"Order {order.id} marked as served"}, status=status.HTTP_200_OK)
    
class TableListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        tables = Table.objects.all().order_by("table_number")
        serializer = TableSerializer(tables, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
class WaiterRequestsByTableAPIView(APIView):
    """
    Returns all waiter requests for a specific table number.
    Example: GET /waiter/requests/5/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, table_number):
        requests = WaiterRequest.objects.filter(table__table_number=table_number).order_by('-created_at')
        serializer = WaiterRequestSerializer(requests, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


    
@api_view(['PATCH'])
@permission_classes([permissions.AllowAny])  
def occupy_table(request, table_number):
    """
    When customer scans QR → mark table as occupied
    """
    try:
        table = Table.objects.get(table_number=table_number)
        if table.status != "occupied":
            table.status = "occupied"
            table.save(update_fields=["status"])
        return Response(
            {"message": f"Table {table_number} marked as occupied"},
            status=status.HTTP_200_OK
        )
    except Table.DoesNotExist:
        return Response(
            {"error": f"Table {table_number} not found"},
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['PATCH'])
@permission_classes([permissions.AllowAny])
def release_table(request, table_number):
    """
    When customer leaves or waiter clears → mark table as available
    """
    try:
        table = Table.objects.get(table_number=table_number)
        if table.status != "available":
            table.status = "available"
            table.save(update_fields=["status"])
        return Response(
            {"message": f"Table {table_number} marked as available"},
            status=status.HTTP_200_OK
        )
    except Table.DoesNotExist:
        return Response(
            {"error": f"Table {table_number} not found"},
            status=status.HTTP_404_NOT_FOUND
        )
class BaseListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        bases = Base.objects.all()
        serializer = BaseSerializer(bases, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class IngredientListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        ingredients = Ingredient.objects.all().order_by("category", "name")
        serializer = IngredientSerializer(ingredients, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CreateCustomDishView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, table_id):
        print("POST payload received:", request.data)
        try:
            table = get_object_or_404(Table, table_number=table_id)
            print("Table found:", table)
        except Exception as e:
            print("Table lookup failed:", e)
            raise

        serializer = CustomDishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        base_id = serializer.validated_data.get("base_id")
        name = serializer.validated_data.get("name")
        special_notes = serializer.validated_data.get("special_notes", "")
        ingredients_payload = request.data.get("ingredients", [])
        add_to_cart = request.data.get("add_to_cart", True)

        try:
            base = get_object_or_404(Base, id=base_id)
            print("Base found:", base)
        except Exception as e:
            print("Base lookup failed:", e)
            raise

        # Create CustomDish
        custom_dish = CustomDish.objects.create(
            name=name,
            base=base,
            special_notes=special_notes,
            total_price=Decimal("0.00"),
            table=table,
        )

        total_price = Decimal(base.price or 0)
        total_time = getattr(base, "preparation_time", 0)

        # Add ingredients
        for item in ingredients_payload:
            ing_id = item.get("ingredient_id")
            qty = max(int(item.get("quantity", 1)), 1)
            print(f"Processing ingredient_id={ing_id} with qty={qty}")

            try:
                ingredient = get_object_or_404(Ingredient, id=ing_id)
                print("Ingredient found:", ingredient)
            except Exception as e:
                print(f"Ingredient lookup failed for id={ing_id}: {e}")
                raise

            CustomDishIngredient.objects.create(
                custom_dish=custom_dish,
                ingredient=ingredient,
                quantity=qty,
            )
            total_price += Decimal(ingredient.price) * qty
            total_time += getattr(ingredient, "preparation_time", 0) * qty

        # Save totals
        custom_dish.total_price = total_price
        custom_dish.preparation_time = total_time
        custom_dish.save()

        # Generate Unsplash image
        try:
            image_url = get_unsplash_image(custom_dish)
            if image_url:
                custom_dish.image_url = image_url
                custom_dish.image_status = "done"
                custom_dish.save(update_fields=["image_url", "image_status"])
            else:
                custom_dish.image_status = "failed"
                custom_dish.save(update_fields=["image_status"])
        except Exception as e:
            print("Failed to generate image:", e)
            custom_dish.image_status = "failed"
            custom_dish.save(update_fields=["image_status"])

        # Optionally add to cart
        if add_to_cart:
            cart, _ = Cart.objects.get_or_create(table=table)
            CartItem.objects.create(
                cart=cart,
                menu_item=None,
                quantity=1,
                special_instructions=special_notes,
                is_custom=True,
                custom_dish=custom_dish,
            )

        out_serializer = CustomDishSerializer(custom_dish)
        return Response(
            {
                "message": "Custom dish created successfully",
                "dish": out_serializer.data,
                "image_url": custom_dish.image_url,
                "image_status": custom_dish.image_status,
            },
            status=status.HTTP_201_CREATED,
        )

class CustomDishListByTableView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, table_id):
        table = get_object_or_404(Table, table_number=table_id)
        dishes = CustomDish.objects.filter(table=table).order_by("-created_at")
        serializer = CustomDishSerializer(dishes, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class CustomDishListAllView(APIView):
    permission_classes = [permissions.AllowAny] 

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        show_all = request.query_params.get("all") == "true"

        dishes = (
            CustomDish.objects.select_related("table", "base")
            .prefetch_related("dish_ingredients__ingredient")
            .order_by("-sold_count", "-created_at")
        )
        if (not user or getattr(user, "role", None) == "customer") and not show_all:
            top_dishes = dishes[:3]
            serializer = CustomDishSerializer(top_dishes, many=True)
            return Response({
                "message": "Top 3 most popular custom dishes",
                "show_all": False,
                "data": serializer.data,
            }, status=status.HTTP_200_OK)
        serializer = CustomDishSerializer(dishes, many=True)
        return Response({
            "message": "All custom dishes",
            "show_all": True,
            "data": serializer.data,
        }, status=status.HTTP_200_OK)

class ReorderCustomDishView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, custom_dish_id):
        custom_dish = get_object_or_404(CustomDish, id=custom_dish_id)
        cart, _ = Cart.objects.get_or_create(table=custom_dish.table)
        CartItem.objects.create(
            cart=cart,
            menu_item=None,
            quantity=1,
            special_instructions=custom_dish.notes,
            is_custom=True,
            custom_dish=custom_dish,
        )
        return Response({"message": "Added custom dish to cart"}, status=status.HTTP_201_CREATED)
     
def generate_custom_dish_image(custom_dish):
    base = getattr(custom_dish.base, "name", "dish")
    ingredients = ", ".join(
        f"{di.quantity}x {di.ingredient.name}" for di in custom_dish.dish_ingredients.all()
    )
    notes = custom_dish.special_notes or ""
    prompt = (
        f"High quality photo of a {base}-based beverage made with {ingredients}. "
        f"{notes}. Served attractively on a table, natural lighting, photorealistic."
    )

    try:
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="512x512"
        )
        image_url = result.data[0].url
        custom_dish.image_url = image_url
        custom_dish.image_status = "ready"
        custom_dish.save(update_fields=["image_url", "image_status"])
        return image_url
    except Exception as e:
        custom_dish.image_status = "failed"
        custom_dish.save(update_fields=["image_status"])
        print("Image generation failed:", e)
        return None
    
class ClearTableDataAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, table_number):
        try:
            table = Table.objects.get(table_number=table_number)
            cart_data = [
                {
                    "item_name": item.menu_item.name if item.menu_item else item.custom_dish.name,
                    "quantity": item.quantity,
                    "subtotal": float(item.subtotal),
                    "is_custom": item.custom_dish is not None
                } for cart in Cart.objects.filter(table=table) for item in cart.items.all()
            ]

            order_data = [
                {
                    "item_name": item.menu_item.name if item.menu_item else item.custom_dish.name,
                    "quantity": item.quantity,
                    "subtotal": float(item.subtotal),
                    "is_custom": item.custom_dish is not None
                } for order in Order.objects.filter(table=table) for item in order.items.all()
            ]

            request_data = [
                {
                    "type": req.type,
                    "description": req.description,
                    "status": req.status
                } for req in WaiterRequest.objects.filter(table=table)
            ]

            TableHistory.objects.create(
                table=table,
                status="available",
                changed_by=request.user,
                snapshot={
                    "cart": cart_data,
                    "orders": order_data,
                    "requests": request_data
                }
            )

            Cart.objects.filter(table=table).delete()
            Order.objects.filter(table=table).delete()
            WaiterRequest.objects.filter(table=table).delete()
            table.status = "available"
            table.save()

            return Response(
                {"message": f"Table {table.table_number} cleared and archived."},
                status=status.HTTP_200_OK
            )

        except Table.DoesNotExist:
            return Response({"error": "Table not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        



# ============================================================
# Keywords & Off-topic Detection
# ============================================================

FOOD_KEYWORDS = [
    # General
    "food", "meal", "dish", "menu", "order", "recipe", "ingredient",
    "spice", "sauce", "starter", "dessert", "snack", "drink", "beverage",
    "juice", "coffee", "tea", "breakfast", "lunch", "dinner", "brunch",

    # Nutrition & diet
    "diet", "diet plan", "healthy", "health", "nutrition", "nutrient",
    "vitamin", "protein", "carb", "fat", "fiber", "calorie", "balanced",
    "weight loss", "meal plan", "fitness", "detox", "keto", "paleo", "vegan",
    "vegetarian", "gluten", "allergy", "low calorie", "low carb", "high protein",

    # Restaurant
    "restaurant", "table", "waiter", "bill", "chef", "special",
    "recommend", "menu item", "order now", "spicy"
]

OFFTOPIC_PATTERNS = re.compile(
    r"\b(politics|president|religion|war|sex|porn|crypto|stock|investment|lawsuit|celebrity|movie|game)\b",
    re.IGNORECASE,
)

# ============================================================
# Helper Functions
# ============================================================

def looks_food_related(text: str) -> bool:
    """Detect if the message is food-related, with fuzzy typo tolerance."""
    text_l = text.lower()
    words = re.findall(r"\b\w+\b", text_l)

    # Direct keyword match
    for kw in FOOD_KEYWORDS:
        if kw in text_l:
            return True

    # Fuzzy typo match
    for word in words:
        close = difflib.get_close_matches(word, FOOD_KEYWORDS, n=1, cutoff=0.8)
        if close:
            return True

    # Regex fallback
    if re.search(r"\b(cook|eat|restaurant|nutrition|diet|food|menu|dish|meal|ingredient|health|protein|fruit|vegetable|spicy)\b", text_l):
        return True
    return False

def cleanup_response(resp_text: str) -> str:
    """Cleans Gemini's raw output for user-friendly display."""
    if not resp_text:
        return "Sorry, I couldn’t generate a response."

    if OFFTOPIC_PATTERNS.search(resp_text):
        return "I can only help with food, health, nutrition, and menu-related questions."

    text = resp_text
    text = re.sub(r"(?is)(okay!|sure!|to give you the best recommendations|could you tell me more|once I know).*", "", text)
    text = re.sub(r"[*_#>`~-]+", "", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    if len(text.split()) > 100:
        text = " ".join(text.split()[:100]) + "..."
    return text

# ============================================================
# Dynamic DB Context Fetching
# ============================================================

def find_relevant_items(question: str):
    """Return relevant dishes or ingredients based on context keywords."""
    question = question.lower()
    dishes = []
    ingredients = []

    # --- Spicy ---
    if "spicy" in question:
        dishes = list(MenuItem.objects.filter(spice_level__gte=2, availability=True).values_list("name", flat=True))
        ingredients = list(Ingredient.objects.filter(category="spice").values_list("name", flat=True))

    # --- Diet / Healthy ---
    elif "diet" in question or "healthy" in question:
        bases = list(Base.objects.all().values("name", "description"))
        ingredient_objs = Ingredient.objects.filter(category__in=["fruit", "green", "citrus", "extra", "sweetener"]).order_by("category", "name")
        ingredients = [i.name for i in ingredient_objs]

        # Combine bases with 2-3 ingredients randomly for suggestions
        diet_suggestions = []
        for base in bases:
            combo = f"{base['name']} with " + ", ".join(ingredients[:3])
            diet_suggestions.append(combo)
        dishes = diet_suggestions

    # --- Dessert / Sweet ---
    elif "dessert" in question or "sweet" in question:
        dishes = list(MenuItem.objects.filter(category="dessert", availability=True).values_list("name", flat=True))
        ingredients = list(Ingredient.objects.filter(category="sweetener").values_list("name", flat=True))

    # --- Fallback ---
    if not dishes and not ingredients:
        return None

    return {
        "dishes": dishes,
        "ingredients": ingredients,
    }

# ============================================================
# API Endpoint
# ============================================================

@api_view(["POST"])
@permission_classes([AllowAny])
def chat_with_gemini(request):
    """Handles SmartDine AI chat requests."""
    question = (request.data.get("message") or "").strip()
    if not question:
        return Response({"error": "Empty message"}, status=400)

    if not looks_food_related(question):
        return Response({"reply": "I can only help with food, health, nutrition, and menu-related questions."})

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return Response({"error": "Gemini API key not set"}, status=500)

    context_data = find_relevant_items(question)
    base_context = ""
    if context_data:
        dishes = ", ".join(context_data.get("dishes", [])) or "none found"
        ingredients = ", ".join(context_data.get("ingredients", [])) or "none found"
        base_context = f"Related dishes: {dishes}. Ingredients you can use: {ingredients}."

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[{
                "parts": [{
                    "text": (
                        "You are SmartDine’s AI assistant. Only answer questions about food, diet, health, or restaurant menus. "
                        "Keep responses short, natural, and under 100 words. Never use markdown or bullet lists.\n\n"
                        f"{base_context}\nUser: {question}"
                    )
                }]
            }],
        )

        reply = cleanup_response(response.text)
        return Response({"reply": reply})

    except Exception as e:
        return Response({"error": "Gemini API request failed", "details": str(e)}, status=502)