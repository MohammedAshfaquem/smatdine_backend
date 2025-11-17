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
                          OrderSerializer,BaseSerializer
)
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .utils import send_verification_email,get_unsplash_image
from .models import (Table,MenuItem,CartItem,Cart,OrderItem,Order,
                     Feedback,WaiterRequest,Base,CustomDish,
                     CustomDishIngredient,Ingredient,TableHistory,ChatMessage,ChatSession)
from django.conf import settings
from django.db.models import Sum, FloatField, Count,F,Q
from datetime import timedelta
from datetime import timezone as pytimezone
from django.utils import timezone
import datetime
from decimal import Decimal
from django.db import transaction
import google.generativeai as genai
import requests
import re
import os
import difflib
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from django.http import HttpResponse
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table as TablePDF, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm



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

        if not user.is_reset_token_valid(token):
            return Response({"error": "Invalid or expired token."}, status=400)

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

    def get(self, request, pk=None):
        """Handle GET for all menu items or a single item by ID"""
        if pk:
            item = get_object_or_404(MenuItem, pk=pk)
            serializer = MenuItemSerializer(item)
            return Response(serializer.data, status=status.HTTP_200_OK)

        queryset = MenuItem.objects.all()

        # Optional filters
        category = request.query_params.get("category")
        item_type = request.query_params.get("type")
        available = request.query_params.get("available")
        low_stock = request.query_params.get("low_stock")

        if category:
            queryset = queryset.filter(category__iexact=category)
        if item_type:
            queryset = queryset.filter(type__iexact=item_type)
        if available is not None:
            queryset = queryset.filter(availability=(available.lower() == "true"))
        if low_stock and low_stock.lower() == "true":
            queryset = queryset.filter(stock__lte=F("min_stock"))

        queryset = queryset.order_by("stock", "created_at")

        serializer = MenuItemSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """Create new menu item"""
        serializer = MenuItemSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Menu item created successfully", "data": serializer.data},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk=None):
        """Update existing menu item"""
        if not pk:
            return Response(
                {"error": "Menu item ID is required for update"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item = get_object_or_404(MenuItem, pk=pk)
        serializer = MenuItemSerializer(item, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Menu item updated successfully", "data": serializer.data},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk=None):
        """Delete menu item by ID"""
        if not pk:
            return Response(
                {"error": "Menu item ID is required for deletion"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item = get_object_or_404(MenuItem, pk=pk)
        item.delete()
        return Response(
            {"message": "Menu item deleted successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )

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

        description = request.data.get("description", "").strip() if req_type == "general" else ""

        # Create active waiter request
        waiter_request = WaiterRequest.objects.create(
            table=table,
            type=req_type,
            description=description,
            is_active=True
        )

        msg = f"Waiter request '{req_type}' sent for Table {table.table_number}"
        if req_type == "general" and description:
            msg += f": {description}"

        return Response(
            {
                "message": msg,
                "request": {
                    "id": waiter_request.id,
                    "table_number": waiter_request.table.table_number,
                    "type": waiter_request.type,
                    "description": waiter_request.description,
                    "status": waiter_request.status,
                    "created_at": waiter_request.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
            },
            status=status.HTTP_201_CREATED
        )

class CartAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get_cart(self, table_number):
        """Ensure every table has its own active cart."""
        table = get_object_or_404(Table, table_number=table_number)
        cart, created = Cart.objects.get_or_create(table=table, defaults={"is_active": True})
        if not created and not cart.is_active:
            cart.is_active = True
            cart.save()
        return cart

    def get(self, request, table_number=None):
        if not table_number:
            return Response({"error": "Missing table_number"}, status=status.HTTP_400_BAD_REQUEST)

        cart = self.get_cart(table_number)
        items = cart.items.filter(is_active=True)
        serialized_items = []
        for item in items:
            serialized_items.append({
                "id": item.id,
                "is_custom": item.is_custom,
                "name": item.custom_dish.name if item.is_custom else item.menu_item.name,
                "image": item.custom_dish.image_url if item.is_custom else (item.menu_item.image.url if item.menu_item.image else None),
                "quantity": item.quantity,
                "subtotal": str(item.subtotal),
                "special_instructions": getattr(item, "special_instructions", ""),
            })
        return Response({
            "cart_id": cart.id,
            "table_number": cart.table.table_number,
            "items": serialized_items,
            "total_amount": float(sum(float(i["subtotal"]) for i in serialized_items))
        }, status=status.HTTP_200_OK)

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
            custom_dish = get_object_or_404(CustomDish, id=custom_dish_id, is_active=True)
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                custom_dish=custom_dish,
                defaults={
                    "quantity": quantity,
                    "special_instructions": special_instructions,
                    "is_custom": True,
                    "menu_item": None,
                    "is_active": True,
                },
            )
        else:
            if not menu_item_id:
                return Response({"error": "Missing menu_item_id"}, status=status.HTTP_400_BAD_REQUEST)
            menu_item = get_object_or_404(MenuItem, id=menu_item_id)
            existing_cart_item = CartItem.objects.filter(cart=cart, menu_item=menu_item, is_active=True).first()
            existing_quantity = existing_cart_item.quantity if existing_cart_item else 0

            # Check stock availability and prevent exceeding stock
            if menu_item.stock is not None and (existing_quantity + quantity) > menu_item.stock:
                available_quantity = menu_item.stock - existing_quantity
                return Response(
                    {"message": f"Max quantity reached. Only {available_quantity} item(s) available."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                menu_item=menu_item,
                defaults={
                    "quantity": quantity,
                    "special_instructions": special_instructions,
                    "is_custom": False,
                    "is_active": True,
                },
            )

        if not created:
            new_quantity = cart_item.quantity + quantity
            # Check stock availability and prevent exceeding stock
            if cart_item.menu_item and cart_item.menu_item.stock is not None and new_quantity > cart_item.menu_item.stock:
                available_quantity = cart_item.menu_item.stock - cart_item.quantity
                return Response(
                    {"message": f"Max quantity reached. Only {available_quantity} more item(s) can be added."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cart_item.quantity = new_quantity
            if special_instructions:
                cart_item.special_instructions = special_instructions
            cart_item.is_active = True
            cart_item.save()

        return Response({
            "message": f"Item added to cart for Table {cart.table.table_number}",
            "item": cart_item.custom_dish.name if cart_item.is_custom else cart_item.menu_item.name,
            "quantity": cart_item.quantity,
            "image": cart_item.custom_dish.image_url if cart_item.is_custom else (cart_item.menu_item.image.url if cart_item.menu_item.image else None)
        }, status=status.HTTP_201_CREATED)

    def patch(self, request):
        table_number = request.data.get("table_number")
        item_id = request.data.get("item_id")
        quantity = int(request.data.get("quantity", 1))

        if not table_number or not item_id:
            return Response({"error": "Missing table_number or item_id"}, status=status.HTTP_400_BAD_REQUEST)

        cart = self.get_cart(table_number)
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)

        # Check stock availability and prevent exceeding stock
        if cart_item.menu_item and cart_item.menu_item.stock is not None and quantity > cart_item.menu_item.stock:
            return Response({"message": f"Max quantity reached. Only {cart_item.menu_item.stock} item(s) available."},
                            status=status.HTTP_400_BAD_REQUEST)

        cart_item.quantity = quantity
        cart_item.save()
        return Response({"message": "Quantity updated", "quantity": cart_item.quantity}, status=status.HTTP_200_OK)

    def delete(self, request, item_id=None, table_number=None):
        table_number = table_number or request.query_params.get("table_number")

        if not table_number:
            return Response({"error": "Missing table_number"}, status=status.HTTP_400_BAD_REQUEST)

        cart = self.get_cart(table_number)

        if item_id:
            cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
            cart_item.delete()
            return Response({"message": "Item removed"}, status=status.HTTP_204_NO_CONTENT)

        cart.items.all().delete()
        return Response({"message": "Cart cleared"}, status=status.HTTP_204_NO_CONTENT)
 
class CartCountView(APIView):   
    permission_classes = [permissions.AllowAny]

    def get(self, request, table_number):
        # Get the latest active cart for the table
        cart = Cart.objects.filter(table__table_number=table_number, is_active=True).first()
        if not cart:
            return Response({"count": 0})  # No active cart, count is 0

        # Count only active items in the cart
        item_count = cart.items.filter(is_active=True).count()
        return Response({"count": item_count})

class CartItemQuantityAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, table_number):
        menu_item_id = request.query_params.get("menu_item_id")
        cart = get_object_or_404(Cart, table__table_number=table_number)
        quantity = 0
        if menu_item_id:
            cart_item = CartItem.objects.filter(cart=cart, menu_item_id=menu_item_id, is_active=True).first()
            if cart_item:
                quantity = cart_item.quantity
        return Response({"quantity": quantity}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_cart_items(request, table_number):
    """Return active cart items only."""
    try:
        table = Table.objects.get(table_number=table_number)
    except Table.DoesNotExist:
        return Response({"detail": "No Table matches the given number."}, status=status.HTTP_404_NOT_FOUND)

    cart, created = Cart.objects.get_or_create(table=table, defaults={"is_active": True})
    items = cart.items.filter(is_active=True)

    data = {
        "table": table.table_number,
        "items": [
            {
                "id": item.id,
                "menu_item": item.menu_item.name if item.menu_item else None,
                "custom_dish": item.custom_dish.name if item.custom_dish else None,
                "quantity": item.quantity,
                "special_instructions": getattr(item, "special_instructions", ""),
                "subtotal": str(item.subtotal)
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
            is_active=True,
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
   
from datetime import datetime

class TableSessionAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, table_number):
        table = get_object_or_404(Table, table_number=table_number)
        return Response({"session_id": table.session_id})

class OrdersListAPIView(APIView):
    """
    Unified endpoint for order listings and sales analytics.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        status_param = request.query_params.get("status", "").lower().strip()
        date_param = request.query_params.get("date", "").lower().strip()
        group_by = request.query_params.get("group_by", "").lower().strip()
        show_all = str(request.query_params.get("all", "")).lower().strip() == "true"
        sales_param = request.query_params.get("sales", "").lower().strip()
        year_param = request.query_params.get("year", "").strip()

        queryset = (
            Order.objects.all()
            .select_related("table")
            .prefetch_related("items__menu_item")
        )
        if status_param and status_param != "all":
            valid_statuses = ["pending", "preparing", "ready", "served"]
            if status_param in valid_statuses:
                queryset = queryset.filter(status=status_param)
                if status_param in ["pending", "preparing", "ready", "served"]:
                    queryset = queryset.filter(is_active=True)
            else:
                return Response(
                    {"error": f"Invalid status '{status_param}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )


        if sales_param:
            now_local = timezone.localtime()
            today_local = now_local.date()

            start_date = None
            end_date = None

            if sales_param == "top_items":
                top_items = (
                    OrderItem.objects.filter(order__status="served")
                    .values(item_name=F("menu_item__name"))
                    .annotate(
                        quantity_sold=Sum("quantity"),
                        revenue=Sum(F("quantity") * F("price"), output_field=FloatField()),
                    )
                    .order_by("-quantity_sold")[:5]
                )
                return Response(
                    {"sales_type": "top_items", "top_5_items": list(top_items)},
                    status=status.HTTP_200_OK,
                )

            elif sales_param == "today":
                start_date = datetime.combine(today_local, datetime.min.time(), tzinfo=pytimezone.utc)
                end_date = start_date + timedelta(days=1)

            elif sales_param == "week":
                start_of_week = today_local - timedelta(days=today_local.weekday())
                start_date = datetime.combine(start_of_week, datetime.min.time(), tzinfo=pytimezone.utc)
                end_date = start_date + timedelta(days=7)

                daily_data = []
                for i in range(7):
                    day_start = start_date + timedelta(days=i)
                    day_end = day_start + timedelta(days=1)
                    total = (
                        Order.objects.filter(
                            status="served",
                            created_at__gte=day_start,
                            created_at__lt=day_end,
                        ).aggregate(
                            total_sales=Sum("total", output_field=FloatField())
                        )["total_sales"]
                        or 0
                    )
                    daily_data.append({
                        "date": day_start.strftime("%a"), 
                        "total_sales": round(total, 2),
                    })

                total_week_sales = sum(d["total_sales"] for d in daily_data)
                order_count = (
                    Order.objects.filter(
                        status="served",
                        created_at__gte=start_date,
                        created_at__lt=end_date,
                    ).count()
                )

                return Response(
                    {
                        "sales_type": "week",
                        "range": {"start": start_date, "end": end_date},
                        "served_sales_total": round(total_week_sales, 2),
                        "served_orders_count": order_count,
                        "daily_revenue": daily_data,
                    },
                    status=status.HTTP_200_OK,
                )

            elif sales_param == "month":
                start_date = datetime.combine(today_local.replace(day=1), datetime.min.time(), tzinfo=pytimezone.utc)
                if today_local.month == 12:
                    end_date = datetime(today_local.year + 1, 1, 1, tzinfo=pytimezone.utc)
                else:
                    end_date = datetime(today_local.year, today_local.month + 1, 1, tzinfo=pytimezone.utc)

            elif sales_param == "year":
                year = int(year_param) if year_param else today_local.year
                start_date = datetime(year, 1, 1, tzinfo=pytimezone.utc)
                end_date = datetime(year + 1, 1, 1, tzinfo=pytimezone.utc)

            elif sales_param == "total":
                agg = (
                    Order.objects.filter(status="served")
                    .aggregate(
                        total_sales=Sum("total", output_field=FloatField()),
                        total_count=Count("id"),
                    )
                )
                return Response(
                    {
                        "sales_type": "total",
                        "served_sales_total": round(agg["total_sales"] or 0, 2),
                        "served_orders_count": agg["total_count"] or 0,
                    },
                    status=status.HTTP_200_OK,
                )

            elif sales_param == "custom":
                start_str = request.query_params.get("start")
                end_str = request.query_params.get("end")
                if not start_str or not end_str:
                    return Response(
                        {"error": "Provide both start and end dates."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                start_date = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=pytimezone.utc)
                end_date = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=pytimezone.utc) + timedelta(days=1)

            if start_date and end_date:
                agg = (
                    Order.objects.filter(
                        status="served",
                        created_at__gte=start_date,
                        created_at__lt=end_date,
                    ).aggregate(
                        total_sales=Sum("total", output_field=FloatField()),
                        total_count=Count("id"),
                    )
                )
                return Response(
                    {
                        "sales_type": sales_param,
                        "range": {"start": start_date, "end": end_date},
                        "served_sales_total": round(agg["total_sales"] or 0, 2),
                        "served_orders_count": agg["total_count"] or 0,
                    },
                    status=status.HTTP_200_OK,
                )
        if show_all or status_param == "all" or date_param == "all":
            queryset = queryset.filter(is_active=True).order_by("-created_at")
            serializer = OrderSerializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        now_local = timezone.localtime()
        today_local = now_local.date()
        tz_local = timezone.get_current_timezone()

        if date_param == "today" or not date_param:
            target_date = today_local
        elif date_param == "week":
            start_of_week = today_local - timedelta(days=today_local.weekday())
            start_of_week_dt = datetime.combine(start_of_week, datetime.min.time(), tzinfo=pytimezone.utc)
            queryset = queryset.filter(created_at__gte=start_of_week_dt, is_active=True)
            queryset = queryset.order_by("-created_at")
            serializer = OrderSerializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            try:
                target_date = datetime.strptime(date_param, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        start_of_day = datetime.combine(target_date, datetime.min.time(), tzinfo=pytimezone.utc)
        end_of_day = start_of_day + timedelta(days=1)
        queryset = queryset.filter(created_at__gte=start_of_day, created_at__lt=end_of_day, is_active=True)

        if group_by == "hourly":
            slots = [(9, 11), (11, 13), (13, 15), (15, 17), (17, 19)]
            result = []
            for start_hour, end_hour in slots:
                start_time_local = datetime.combine(target_date, datetime.min.time()).replace(
                    hour=start_hour, tzinfo=tz_local
                )
                end_time_local = datetime.combine(target_date, datetime.min.time()).replace(
                    hour=end_hour, tzinfo=tz_local
                )

                start_time_utc = start_time_local.astimezone(pytimezone.utc)
                end_time_utc = end_time_local.astimezone(pytimezone.utc)

                count = queryset.filter(
                    created_at__gte=start_time_utc,
                    created_at__lt=end_time_utc,
                ).count()

                result.append({
                    "label": f"{start_hour}:00-{end_hour}:00",
                    "orders": count,
                })

            return Response(result, status=status.HTTP_200_OK)

        queryset = queryset.filter(is_active=True).order_by("-created_at")
        serializer = OrderSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
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
            # Fetch only active orders
            orders = Order.objects.filter(table__table_number=table_id, is_active=True).order_by('-created_at')

            data = []
            for order in orders:
                estimated_minutes = order.estimated_time or 0
                expected_ready_time = order.created_at + timedelta(minutes=estimated_minutes)

                now = timezone.now()
                remaining = expected_ready_time - now
                minutes_left = max(int(remaining.total_seconds() // 60), 0)
                time_remaining = f"{minutes_left} minutes left" if minutes_left > 0 else "Ready"

                items = []
                for item in OrderItem.objects.filter(order=order, order__is_active=True):
                    if item.menu_item and getattr(item, 'is_active', True):
                        items.append({
                            "type": "menu_item",
                            "name": item.menu_item.name,
                            "image": item.menu_item.image.url if item.menu_item.image else None,
                            "quantity": item.quantity,
                            "subtotal": str(item.subtotal),
                            "preparation_time": getattr(item.menu_item, 'preparation_time', None),
                            "spice_level": getattr(item.menu_item, 'spice_level', None),
                        })
                    elif item.custom_dish and item.custom_dish.is_active:
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

            # Always return a list, even if empty
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
    and fetches active requests.
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

        description = request.data.get("description", "").strip() if req_type == "general" else ""

        if req_type == "general" and not description:
            return Response(
                {"error": "Description is required for general requests."},
                status=status.HTTP_400_BAD_REQUEST
            )

        waiter_request = WaiterRequest.objects.create(
            table=table,
            type=req_type,
            description=description,
            is_active=True
        )

        msg = f"Waiter request '{req_type}' sent for Table {table.table_number}"
        if req_type == "general" and description:
            msg += f": {description}"

        return Response(
            {
                "message": msg,
                "request": {
                    "id": waiter_request.id,
                    "table_number": waiter_request.table.table_number,
                    "type": waiter_request.type,
                    "description": waiter_request.description,
                    "status": waiter_request.status,
                    "is_active": waiter_request.is_active,
                    "created_at": waiter_request.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
            },
            status=status.HTTP_201_CREATED
        )

    def get(self, request, table_id):
        """
        Returns only active waiter requests for a table.
        """
        table = get_object_or_404(Table, table_number=table_id)
        active_requests = WaiterRequest.objects.filter(table=table, is_active=True)

        serialized = [
            {
                "id": req.id,
                "table_number": req.table.table_number,
                "type": req.type,
                "description": req.description,
                "status": req.status,
                "is_active": req.is_active,
                "created_at": req.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for req in active_requests
        ]

        return Response({"active_requests": serialized}, status=status.HTTP_200_OK)

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
    
class ServiceRequestAPIView(APIView):
    """
    Fetch service (waiter) requests for both roles:
    - Waiter → only today's active requests
    - Admin → all active or date-filtered active requests
    """
    permission_classes = [permissions.AllowAny]  

    def get(self, request):
        user_role = request.query_params.get("role", "waiter")
        date_param = request.query_params.get("date", None)
        today = timezone.localdate()

        queryset = WaiterRequest.objects.filter(is_active=True)

        if user_role == "waiter":
            queryset = queryset.filter(created_at__date=today)
        elif date_param: 
            queryset = queryset.filter(created_at__date=date_param)

        queryset = queryset.order_by("-created_at")

        data = [
            {
                "id": r.id,
                "table_number": r.table.table_number,
                "type": r.type,
                "status": r.status,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for r in queryset
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
    
class ChefCompletedOrdersAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()

        orders = (
            Order.objects
            .filter(
                status="served",
                chef=request.user,
                updated_at__date=today
            )
            .order_by("-updated_at")
        )

        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class UpdateOrderStatusAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, order_id):
        """
        Update order status and attach chef.
        PATCH /api/kitchen/orders/5/update-status/
        { "status": "preparing" }
        """
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        new_status = request.data.get("status")
        valid_statuses = ["pending", "preparing", "ready", "completed"]

        if new_status not in valid_statuses:
            return Response(
                {"error": "Invalid status"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user

        # ✅ Ownership enforcement
        if order.chef and order.chef != user:
            return Response(
                {"error": "You are not authorized to update this order."},
                status=status.HTTP_403_FORBIDDEN
            )

        # ✅ If no chef yet and status goes to 'preparing' or beyond, assign this user
        if order.chef is None and new_status in ["preparing", "ready", "completed"]:
            order.chef = user

        # ✅ Disallow skipping stages
        valid_transitions = {
            "pending": ["preparing"],
            "preparing": ["ready"],
            "ready": ["completed"],
            "completed": [],
        }
        if new_status not in valid_transitions.get(order.status, []):
            return Response(
                {"error": f"Invalid transition from {order.status} to {new_status}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = new_status
        order.save(update_fields=["status", "chef", "updated_at"])

        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

class MarkOrderServedAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]  
    def patch(self, request, order_id):
        try:
            order = get_object_or_404(Order, id=order_id)
            
            if order.waiter is None:
                order.waiter = request.user

            order.status = "served"
            order.save()

            if hasattr(order.waiter, "orders_completed"):
                order.waiter.orders_completed += 1
                order.waiter.save()

            if hasattr(order.chef, "orders_completed"):
                order.chef.orders_completed += 1
                order.chef.save()
            
            served_by = getattr(request.user, "username", "Waiter")
            return Response(
                {"message": f"Order {order.id} marked as served", "served_by": served_by},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": f"Failed to mark order as served: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TableListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        occupied = request.query_params.get('occupied', None)

        tables = Table.objects.all().order_by("table_number")

        if occupied is not None:
            if occupied.lower() == 'true':
                tables = tables.filter(status='occupied')
            elif occupied.lower() == 'false':
                tables = tables.exclude(status='occupied')

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

        custom_dish = CustomDish.objects.create(
            name=name,
            base=base,
            special_notes=special_notes,
            total_price=Decimal("0.00"),
            table=table,
        )

        total_price = Decimal(base.price or 0)
        total_time = getattr(base, "preparation_time", 0)

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

        custom_dish.total_price = total_price
        custom_dish.preparation_time = total_time
        custom_dish.save()

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
        table = get_object_or_404(Table, table_number=table_number)

        try:
            cart_data = [
                {
                    "item_name": getattr(item.menu_item, 'name', None) or getattr(item.custom_dish, 'name', "Unknown"),
                    "quantity": item.quantity,
                    "subtotal": float(item.subtotal or 0),
                    "is_custom": item.custom_dish is not None
                }
                for cart in Cart.objects.filter(table=table, is_active=True)
                for item in cart.items.filter(is_active=True)
            ]

            order_data = [
                {
                    "item_name": getattr(item.menu_item, 'name', None) or getattr(item.custom_dish, 'name', "Unknown"),
                    "quantity": item.quantity,
                    "subtotal": float(item.subtotal or 0),
                    "is_custom": item.custom_dish is not None
                }
                for order in Order.objects.filter(table=table, is_active=True)
                for item in order.items.filter(is_active=True)
            ]

            request_data = [
                {
                    "type": req.type,
                    "description": req.description,
                    "status": req.status
                }
                for req in WaiterRequest.objects.filter(table=table, is_active=True)
            ]

            # Save snapshot
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

            # Soft-disable data
            Cart.objects.filter(table=table, is_active=True).update(is_active=False)
            CartItem.objects.filter(cart__table=table, is_active=True).update(is_active=False)
            Order.objects.filter(table=table, is_active=True).update(is_active=False)
            OrderItem.objects.filter(order__table=table, is_active=True).update(is_active=False)
            CustomDish.objects.filter(is_active=True, table=table).update(is_active=False)
            WaiterRequest.objects.filter(table=table, is_active=True).update(is_active=False)
            

            # --- Clear SmartDine AI chat session ---
            session_id = f"TABLE_{table.table_number}"
            ChatSession.objects.filter(session_id=session_id).delete()

            # Mark table as available
            table.status = "available"
            table.save(update_fields=["status"])

            return Response(
                {"message": f"Table {table.table_number} cleared and archived (soft-deleted)."},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


FOOD_KEYWORDS = [
    "food", "meal", "dish", "menu", "order", "recipe", "ingredient",
    "spice", "sauce", "starter", "dessert", "snack", "drink", "beverage",
    "juice", "coffee", "tea", "breakfast", "lunch", "dinner", "brunch",
    "diet", "nutrition", "protein", "vegan", "restaurant", "waiter", "chef",
    "serve", "table", "special", "recommend", "menu item", "order now", "spicy"
]

GREETING_KEYWORDS = [
    "hi", "hello", "hey", "good morning", "good evening", "how are you", "what’s up"
]

OFFTOPIC_PATTERNS = re.compile(
    r"\b(politics|president|religion|war|sex|porn|crypto|stock|investment|lawsuit|celebrity|movie|game)\b",
    re.IGNORECASE
)


def is_offtopic(text: str) -> bool:
    return bool(OFFTOPIC_PATTERNS.search(text))

def is_greeting(text: str) -> bool:
    text_l = text.lower()
    return any(greet in text_l for greet in GREETING_KEYWORDS)

def looks_food_related(text: str) -> bool:
    text_l = text.lower()
    words = re.findall(r"\b\w+\b", text_l)

    for kw in FOOD_KEYWORDS:
        if kw in text_l:
            return True

    # Fuzzy typo tolerance
    for word in words:
        close = difflib.get_close_matches(word, FOOD_KEYWORDS, n=1, cutoff=0.8)
        if close:
            return True
    return False

def cleanup_response(resp_text: str) -> str:
    """Clean Gemini response for readability, preserving number ranges like 15–25."""
    if not resp_text:
        return "Sorry, I couldn’t generate a response."
    if is_offtopic(resp_text):
        return "I can only help with food, health, nutrition, and restaurant menu questions."

    text = re.sub(r"[*_#>`~]+", "", resp_text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    if len(text.split()) > 100:
        text = " ".join(text.split()[:100]) + "..."
    return text

def find_relevant_items(question: str):
    """Fetch relevant dishes or ingredients from the DB for RAG context."""
    question = question.lower()
    dishes, ingredients = [], []

    if "spicy" in question:
        dishes = list(MenuItem.objects.filter(spice_level__gte=2, availability=True)
                      .values_list("name", flat=True))
        ingredients = list(Ingredient.objects.filter(category="spice")
                           .values_list("name", flat=True))

    elif "diet" in question or "healthy" in question:
        bases = list(Base.objects.all().values("name", "description"))
        ingredient_objs = Ingredient.objects.filter(
            category__in=["fruit", "green", "citrus", "extra", "sweetener"]
        ).order_by("category", "name")
        ingredients = [i.name for i in ingredient_objs]
        dishes = [f"{base['name']} with {', '.join(ingredients[:3])}" for base in bases]

    elif "dessert" in question or "sweet" in question:
        dishes = list(MenuItem.objects.filter(category="dessert", availability=True)
                      .values_list("name", flat=True))
        ingredients = list(Ingredient.objects.filter(category="sweetener")
                           .values_list("name", flat=True))

    if not dishes and not ingredients:
        return None
    return {"dishes": dishes, "ingredients": ingredients}

@api_view(["POST"])
@permission_classes([AllowAny])
def chat_with_gemini(request):
    message = (request.data.get("message") or "").strip()
    session_id = request.data.get("session_id")
    if not session_id:
        return Response({"error": "Missing session_id"}, status=400)
    if not message:
        return Response({"error": "Empty message"}, status=400)

    # Load or create session
    session, _ = ChatSession.objects.get_or_create(session_id=session_id)

    # Greeting only if VERY first user message
    is_first_message = (session.messages.count() == 0)

    # Save user message immediately
    ChatMessage.objects.create(session=session, sender="user", text=message)

    # Off-topic check
    if is_offtopic(message):
        reply_text = "I can help only with SmartDine restaurant menu, food, nutrition, or ordering."
        ChatMessage.objects.create(session=session, sender="assistant", text=reply_text)
        return Response({"reply": reply_text})

    # RAG lookup
    context_data = find_relevant_items(message)
    rag_context = ""
    if context_data:
        rag_context = (
            f"Related dishes: {', '.join(context_data.get('dishes', [])) or 'None'}.\n"
            f"Relevant ingredients: {', '.join(context_data.get('ingredients', [])) or 'None'}.\n"
        )

    # Fetch last N messages for memory
    history = list(
        session.messages.order_by("created_at")
        .values("sender", "text")
    )

    # Build conversation prompt
    conversation_txt = ""
    for msg in history:
        role = "Customer" if msg["sender"] == "user" else "Assistant"
        conversation_txt += f"{role}: {msg['text']}\n"

    # System instructions
    system_prompt = (
        "You are SmartDine AI, a restaurant assistant. "
        "You answer ONLY food, menu, nutrition, and restaurant-related questions. "
        "Keep responses concise, specific, and under 100 words. "
        "Never restart the conversation or greet repeatedly. "
        "Maintain context from the conversation history. "
        "If the customer refers to something previously mentioned, interpret it correctly.\n\n"
        f"{rag_context}"
    )

    if is_first_message:
        system_prompt += (
            "Start with a brief welcome on the first message only.\n"
        )

    # Build final prompt
    final_prompt = system_prompt + "\nConversation:\n" + conversation_txt

    # Gemini call
    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(final_prompt)
        reply = cleanup_response(response.text)

        # Save assistant message
        ChatMessage.objects.create(session=session, sender="assistant", text=reply)

        return Response({"reply": reply})

    except Exception as e:
        return Response({
            "error": "Gemini API request failed",
            "details": str(e)
        }, status=502)   
        
class LeaderboardView(APIView):
    """
    Returns a leaderboard of users based on completed orders stored in the User model.
    Each order gives 20 points. Supports kitchen or waiter filter.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        role_filter = None
        if request.query_params.get("kitchen") == "true":
            role_filter = "kitchen"
        elif request.query_params.get("waiter") == "true":
            role_filter = "waiter"

        try:
            if role_filter:
                users = User.objects.filter(role=role_filter, is_active=True)
            else:
                users = User.objects.filter(role__in=["kitchen", "waiter"], is_active=True)

            POINTS_PER_ORDER = 20
            leaderboard = []

            for user in users:
                orders_count = getattr(user, "orders_completed", 0)
                
                leaderboard.append({
                    "email": user.email,
                    "name": getattr(user, "name", ""),
                    "points": orders_count * POINTS_PER_ORDER,
                    "orders_completed": orders_count
                })

            leaderboard.sort(key=lambda x: x["points"], reverse=True)

            return Response({"leaderboard": leaderboard}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": f"Error fetching leaderboard: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
                      
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_completed_orders_pdf(request):
    chef = request.user
    today = datetime.now().date()

    orders = (
        Order.objects.filter(
            status="served",
            chef=chef,
            updated_at__date=today
        )
        .prefetch_related("items")
    )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=completed_orders.pdf"

    pdf = SimpleDocTemplate(
        response,
        pagesize=A4,
        leftMargin=30,
        rightMargin=30,
        topMargin=40,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=colors.HexColor("#059669"),
        spaceAfter=12,
    )
    subtitle_style = ParagraphStyle(
        "subtitle",
        parent=styles["Normal"],
        fontSize=12,
        textColor=colors.grey,
        spaceAfter=8,
    )

    elements = []

    # Header
    elements.append(Paragraph("Completed Orders Report", title_style))
    elements.append(Paragraph(f"Chef: {chef}", subtitle_style))
    elements.append(Paragraph(f"Date: {today}", subtitle_style))
    elements.append(Spacer(1, 12))

    # Table Heading
    data = [["Table", "Items", "Total (₹)", "Completed Time"]]

    # Add all orders
    for order in orders:
        total_items = order.items.aggregate(total=Sum("quantity"))["total"] or 0
        data.append([
            str(order.table.table_number),
            str(total_items),
            str(order.total),
            order.updated_at.strftime("%I:%M %p"),
        ])

    # Table Styling
    table = TablePDF(data, colWidths=[50, 60, 80, 100])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#059669")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 12),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),

            ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),

            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 11),
        ])
    )

    elements.append(table)

    pdf.build(elements)
    return response

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_inventory_pdf(request):

    items = MenuItem.objects.all().order_by("category", "name")

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=inventory_report.pdf"

    pdf = SimpleDocTemplate(
        response,
        pagesize=A4,
        leftMargin=30,
        rightMargin=30,
        topMargin=40,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=colors.HexColor("#059669"),
        spaceAfter=12,
    )
    subtitle_style = ParagraphStyle(
        "subtitle",
        parent=styles["Normal"],
        fontSize=12,
        textColor=colors.grey,
        spaceAfter=8,
    )

    elements = []

    elements.append(Paragraph("Inventory Report", title_style))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%d %b %Y %I:%M %p')}", subtitle_style))
    elements.append(Spacer(1, 14))

    data = [["Name", "Category", "Stock", "Min Stock", "Price (₹)", "Status"]]

    for item in items:
        status = (
            "Out of Stock" if item.stock == 0
            else "Low Stock" if item.stock <= item.min_stock
            else "In Stock"
        )
        data.append([
            item.name,
            item.category,
            str(item.stock),
            str(item.min_stock),
            str(item.price),
            status,
        ])

    table = TablePDF(data, colWidths=[100, 70, 40, 50, 60, 60])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#059669")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 12),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),

            ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 10),

            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (2, 1), (-2, -1), "CENTER"),
        ])
    )

    elements.append(table)

    pdf.build(elements)
    return response

