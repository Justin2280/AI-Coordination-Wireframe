"""
Game logic engine for Spaceship Coordination Experiment
Implements the formal game mechanics as specified in the game rules document
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
        """Start a new round following formal mechanics"""
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
        """Start the briefing stage - communication enabled"""
        round_state.stage = 'briefing'
        round_state.stage_start_time = datetime.now()
        round_state.save()
        
        self.crew.current_stage = 'briefing'
        self.crew.save()
        
        # If LLM captain, trigger AI messages
        if self.session.captain_type == 'llm':
            self._trigger_ai_captain_messages(round_state)
    
    def start_action_stage(self, round_state):
        """Start the action stage - communication disabled"""
        round_state.stage = 'action'
        round_state.stage_start_time = datetime.now()
        round_state.action_time_remaining = self.config['ACTION_STAGE_TIME']
        round_state.save()
        
        self.crew.current_stage = 'action'
        self.crew.save()
    
    def start_result_stage(self, round_state):
        """Start the result stage - process actions and show outcomes"""
        round_state.stage = 'result'
        round_state.stage_start_time = datetime.now()
        round_state.result_time_remaining = self.config['RESULT_STAGE_TIME']
        round_state.save()
        
        self.crew.current_stage = 'result'
        self.crew.save()
        
        # Process actions and generate outcomes following formal mechanics
        self._process_round_actions(round_state)
    
    def submit_action(self, participant, action_type, target_asteroid=None, pu_spent=0):
        """Submit an action for a participant with formal validation"""
        try:
            round_state = RoundState.objects.get(
                crew=self.crew,
                round_number=self.crew.current_round,
                stage='action'
            )
            
            # Validate action according to formal rules
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
        """Validate if an action is legal according to formal rules"""
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
            return False  # Captain cannot take actions per formal rules
        
        return False
    
    def _validate_navigator_action(self, action_type, target_asteroid, pu_spent, round_state):
        """Validate navigator actions according to formal rules"""
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
            # Check max probes per round (formal rule: max 2)
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
        """Validate driller actions according to formal rules"""
        if action_type == 'do_nothing':
            return pu_spent == 0
        elif action_type in ['mine_shallow', 'mine_deep']:
            if not target_asteroid:
                return False
            # Check if asteroid is already mined (formal rule: each asteroid can only be mined once)
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
            # Check max robots per round (formal rule: max 1)
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
        """Process all actions for the round following formal execution order"""
        # Get all actions for this round
        actions = Action.objects.filter(round_state=round_state).order_by('participant__role')
        
        # Process navigator actions FIRST (formal rule: Navigator effects precede Driller effects during result stage)
        navigator_actions = [a for a in actions if a.participant.role == 'navigator']
        for action in navigator_actions:
            self._process_navigator_action(action, round_state)
        
        # Process driller actions SECOND (effects processed after Navigator effects)
        driller_actions = [a for a in actions if a.participant.role == 'driller']
        for action in driller_actions:
            self._process_driller_action(action, round_state)
        
        # Update intel visibility based on complexity condition
        self._update_intel_visibility(round_state)
        
        # Create analytics snapshot
        self._create_analytics_snapshot(round_state)
    
    def _process_navigator_action(self, action, round_state):
        """Process navigator action following formal mechanics"""
        if action.action_type == 'travel':
            # Update crew location
            self.crew.current_system = action.target_asteroid
            self.crew.save()
            
            # Update round state
            round_state.current_system = action.target_asteroid
            round_state.save()
        
        elif action.action_type == 'send_probe':
            # Mark asteroid as discovered and reveal max minerals
            asteroid = Asteroid.objects.get(name=action.target_asteroid, session=self.session)
            if not asteroid.discovered_by:
                asteroid.discovered_by = action.participant
                asteroid.discovered_round = round_state.round_number
                asteroid.save()
            
            # Log intel visibility for this probe
            self._log_intel_visibility(
                round_state, asteroid, 'max_minerals', 
                action.participant, round_state.round_number
            )
    
    def _process_driller_action(self, action, round_state):
        """Process driller action following formal mechanics"""
        if action.action_type in ['mine_shallow', 'mine_deep']:
            # Get asteroid
            asteroid = Asteroid.objects.get(name=action.target_asteroid, session=self.session)
            
            # Determine intel combo for probability calculation
            intel_combo = self._determine_intel_combo(asteroid, round_state)
            
            # Calculate mining outcome using formal probability matrix
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
            
            # Mark asteroid as mined (formal rule: each asteroid can only be mined once)
            asteroid.mined = True
            asteroid.mined_round = round_state.round_number
            asteroid.save()
        
        elif action.action_type == 'deploy_robot':
            # Robot deployment reveals mining costs
            asteroid = Asteroid.objects.get(name=action.target_asteroid, session=self.session)
            
            # Log intel visibility for this robot deployment
            self._log_intel_visibility(
                round_state, asteroid, 'shallow_cost', 
                action.participant, round_state.round_number
            )
            self._log_intel_visibility(
                round_state, asteroid, 'deep_cost', 
                action.participant, round_state.round_number
            )
    
    def _determine_intel_combo(self, asteroid, round_state):
        """Determine what intel is available for probability calculation"""
        # Check if asteroid was probed (reveals max minerals)
        probed = Action.objects.filter(
            round_state__crew=self.crew,
            round_state__round_number__lte=round_state.round_number,
            action_type='send_probe',
            target_asteroid=asteroid.name
        ).exists()
        
        # Check if robot was deployed (reveals mining costs)
        robot_deployed = Action.objects.filter(
            round_state__crew=self.crew,
            round_state__round_number__lte=round_state.round_number,
            action_type='deploy_robot',
            target_asteroid=asteroid.name
        ).exists()
        
        # Return intel combo according to formal rules
        if probed and robot_deployed:
            return 'probe_plus_robot'
        elif probed:
            return 'probe_only'
        elif robot_deployed:
            return 'robot_only'
        else:
            return 'none'
    
    def _calculate_mining_outcome(self, asteroid, mining_type, intel_combo):
        """Calculate mining outcome based on formal probability matrix"""
        depth = mining_type.replace('mine_', '')
        probability_matrix = self.config['DEFAULT_PROBABILITY_MATRIX']
        
        # Get success probability from formal matrix
        success_prob = probability_matrix[depth][intel_combo]
        
        # Determine if full extraction based on probability
        if random.random() < success_prob:
            minerals_gained = asteroid.max_minerals
            full_extraction = True
            partial_fraction = 1.0
        else:
            # Partial extraction (formal rule: always yields some positive amount)
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
                'success_probability': success_prob,
                'asteroid_max': asteroid.max_minerals
            }
        }
    
    def _log_intel_visibility(self, round_state, asteroid, intel_type, participant, round_number):
        """Log intel visibility for audit purposes"""
        IntelVisibility.objects.get_or_create(
            round_state=round_state,
            asteroid=asteroid,
            intel_type=intel_type,
            visible_to_participant=participant,
            discovered_round=round_number,
            visibility_footprint={
                'complexity': self.session.complexity,
                'shared': self.session.complexity == 'low',
                'discovery_method': 'probe' if intel_type == 'max_minerals' else 'robot'
            }
        )
    
    def _update_intel_visibility(self, round_state):
        """Update intel visibility based on complexity condition"""
        if self.session.complexity == 'low':
            # Low complexity: all intel is shared (visible to all crew)
            self._share_all_intel(round_state)
        else:
            # High complexity: intel remains private to discoverer
            self._maintain_private_intel(round_state)
    
    def _share_all_intel(self, round_state):
        """Share all discovered intel with all crew members (low complexity)"""
        # Get all crew members
        crew_members = [self.crew.captain, self.crew.navigator, self.crew.driller]
        
        # Get all asteroids with discovered intel
        asteroids = Asteroid.objects.filter(session=self.session)
        
        for asteroid in asteroids:
            for member in crew_members:
                if member:
                    # Share max minerals if discovered
                    if asteroid.discovered_by:
                        IntelVisibility.objects.get_or_create(
                            round_state=round_state,
                            asteroid=asteroid,
                            intel_type='max_minerals',
                            visible_to_participant=member,
                            discovered_round=asteroid.discovered_round or 0,
                            visibility_footprint={'shared': True, 'complexity': 'low'}
                        )
                    
                    # Share mining costs if robot was deployed
                    robot_actions = Action.objects.filter(
                        round_state__crew=self.crew,
                        round_state__round_number__lte=round_state.round_number,
                        action_type='deploy_robot',
                        target_asteroid=asteroid.name
                    )
                    if robot_actions.exists():
                        IntelVisibility.objects.get_or_create(
                            round_state=round_state,
                            asteroid=asteroid,
                            intel_type='shallow_cost',
                            visible_to_participant=member,
                            discovered_round=round_state.round_number,
                            visibility_footprint={'shared': True, 'complexity': 'low'}
                        )
                        IntelVisibility.objects.get_or_create(
                            round_state=round_state,
                            asteroid=asteroid,
                            intel_type='deep_cost',
                            visible_to_participant=member,
                            discovered_round=round_state.round_number,
                            visibility_footprint={'shared': True, 'complexity': 'low'}
                        )
    
    def _maintain_private_intel(self, round_state):
        """Maintain private intel visibility for high complexity"""
        # Intel remains private to discoverer - just log for audit
        asteroids = Asteroid.objects.filter(session=self.session)
        
        for asteroid in asteroids:
            # Log max minerals visibility
            if asteroid.discovered_by:
                IntelVisibility.objects.get_or_create(
                    round_state=round_state,
                    asteroid=asteroid,
                    intel_type='max_minerals',
                    visible_to_participant=asteroid.discovered_by,
                    discovered_round=asteroid.discovered_round,
                    visibility_footprint={'shared': False, 'complexity': 'high'}
                )
            
            # Log mining costs visibility
            robot_actions = Action.objects.filter(
                round_state__crew=self.crew,
                round_state__round_number__lte=round_state.round_number,
                action_type='deploy_robot',
                target_asteroid=asteroid.name
            )
            for robot_action in robot_actions:
                IntelVisibility.objects.get_or_create(
                    round_state=round_state,
                    asteroid=asteroid,
                    intel_type='shallow_cost',
                    visible_to_participant=robot_action.participant,
                    discovered_round=round_state.round_number,
                    visibility_footprint={'shared': False, 'complexity': 'high'}
                )
                IntelVisibility.objects.get_or_create(
                    round_state=round_state,
                    asteroid=asteroid,
                    intel_type='deep_cost',
                    visible_to_participant=robot_action.participant,
                    discovered_round=round_state.round_number,
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
                    # Create auto "do nothing" action (formal rule: default to DoNothing)
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
                        'depth': outcome.depth,
                        'intel_combo': outcome.intel_combo
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
            'total_minerals': self._calculate_total_minerals(),
            'total_pu_spent': sum(action.pu_spent for action in actions),
            'rounds_completed': analytics.count(),
            'last_updated': crew.stage_start_time
        }
    
    def _calculate_total_minerals(self):
        """Calculate total minerals gained across all rounds"""
        outcomes = Outcome.objects.filter(round_state__crew=self.crew)
        return sum(outcome.minerals_gained for outcome in outcomes)
    
    def get_available_actions(self, participant):
        """Get available actions for a participant based on their role and current stage"""
        try:
            current_round_state = RoundState.objects.get(
                crew=self.crew,
                round_number=self.crew.current_round
            )
        except RoundState.DoesNotExist:
            return []
        
        if current_round_state.stage != 'action':
            return []
        
        if participant.role == 'navigator':
            return [
                {'type': 'do_nothing', 'label': 'Do Nothing', 'pu_cost': 0},
                {'type': 'travel', 'label': 'Travel', 'pu_cost': 1},
                {'type': 'send_probe', 'label': 'Send Probe', 'pu_cost': 1}
            ]
        elif participant.role == 'driller':
            return [
                {'type': 'do_nothing', 'label': 'Do Nothing', 'pu_cost': 0},
                {'type': 'mine_shallow', 'label': 'Mine Shallow', 'pu_cost': 1},
                {'type': 'mine_deep', 'label': 'Mine Deep', 'pu_cost': 2},
                {'type': 'deploy_robot', 'label': 'Deploy Robot', 'pu_cost': 1}
            ]
        
        return []
    
    def can_communicate(self, participant):
        """Check if participant can communicate based on current stage and role"""
        # Check both the round state stage and the crew's current stage
        try:
            current_round_state = RoundState.objects.get(
                crew=self.crew,
                round_number=self.crew.current_round
            )
        except RoundState.DoesNotExist:
            return False
        
        if (current_round_state.stage != 'briefing' and 
            self.crew.current_stage != 'briefing'):
            return False
        
        # Only captain can communicate during briefing (formal rule)
        return participant.role == 'captain'
    
    def get_asteroid_info(self, asteroid_name, participant):
        """Get asteroid information based on complexity and participant's intel"""
        try:
            asteroid = Asteroid.objects.get(
                name=asteroid_name,
                session=self.crew.session
            )
            
            info = {
                'name': asteroid.name,
                'travel_cost': asteroid.travel_cost,
                'discovered': asteroid.discovered_by is not None,
                'mined': asteroid.mined
            }
            
            # Check complexity level for intel visibility
            if self.crew.session.complexity == 'low':
                # Low complexity: share all info with all crew
                info.update({
                    'max_minerals': asteroid.max_minerals,
                    'shallow_cost': asteroid.shallow_cost,
                    'deep_cost': asteroid.deep_cost
                })
            else:
                # High complexity: only show info if participant has intel
                # Check if participant has probed this asteroid
                probe_action = Action.objects.filter(
                    participant=participant,
                    action_type='send_probe',
                    target_asteroid=asteroid_name
                ).exists()
                
                if probe_action:
                    info['max_minerals'] = asteroid.max_minerals
                
                # Check if participant has deployed robot
                robot_action = Action.objects.filter(
                    participant=participant,
                    action_type='deploy_robot',
                    target_asteroid=asteroid_name
                ).exists()
                
                if robot_action:
                    info.update({
                        'shallow_cost': asteroid.shallow_cost,
                        'deep_cost': asteroid.deep_cost
                    })
            
            return info
            
        except Asteroid.DoesNotExist:
            return None
    
    def get_crew_intel_summary(self):
        """Get summary of crew's intel for debugging/admin purposes"""
        crew = self.crew
        
        # Get all asteroids
        asteroids = Asteroid.objects.filter(session=crew.session)
        
        intel_summary = {}
        for asteroid in asteroids:
            intel_summary[asteroid.name] = {
                'max_minerals': {
                    'discovered': asteroid.discovered_by is not None,
                    'discovered_by': asteroid.discovered_by.role if asteroid.discovered_by else None,
                    'discovered_round': asteroid.discovered_round,
                    'value': asteroid.max_minerals if asteroid.discovered_by else 'Unknown'
                },
                'mining_costs': {
                    'shallow_cost': asteroid.shallow_cost,
                    'deep_cost': asteroid.deep_cost,
                    'robot_deployed': Action.objects.filter(
                        round_state__crew=crew,
                        action_type='deploy_robot',
                        target_asteroid=asteroid.name
                    ).exists()
                },
                'mined': {
                    'status': asteroid.mined,
                    'round': asteroid.mined_round,
                    'minerals_gained': None
                }
            }
            
            # Get minerals gained if mined
            if asteroid.mined:
                outcome = Outcome.objects.filter(
                    round_state__crew=crew,
                    asteroid=asteroid
                ).first()
                if outcome:
                    intel_summary[asteroid.name]['mined']['minerals_gained'] = outcome.minerals_gained
        
        return intel_summary





