from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0002_booking_reminder_sent_1h_booking_reminder_sent_24h'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('doctors', '0002_availabilityslot_is_recurring_and_more'),
    ]

    # Keep this migration node for existing databases; 0002 already creates these models.
    operations = []
