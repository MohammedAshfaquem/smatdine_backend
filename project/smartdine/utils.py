
from django.core.mail import send_mail
from django.conf import settings
import os

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
        
def get_unsplash_image(dish):
    """
    Generate an Unsplash image URL for a CustomDish based on its base and ingredients.
    Returns None if the request fails or no image is found.
    """
    import os
    import requests

    access_key = os.getenv("UNSPLASH_ACCESS_KEY")
    if not access_key:
        print("UNSPLASH_ACCESS_KEY not set")
        return None

    base_name = dish.base.name if dish.base else "custom drink"
    ingredients_list = [di.ingredient.name for di in dish.dish_ingredients.all()]
    ingredients_str = ", ".join(ingredients_list) if ingredients_list else ""
    descriptive_words = []
    citrus_keywords = {"lime", "lemon", "orange", "grapefruit", "tangerine"}
    tropical_keywords = {"pineapple", "mango", "coconut", "passion fruit"}
    sweet_keywords = {"honey", "syrup", "sugar", "chocolate"}

    if any(ing.lower() in citrus_keywords for ing in ingredients_list):
        descriptive_words.append("fresh, zesty, bright")
    if any(ing.lower() in tropical_keywords for ing in ingredients_list):
        descriptive_words.append("tropical, colorful, exotic")
    if any(ing.lower() in sweet_keywords for ing in ingredients_list):
        descriptive_words.append("sweet, glossy, appealing")
    prompt = (
        f"A glass of {base_name.lower()} with {ingredients_str}, "
        f"{', '.join(descriptive_words)}, "
        "realistic lighting, photorealistic, colorful background, high resolution, served in a clear glass"
    )

    try:
        response = requests.get(
            "https://api.unsplash.com/photos/random",
            params={"query": prompt, "orientation": "squarish"},
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        return data.get("urls", {}).get("regular")
    except requests.RequestException as e:
        print("Unsplash request failed:", e)
        return None


