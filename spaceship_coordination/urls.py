"""
URL configuration for Spaceship Coordination Experiment
"""

from django.urls import path
from . import views

app_name = 'spaceship_coordination'

urlpatterns = [
    # Main pages
    path('', views.IndexView.as_view(), name='index'),
    path('game/', views.GameView.as_view(), name='game'),
    path('waiting/', views.WaitingRoomView.as_view(), name='waiting_room'),
    path('role-selection/', views.RoleSelectionView.as_view(), name='role_selection'),
    path('cancelled/', views.GameCancelledView.as_view(), name='cancelled'),
    
    # API endpoints
    path('api/crew/<int:crew_id>/status/', views.CrewStatusView.as_view(), name='crew_status'),
    path('api/participant/status/', views.ParticipantStatusView.as_view(), name='participant_status'),
    path('api/crew/<int:crew_id>/actions/', views.ActionSubmitView.as_view(), name='action_submit'),
    path('api/crew/<int:crew_id>/chat/', views.ChatMessageView.as_view(), name='chat_message'),
    path('api/crew/<int:crew_id>/round/<int:round_number>/', views.RoundStatusView.as_view(), name='round_status'),
    path('api/crew/<int:crew_id>/timer-sync/', views.TimerSyncView.as_view(), name='timer_sync'),
    
    # Admin endpoints
    path('admin/crews/', views.AdminCrewListView.as_view(), name='admin_crews'),
    path('admin/crew/<int:crew_id>/', views.AdminCrewDetailView.as_view(), name='admin_crew_detail'),
    path('admin/sessions/', views.AdminSessionListView.as_view(), name='admin_sessions'),
    path('admin/analytics/', views.AdminAnalyticsView.as_view(), name='admin_analytics'),
    
    # Game management
    path('game/start/<int:crew_id>/', views.StartGameView.as_view(), name='start_game'),
    path('game/next-stage/<int:crew_id>/', views.NextStageView.as_view(), name='next_stage'),
    path('game/pause/<int:crew_id>/', views.PauseGameView.as_view(), name='pause_game'),
    
    # Results and analytics
    path('results/<int:crew_id>/', views.GameResultsView.as_view(), name='game_results'),
    path('analytics/<int:crew_id>/', views.CrewAnalyticsView.as_view(), name='crew_analytics'),
    
    # Survey and completion
    path('survey/<int:crew_id>/', views.SurveyView.as_view(), name='survey'),
    path('complete/<int:crew_id>/', views.GameCompleteView.as_view(), name='complete'),
]


