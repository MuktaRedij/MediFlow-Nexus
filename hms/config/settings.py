import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _environment_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise ImproperlyConfigured(f'{name} must be set to a boolean value.')


DEBUG = _environment_bool('DEBUG', True)

SECRET_KEY = os.getenv('SECRET_KEY', '').strip()
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            'SECRET_KEY must be configured when DEBUG is disabled.'
        )
    SECRET_KEY = get_random_secret_key()
elif not DEBUG and (
    SECRET_KEY.lower().startswith(
        ('your-', 'replace-with', 'change-me', 'changeme', '<')
    )
    or any(
        marker in SECRET_KEY.lower()
        for marker in ('placeholder', 'example', 'django-insecure')
    )
):
    raise ImproperlyConfigured(
        'Replace the SECRET_KEY placeholder with a secure production value.'
    )

allowed_hosts_setting = os.getenv('ALLOWED_HOSTS')
ALLOWED_HOSTS = [
    host.strip()
    for host in (
        allowed_hosts_setting
        if allowed_hosts_setting is not None
        else ('localhost,127.0.0.1' if DEBUG else '')
    ).split(',')
    if host.strip()
]
if not DEBUG and (
    not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS
):
    raise ImproperlyConfigured(
        'ALLOWED_HOSTS must list explicit production host names when DEBUG is disabled.'
    )

ALLOW_TEST_PAYMENTS = (
    DEBUG and _environment_bool('ALLOW_TEST_PAYMENTS', False)
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'doctors',
    'patients',
    'bookings',
    'admin_management',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# SQLite for development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# PostgreSQL configuration (uncomment for production)
# DATABASES = {
#     'default': {
#          'ENGINE': 'django.db.backends.postgresql',
#          'NAME': os.getenv('DB_NAME', 'hms_db'),
#          'USER': os.getenv('DB_USER', 'postgres'),
#          'PASSWORD': os.getenv('DB_PASSWORD', ''),
#          'HOST': os.getenv('DB_HOST', 'localhost'),
#          'PORT': os.getenv('DB_PORT', '5432'),
#      }
#  }

AUTH_USER_MODEL = 'accounts.CustomUser'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files configuration
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'home'

# Session Configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 1209600  # 2 weeks
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# CSRF Configuration
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False  # Must be False for CSRF token access
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_AGE = 31449600  # 1 year
csrf_origins_setting = os.getenv('CSRF_TRUSTED_ORIGINS')
CSRF_TRUSTED_ORIGINS = (
    [origin.strip() for origin in csrf_origins_setting.split(',') if origin.strip()]
    if csrf_origins_setting is not None
    else (
        ['http://localhost:8000', 'http://127.0.0.1:8000']
        if DEBUG else []
    )
)
CSRF_FAILURE_VIEW = 'accounts.views.csrf_failure_view'

# Google OAuth settings
GOOGLE_CLIENT_ID = os.getenv(
    'GOOGLE_CLIENT_ID'
    
)

GOOGLE_CLIENT_SECRET = os.getenv(
    'GOOGLE_CLIENT_SECRET'
)

GOOGLE_REDIRECT_URI = os.getenv(
    'GOOGLE_REDIRECT_URI'
)

# Email service settings
EMAIL_SERVICE_URL = os.getenv(
    'EMAIL_SERVICE_URL'
)

# Razorpay API Keys
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID', 'your_razorpay_key_id')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET', 'your_razorpay_key_secret')
