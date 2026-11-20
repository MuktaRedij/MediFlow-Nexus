"""Management command to create demo users for testing."""
import os

from django.core.management.base import BaseCommand, CommandError
from accounts.models import CustomUser


class Command(BaseCommand):
    """Create demo users command."""
    
    help = 'Create demo admin, doctor, and patient users for testing'
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--admin-email',
            type=str,
            default=os.getenv('MEDIFLOW_DEMO_ADMIN_EMAIL'),
            help='Admin email (or set MEDIFLOW_DEMO_ADMIN_EMAIL)'
        )
        parser.add_argument(
            '--admin-password',
            type=str,
            default=os.getenv('MEDIFLOW_DEMO_ADMIN_PASSWORD'),
            help='Admin password (or set MEDIFLOW_DEMO_ADMIN_PASSWORD)'
        )
        parser.add_argument(
            '--doctor-email',
            type=str,
            default=os.getenv('MEDIFLOW_DEMO_DOCTOR_EMAIL'),
            help='Doctor email (or set MEDIFLOW_DEMO_DOCTOR_EMAIL)'
        )
        parser.add_argument(
            '--doctor-password',
            type=str,
            default=os.getenv('MEDIFLOW_DEMO_DOCTOR_PASSWORD'),
            help='Doctor password (or set MEDIFLOW_DEMO_DOCTOR_PASSWORD)'
        )
        parser.add_argument(
            '--patient-email',
            type=str,
            default=os.getenv('MEDIFLOW_DEMO_PATIENT_EMAIL'),
            help='Patient email (or set MEDIFLOW_DEMO_PATIENT_EMAIL)'
        )
        parser.add_argument(
            '--patient-password',
            type=str,
            default=os.getenv('MEDIFLOW_DEMO_PATIENT_PASSWORD'),
            help='Patient password (or set MEDIFLOW_DEMO_PATIENT_PASSWORD)'
        )
    
    def handle(self, *args, **options):
        """Handle command execution."""
        required_options = {
            'admin_email': 'MEDIFLOW_DEMO_ADMIN_EMAIL',
            'admin_password': 'MEDIFLOW_DEMO_ADMIN_PASSWORD',
            'doctor_email': 'MEDIFLOW_DEMO_DOCTOR_EMAIL',
            'doctor_password': 'MEDIFLOW_DEMO_DOCTOR_PASSWORD',
            'patient_email': 'MEDIFLOW_DEMO_PATIENT_EMAIL',
            'patient_password': 'MEDIFLOW_DEMO_PATIENT_PASSWORD',
        }
        missing = [
            env_name
            for option, env_name in required_options.items()
            if not options.get(option)
        ]
        if missing:
            raise CommandError(
                'Set the required demo-user environment variables: '
                + ', '.join(missing)
            )

        admin_email = options['admin_email'].lower()
        admin_password = options['admin_password']
        doctor_email = options['doctor_email'].lower()
        doctor_password = options['doctor_password']
        patient_email = options['patient_email'].lower()
        patient_password = options['patient_password']
        
        # Create or update admin user
        admin_user, admin_created = CustomUser.objects.get_or_create(
            email=admin_email,
            defaults={
                'username': admin_email,
                'first_name': 'Admin',
                'last_name': 'User',
                'is_staff': True,
                'is_superuser': True,
                'role': 'ADMIN' if hasattr(CustomUser, 'ROLE_CHOICES') else 'DOCTOR',
            }
        )
        
        if not admin_created:
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.first_name = 'Admin'
            admin_user.last_name = 'User'
        
        admin_user.set_password(admin_password)
        admin_user.save()
        
        # Create or update demo doctor
        doctor_user, doctor_created = CustomUser.objects.get_or_create(
            email=doctor_email,
            defaults={
                'username': doctor_email,
                'first_name': 'Demo',
                'last_name': 'Doctor',
                'role': 'DOCTOR',
            }
        )
        
        if not doctor_created:
            doctor_user.first_name = 'Demo'
            doctor_user.last_name = 'Doctor'
            doctor_user.role = 'DOCTOR'
        
        doctor_user.set_password(doctor_password)
        doctor_user.save()
        
        # Create or update demo patient
        patient_user, patient_created = CustomUser.objects.get_or_create(
            email=patient_email,
            defaults={
                'username': patient_email,
                'first_name': 'Demo',
                'last_name': 'Patient',
                'role': 'PATIENT',
            }
        )
        
        if not patient_created:
            patient_user.first_name = 'Demo'
            patient_user.last_name = 'Patient'
            patient_user.role = 'PATIENT'
        
        patient_user.set_password(patient_password)
        patient_user.save()
        
        self.stdout.write(self.style.SUCCESS('\n✓ Demo users created/updated successfully!\n'))
        self.stdout.write('Created or updated the configured demo accounts.')
