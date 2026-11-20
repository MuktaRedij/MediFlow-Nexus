"""URL Configuration for HMS."""
from django.contrib import admin
from django.urls import path, include
from accounts.views import home
from patients.views import block_public_medical_report_media
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path(
        'media/medical_records/<path:file_path>',
        block_public_medical_report_media,
        name='block_public_medical_report_media',
    ),
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    path('dashboard/', include('admin_management.urls')),
    path('auth/', include('accounts.urls')),
    path('doctors/', include('doctors.urls')),
    path('patients/', include('patients.urls')),
    path('bookings/', include('bookings.urls')),

]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
