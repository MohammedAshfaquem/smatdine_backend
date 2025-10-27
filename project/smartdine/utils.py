
from django.core.mail import send_mail
from django.conf import settings

def send_verification_email(user):
    try:
        verification_link = f"{settings.FRONTEND_URL}/verify-email/{user.email_verification_token}"
        subject = "Verify your email"
        message = f"Click the link to verify your email: {verification_link}"
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=f'<p>Click here to verify your email: <a href="{verification_link}">{verification_link}</a></p>'
        )
        print(f"Verification email sent to {user.email}")
    except Exception as e:
        print(f"Failed to send email to {user.email}: {e}")
