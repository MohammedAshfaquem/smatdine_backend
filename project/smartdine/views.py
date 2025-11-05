from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404,redirect
from rest_framework import status, permissions,parsers
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
from .utils import send_verification_email
from .models import Table,MenuItem,CartItem,Cart,OrderItem,Order,Feedback,WaiterRequest,Base,CustomDish,CustomDishIngredient,Ingredient
from django.conf import settings
from datetime import timedelta
from django.utils import timezone
import datetime
from decimal import Decimal





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
    frontend_url = f"http://localhost:3001/table/{table.table_number}"
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
        # Show only admin-approved staff
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
        # Anyone can view menu; authenticated users can modify
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    # ✅ GET: List or filter menu items dynamically
    def get(self, request):
        queryset = MenuItem.objects.all().order_by('-created_at')

        # Get query parameters from URL
        category = request.query_params.get("category")
        item_type = request.query_params.get("type")
        available = request.query_params.get("available")

        # ✅ Apply filters if provided
        if category:
            queryset = queryset.filter(category__iexact=category)
        if item_type:
            queryset = queryset.filter(type__iexact=item_type)
        if available:
            queryset = queryset.filter(availability=(available.lower() == "true"))

        serializer = MenuItemSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # ✅ POST: Create a new menu item
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

    # GET: Retrieve single item
    def get(self, request, pk):
        item = get_object_or_404(MenuItem, pk=pk)
        serializer = MenuItemSerializer(item)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # PUT: Update full item
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

    # PATCH: Partial update (like changing availability)
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

    # DELETE: Delete item
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

    # 🛒 Get full cart by table
    def get(self, request, table_number):
        cart = self.get_cart(table_number)
        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # ➕ Add menu item or custom dish
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

        # Handle adding a custom dish
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
            # Normal menu item
            if not menu_item_id:
                return Response({"error": "Missing menu_item_id"}, status=status.HTTP_400_BAD_REQUEST)

            menu_item = get_object_or_404(MenuItem, id=menu_item_id)
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                menu_item=menu_item,
                defaults={
                    "quantity": quantity,
                    "special_instructions": special_instructions,
                    "is_custom": False,
                },
            )

        # If already exists, update quantity and notes
        if not created:
            cart_item.quantity += quantity
            if special_instructions:
                cart_item.special_instructions = special_instructions
            cart_item.save()

        name = (
            cart_item.custom_dish.name
            if getattr(cart_item, "is_custom", False)
            else cart_item.menu_item.name
        )

        return Response(
            {
                "message": f"Item added to cart for Table {cart.table.table_number}",
                "item": name,
                "quantity": cart_item.quantity,
            },
            status=status.HTTP_201_CREATED,
        )

    # 🔄 Update item quantity
    def patch(self, request):
        table_number = request.data.get("table_number")
        item_id = request.data.get("item_id")
        quantity = request.data.get("quantity")

        if not table_number or not item_id:
            return Response(
                {"error": "Missing table_number or item_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart = self.get_cart(table_number)
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)

        cart_item.quantity = quantity
        cart_item.save()

        return Response(
            {"message": f"Quantity updated for Table {cart.table.table_number}"},
            status=status.HTTP_200_OK,
        )

    # ❌ Remove item
    def delete(self, request, item_id):
        table_number = request.query_params.get("table_number")
        if not table_number:
            return Response(
                {"error": "Missing table_number in query params"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart = self.get_cart(table_number)
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        cart_item.delete()

        return Response(
            {"message": f"Item removed from Table {cart.table.table_number}"},
            status=status.HTTP_204_NO_CONTENT,
        )
        

class CartCountView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, table_number):
        try:
            # 👇 Adjust this based on your Table model field
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
        Convert Cart → Order
        """
        table_number = request.data.get("table_number")
        if not table_number:
            return Response({"error": "Missing table_number"}, status=status.HTTP_400_BAD_REQUEST)

        table = get_object_or_404(Table, table_number=table_number)
        cart = get_object_or_404(Cart, table=table)
        cart_items = CartItem.objects.filter(cart=cart)

        if not cart_items.exists():
            return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

        order = Order.objects.create(table=table, status="pending")
        total = Decimal("0.00")

        for item in cart_items:
            if item.menu_item:
                subtotal = Decimal(item.menu_item.price) * item.quantity
                OrderItem.objects.create(
                    order=order,
                    menu_item=item.menu_item,
                    quantity=item.quantity,
                    price=item.menu_item.price,
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

        order.total = total
        order.update_total_and_eta()

        # ✅ Calculate when the order will be ready
        expected_ready_time = timezone.now() + timedelta(minutes=order.estimated_time)

        # ✅ Clear cart
        cart_items.delete()

        serializer = OrderSerializer(order)
        return Response(
            {
                "message": f"Order placed successfully for Table {table_number}",
                "order": {
                    **serializer.data,
                    "expected_ready_time": expected_ready_time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            },
            status=status.HTTP_201_CREATED,
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
                    if item.menu_item:  # ✅ normal menu item
                        items.append({
                            "type": "menu_item",
                            "name": item.menu_item.name,
                            "image": item.menu_item.image.url if item.menu_item.image else None,
                            "quantity": item.quantity,
                            "subtotal": str(item.subtotal),
                        })
                    elif item.custom_dish:  # ✅ custom dish
                        items.append({
                            "type": "custom_dish",
                            "name": item.custom_dish.name,
                            "ingredients": [
                                {
                                    "name": di.ingredient.name,
                                    "quantity": di.quantity
                                } for di in item.custom_dish.dish_ingredients.all()
                            ],
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

            # ✅ Estimated and ready time
            estimated_minutes = order.estimated_time or 0
            expected_ready_time = order.created_at + timedelta(minutes=estimated_minutes)

            now = timezone.now()
            remaining = expected_ready_time - now
            minutes_left = max(int(remaining.total_seconds() // 60), 0)
            time_remaining = (
                f"{minutes_left} minutes left" if minutes_left > 0 else "Ready"
            )

            # ✅ Fetch all order items (handle both menu + custom dish)
            items = []
            for item in OrderItem.objects.filter(order=order):
                if item.menu_item:  # Normal menu item
                    items.append({
                        "type": "menu_item",
                        "name": item.menu_item.name,
                        "image": item.menu_item.image.url if item.menu_item.image else None,
                        "quantity": item.quantity,
                        "subtotal": str(item.subtotal),
                    })
                elif item.custom_dish:  # Custom dish
                    items.append({
                        "type": "custom_dish",
                        "name": item.custom_dish.name,
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

            # ✅ Final response
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
    permission_classes = [permissions.AllowAny]  # ✅ Allow anyone (no login required)

    def get(self, request, order_id):
        """Check if feedback exists for this order"""
        exists = Feedback.objects.filter(order_id=order_id).exists()
        return Response({"exists": exists})

    def post(self, request, order_id):
        """Submit feedback for an order"""
        order = get_object_or_404(Order, id=order_id)

        # Prevent multiple submissions
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
    Customer creates a waiter request (e.g., need water, need bill, clean table)
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, table_id):
        # Support both table id and table_number matching
        table = get_object_or_404(Table, table_number=table_id)

        req_type = request.data.get("type")
        valid_types = ['need water', 'need bill', 'clean table']

        if req_type not in valid_types:
            return Response(
                {"error": f"Invalid request type. Must be one of {valid_types}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create the request
        WaiterRequest.objects.create(table=table, type=req_type)

        return Response(
            {"message": f"Waiter request '{req_type}' sent for Table {table.table_number}"},
            status=status.HTTP_201_CREATED,
        )


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
    permission_classes = [permissions.AllowAny]  # change later if you use JWT

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

        if not requests.exists():
            return Response(
                {"message": f"No requests found for Table {table_number}"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = WaiterRequestSerializer(requests, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    
@api_view(['PATCH'])
@permission_classes([permissions.AllowAny])  # since customers are public users
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
    """
    POST payload example:
    {
      "name": "Berry Blast Supreme",
      "base_id": 1,
      "special_notes": "Extra ice",
      "ingredients": [
         {"ingredient_id": 3, "quantity": 1},
         {"ingredient_id": 7, "quantity": 2}
      ],
      "add_to_cart": true
    }
    """
    permission_classes = [permissions.AllowAny]  # customers can create

    def post(self, request, table_id):
        # ✅ Get the table using table_number (for consistency)
        table = get_object_or_404(Table, table_number=table_id)
        serializer = CustomDishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        base_id = serializer.validated_data.get("base_id")
        name = serializer.validated_data.get("name")
        special_notes = serializer.validated_data.get("special_notes", "")
        ingredients_payload = request.data.get("ingredients", [])
        add_to_cart = request.data.get("add_to_cart", True)

        base = get_object_or_404(Base, id=base_id)

        # ✅ Create dish and associate with the table
        custom_dish = CustomDish.objects.create(
            name=name,
            base=base,
            special_notes=special_notes,
            total_price=Decimal("0.00"),
            table=table,  # ✅ associate with table
        )

        total_price = Decimal(base.price or 0)
        total_time = base.preparation_time if hasattr(base, "preparation_time") else 0  # optional

        # ✅ Add ingredients
        for item in ingredients_payload:
            ing_id = item.get("ingredient_id")
            qty = int(item.get("quantity", 1))
            if qty <= 0:
                qty = 1

            ingredient = get_object_or_404(Ingredient, id=ing_id)
            CustomDishIngredient.objects.create(
                custom_dish=custom_dish,
                ingredient=ingredient,
                quantity=qty,
            )
            total_price += Decimal(ingredient.price) * qty
            # optional: if Ingredient has prep_time
            total_time += getattr(ingredient, "preparation_time", 0) * qty

        # ✅ Save updated totals
        custom_dish.total_price = total_price
        custom_dish.preparation_time = total_time  # ✅ update prep time
        custom_dish.save()

        # ✅ Optionally add to the cart
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
            {"message": "Custom dish created successfully", "dish": out_serializer.data},
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
    permission_classes = [permissions.AllowAny]  # allow all to view

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        show_all = request.query_params.get("all") == "true"

        dishes = (
            CustomDish.objects.select_related("table", "base")
            .prefetch_related("dish_ingredients__ingredient")
            .order_by("-sold_count", "-created_at")
        )

        # 🧠 Customers (unauthenticated or role=customer)
        if (not user or getattr(user, "role", None) == "customer") and not show_all:
            top_dishes = dishes[:3]
            serializer = CustomDishSerializer(top_dishes, many=True)
            return Response({
                "message": "Top 3 most popular custom dishes",
                "show_all": False,
                "data": serializer.data,
            }, status=status.HTTP_200_OK)

        # 👨‍🍳 Admin/Waiter (or ?all=true)
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