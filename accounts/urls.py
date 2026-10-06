from django.urls import path
from accounts import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='password_reset'),
    path('reset-password/<str:uidb64>/<str:token>/', views.ResetPasswordConfirmView.as_view(), name='password_reset_confirm'),
    path('reset-password/done/', views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('verify-email/<str:token>/', views.VerifyEmailView.as_view(), name='verify_email'),
    path('resend-verification/', views.ResendVerificationEmailView.as_view(), name='resend_verification'),
]
