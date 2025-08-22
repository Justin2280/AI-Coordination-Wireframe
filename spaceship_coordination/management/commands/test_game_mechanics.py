"""
Management command to test the enhanced game mechanics
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from spaceship_coordination.models import *
from spaceship_coordination.game_logic import GameEngine
import random


class Command(BaseCommand):
    help = 'Test the enhanced game mechanics implementation'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--session-id',
            type=str,
            default='test_mechanics',
            help='Session ID for testing'
        )
        parser.add_argument(
            '--complexity',
            type=str,
            choices=['high', 'low'],
            default='high',
            help='Complexity condition to test'
        )
        parser.add_argument(
            '--pressure',
            type=str,
            choices=['high', 'low'],
            default='low',
            help='Pressure condition to test'
        )
    
    def handle(self, *args, **options):
        session_id = options['session_id']
        complexity = options['complexity']
        pressure = options['pressure']
        
        self.stdout.write(f"Testing game mechanics for session {session_id}")
        self.stdout.write(f"Complexity: {complexity}, Pressure: {pressure}")
        
        # Create test session
        session = self.create_test_session(session_id, complexity, pressure)
        
        # Create test crew
        crew = self.create_test_crew(session)
        
        # Test game mechanics
        self.test_game_mechanics(crew)
        
        self.stdout.write(self.style.SUCCESS("Game mechanics test completed successfully!"))
    
    def create_test_session(self, session_id, complexity, pressure):
        """Create a test session"""
        session, created = ExperimentSession.objects.get_or_create(
            session_id=session_id,
            defaults={
                'pressure': pressure,
                'complexity': complexity,
                'captain_type': 'human',
                'seed': random.randint(1, 999999)
            }
        )
        
        if created:
            self.stdout.write(f"Created test session: {session}")
        else:
            self.stdout.write(f"Using existing session: {session}")
        
        return session
    
    def create_test_crew(self, session):
        """Create a test crew with participants"""
        crew, created = Crew.objects.get_or_create(
            session=session,
            defaults={
                'room_id': f'crew_{session.session_id}',
                'current_system': 'Alpha',
                'current_round': 0,
                'current_stage': 'waiting'
            }
        )
        
        if created:
            self.stdout.write(f"Created test crew: {crew}")
        else:
            self.stdout.write(f"Using existing crew: {crew}")
        
        # Create test participants
        captain = Participant.objects.get_or_create(
            participant_id=f'captain_{session.session_id}',
            defaults={
                'role': 'captain',
                'crew': crew,
                'consent_given': True
            }
        )[0]
        
        navigator = Participant.objects.get_or_create(
            participant_id=f'navigator_{session.session_id}',
            defaults={
                'role': 'navigator',
                'crew': crew,
                'consent_given': True
            }
        )[0]
        
        driller = Participant.objects.get_or_create(
            participant_id=f'driller_{session.session_id}',
            defaults={
                'role': 'driller',
                'crew': crew,
                'consent_given': True
            }
        )[0]
        
        # Assign participants to crew
        crew.captain = captain
        crew.navigator = navigator
        crew.driller = driller
        crew.save()
        
        self.stdout.write(f"Created test participants: Captain, Navigator, Driller")
        
        return crew
    
    def test_game_mechanics(self, crew):
        """Test the enhanced game mechanics"""
        game_engine = GameEngine(crew)
        
        # Test round progression
        self.stdout.write("\n=== Testing Round Progression ===")
        
        # Start round 1
        round_state = game_engine.start_round(1)
        self.stdout.write(f"Started round 1: {round_state.stage}")
        
        # Test briefing stage
        game_engine.start_briefing_stage(round_state)
        self.stdout.write(f"Briefing stage: {round_state.stage}")
        
        # Test action stage
        game_engine.start_action_stage(round_state)
        self.stdout.write(f"Action stage: {round_state.stage}")
        
        # Test action submission
        self.stdout.write("\n=== Testing Action Submission ===")
        
        # Navigator actions
        success, message = game_engine.submit_action(
            crew.navigator, 'travel', 'Beta', 1
        )
        self.stdout.write(f"Navigator travel to Beta: {success} - {message}")
        
        success, message = game_engine.submit_action(
            crew.navigator, 'send_probe', 'Beta', 1
        )
        self.stdout.write(f"Navigator probe Beta: {success} - {message}")
        
        # Driller actions
        success, message = game_engine.submit_action(
            crew.driller, 'deploy_robot', 'Beta', 1
        )
        self.stdout.write(f"Driller deploy robot to Beta: {success} - {message}")
        
        success, message = game_engine.submit_action(
            crew.driller, 'mine_deep', 'Beta', 2
        )
        self.stdout.write(f"Driller mine deep Beta: {success} - {message}")
        
        # Test result stage
        game_engine.start_result_stage(round_state)
        self.stdout.write(f"Result stage: {round_state.stage}")
        
        # Test intel visibility
        self.stdout.write("\n=== Testing Intel Visibility ===")
        
        # Get asteroid info for different participants
        beta_info_captain = game_engine.get_asteroid_info('Beta', crew.captain)
        beta_info_navigator = game_engine.get_asteroid_info('Beta', crew.navigator)
        beta_info_driller = game_engine.get_asteroid_info('Beta', crew.driller)
        
        self.stdout.write(f"Captain Beta info: {beta_info_captain}")
        self.stdout.write(f"Navigator Beta info: {beta_info_navigator}")
        self.stdout.write(f"Driller Beta info: {beta_info_driller}")
        
        # Test intel summary
        intel_summary = game_engine.get_crew_intel_summary()
        self.stdout.write(f"\nIntel Summary: {intel_summary}")
        
        # Test round summary
        round_summary = game_engine.get_round_summary(1)
        self.stdout.write(f"\nRound Summary: {round_summary}")
        
        # Test game summary
        game_summary = game_engine.get_game_summary()
        self.stdout.write(f"\nGame Summary: {game_summary}")
        
        # Test constraints
        self.stdout.write("\n=== Testing Game Constraints ===")
        
        # Test max probes per round
        success, message = game_engine.submit_action(
            crew.navigator, 'send_probe', 'Gamma', 1
        )
        self.stdout.write(f"Third probe attempt: {success} - {message}")
        
        # Test max robots per round
        success, message = game_engine.submit_action(
            crew.driller, 'deploy_robot', 'Gamma', 1
        )
        self.stdout.write(f"Second robot deployment: {success} - {message}")
        
        # Test mining already mined asteroid
        success, message = game_engine.submit_action(
            crew.driller, 'mine_shallow', 'Beta', 1
        )
        self.stdout.write(f"Mining already mined Beta: {success} - {message}")
        
        # Test captain actions (should fail)
        success, message = game_engine.submit_action(
            crew.captain, 'travel', 'Gamma', 1
        )
        self.stdout.write(f"Captain action attempt: {success} - {message}")
        
        self.stdout.write("\n=== Game Mechanics Test Complete ===")
