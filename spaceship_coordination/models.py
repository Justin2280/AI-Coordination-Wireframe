"""
Data models for Spaceship Coordination Experiment
"""

import json
from django.db import models
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.signals import post_save
from django.dispatch import receiver

# Constants class
class C:
    name_in_url = 'spaceship_coordination'
    players_per_group = 3
    num_rounds = 6
    
    # oTree expects these in uppercase
    NAME_IN_URL = 'spaceship_coordination'
    PLAYERS_PER_GROUP = 3
    NUM_ROUNDS = 6


class ExperimentSession(models.Model):
    """Main session for the experiment"""
    session_id = models.CharField(max_length=100, unique=True)  # Session identifier
    pressure = models.CharField(max_length=10, choices=[
        ('high', 'High Pressure (90s)'),
        ('low', 'Low Pressure (180s)')
    ])
    complexity = models.CharField(max_length=10, choices=[
        ('high', 'High Complexity (Private Intel)'),
        ('low', 'Low Complexity (Shared Intel)')
    ])
    captain_type = models.CharField(max_length=10, choices=[
        ('human', 'Human Captain'),
        ('llm', 'LLM Captain')
    ])
    seed = models.IntegerField(help_text="Random seed for this session")
    created_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'experiment_session'
    
    def create_default_setup(self):
        """Create default asteroids and crew for this session"""
        from django.utils import timezone
        import random
        
        # Set random seed for this session
        if not self.seed:
            self.seed = random.randint(1, 999999)
            self.save()
        
        # Create default asteroids
        default_asteroids = [
            {'name': 'Alpha', 'max_minerals': 128, 'shallow_cost': 2, 'deep_cost': 3, 'travel_cost': 1},
            {'name': 'Beta', 'max_minerals': 105, 'shallow_cost': 1, 'deep_cost': 3, 'travel_cost': 2},
            {'name': 'Gamma', 'max_minerals': 94, 'shallow_cost': 2, 'deep_cost': 4, 'travel_cost': 3},
            {'name': 'Omega', 'max_minerals': 140, 'shallow_cost': 2, 'deep_cost': 2, 'travel_cost': 3}
        ]
        
        for asteroid_data in default_asteroids:
            Asteroid.objects.create(
                session=self,
                **asteroid_data
            )
        
        # Create default crew
        crew = Crew.objects.create(
            session=self,
            room_id=f"crew_{self.session_id}",
            current_system='Alpha',
            current_round=0,
            current_stage='waiting'
        )
        
        return crew
    
    def reset_to_default(self):
        """Reset session to default state"""
        # Delete all existing data
        self.crew_set.all().delete()
        self.asteroid_set.all().delete()
        self.participant_set.all().delete()
        
        # Reset session state
        self.completed = False
        self.save()
        
        # Recreate default setup
        return self.create_default_setup()
    
    def __str__(self):
        return f"Session {self.session_id} - {self.pressure}/{self.complexity}/{self.captain_type}"


class Crew(models.Model):
    """Crew/room for a group of participants"""
    session = models.ForeignKey(ExperimentSession, on_delete=models.CASCADE)
    room_id = models.CharField(max_length=50, unique=True)
    captain = models.ForeignKey('Participant', on_delete=models.SET_NULL, null=True, blank=True, related_name='captain_crews')
    navigator = models.ForeignKey('Participant', on_delete=models.SET_NULL, null=True, blank=True, related_name='navigator_crews')
    driller = models.ForeignKey('Participant', on_delete=models.SET_NULL, null=True, blank=True, related_name='driller_crews')
    current_system = models.CharField(max_length=20, default='Alpha')
    current_round = models.IntegerField(default=0)
    current_stage = models.CharField(max_length=20, default='waiting', choices=[
        ('waiting', 'Waiting for Crew'),
        ('briefing', 'Briefing'),
        ('action', 'Action'),
        ('result', 'Result'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ])
    stage_start_time = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'crew'


class Participant(models.Model):
    """Extended participant model for the experiment"""
    participant_id = models.CharField(max_length=100, unique=True)  # Participant identifier
    prolific_id = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=20, choices=[
        ('captain', 'Captain'),
        ('navigator', 'Navigator'),
        ('driller', 'Driller')
    ])
    crew = models.ForeignKey(Crew, on_delete=models.CASCADE, null=True, blank=True)
    consent_given = models.BooleanField(default=False)
    consent_timestamp = models.DateTimeField(null=True, blank=True)
    comprehension_correct = models.BooleanField(null=True, blank=True)
    comprehension_first_try = models.BooleanField(null=True, blank=True)
    survey_completed = models.BooleanField(default=False)
    bonus_amount = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'experiment_participant'


class Asteroid(models.Model):
    """Asteroid information and state"""
    name = models.CharField(max_length=20, choices=[
        ('Alpha', 'Alpha'),
        ('Beta', 'Beta'),
        ('Gamma', 'Gamma'),
        ('Omega', 'Omega')
    ])
    max_minerals = models.IntegerField(help_text="Maximum minerals available")
    shallow_cost = models.IntegerField(help_text="Cost to mine shallow")
    deep_cost = models.IntegerField(help_text="Cost to mine deep")
    travel_cost = models.IntegerField(help_text="Cost to travel to this asteroid")
    discovered_by = models.ForeignKey(Participant, on_delete=models.SET_NULL, null=True, blank=True)
    discovered_round = models.IntegerField(null=True, blank=True)
    mined = models.BooleanField(default=False)
    mined_round = models.IntegerField(null=True, blank=True)
    session = models.ForeignKey(ExperimentSession, on_delete=models.CASCADE)
    
    class Meta:
        db_table = 'asteroid'
        unique_together = ['name', 'session']


class RoundState(models.Model):
    """State of the game for each round"""
    crew = models.ForeignKey(Crew, on_delete=models.CASCADE)
    round_number = models.IntegerField()
    stage = models.CharField(max_length=20, choices=[
        ('briefing', 'Briefing'),
        ('action', 'Action'),
        ('result', 'Result')
    ])
    stage_start_time = models.DateTimeField(auto_now_add=True)
    pu_remaining = models.IntegerField()
    current_system = models.CharField(max_length=20)
    briefing_time_remaining = models.IntegerField(null=True, blank=True)
    action_time_remaining = models.IntegerField(null=True, blank=True)
    result_time_remaining = models.IntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'round_state'
        unique_together = ['crew', 'round_number']


class Action(models.Model):
    """Actions taken by participants"""
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    round_state = models.ForeignKey(RoundState, on_delete=models.CASCADE)
    action_type = models.CharField(max_length=20, choices=[
        ('do_nothing', 'Do Nothing'),
        ('travel', 'Travel'),
        ('send_probe', 'Send Probe'),
        ('mine_shallow', 'Mine Shallow'),
        ('mine_deep', 'Mine Deep'),
        ('deploy_robot', 'Deploy Robot')
    ])
    target_asteroid = models.CharField(max_length=20, null=True, blank=True)
    pu_spent = models.IntegerField(default=0)
    auto_do_nothing = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'action'


class Outcome(models.Model):
    """Mining outcomes and results"""
    round_state = models.ForeignKey(RoundState, on_delete=models.CASCADE)
    asteroid = models.ForeignKey(Asteroid, on_delete=models.CASCADE)
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    action = models.ForeignKey(Action, on_delete=models.CASCADE)
    minerals_gained = models.IntegerField()
    full_extraction = models.BooleanField()
    partial_fraction = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    probability_basis = models.JSONField(encoder=DjangoJSONEncoder)
    depth = models.CharField(max_length=10, choices=[
        ('shallow', 'Shallow'),
        ('deep', 'Deep')
    ])
    intel_combo = models.CharField(max_length=20, choices=[
        ('none', 'No Intel'),
        ('probe_only', 'Probe Only'),
        ('robot_only', 'Robot Only'),
        ('probe_plus_robot', 'Probe + Robot')
    ])
    
    class Meta:
        db_table = 'outcome'


class ChatMessage(models.Model):
    """Chat messages between participants"""
    from_participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='sent_messages')
    to_participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='received_messages', null=True, blank=True)
    round_state = models.ForeignKey(RoundState, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    stage_only = models.CharField(max_length=20, default='briefing')
    
    @property
    def is_broadcast(self):
        """Check if this message is visible to all team members"""
        return self.to_participant is None
    
    class Meta:
        db_table = 'chat_message'


class AnalyticsSnapshot(models.Model):
    """Analytics data for charts and tables"""
    crew = models.ForeignKey(Crew, on_delete=models.CASCADE)
    round_number = models.IntegerField()
    cumulative_minerals = models.IntegerField()
    cumulative_pu_team = models.IntegerField()
    cumulative_pu_captain = models.IntegerField()
    cumulative_pu_navigator = models.IntegerField()
    cumulative_pu_driller = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'analytics_snapshot'
        unique_together = ['crew', 'round_number']


class Survey(models.Model):
    """Debrief survey responses"""
    participant = models.OneToOneField(Participant, on_delete=models.CASCADE)
    difficulty_rating = models.IntegerField(choices=[(i, i) for i in range(1, 8)])
    gender = models.CharField(max_length=20, choices=[
        ('female', 'Female'),
        ('male', 'Male'),
        ('other', 'Other')
    ])
    gender_other = models.CharField(max_length=100, blank=True)
    age = models.IntegerField(choices=[(i, i) for i in range(18, 66)])
    education = models.JSONField(encoder=DjangoJSONEncoder, help_text="List of selected education options")
    employment_status = models.CharField(max_length=30, choices=[
        ('self_employed', 'Self-employed'),
        ('employed_full_time', 'Employed full time'),
        ('employed_part_time', 'Employed part time'),
        ('unemployed_looking', 'Unemployed looking'),
        ('unemployed_not_looking', 'Unemployed not looking'),
        ('retired', 'Retired'),
        ('student', 'Student'),
        ('unable_to_work', 'Unable to work')
    ])
    industry = models.CharField(max_length=100)
    years_experience = models.IntegerField()
    job_title = models.CharField(max_length=200)
    annual_income = models.CharField(max_length=50)
    open_comments = models.TextField(blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'survey'


class SystemEvent(models.Model):
    """System events like disconnects, cancellations, etc."""
    crew = models.ForeignKey(Crew, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=30, choices=[
        ('disconnect', 'Participant Disconnected'),
        ('reconnect', 'Participant Reconnected'),
        ('cancel', 'Session Cancelled'),
        ('timeout', 'Action Timeout'),
        ('grace_period_start', 'Grace Period Started'),
        ('grace_period_end', 'Grace Period Ended')
    ])
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, null=True, blank=True)
    details = models.JSONField(encoder=DjangoJSONEncoder, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'system_event'


class IntelVisibility(models.Model):
    """Track intel visibility for audit purposes"""
    round_state = models.ForeignKey(RoundState, on_delete=models.CASCADE)
    asteroid = models.ForeignKey(Asteroid, on_delete=models.CASCADE)
    intel_type = models.CharField(max_length=20, choices=[
        ('max_minerals', 'Max Minerals'),
        ('shallow_cost', 'Shallow Mining Cost'),
        ('deep_cost', 'Deep Mining Cost')
    ])
    visible_to_participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    discovered_round = models.IntegerField()
    visibility_footprint = models.JSONField(encoder=DjangoJSONEncoder, help_text="JSON audit trail")
    
    class Meta:
        db_table = 'intel_visibility'
        unique_together = ['round_state', 'asteroid', 'intel_type', 'visible_to_participant']


# Signals
@receiver(post_save, sender=ExperimentSession)
def create_default_setup_on_save(sender, instance, created, **kwargs):
    """Automatically create default setup when a new ExperimentSession is created"""
    if created:
        try:
            instance.create_default_setup()
        except Exception as e:
            # Log the error but don't fail the save
            print(f"Error creating default setup for session {instance.session_id}: {str(e)}")


