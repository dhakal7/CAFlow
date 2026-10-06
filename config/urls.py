"""
URL configuration for CAFlow project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from accounts import views as account_views
from firms import views as firm_views

urlpatterns = [
    # Top-level direct entrypoints requested by CAFlow specification
    path('login/', account_views.LoginView.as_view(), name='top_login'),
    path('register/', account_views.RegisterView.as_view(), name='top_register'),
    path('logout/', account_views.LogoutView.as_view(), name='top_logout'),
    path('forgot-password/', account_views.ForgotPasswordView.as_view(), name='top_forgot_password'),
    path('reset-password/<str:uidb64>/<str:token>/', account_views.ResetPasswordConfirmView.as_view(), name='top_reset_password'),
    path('verify-email/<str:token>/', account_views.VerifyEmailView.as_view(), name='top_verify_email'),
    path('profile/', account_views.ProfileView.as_view(), name='top_profile'),
    path('team/', firm_views.TeamListView.as_view(), name='top_team'),
    path('firm/settings/', firm_views.FirmSettingsView.as_view(), name='top_firm_settings'),
    path('invitations/accept/<str:token>/', firm_views.AcceptInvitationView.as_view(), name='top_accept_invitation'),

    # Core public and dashboard routes
    path('', include('core.urls')),

    # Auth & accounts namespace
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
