from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import StaffRegisterSerializer, StaffLoginSerializer
from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt



User = get_user_model()

# ---------------------------
# Register Staff
# ---------------------------
class StaffRegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = StaffRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            try:
                from .utils import send_verification_email
                send_verification_email(user)
            except Exception as e:
                print(f"Email sending failed: {e}")
            return Response({"success": True, "message": "Registered successfully! Please verify your email."}, status=201)
        return Response(serializer.errors, status=400)

# ---------------------------
# Email Verification
# ---------------------------
@api_view(['GET'])
@permission_classes([AllowAny])
def verify_staff_email(request, token):
    try:
        user = get_object_or_404(User, email_verification_token=token)
        if user.is_email_verified:
            return Response({"message": "Email already verified!"})
        user.is_email_verified = True
        user.is_active = True
        user.save()
        return Response({"message": "Email verified successfully!"})
    except Exception:
        return Response({"message": "Invalid or expired token."}, status=400)

# ---------------------------
# Staff Login
# ---------------------------
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
        if user.isBlocked:
            return Response({"error": "Your account is blocked."}, status=401)

        return Response(data, status=200)

# ---------------------------
# Admin: Pending Users

# ---------------------------
# Password Reset
# ---------------------------
class RequestPasswordResetView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"error": "Email is required"}, status=400)
        try:
            user = User.objects.get(email=email)
            token = default_token_generator.make_token(user)
            reset_url = f"http://localhost:3001/reset-password/{user.id}/{token}"
            send_mail("Password Reset Request", f"Click here: {reset_url}", from_email=None, recipient_list=[user.email])
            return Response({"message": "Password reset link sent to email."}, status=200)
        except User.DoesNotExist:
            return Response({"error": "User does not exist."}, status=404)

class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, user_id, token):
        password = request.data.get('password')
        confirm_password = request.data.get('confirm_password')

        if not password or not confirm_password:
            return Response({"error": "Both password fields are required."}, status=400)

        if password != confirm_password:
            return Response({"error": "Passwords do not match."}, status=400)

        user = get_object_or_404(User, id=user_id)

        if default_token_generator.check_token(user, token):
            user.set_password(password)
            user.save()
            return Response({"message": "Password reset successful."}, status=200)

        return Response({"error": "Invalid or expired token."}, status=400)
    
 
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_pending_users(request):
    if request.user.role != "admin":
        return Response({"error": "Only admins can view pending users."}, status=403)

    pending_users = User.objects.filter(is_email_verified=True, is_approved_by_admin=False)
    data = [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "is_email_verified": u.is_email_verified,
            "is_approved_by_admin": u.is_approved_by_admin,
        }
        for u in pending_users
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
    
    
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_requests_count(request):
    """
    Return the number of pending user requests (excluding superusers)
    """
    count = User.objects.filter(
        is_approved_by_admin=False,
        is_superuser=False
    ).count()
    return Response({"pending_count": count})