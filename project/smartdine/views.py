from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404,redirect
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny,IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import StaffRegisterSerializer, StaffLoginSerializer,TableSerializer,StaffSerializer
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .utils import send_verification_email
from .models import Table
from django.conf import settings




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