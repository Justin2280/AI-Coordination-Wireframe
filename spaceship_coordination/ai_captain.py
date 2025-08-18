"""
AI Captain system for LLM Captain conditions
"""

import json
import random
from datetime import datetime
from django.conf import settings
from .models import *
from .game_logic import GameEngine


class AICaptain:
    """AI Captain that provides coordination messages during briefing"""
    
    def __init__(self, crew):
        self.crew = crew
        self.session = crew.session
        self.game_engine = GameEngine(crew)
        
        # AI personality and constraints
        self.max_message_length = 300
        self.rate_limit_seconds = 5
        self.last_message_time = None
        
        # Role-specific guidance templates
        self.guidance_templates = {
            'navigator': [
                "Consider probing {asteroid} to gather intel on mineral potential.",
                "Travel to {asteroid} if the team needs to access new resources.",
                "Focus on strategic positioning for the team's mining operations.",
                "Use probes efficiently - prioritize unexplored asteroids.",
                "Coordinate travel with the driller's mining plans."
            ],
            'driller': [
                "Consider mining {asteroid} - it shows good potential based on our intel.",
                "Deploy a robot to {asteroid} to assess mining costs.",
                "Focus on high-value targets that maximize mineral extraction.",
                "Balance shallow vs deep mining based on available intel.",
                "Coordinate with the navigator's travel plans."
            ]
        }
    
    def get_visible_state(self):
        """Get the current game state visible to the AI captain"""
        try:
            current_round = self.crew.current_round
            current_system = self.crew.current_system
            
            # Get asteroid information
            asteroids = Asteroid.objects.filter(session=self.session)
            asteroid_info = []
            
            for asteroid in asteroids:
                info = {
                    'name': asteroid.name,
                    'travel_cost': asteroid.travel_cost,
                    'max_minerals': None,
                    'shallow_cost': None,
                    'deep_cost': None,
                    'mined': asteroid.mined,
                    'current_location': asteroid.name == current_system
                }
                
                # Show intel that would be visible to a human captain
                if asteroid.discovered_by:
                    info['max_minerals'] = asteroid.max_minerals
                
                # Check if robot has been deployed (reveals costs)
                robot_deployed = Action.objects.filter(
                    round_state__crew=self.crew,
                    action_type='deploy_robot',
                    target_asteroid=asteroid.name
                ).exists()
                
                if robot_deployed:
                    info['shallow_cost'] = asteroid.shallow_cost
                    info['deep_cost'] = asteroid.deep_cost
                
                asteroid_info.append(info)
            
            # Get crew action history
            actions = Action.objects.filter(
                round_state__crew=self.crew,
                round_state__round_number__lt=current_round
            ).order_by('round_state__round_number')
            
            action_history = []
            for action in actions:
                action_history.append({
                    'round': action.round_state.round_number,
                    'role': action.participant.role,
                    'action': action.action_type,
                    'target': action.target_asteroid,
                    'pu_spent': action.pu_spent
                })
            
            # Get outcomes history
            outcomes = Outcome.objects.filter(
                round_state__crew=self.crew,
                round_state__round_number__lt=current_round
            ).order_by('round_state__round_number')
            
            outcome_history = []
            for outcome in outcomes:
                outcome_history.append({
                    'round': outcome.round_state.round_number,
                    'asteroid': outcome.asteroid.name,
                    'minerals_gained': outcome.minerals_gained,
                    'full_extraction': outcome.full_extraction,
                    'depth': outcome.depth
                })
            
            # Get current PU status
            current_pu = 4  # Default per round
            
            return {
                'current_round': current_round,
                'current_system': current_system,
                'asteroids': asteroid_info,
                'action_history': action_history,
                'outcome_history': outcome_history,
                'pu_remaining': current_pu,
                'complexity': self.session.complexity,
                'pressure': self.session.pressure
            }
            
        except Exception as e:
            return {
                'error': f"Failed to get game state: {str(e)}",
                'current_round': 0,
                'current_system': 'Alpha'
            }
    
    def post_message(self, to_role, text):
        """Post a message to a specific role's chat"""
        try:
            # Rate limiting
            if self.last_message_time:
                time_since_last = (datetime.now() - self.last_message_time).total_seconds()
                if time_since_last < self.rate_limit_seconds:
                    return False, f"Rate limit: wait {self.rate_limit_seconds - time_since_last:.1f}s"
            
            # Message length validation
            if len(text) > self.max_message_length:
                return False, f"Message too long: {len(text)}/{self.max_message_length} chars"
            
            # Get current round state
            try:
                round_state = RoundState.objects.get(
                    crew=self.crew,
                    round_number=self.crew.current_round,
                    stage='briefing'
                )
            except RoundState.DoesNotExist:
                return False, "No active briefing stage"
            
            # Get target participant
            if to_role == 'navigator':
                target_participant = self.crew.navigator
            elif to_role == 'driller':
                target_participant = self.crew.driller
            else:
                return False, f"Invalid role: {to_role}"
            
            if not target_participant:
                return False, f"No {to_role} assigned to crew"
            
            # Create chat message
            ChatMessage.objects.create(
                from_participant=self.crew.captain,  # AI captain
                to_participant=target_participant,
                round_state=round_state,
                message=text,
                stage_only='briefing'
            )
            
            # Update rate limiting
            self.last_message_time = datetime.now()
            
            return True, "Message sent successfully"
            
        except Exception as e:
            return False, f"Failed to send message: {str(e)}"
    
    def generate_coordination_message(self, to_role):
        """Generate a coordination message for a specific role"""
        try:
            # Get current game state
            game_state = self.get_visible_state()
            
            if 'error' in game_state:
                return f"Unable to provide guidance at this time. Please coordinate with your team."
            
            # Analyze current situation
            analysis = self._analyze_game_situation(game_state)
            
            # Generate role-specific guidance
            if to_role == 'navigator':
                message = self._generate_navigator_guidance(game_state, analysis)
            elif to_role == 'driller':
                message = self._generate_driller_guidance(game_state, analysis)
            else:
                return "Invalid role for guidance."
            
            # Ensure message length
            if len(message) > self.max_message_length:
                message = message[:self.max_message_length-3] + "..."
            
            return message
            
        except Exception as e:
            return f"Guidance generation error. Please use your best judgment."
    
    def _analyze_game_situation(self, game_state):
        """Analyze the current game situation"""
        analysis = {
            'unexplored_asteroids': [],
            'high_value_targets': [],
            'strategic_positions': [],
            'pu_efficiency': 'good'
        }
        
        # Find unexplored asteroids
        for asteroid in game_state['asteroids']:
            if not asteroid['mined'] and not asteroid['max_minerals']:
                analysis['unexplored_asteroids'].append(asteroid['name'])
        
        # Find high value targets
        for asteroid in game_state['asteroids']:
            if not asteroid['mined'] and asteroid['max_minerals']:
                if asteroid['max_minerals'] > 100:  # High value threshold
                    analysis['high_value_targets'].append(asteroid['name'])
        
        # Strategic positioning
        current_system = game_state['current_system']
        if current_system != 'Alpha':
            analysis['strategic_positions'].append(f"Currently at {current_system}")
        
        # PU efficiency
        total_pu_used = sum(action['pu_spent'] for action in game_state['action_history'])
        if total_pu_used > 20:  # Threshold for PU efficiency
            analysis['pu_efficiency'] = 'high'
        
        return analysis
    
    def _generate_navigator_guidance(self, game_state, analysis):
        """Generate guidance for the navigator"""
        messages = []
        
        # Prioritize unexplored asteroids for probing
        if analysis['unexplored_asteroids']:
            target = random.choice(analysis['unexplored_asteroids'])
            messages.append(f"Priority: Probe {target} to gather intel.")
        
        # Suggest strategic travel
        if game_state['current_system'] == 'Alpha':
            if analysis['high_value_targets']:
                target = random.choice(analysis['high_value_targets'])
                messages.append(f"Consider traveling to {target} for mining operations.")
        
        # General strategy
        if len(messages) < 2:
            messages.append("Focus on efficient intel gathering and strategic positioning.")
        
        return " ".join(messages)
    
    def _generate_driller_guidance(self, game_state, analysis):
        """Generate guidance for the driller"""
        messages = []
        
        # Suggest high-value mining targets
        if analysis['high_value_targets']:
            target = random.choice(analysis['high_value_targets'])
            messages.append(f"Focus on {target} - shows high mineral potential.")
        
        # Suggest robot deployment for unexplored asteroids
        if analysis['unexplored_asteroids']:
            target = random.choice(analysis['unexplored_asteroids'])
            messages.append(f"Deploy robot to {target} to assess mining costs.")
        
        # General strategy
        if len(messages) < 2:
            messages.append("Balance exploration with exploitation based on available intel.")
        
        return " ".join(messages)
    
    def auto_coordinate(self):
        """Automatically send coordination messages during briefing"""
        try:
            # Check if we're in briefing stage
            if self.crew.current_stage != 'briefing':
                return False, "Not in briefing stage"
            
            # Check rate limiting
            if self.last_message_time:
                time_since_last = (datetime.now() - self.last_message_time).total_seconds()
                if time_since_last < self.rate_limit_seconds:
                    return False, "Rate limited"
            
            # Generate and send messages to both roles
            success_count = 0
            
            # Message to navigator
            nav_message = self.generate_coordination_message('navigator')
            success, _ = self.post_message('navigator', nav_message)
            if success:
                success_count += 1
            
            # Message to driller
            drill_message = self.generate_coordination_message('driller')
            success, _ = self.post_message('driller', drill_message)
            if success:
                success_count += 1
            
            if success_count > 0:
                return True, f"Sent {success_count} coordination messages"
            else:
                return False, "Failed to send any messages"
                
        except Exception as e:
            return False, f"Auto-coordination failed: {str(e)}"
    
    def get_ai_status(self):
        """Get current AI captain status"""
        return {
            'active': True,
            'last_message_time': self.last_message_time.isoformat() if self.last_message_time else None,
            'rate_limit_seconds': self.rate_limit_seconds,
            'max_message_length': self.max_message_length,
            'messages_sent': ChatMessage.objects.filter(
                from_participant=self.crew.captain,
                round_state__crew=self.crew
            ).count()
        }




