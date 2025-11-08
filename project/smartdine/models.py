from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser, BaseUserManager, PermissionsMixin
)
import uuid
import qrcode
from io import BytesIO
from django.core.files import File
from datetime import timedelta
from django.utils import timezone
from decimal import Decimal
from django.conf import settings  # <-- important


class UserManager(BaseUserManager):
    def create_user(self, email, name, role='waiter', password=None, **extra_fields):
        if not email:
            raise ValueError("Email must be provided")
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            name=name,
            role=role,
            is_active=False,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None, **extra_fields):
        user = self.create_user(email, name, role='admin', password=password, **extra_fields)
        user.is_staff = True
        user.is_superuser = True
        user.is_approved_by_admin = True
        user.is_email_verified = True
        user.is_active = True
        user.save(using=self._db)
        return user

class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('kitchen', 'Kitchen'),
        ('waiter', 'Waiter'),
    ]

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    is_approved_by_admin = models.BooleanField(default=False)
    email_verification_token = models.UUIDField(default=uuid.uuid4, editable=False)
    password_reset_token = models.UUIDField(null=True, blank=True)
    password_reset_sent_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    objects = UserManager()

    def __str__(self):
        return f"{self.name} ({self.email})"

    def create_reset_token(self):
        self.password_reset_token = uuid.uuid4()
        self.password_reset_sent_at = timezone.now()
        self.save(update_fields=["password_reset_token", "password_reset_sent_at"])
        return self.password_reset_token

    def is_reset_token_valid(self, token, expiry_minutes=10):
        if not self.password_reset_token or not self.password_reset_sent_at:
            return False
        if str(self.password_reset_token) != str(token):
            return False
        expiry_time = self.password_reset_sent_at + timedelta(minutes=expiry_minutes)
        return timezone.now() <= expiry_time

    def clear_reset_token(self):
        self.password_reset_token = None
        self.password_reset_sent_at = None
        self.save(update_fields=["password_reset_token", "password_reset_sent_at"])


class Table(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('occupied', 'Occupied'),
        ('reserved', 'Reserved'),
    ]

    table_number = models.PositiveIntegerField(unique=True)
    seats = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """
        Save the Table instance, then generate and attach a QR code image.
        The QR will contain a link to the frontend customer dashboard.
        """
        super().save(*args, **kwargs)

        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3001")
        qr_data = f"{frontend_url}/customer/dashboard?table={self.table_number}"

        qr_img = qrcode.make(qr_data)
        buffer = BytesIO()
        qr_img.save(buffer, format="PNG")
        file_name = f"table_{self.table_number}_qr.png"

        self.qr_code.save(file_name, File(buffer), save=False)
        super().save(update_fields=['qr_code'])

    def __str__(self):
        return f"Table {self.table_number}"



class MenuItem(models.Model):
    CATEGORY_CHOICES = [
        ('starter', 'Starter'),
        ('main', 'Main Course'),
        ('dessert', 'Dessert'),
        ('drink', 'Drink'),
    ]

    TYPE_CHOICES = [
        ('veg', 'Veg'),
        ('non-veg', 'Non-Veg'),
    ]

    SPICE_CHOICES = [
        (0, 'No Spice'),
        (1, 'Mild'),
        (2, 'Medium'),
        (3, 'Hot'),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='veg')
    spice_level = models.IntegerField(choices=SPICE_CHOICES, default=0)
    customizable = models.BooleanField(default=False)
    image = models.ImageField(upload_to='menu_images/', null=True, blank=True)
    stock = models.PositiveIntegerField(default=0, help_text="Available quantity for this item")
    availability = models.BooleanField(default=True)
    preparation_time = models.PositiveIntegerField(default=10) 
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    min_stock = models.PositiveIntegerField(
        default=5,
        help_text="Minimum stock before triggering low stock alert"
    )

    def __str__(self):
        return f"{self.name} ({self.type})"

    def is_available(self):
        """Check if item can be ordered based on stock and availability."""
        return self.availability and self.stock > 0
    
    def is_low_stock(self):
        """Check if stock is below minimum threshold."""
        return self.stock <= self.min_stock

class Cart(models.Model):
    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name="cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for Table {self.table.table_number}"

    @property
    def total_amount(self):
        return sum(item.subtotal for item in self.items.all())

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, null=True, blank=True)
    custom_dish = models.ForeignKey("CustomDish", on_delete=models.CASCADE, null=True, blank=True)

    quantity = models.PositiveIntegerField(default=1)
    special_instructions = models.TextField(blank=True, null=True)
    is_custom = models.BooleanField(default=False)

    def __str__(self):
        if self.is_custom and self.custom_dish:
            return f"Custom: {self.custom_dish.name} x{self.quantity}"
        elif self.menu_item:
            return f"{self.menu_item.name} x{self.quantity}"
        return f"Cart Item x{self.quantity}"

    @property
    def subtotal(self):
        if self.is_custom and self.custom_dish:
            return float(self.custom_dish.total_price) * self.quantity
        return float(self.menu_item.price) * self.quantity

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('served', 'Served'),
    ]

    table = models.ForeignKey("Table", on_delete=models.CASCADE)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    estimated_time = models.PositiveIntegerField(default=0)  # in minutes
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    started_preparing_at = models.DateTimeField(null=True, blank=True)  # ✅ NEW


    def __str__(self):
        return f"Order {self.id} - Table {self.table.table_number}"

    def update_total_and_eta(self):
        items = self.items.select_related("menu_item", "custom_dish").all()
        self.total = sum(item.subtotal for item in items)
        total_time = 0
        for item in items:
            if item.menu_item:
                total_time += (item.menu_item.preparation_time or 0) * item.quantity
            elif item.custom_dish:
                total_time += (item.custom_dish.preparation_time or 0) * item.quantity

        self.estimated_time = total_time or 10 
        self.save()

class OrderItem(models.Model):
    order = models.ForeignKey("Order", on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey("MenuItem", on_delete=models.CASCADE, null=True, blank=True)
    custom_dish = models.ForeignKey("CustomDish", on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        """Auto-calculate subtotal and update parent order."""
        self.subtotal = self.quantity * self.price
        super().save(*args, **kwargs)
        if self.order_id:
            self.order.update_total_and_eta()

    def __str__(self):
        if self.menu_item:
            return f"{self.menu_item.name} x{self.quantity}"
        elif self.custom_dish:
            return f"{self.custom_dish.name} (Custom) x{self.quantity}"
        return f"Unknown Item x{self.quantity}"

class WaiterRequest(models.Model):
    TYPE_CHOICES = [
        ('need water', 'Need Water'),
        ('need bill', 'Need Bill'),
        ('clean table', 'Clean Table'),
        ('general', 'General Request'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in-progress', 'In Progress'),
        ('completed', 'Completed'),
    ]

    table = models.ForeignKey(Table, on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description = models.TextField(blank=True, null=True) 
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.type} - Table {self.table.table_number}"
  
class Feedback(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="feedback")
    food_rating = models.PositiveIntegerField(default=0)
    service_rating = models.PositiveIntegerField(default=0)
    comments = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Feedback for Order #{self.order.id}"

class Base(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=6, decimal_places=2)
  
    def __str__(self):
       return self.name
   
class Ingredient(models.Model):
    CATEGORY_CHOICES = [
        ('fruit', 'Fruit'),
        ('green', 'Green'),
        ('sweetener', 'Sweetener'),
        ('extra', 'Extra'),
        ('spice', 'Spice'),
        ('citrus', 'Citrus'),
    ]

    name = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return f"{self.name} ({self.get_category_display()}) - ₹{self.price}"

class CustomDish(models.Model):
    table = models.ForeignKey(
        "Table",
        on_delete=models.CASCADE,
        related_name="custom_dishes",
        null=True,
        blank=True
    )
    name = models.CharField(max_length=120)
    base = models.ForeignKey("Base", on_delete=models.SET_NULL, null=True, blank=True)
    total_price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    special_notes = models.TextField(blank=True, null=True)
    preparation_time = models.PositiveIntegerField(default=0, help_text="Time in minutes")
    created_at = models.DateTimeField(auto_now_add=True)
    sold_count = models.PositiveIntegerField(default=0)
    image_url = models.URLField(blank=True, null=True)
    image_status = models.CharField(max_length=20, default="pending")  

    def calculate_total(self):
        """Calculate total = base price + all ingredients"""
        base_price = self.base.price if self.base else Decimal("0.00")
        ingredients_total = sum(
            item.ingredient.price * item.quantity for item in self.dish_ingredients.all()
        )
        return base_price + ingredients_total

    def calculate_preparation_time(self):
        """
        Optional: estimate preparation time.
        Example: base has time + ingredients add extra minutes.
        """
        base_time = getattr(self.base, "preparation_time", 5)  
        ingredients_time = sum(
            getattr(item.ingredient, "preparation_time", 1) * item.quantity
            for item in self.dish_ingredients.all()
        )
        return base_time + ingredients_time

    def save(self, *args, **kwargs):
        """Auto-update total price and preparation time before saving"""
        super().save(*args, **kwargs)

        new_total = self.calculate_total()
        new_prep_time = self.calculate_preparation_time()

        update_fields = []
        if self.total_price != new_total:
            self.total_price = new_total
            update_fields.append("total_price")
        if self.preparation_time != new_prep_time:
            self.preparation_time = new_prep_time
            update_fields.append("preparation_time")

        if update_fields:
            super().save(update_fields=update_fields)

    def __str__(self):
        return f"{self.name or 'Custom Dish'} - ₹{self.total_price} ({self.preparation_time} min)"

class CustomDishIngredient(models.Model):
    custom_dish = models.ForeignKey(
        CustomDish,
        on_delete=models.CASCADE,
        related_name="dish_ingredients"
    )
    ingredient = models.ForeignKey("Ingredient", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("custom_dish", "ingredient")

    def __str__(self):
        return self.ingredient.name
    
    
class TableHistory(models.Model):
    table = models.ForeignKey("Table", on_delete=models.CASCADE, related_name="history")
    status = models.CharField(max_length=20, choices=[('available','Available'), ('occupied','Occupied')])
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    snapshot = models.JSONField(default=dict)  

    def __str__(self):
        return f"Table {self.table.table_number} cleared at {self.timestamp}"