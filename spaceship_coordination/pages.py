"""
oTree pages for Spaceship Coordination Experiment
"""

import json
import random
from datetime import datetime, timedelta
from django.conf import settings
from otree.api import (
    BaseConstants, BaseSubsession, BaseGroup, BasePlayer,
    Currency, currency_range, SubmissionMustFail, Submission, Page
)
from otree.models import Participant
from .models import *
from .game_logic import GameEngine
from .ai_captain import AICaptain


class Constants(BaseConstants):
    name_in_url = 'spaceship_coordination'
    players_per_group = 3
    num_rounds = 6  # Round 0 is training, Rounds 1-5 count for payout


class Subsession(BaseSubsession):
    def creating_session(self):
        """Initialize the experiment session"""
        if self.round_number == 1:
            # Create experiment session with random conditions
            pressure = random.choice(['high', 'low'])
            complexity = random.choice(['high', 'low'])
            captain_type = random.choice(['human', 'llm'])
            seed = random.randint(1, 1000000)
            
            experiment_session = ExperimentSession.objects.create(
                session=self.session,
                pressure=pressure,
                complexity=complexity,
                captain_type=captain_type,
                seed=seed
            )
            
            # Set session variables for oTree
            self.session.vars['pressure'] = pressure
            self.session.vars['complexity'] = complexity
            self.session.vars['captain_type'] = captain_type
            self.session.vars['seed'] = seed
            self.session.vars['experiment_session_id'] = experiment_session.id


class Group(BaseGroup):
    def set_players(self):
        """Set player roles and create crew"""
        if self.round_number == 1:
            # Get experiment session
            experiment_session = ExperimentSession.objects.get(
                id=self.session.vars['experiment_session_id']
            )
            
            # Create crew
            crew = Crew.objects.create(
                session=experiment_session,
                room_id=f"crew_{self.id}_{self.session.id}",
                current_system='Alpha'
            )
            
            # Assign roles randomly
            roles = ['captain', 'navigator', 'driller']
            random.shuffle(roles)
            
            for i, player in enumerate(self.get_players()):
                role = roles[i]
                player.role = role
                player.crew = crew
                
                # Set crew relationships
                if role == 'captain':
                    crew.captain = player
                elif role == 'navigator':
                    crew.navigator = player
                elif role == 'driller':
                    crew.driller = player
                
                player.save()
            
            crew.save()
            
            # Initialize asteroids for this session
            self._initialize_asteroids(experiment_session)
            
            # Set group variables
            self.crew_id = crew.id
            self.current_system = 'Alpha'
            self.current_round = 0
            self.current_stage = 'waiting'
    
    def _initialize_asteroids(self, experiment_session):
        """Initialize asteroids with random values"""
        random.seed(experiment_session.seed)
        
        # Generate random asteroid properties
        asteroid_data = {
            'Alpha': {'max_minerals': random.randint(50, 100), 'shallow_cost': 1, 'deep_cost': 2, 'travel_cost': 0},
            'Beta': {'max_minerals': random.randint(60, 120), 'shallow_cost': random.randint(1, 3), 'deep_cost': random.randint(2, 4), 'travel_cost': 1},
            'Gamma': {'max_minerals': random.randint(70, 140), 'shallow_cost': random.randint(1, 3), 'deep_cost': random.randint(2, 4), 'travel_cost': 2},
            'Omega': {'max_minerals': random.randint(80, 160), 'shallow_cost': random.randint(1, 3), 'deep_cost': random.randint(2, 4), 'travel_cost': 3}
        }
        
        for name, data in asteroid_data.items():
            Asteroid.objects.create(
                name=name,
                max_minerals=data['max_minerals'],
                shallow_cost=data['shallow_cost'],
                deep_cost=data['deep_cost'],
                travel_cost=data['travel_cost'],
                session=experiment_session
            )


class Player(BasePlayer):
    # Player fields
    role = models.CharField()
    crew_id = models.IntegerField()
    current_system = models.CharField()
    current_round = models.IntegerField()
    current_stage = models.CharField()
    
    # Consent and comprehension
    consent_given = models.BooleanField(default=False)
    comprehension_answer = models.CharField(max_length=500)
    comprehension_correct = models.BooleanField()
    comprehension_first_try = models.BooleanField()
    
    # Game state
    pu_remaining = models.IntegerField(default=4)
    action_submitted = models.BooleanField(default=False)
    action_type = models.CharField(max_length=50, blank=True)
    target_asteroid = models.CharField(max_length=50, blank=True)
    pu_spent = models.IntegerField(default=0)
    
    # Survey responses
    difficulty_rating = models.IntegerField(
        choices=[(i, str(i)) for i in range(1, 8)],
        blank=True
    )
    gender = models.CharField(
        max_length=20,
        choices=[('female', 'Female'), ('male', 'Male'), ('other', 'Other')],
        blank=True
    )
    gender_other = models.CharField(max_length=100, blank=True)
    age = models.IntegerField(
        choices=[(i, str(i)) for i in range(18, 66)],
        blank=True
    )
    education = models.CharField(max_length=500, blank=True)  # JSON string
    employment_status = models.CharField(
        max_length=50,
        choices=[
            ('self_employed', 'Self-employed'),
            ('employed_full_time', 'Employed full-time'),
            ('employed_part_time', 'Employed part-time'),
            ('unemployed_looking', 'Unemployed, looking for work'),
            ('unemployed_not_looking', 'Unemployed, not looking for work'),
            ('retired', 'Retired'),
            ('student', 'Student'),
            ('unable_to_work', 'Unable to work')
        ],
        blank=True
    )
    industry = models.CharField(max_length=100, blank=True)
    years_experience = models.IntegerField(blank=True)
    job_title = models.CharField(max_length=100, blank=True)
    annual_income = models.CharField(max_length=50, blank=True)
    open_comments = models.TextField(blank=True)
    
    # Results
    final_mineral_points = models.IntegerField(default=0)
    total_pu_used = models.IntegerField(default=0)
    bonus_amount = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    
    def role_(self):
        return self.role
    
    def is_captain(self):
        return self.role == 'captain'
    
    def is_navigator(self):
        return self.role == 'navigator'
    
    def is_driller(self):
        return self.role == 'driller'
    
    def get_crew(self):
        return Crew.objects.get(id=self.crew_id)
    
    def get_crew_members(self):
        crew = self.get_crew()
        return {
            'captain': crew.captain,
            'navigator': crew.navigator,
            'driller': crew.driller
        }
    
    def get_visible_asteroids(self):
        """Get asteroids visible to this player based on complexity"""
        crew = self.get_crew()
        experiment_session = crew.session
        
        if experiment_session.complexity == 'low':
            # Low complexity: all discovered intel is shared
            return self._get_all_asteroid_info()
        else:
            # High complexity: only show intel discovered by this player
            return self._get_private_asteroid_info()
    
    def _get_all_asteroid_info(self):
        """Get all asteroid information (low complexity)"""
        crew = self.get_crew()
        asteroids = Asteroid.objects.filter(session=crew.session)
        
        asteroid_info = []
        for asteroid in asteroids:
            info = {
                'name': asteroid.name,
                'travel_cost': asteroid.travel_cost,
                'max_minerals': None,
                'shallow_cost': None,
                'deep_cost': None,
                'mined': asteroid.mined,
                'auto_populated': False
            }
            
            # Check if intel has been discovered
            if asteroid.discovered_by:
                info['max_minerals'] = asteroid.max_minerals
                info['auto_populated'] = True
            
            # Check if robot has been deployed
            robot_actions = Action.objects.filter(
                round_state__crew=crew,
                action_type='deploy_robot',
                target_asteroid=asteroid.name
            ).exists()
            
            if robot_actions:
                info['shallow_cost'] = asteroid.shallow_cost
                info['deep_cost'] = asteroid.deep_cost
                info['auto_populated'] = True
            
            asteroid_info.append(info)
        
        return asteroid_info
    
    def _get_private_asteroid_info(self):
        """Get private asteroid information (high complexity)"""
        crew = self.get_crew()
        asteroids = Asteroid.objects.filter(session=crew.session)
        
        asteroid_info = []
        for asteroid in asteroids:
            info = {
                'name': asteroid.name,
                'travel_cost': asteroid.travel_cost,
                'max_minerals': None,
                'shallow_cost': None,
                'deep_cost': None,
                'mined': asteroid.mined,
                'auto_populated': False
            }
            
            # Only show intel if this player discovered it
            if asteroid.discovered_by == self:
                info['max_minerals'] = asteroid.max_minerals
            
            # Only show costs if this player deployed a robot
            robot_actions = Action.objects.filter(
                round_state__crew=crew,
                action_type='deploy_robot',
                target_asteroid=asteroid.name,
                participant=self
            ).exists()
            
            if robot_actions:
                info['shallow_cost'] = asteroid.shallow_cost
                info['deep_cost'] = asteroid.deep_cost
            
            asteroid_info.append(info)
        
        return asteroid_info


# Page classes
class ConsentPage(Page):
    """Information and consent page"""
    form_model = 'player'
    form_fields = ['consent_given']
    
    def is_displayed(self):
        return self.round_number == 1
    
    def before_next_page(self):
        if self.player.consent_given:
            self.player.consent_timestamp = datetime.now()
            self.player.save()


class StudyOverviewPage(Page):
    """Study overview and payment information"""
    form_model = 'player'
    form_fields = ['comprehension_answer']
    
    def is_displayed(self):
        return self.round_number == 1 and self.player.consent_given
    
    def error_message(self, values):
        if values['comprehension_answer'] != 'guaranteed_plus_same_bonus':
            return 'Incorrect answer. Please try again.'
    
    def before_next_page(self):
        # Log comprehension result
        self.player.comprehension_correct = True
        self.player.comprehension_first_try = True  # This would need more logic to track first try
        self.player.save()


class WaitingRoomPage(Page):
    """Waiting room until crew is formed"""
    timeout_seconds = 300  # 5 minutes max wait
    
    def is_displayed(self):
        return self.round_number == 1 and self.player.comprehension_correct
    
    def vars_for_template(self):
        return {
            'role': self.player.role,
            'crew_id': self.player.crew_id
        }


class GamePage(Page):
    """Main game page with real-time updates"""
    timeout_seconds = 300  # 5 minutes max per round
    
    def is_displayed(self):
        return self.round_number >= 1
    
    def vars_for_template(self):
        crew = self.player.get_crew()
        return {
            'role': self.player.role,
            'round_number': self.round_number,
            'current_stage': crew.current_stage,
            'current_system': crew.current_system,
            'pu_remaining': self.player.pu_remaining,
            'asteroids': self.player.get_visible_asteroids(),
            'is_training': self.round_number == 0,
            'crew_id': self.player.crew_id
        }


class SurveyPage(Page):
    """Debrief survey page"""
    form_model = 'player'
    form_fields = [
        'difficulty_rating', 'gender', 'gender_other', 'age', 'education',
        'employment_status', 'industry', 'years_experience', 'job_title',
        'annual_income', 'open_comments'
    ]
    
    def is_displayed(self):
        return self.round_number == Constants.num_rounds
    
    def before_next_page(self):
        # Save survey to database
        survey_data = {
            'difficulty_rating': self.player.difficulty_rating,
            'gender': self.player.gender,
            'gender_other': self.player.gender_other,
            'age': self.player.age,
            'education': self.player.education,
            'employment_status': self.player.employment_status,
            'industry': self.player.industry,
            'years_experience': self.player.years_experience,
            'job_title': self.player.job_title,
            'annual_income': self.player.annual_income,
            'open_comments': self.player.open_comments
        }
        
        Survey.objects.create(
            participant=self.player,
            **survey_data
        )
        
        self.player.survey_completed = True
        self.player.save()


class FinalResultPage(Page):
    """Final game results and bonus calculation"""
    def is_displayed(self):
        return self.round_number == Constants.num_rounds and self.player.survey_completed
    
    def vars_for_template(self):
        # Calculate final results
        crew = self.player.get_crew()
        
        # Get cumulative data
        analytics = AnalyticsSnapshot.objects.filter(crew=crew).order_by('round_number')
        
        mineral_points = []
        pu_used = []
        
        for analytic in analytics:
            mineral_points.append(analytic.cumulative_minerals)
            pu_used.append(analytic.cumulative_pu_team)
        
        # Calculate bonus (simplified formula)
        final_minerals = mineral_points[-1] if mineral_points else 0
        total_pu = pu_used[-1] if pu_used else 0
        
        bonus = max(0, (final_minerals * 0.1) - (total_pu * 0.05))
        bonus = min(bonus, 3.00)  # Cap at £3.00
        
        self.player.final_mineral_points = final_minerals
        self.player.total_pu_used = total_pu
        self.player.bonus_amount = bonus
        self.player.save()
        
        return {
            'final_minerals': final_minerals,
            'total_pu': total_pu,
            'bonus': bonus,
            'mineral_points_chart': mineral_points,
            'pu_used_chart': pu_used
        }


class StudyCompletedPage(Page):
    """Study completion and Prolific redirect"""
    def is_displayed(self):
        return self.round_number == Constants.num_rounds and self.player.survey_completed
    
    def vars_for_template(self):
        return {
            'final_minerals': self.player.final_mineral_points,
            'total_pu': self.player.total_pu_used,
            'bonus': self.player.bonus_amount,
            'prolific_completion_url': 'https://app.prolific.co/submissions/complete?cc=XXXXX'
        }


# Page sequence
page_sequence = [
    ConsentPage,
    StudyOverviewPage,
    WaitingRoomPage,
    GamePage,
    SurveyPage,
    FinalResultPage,
    StudyCompletedPage,
]


