"""
Game logic engine for Spaceship Coordination Experiment
"""

import random
import json
from datetime import datetime, timedelta
from django.conf import settings
from django.db import transaction
from .models import *


class GameEngine:
    """Main game engine for managing rounds, actions, and outcomes"""
    
    def __init__(self, crew):
        self.crew = crew
        self.session = crew.session
        self.config = settings.EXPERIMENT_CONFIG
        
        # Set random seed for this session
        random.seed(self.session.seed)
    
    def start_round(self, round_number):
        """Start a new round"""
        with transaction.atomic():
            # Create round state
            round_state = RoundState.objects.create(
                crew=self.crew,
                round_number=round_number,
                stage='briefing',
                pu_remaining=self.config['PU_PER_ROUND'],
                current_system=self.crew.current_system
            )
            
            # Set briefing timer based on pressure condition
            if self.session.pressure == 'high':
                round_state.briefing_time_remaining = self.config['BRIEFING_HIGH_PRESSURE']
            else:
                round_state.briefing_time_remaining = self.config['BRIEFING_LOW_PRESSURE']
            
            round_state.save()
            
            # Update crew state
            self.crew.current_round = round_number
            self.crew.current_stage = 'briefing'
            self.crew.stage_start_time = datetime.now()
            self.crew.save()
            
            return round_state
    
    def start_briefing_stage(self, round_state):
        """Start the briefing stage"""
        round_state.stage = 'briefing'
        round_state.stage_start_time = datetime.now()
        round_state.save()
        
        self.crew.current_stage = 'briefing'
        self.crew.save()
        
        # If LLM captain, trigger AI messages
        if self.session.captain_type == 'llm':
            self._trigger_ai_captain_messages(round_state)
    
    def start_action_stage(self, round_state):
        """Start the action stage"""
        round_state.stage = 'action'
        round_state.stage_start_time = datetime.now()
        round_state.action_time_remaining = self.config['ACTION_STAGE_TIME']
        round_state.save()
        
        self.crew.current_stage = 'action'
        self.crew.save()
    
    def start_result_stage(self, round_state):
        """Start the result stage"""
        round_state.stage = 'result'
        round_state.stage_start_time = datetime.now()
        round_state.result_time_remaining = self.config['RESULT_STAGE_TIME']
        round_state.save()
        
        self.crew.current_stage = 'result'
        self.crew.save()
        
        # Process actions and generate outcomes
        self._process_round_actions(round_state)
    
    def submit_action(self, participant, action_type, target_asteroid=None, pu_spent=0):
        """Submit an action for a participant"""
        try:
            round_state = RoundState.objects.get(
                crew=self.crew,
                round_number=self.crew.current_round,
                stage='action'
            )
            
            # Validate action
            if not self._validate_action(participant, action_type, target_asteroid, pu_spent, round_state):
                return False, "Invalid action"
            
            # Create action record
            action = Action.objects.create(
                participant=participant,
                round_state=round_state,
                action_type=action_type,
                target_asteroid=target_asteroid,
                pu_spent=pu_spent
            )
            
            # Update PU remaining
            round_state.pu_remaining -= pu_spent
            round_state.save()
            
            return True, "Action submitted successfully"
            
        except RoundState.DoesNotExist:
            return False, "No active action stage"
    
    def _validate_action(self, participant, action_type, target_asteroid, pu_spent, round_state):
        """Validate if an action is legal"""
        # Check if participant has enough PU
        if pu_spent > round_state.pu_remaining:
            return False
        
        # Check if target asteroid is valid
        if target_asteroid and target_asteroid not in ['Alpha', 'Beta', 'Gamma', 'Omega']:
            return False
        
        # Role-specific validations
        if participant.role == 'navigator':
            return self._validate_navigator_action(action_type, target_asteroid, pu_spent, round_state)
        elif participant.role == 'driller':
            return self._validate_driller_action(action_type, target_asteroid, pu_spent, round_state)
        elif participant.role == 'captain':
            return False  # Captain cannot take actions
        
        return False
    
    def _validate_navigator_action(self, action_type, target_asteroid, pu_spent, round_state):
        """Validate navigator actions"""
        if action_type == 'do_nothing':
            return pu_spent == 0
        elif action_type == 'travel':
            if not target_asteroid:
                return False
            travel_cost = self.config['TRAVEL_COSTS'].get(target_asteroid, 999)
            return pu_spent == travel_cost
        elif action_type == 'send_probe':
            if not target_asteroid:
                return False
            # Check max probes per round
            probe_count = Action.objects.filter(
                round_state=round_state,
                participant__role='navigator',
                action_type='send_probe'
            ).count()
            if probe_count >= 2:
                return False
            return pu_spent == self.config['PROBE_COST']
        
        return False
    
    def _validate_driller_action(self, action_type, target_asteroid, pu_spent, round_state):
        """Validate driller actions"""
        if action_type == 'do_nothing':
            return pu_spent == 0
        elif action_type in ['mine_shallow', 'mine_deep']:
            if not target_asteroid:
                return False
            # Check if asteroid is already mined
            asteroid = Asteroid.objects.get(name=target_asteroid, session=self.session)
            if asteroid.mined:
                return False
            
            # Check costs
            if action_type == 'mine_shallow':
                return pu_spent == self.config['MINE_SHALLOW_COST']
            else:
                return pu_spent == self.config['MINE_DEEP_COST']
        
        elif action_type == 'deploy_robot':
            if not target_asteroid:
                return False
            # Check max robots per round
            robot_count = Action.objects.filter(
                round_state=round_state,
                participant__role='driller',
                action_type='deploy_robot'
            ).count()
            if robot_count >= 1:
                return False
            return pu_spent == self.config['ROBOT_COST']
        
        return False
    
    def _process_round_actions(self, round_state):
        """Process all actions for the round and generate outcomes"""
        # Get all actions for this round
        actions = Action.objects.filter(round_state=round_state).order_by('participant__role')
        
        # Process navigator actions first
        navigator_actions = [a for a in actions if a.participant.role == 'navigator']
        for action in navigator_actions:
            self._process_navigator_action(action, round_state)
        
        # Process driller actions
        driller_actions = [a for a in actions if a.participant.role == 'driller']
        for action in driller_actions:
            self._process_driller_action(action, round_state)
        
        # Update intel visibility based on complexity
        self._update_intel_visibility(round_state)
        
        # Create analytics snapshot
        self._create_analytics_snapshot(round_state)
    
    def _process_navigator_action(self, action, round_state):
        """Process navigator action"""
        if action.action_type == 'travel':
            # Update crew location
            self.crew.current_system = action.target_asteroid
            self.crew.save()
            
            # Update round state
            round_state.current_system = action.target_asteroid
            round_state.save()
        
        elif action.action_type == 'send_probe':
            # Mark asteroid as discovered
            asteroid = Asteroid.objects.get(name=action.target_asteroid, session=self.session)
            if not asteroid.discovered_by:
                asteroid.discovered_by = action.participant
                asteroid.discovered_round = round_state.round_number
                asteroid.save()
    
    def _process_driller_action(self, action, round_state):
        """Process driller action"""
        if action.action_type in ['mine_shallow', 'mine_deep']:
            # Get asteroid
            asteroid = Asteroid.objects.get(name=action.target_asteroid, session=self.session)
            
            # Determine intel combo for probability calculation
            intel_combo = self._determine_intel_combo(asteroid, round_state)
            
            # Calculate mining outcome
            outcome = self._calculate_mining_outcome(
                asteroid, action.action_type, intel_combo
            )
            
            # Create outcome record
            Outcome.objects.create(
                round_state=round_state,
                asteroid=asteroid,
                participant=action.participant,
                action=action,
                minerals_gained=outcome['minerals_gained'],
                full_extraction=outcome['full_extraction'],
                partial_fraction=outcome['partial_fraction'],
                probability_basis=outcome['probability_basis'],
                depth=action.action_type.replace('mine_', ''),
                intel_combo=intel_combo
            )
            
            # Mark asteroid as mined
            asteroid.mined = True
            asteroid.mined_round = round_state.round_number
            asteroid.save()
        
        elif action.action_type == 'deploy_robot':
            # Robot deployment reveals mining costs
            asteroid = Asteroid.objects.get(name=action.target_asteroid, session=self.session)
            # Costs are already known from asteroid creation, just log the action
    
    def _determine_intel_combo(self, asteroid, round_state):
        """Determine what intel is available for probability calculation"""
        # Check if asteroid was probed
        probed = Action.objects.filter(
            round_state__crew=self.crew,
            round_state__round_number__lte=round_state.round_number,
            action_type='send_probe',
            target_asteroid=asteroid.name
        ).exists()
        
        # Check if robot was deployed
        robot_deployed = Action.objects.filter(
            round_state__crew=self.crew,
            round_state__round_number__lte=round_state.round_number,
            action_type='deploy_robot',
            target_asteroid=asteroid.name
        ).exists()
        
        if probed and robot_deployed:
            return 'probe_plus_robot'
        elif probed:
            return 'probe_only'
        elif robot_deployed:
            return 'robot_only'
        else:
            return 'none'
    
    def _calculate_mining_outcome(self, asteroid, mining_type, intel_combo):
        """Calculate mining outcome based on probability matrix"""
        depth = mining_type.replace('mine_', '')
        probability_matrix = self.config['DEFAULT_PROBABILITY_MATRIX']
        
        # Get success probability
        success_prob = probability_matrix[depth][intel_combo]
        
        # Determine if full extraction
        if random.random() < success_prob:
            minerals_gained = asteroid.max_minerals
            full_extraction = True
            partial_fraction = None
        else:
            # Partial extraction
            partial_range = self.config['PARTIAL_YIELD_RANGE']
            partial_fraction = random.uniform(partial_range[0], partial_range[1])
            minerals_gained = int(asteroid.max_minerals * partial_fraction)
            full_extraction = False
        
        return {
            'minerals_gained': minerals_gained,
            'full_extraction': full_extraction,
            'partial_fraction': partial_fraction,
            'probability_basis': {
                'depth': depth,
                'intel_combo': intel_combo,
                'success_probability': success_prob
            }
        }
    
    def _update_intel_visibility(self, round_state):
        """Update intel visibility based on complexity condition"""
        if self.session.complexity == 'low':
            # Low complexity: all intel is shared
            self._share_all_intel(round_state)
        else:
            # High complexity: intel remains private
            self._maintain_private_intel(round_state)
    
    def _share_all_intel(self, round_state):
        """Share all discovered intel with all crew members"""
        # This is handled in the UI layer for low complexity
        # Here we just log the visibility for audit purposes
        asteroids = Asteroid.objects.filter(session=self.session)
        crew_members = [self.crew.captain, self.crew.navigator, self.crew.driller]
        
        for asteroid in asteroids:
            for member in crew_members:
                if member:
                    IntelVisibility.objects.get_or_create(
                        round_state=round_state,
                        asteroid=asteroid,
                        intel_type='max_minerals',
                        visible_to_participant=member,
                        discovered_round=asteroid.discovered_round or 0,
                        visibility_footprint={'shared': True, 'complexity': 'low'}
                    )
    
    def _maintain_private_intel(self, round_state):
        """Maintain private intel visibility for high complexity"""
        # Log visibility for audit purposes
        asteroids = Asteroid.objects.filter(session=self.session)
        
        for asteroid in asteroids:
            if asteroid.discovered_by:
                IntelVisibility.objects.get_or_create(
                    round_state=round_state,
                    asteroid=asteroid,
                    intel_type='max_minerals',
                    visible_to_participant=asteroid.discovered_by,
                    discovered_round=asteroid.discovered_round,
                    visibility_footprint={'shared': False, 'complexity': 'high'}
                )
    
    def _create_analytics_snapshot(self, round_state):
        """Create analytics snapshot for this round"""
        # Calculate cumulative values
        crew = self.crew
        
        # Get all outcomes up to this round
        outcomes = Outcome.objects.filter(
            round_state__crew=crew,
            round_state__round_number__lte=round_state.round_number
        )
        
        cumulative_minerals = sum(outcome.minerals_gained for outcome in outcomes)
        
        # Get all actions up to this round
        actions = Action.objects.filter(
            round_state__crew=crew,
            round_state__round_number__lte=round_state.round_number
        )
        
        cumulative_pu_team = sum(action.pu_spent for action in actions)
        cumulative_pu_captain = sum(
            action.pu_spent for action in actions 
            if action.participant.role == 'captain'
        )
        cumulative_pu_navigator = sum(
            action.pu_spent for action in actions 
            if action.participant.role == 'navigator'
        )
        cumulative_pu_driller = sum(
            action.pu_spent for action in actions 
            if action.participant.role == 'driller'
        )
        
        # Create snapshot
        AnalyticsSnapshot.objects.create(
            crew=crew,
            round_number=round_state.round_number,
            cumulative_minerals=cumulative_minerals,
            cumulative_pu_team=cumulative_pu_team,
            cumulative_pu_captain=cumulative_pu_captain,
            cumulative_pu_navigator=cumulative_pu_navigator,
            cumulative_pu_driller=cumulative_pu_driller
        )
    
    def _trigger_ai_captain_messages(self, round_state):
        """Trigger AI captain messages during briefing"""
        # This would integrate with the AI captain system
        # For now, just log that AI messages should be sent
        pass
    
    def handle_timeout(self, round_state):
        """Handle timeout for participants who didn't submit actions"""
        if round_state.stage == 'action':
            # Find participants without actions
            participants_with_actions = Action.objects.filter(
                round_state=round_state
            ).values_list('participant_id', flat=True)
            
            crew_members = [self.crew.captain, self.crew.navigator, self.crew.driller]
            
            for member in crew_members:
                if member and member.id not in participants_with_actions:
                    # Create auto "do nothing" action
                    Action.objects.create(
                        participant=member,
                        round_state=round_state,
                        action_type='do_nothing',
                        pu_spent=0,
                        auto_do_nothing=True
                    )
    
    def get_round_summary(self, round_number):
        """Get summary of a specific round"""
        try:
            round_state = RoundState.objects.get(
                crew=self.crew,
                round_number=round_number
            )
            
            actions = Action.objects.filter(round_state=round_state)
            outcomes = Outcome.objects.filter(round_state=round_state)
            
            return {
                'round_number': round_number,
                'stage': round_state.stage,
                'pu_remaining': round_state.pu_remaining,
                'current_system': round_state.current_system,
                'actions': [
                    {
                        'participant': action.participant.role,
                        'action_type': action.action_type,
                        'target': action.target_asteroid,
                        'pu_spent': action.pu_spent,
                        'auto': action.auto_do_nothing
                    }
                    for action in actions
                ],
                'outcomes': [
                    {
                        'asteroid': outcome.asteroid.name,
                        'minerals_gained': outcome.minerals_gained,
                        'full_extraction': outcome.full_extraction,
                        'depth': outcome.depth
                    }
                    for outcome in outcomes
                ]
            }
        except RoundState.DoesNotExist:
            return None
    
    def get_game_summary(self):
        """Get overall game summary"""
        crew = self.crew
        
        # Get all analytics snapshots
        analytics = AnalyticsSnapshot.objects.filter(crew=crew).order_by('round_number')
        
        # Get all actions
        actions = Action.objects.filter(round_state__crew=crew).order_by('round_state__round_number')
        
        return {
            'crew_id': crew.id,
            'current_round': crew.current_round,
            'current_stage': crew.current_stage,
            'current_system': crew.current_system,
            'cumulative_minerals': analytics.last().cumulative_minerals if analytics.exists() else 0,
            'cumulative_pu_used': analytics.last().cumulative_pu_team if analytics.exists() else 0,
            'round_summaries': [
                self.get_round_summary(i) for i in range(crew.current_round + 1)
            ]
        }




