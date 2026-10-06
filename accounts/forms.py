import secrets
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from firms.models import Firm, FirmMembership, FirmRole, MembershipStatus

User = get_user_model()


class LoginForm(forms.Form):
    """Clean, secure login form using email as identifier."""
    email = forms.EmailField(
        label=_("Official Work Email"),
        widget=forms.EmailInput(attrs={
            'class': 'cf-input',
            'placeholder': 'partner@firm.com.np',
            'autocomplete': 'email',
            'autofocus': 'autofocus',
        })
    )
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={
            'class': 'cf-input',
            'placeholder': '••••••••••••',
            'autocomplete': 'current-password',
        })
    )
    remember_me = forms.BooleanField(
        label=_("Keep me signed in on this device"),
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'cf-checkbox'})
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            email_clean = email.strip().lower()
            user = authenticate(email=email_clean, password=password)
            if user is None:
                # Check if user exists but is inactive
                user_exists = User.objects.filter(email__iexact=email_clean).first()
                if user_exists and not user_exists.is_active:
                    raise ValidationError(_("This account has been deactivated. Please contact support or your firm owner."))
                raise ValidationError(_("Invalid email or password. Please verify your credentials."))
            cleaned_data['user'] = user
        return cleaned_data


class FirmRegistrationForm(forms.Form):
    """
    Onboarding registration form for new Chartered Accountant firm practice owners.
    Creates User + Firm + OWNER Membership atomically.
    """
    first_name = forms.CharField(
        label=_("First Name"),
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Suyog'})
    )
    last_name = forms.CharField(
        label=_("Last Name"),
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Dhakal'})
    )
    email = forms.EmailField(
        label=_("Official Work Email"),
        widget=forms.EmailInput(attrs={'class': 'cf-input', 'placeholder': 'suyog@dhakalca.com.np'})
    )
    password = forms.CharField(
        label=_("Create Password"),
        widget=forms.PasswordInput(attrs={'class': 'cf-input', 'placeholder': 'Minimum 8 characters'}),
        help_text=_("Use 8+ characters with a combination of letters and numbers.")
    )
    password_confirm = forms.CharField(
        label=_("Confirm Password"),
        widget=forms.PasswordInput(attrs={'class': 'cf-input', 'placeholder': 'Re-enter your password'})
    )
    firm_name = forms.CharField(
        label=_("CA Practice / Firm Name"),
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Dhakal & Associates, Chartered Accountants'})
    )
    phone = forms.CharField(
        label=_("Contact Phone"),
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'class': 'cf-input', 'placeholder': '+977 9800000000'})
    )
    pan_number = forms.CharField(
        label=_("Firm IRD PAN (Optional)"),
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={'class': 'cf-input', 'placeholder': '9-digit PAN (e.g. 600123456)'})
    )
    city = forms.CharField(
        label=_("City / Municipality"),
        max_length=100,
        required=False,
        initial='Kathmandu',
        widget=forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Kathmandu'})
    )
    address = forms.CharField(
        label=_("Office Address"),
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Putalisadak, Ward 28'})
    )
    terms_accepted = forms.BooleanField(
        label=_("I agree to the CAFlow Terms of Service, Confidentiality, and ICAN Compliance Standards"),
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'cf-checkbox'})
    )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("An account with this email already exists. Please sign in instead."))
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm:
            if password != password_confirm:
                self.add_error('password_confirm', _("Passwords do not match."))
            else:
                validate_password(password)

        return cleaned_data


class ForgotPasswordForm(forms.Form):
    """Password reset request form."""
    email = forms.EmailField(
        label=_("Registered Email Address"),
        widget=forms.EmailInput(attrs={
            'class': 'cf-input',
            'placeholder': 'partner@firm.com.np',
            'autofocus': 'autofocus',
        })
    )


class ResetPasswordForm(forms.Form):
    """Password reset confirmation form."""
    new_password = forms.CharField(
        label=_("New Password"),
        widget=forms.PasswordInput(attrs={'class': 'cf-input', 'placeholder': '••••••••••••'}),
        help_text=_("Must be at least 8 characters long.")
    )
    new_password_confirm = forms.CharField(
        label=_("Confirm New Password"),
        widget=forms.PasswordInput(attrs={'class': 'cf-input', 'placeholder': '••••••••••••'})
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('new_password')
        p2 = cleaned_data.get('new_password_confirm')

        if p1 and p2:
            if p1 != p2:
                self.add_error('new_password_confirm', _("Passwords do not match."))
            else:
                validate_password(p1)

        return cleaned_data


class UserProfileForm(forms.ModelForm):
    """Profile edit form for authenticated users."""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'ican_membership_no', 'profile_photo']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'cf-input'}),
            'last_name': forms.TextInput(attrs={'class': 'cf-input'}),
            'phone': forms.TextInput(attrs={'class': 'cf-input'}),
            'ican_membership_no': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'FCA-1234 or ACA-5678'}),
            'profile_photo': forms.FileInput(attrs={'class': 'cf-input'}),
        }


class ChangePasswordForm(forms.Form):
    """In-app password change form for authenticated users."""
    current_password = forms.CharField(
        label=_("Current Password"),
        widget=forms.PasswordInput(attrs={'class': 'cf-input', 'placeholder': '••••••••••••'})
    )
    new_password = forms.CharField(
        label=_("New Password"),
        widget=forms.PasswordInput(attrs={'class': 'cf-input', 'placeholder': '••••••••••••'})
    )
    new_password_confirm = forms.CharField(
        label=_("Confirm New Password"),
        widget=forms.PasswordInput(attrs={'class': 'cf-input', 'placeholder': '••••••••••••'})
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        current_password = self.cleaned_data['current_password']
        if not self.user.check_password(current_password):
            raise ValidationError(_("Your current password was entered incorrectly."))
        return current_password

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('new_password')
        p2 = cleaned_data.get('new_password_confirm')

        if p1 and p2:
            if p1 != p2:
                self.add_error('new_password_confirm', _("Passwords do not match."))
            else:
                validate_password(p1, self.user)

        return cleaned_data
