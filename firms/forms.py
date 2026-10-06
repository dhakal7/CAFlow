from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from firms.models import Firm, FirmRole

User = get_user_model()


class FirmSettingsForm(forms.ModelForm):
    """Firm practice settings and configuration form."""
    class Meta:
        model = Firm
        fields = [
            'name', 'logo', 'email', 'phone', 'address', 'city', 'country',
            'pan_number', 'ican_firm_reg_no', 'currency', 'timezone',
            'current_fiscal_year'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Firm Name'}),
            'email': forms.EmailInput(attrs={'class': 'cf-input', 'placeholder': 'office@firm.com.np'}),
            'phone': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': '+977 1-4XXXXXX'}),
            'address': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Office Address'}),
            'city': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Kathmandu'}),
            'country': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Nepal'}),
            'pan_number': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': '9-digit IRD PAN'}),
            'ican_firm_reg_no': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'ICAN Firm Reg No'}),
            'currency': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'NPR'}),
            'timezone': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Asia/Kathmandu'}),
            'logo': forms.FileInput(attrs={'class': 'cf-input'}),
        }


class FirmCreateForm(forms.ModelForm):
    """Firm practice creation form for authenticated practitioners."""
    class Meta:
        model = Firm
        fields = ['name', 'firm_type', 'pan_number', 'ican_firm_reg_no', 'email', 'phone', 'city', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'e.g. Dhakal & Associates, Chartered Accountants', 'required': 'required'}),
            'firm_type': forms.Select(attrs={'class': 'cf-input'}),
            'pan_number': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': '9-digit IRD PAN'}),
            'ican_firm_reg_no': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'ICAN Firm Registration Number'}),
            'email': forms.EmailInput(attrs={'class': 'cf-input', 'placeholder': 'official@firm.com.np'}),
            'phone': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': '+977 1-4XXXXXX'}),
            'city': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Kathmandu'}),
            'address': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Office Address'}),
        }



class InviteStaffForm(forms.Form):
    """Team member invitation form."""
    email = forms.EmailField(
        label=_("Staff / Member Work Email"),
        widget=forms.EmailInput(attrs={
            'class': 'cf-input',
            'placeholder': 'associate@firm.com.np',
            'required': 'required',
        })
    )
    role = forms.ChoiceField(
        label=_("Assigned Firm Role"),
        choices=[c for c in FirmRole.choices if c[0] != FirmRole.OWNER],
        initial=FirmRole.STAFF,
        widget=forms.Select(attrs={'class': 'cf-input'})
    )


class ChangeMemberRoleForm(forms.Form):
    """Change member role in firm."""
    role = forms.ChoiceField(
        label=_("New Role"),
        choices=[c for c in FirmRole.choices if c[0] != FirmRole.OWNER],
        widget=forms.Select(attrs={'class': 'cf-input'})
    )


class AcceptInvitationRegistrationForm(forms.Form):
    """Account creation for invited staff members."""
    first_name = forms.CharField(
        label=_("First Name"),
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Aayush'})
    )
    last_name = forms.CharField(
        label=_("Last Name"),
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Sharma'})
    )
    phone = forms.CharField(
        label=_("Mobile Number"),
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'class': 'cf-input', 'placeholder': '+977 98XXXXXXXX'})
    )
    password = forms.CharField(
        label=_("Create Password"),
        widget=forms.PasswordInput(attrs={'class': 'cf-input', 'placeholder': '••••••••••••'}),
        help_text=_("Must be at least 8 characters long.")
    )
    password_confirm = forms.CharField(
        label=_("Confirm Password"),
        widget=forms.PasswordInput(attrs={'class': 'cf-input', 'placeholder': '••••••••••••'})
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('password_confirm')
        if p1 and p2:
            if p1 != p2:
                self.add_error('password_confirm', _("Passwords do not match."))
            else:
                validate_password(p1)
        return cleaned_data
