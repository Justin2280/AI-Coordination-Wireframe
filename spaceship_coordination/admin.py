"""
Django admin configuration for Spaceship Coordination Experiment
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import *
from datetime import datetime


@admin.register(ExperimentSession)
class ExperimentSessionAdmin(admin.ModelAdmin):
    """Admin interface for experiment sessions"""
    list_display = ['id', 'session_id', 'pressure', 'complexity', 'captain_type', 'seed', 'created_at', 'completed']
    list_filter = ['pressure', 'complexity', 'captain_type', 'completed', 'created_at']
    search_fields = ['session_id', 'seed']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Session Information', {
            'fields': ('session_id', 'pressure', 'complexity', 'captain_type', 'seed')
        }),
        ('Status', {
            'fields': ('completed', 'created_at')
        }),
    )


@admin.register(Crew)
class CrewAdmin(admin.ModelAdmin):
    """Admin interface for crews"""
    list_display = ['id', 'room_id', 'current_round', 'current_stage', 'current_system', 'created_at', 'get_participants']
    list_filter = ['current_stage', 'current_system', 'created_at']
    search_fields = ['room_id']
    readonly_fields = ['created_at', 'stage_start_time']
    
    def get_participants(self, obj):
        """Display participant roles"""
        participants = []
        if obj.captain:
            participants.append(f"Captain: {obj.captain.role}")
        if obj.navigator:
            participants.append(f"Navigator: {obj.navigator.role}")
        if obj.driller:
            participants.append(f"Driller: {obj.driller.role}")
        return ", ".join(participants)
    get_participants.short_description = 'Participants'
    
    fieldsets = (
        ('Crew Information', {
            'fields': ('session', 'room_id', 'current_round', 'current_stage', 'current_system')
        }),
        ('Participants', {
            'fields': ('captain', 'navigator', 'driller')
        }),
        ('Timing', {
            'fields': ('stage_start_time', 'created_at')
        }),
    )


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    """Admin interface for participants"""
    list_display = ['id', 'participant_id', 'role', 'crew', 'consent_given', 'comprehension_correct', 'survey_completed', 'bonus_amount']
    list_filter = ['role', 'consent_given', 'comprehension_correct', 'survey_completed', 'created_at']
    search_fields = ['participant_id', 'prolific_id']
    readonly_fields = ['created_at', 'consent_timestamp']
    
    fieldsets = (
        ('Participant Information', {
            'fields': ('participant_id', 'prolific_id', 'role', 'crew')
        }),
        ('Consent & Comprehension', {
            'fields': ('consent_given', 'consent_timestamp', 'comprehension_correct', 'comprehension_first_try')
        }),
        ('Study Progress', {
            'fields': ('survey_completed', 'bonus_amount')
        }),
        ('Timing', {
            'fields': ('created_at',)
        }),
    )


@admin.register(Asteroid)
class AsteroidAdmin(admin.ModelAdmin):
    """Admin interface for asteroids"""
    list_display = ['name', 'session', 'max_minerals', 'shallow_cost', 'deep_cost', 'travel_cost', 'mined', 'discovered_by', 'discovered_round']
    list_filter = ['name', 'mined', 'discovered_round', 'session']
    search_fields = ['name', 'session__id']
    readonly_fields = ['discovered_round', 'mined_round']
    
    fieldsets = (
        ('Asteroid Properties', {
            'fields': ('name', 'session', 'max_minerals', 'shallow_cost', 'deep_cost', 'travel_cost')
        }),
        ('Discovery Status', {
            'fields': ('discovered_by', 'discovered_round')
        }),
        ('Mining Status', {
            'fields': ('mined', 'mined_round')
        }),
    )


@admin.register(RoundState)
class RoundStateAdmin(admin.ModelAdmin):
    """Admin interface for round states"""
    list_display = ['id', 'crew', 'round_number', 'stage', 'pu_remaining', 'current_system', 'stage_start_time']
    list_filter = ['stage', 'round_number', 'stage_start_time']
    search_fields = ['crew__room_id']
    readonly_fields = ['stage_start_time']
    
    fieldsets = (
        ('Round Information', {
            'fields': ('crew', 'round_number', 'stage', 'current_system')
        }),
        ('Resources', {
            'fields': ('pu_remaining',)
        }),
        ('Timing', {
            'fields': ('stage_start_time', 'briefing_time_remaining', 'action_time_remaining', 'result_time_remaining')
        }),
    )


@admin.register(Action)
class ActionAdmin(admin.ModelAdmin):
    """Admin interface for actions"""
    list_display = ['id', 'participant', 'round_state', 'action_type', 'target_asteroid', 'pu_spent', 'auto_do_nothing', 'timestamp']
    list_filter = ['action_type', 'auto_do_nothing', 'timestamp']
    search_fields = ['participant__otree_participant__code', 'target_asteroid']
    readonly_fields = ['timestamp']
    
    fieldsets = (
        ('Action Details', {
            'fields': ('participant', 'round_state', 'action_type', 'target_asteroid')
        }),
        ('Costs', {
            'fields': ('pu_spent', 'auto_do_nothing')
        }),
        ('Timing', {
            'fields': ('timestamp',)
        }),
    )


@admin.register(Outcome)
class OutcomeAdmin(admin.ModelAdmin):
    """Admin interface for outcomes"""
    list_display = ['id', 'round_state', 'asteroid', 'participant', 'minerals_gained', 'full_extraction', 'depth', 'intel_combo']
    list_filter = ['full_extraction', 'depth', 'intel_combo', 'round_state__round_number']
    search_fields = ['asteroid__name', 'participant__otree_participant__code']
    
    fieldsets = (
        ('Outcome Details', {
            'fields': ('round_state', 'asteroid', 'participant', 'action')
        }),
        ('Results', {
            'fields': ('minerals_gained', 'full_extraction', 'partial_fraction', 'depth')
        }),
        ('Probability Basis', {
            'fields': ('probability_basis', 'intel_combo')
        }),
    )


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """Admin interface for chat messages"""
    list_display = ['id', 'from_participant', 'to_participant', 'round_state', 'message_preview', 'stage_only', 'timestamp']
    list_filter = ['stage_only', 'timestamp']
    search_fields = ['message', 'from_participant__otree_participant__code', 'to_participant__otree_participant__code']
    readonly_fields = ['timestamp']
    
    def message_preview(self, obj):
        """Show message preview"""
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    message_preview.short_description = 'Message Preview'
    
    fieldsets = (
        ('Message Details', {
            'fields': ('from_participant', 'to_participant', 'round_state', 'message')
        }),
        ('Context', {
            'fields': ('stage_only', 'timestamp')
        }),
    )


@admin.register(AnalyticsSnapshot)
class AnalyticsSnapshotAdmin(admin.ModelAdmin):
    """Admin interface for analytics snapshots"""
    list_display = ['id', 'crew', 'round_number', 'cumulative_minerals', 'cumulative_pu_team', 'timestamp']
    list_filter = ['round_number', 'timestamp']
    search_fields = ['crew__room_id']
    readonly_fields = ['timestamp']
    
    fieldsets = (
        ('Snapshot Information', {
            'fields': ('crew', 'round_number')
        }),
        ('Cumulative Values', {
            'fields': ('cumulative_minerals', 'cumulative_pu_team', 'cumulative_pu_captain', 'cumulative_pu_navigator', 'cumulative_pu_driller')
        }),
        ('Timing', {
            'fields': ('timestamp',)
        }),
    )


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    """Admin interface for surveys"""
    list_display = ['id', 'participant', 'difficulty_rating', 'gender', 'age', 'employment_status', 'industry', 'completed_at']
    list_filter = ['difficulty_rating', 'gender', 'employment_status', 'completed_at']
    search_fields = ['participant__otree_participant__code', 'job_title']
    readonly_fields = ['completed_at']
    
    fieldsets = (
        ('Participant', {
            'fields': ('participant',)
        }),
        ('Difficulty Rating', {
            'fields': ('difficulty_rating',)
        }),
        ('Demographics', {
            'fields': ('gender', 'gender_other', 'age', 'education', 'employment_status')
        }),
        ('Professional Information', {
            'fields': ('industry', 'years_experience', 'job_title', 'annual_income')
        }),
        ('Comments', {
            'fields': ('open_comments',)
        }),
        ('Timing', {
            'fields': ('completed_at',)
        }),
    )


@admin.register(SystemEvent)
class SystemEventAdmin(admin.ModelAdmin):
    """Admin interface for system events"""
    list_display = ['id', 'crew', 'event_type', 'participant', 'timestamp', 'details_preview']
    list_filter = ['event_type', 'timestamp']
    search_fields = ['crew__room_id', 'participant__otree_participant__code']
    readonly_fields = ['timestamp']
    
    def details_preview(self, obj):
        """Show details preview"""
        if obj.details:
            details_str = str(obj.details)
            return details_str[:50] + "..." if len(details_str) > 50 else details_str
        return "No details"
    details_preview.short_description = 'Details Preview'
    
    fieldsets = (
        ('Event Information', {
            'fields': ('crew', 'event_type', 'participant')
        }),
        ('Details', {
            'fields': ('details', 'timestamp')
        }),
    )


@admin.register(IntelVisibility)
class IntelVisibilityAdmin(admin.ModelAdmin):
    """Admin interface for intel visibility tracking"""
    list_display = ['id', 'round_state', 'asteroid', 'intel_type', 'visible_to_participant', 'discovered_round']
    list_filter = ['intel_type', 'discovered_round']
    search_fields = ['asteroid__name', 'visible_to_participant__otree_participant__code']
    
    fieldsets = (
        ('Visibility Information', {
            'fields': ('round_state', 'asteroid', 'intel_type', 'visible_to_participant')
        }),
        ('Discovery', {
            'fields': ('discovered_round', 'visibility_footprint')
        }),
    )


# Custom admin actions
@admin.action(description="Start new round for selected crews")
def start_new_round(modeladmin, request, queryset):
    """Admin action to start a new round for selected crews"""
    from .game_logic import GameEngine
    
    success_count = 0
    for crew in queryset:
        try:
            game_engine = GameEngine(crew)
            next_round = crew.current_round + 1
            if next_round <= 5:
                game_engine.start_round(next_round)
                success_count += 1
        except Exception as e:
            modeladmin.message_user(request, f"Error starting round for crew {crew.id}: {str(e)}")
    
    if success_count > 0:
        modeladmin.message_user(request, f"Successfully started new round for {success_count} crews.")


@admin.action(description="Pause selected crews")
def pause_crews(modeladmin, request, queryset):
    """Admin action to pause selected crews"""
    for crew in queryset:
        try:
            SystemEvent.objects.create(
                crew=crew,
                event_type='pause_round',
                details={'timestamp': datetime.now().isoformat(), 'admin_action': True}
            )
        except Exception as e:
            modeladmin.message_user(request, f"Error pausing crew {crew.id}: {str(e)}")
    
    modeladmin.message_user(request, f"Pause events created for {queryset.count()} crews.")


# Add custom actions to Crew admin
CrewAdmin.actions = [start_new_round, pause_crews]


# Admin site customization
admin.site.site_header = "Spaceship Coordination Experiment Admin"
admin.site.site_title = "Spaceship Coordination Admin"
admin.site.index_title = "Welcome to Spaceship Coordination Experiment Administration"


