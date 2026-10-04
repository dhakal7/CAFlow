"""
URL configuration for CAFlow project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Core public and dashboard routes
    path('', include('core.urls')),

    # Auth & accounts
    path('accounts/', include('accounts.urls')),

    # Workspace & Domain Modules
    path('firms/', include('firms.urls')),
    path('clients/', include('clients.urls')),
    path('tasks/', include('tasks.urls')),
    path('documents/', include('documents.urls')),
    path('compliance/', include('compliance.urls')),
    path('calendar/', include('calendar_app.urls')),
    path('messages/', include('messages_app.urls')),
    path('notifications/', include('notifications.urls')),
    path('billing/', include('billing.urls')),
    path('reports/', include('reports.urls')),
    path('audit/', include('audit.urls')),

    # Django Admin
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
