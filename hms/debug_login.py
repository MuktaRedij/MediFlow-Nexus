"""Debug script to check user credentials."""
import os

email = os.environ.get('MEDIFLOW_DEMO_ADMIN_EMAIL')
password = os.environ.get('MEDIFLOW_DEMO_ADMIN_PASSWORD')
if not email or not password:
    raise SystemExit(
        'Set MEDIFLOW_DEMO_ADMIN_EMAIL and MEDIFLOW_DEMO_ADMIN_PASSWORD '
        'in the environment before running this diagnostic.'
    )

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from accounts.models import CustomUser

print("Checking configured demo administrator account...")

# Check if user exists
try:
    user = CustomUser.objects.get(email__iexact=email)
    print("Account found.")
    print(f"  Role: {user.role}")
    print(f"  Is Staff: {user.is_staff}")
    print(f"  Is Superuser: {user.is_superuser}")
    
    # Check if password is correct
    if user.check_password(password):
        print("Configured password matches.")
    else:
        print("Configured password does not match.")
        print("If appropriate, configure demo-user values and run the demo-user command.")
    
except CustomUser.DoesNotExist:
    print("Configured demo administrator account was not found.")
    print("If appropriate, configure demo-user values and run the demo-user command.")
