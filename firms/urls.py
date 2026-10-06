from django.urls import path
from firms import views

app_name = 'firms'

urlpatterns = [
    path('no-workspace/', views.NoFirmView.as_view(), name='no_firm'),
    path('create/', views.FirmCreateView.as_view(), name='create_firm'),
    path('settings/', views.FirmSettingsView.as_view(), name='firm_settings'),
    path('switch/<uuid:firm_id>/', views.SwitchFirmView.as_view(), name='switch_firm'),
    path('team/', views.TeamListView.as_view(), name='team_list'),
    path('team/invite/', views.TeamInviteView.as_view(), name='team_invite'),
    path('team/change-role/<uuid:membership_id>/', views.TeamChangeRoleView.as_view(), name='team_change_role'),
    path('team/deactivate/<uuid:membership_id>/', views.TeamDeactivateMemberView.as_view(), name='team_deactivate'),
    path('team/reactivate/<uuid:membership_id>/', views.TeamReactivateMemberView.as_view(), name='team_reactivate'),
    path('team/revoke-invite/<uuid:invitation_id>/', views.TeamRevokeInviteView.as_view(), name='team_revoke_invite'),
    path('invitations/accept/<str:token>/', views.AcceptInvitationView.as_view(), name='accept_invitation'),
]

