"""
Management command to test the Spaceship Coordination game logic
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from spaceship_coordination.models import *
from spaceship_coordination.game_logic import GameEngine
from spaceship_coordination.ai_captain import AICaptain


class Command(BaseCommand):
    help = 'Test the Spaceship Coordination game logic'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-session',
            action='store_true',
            help='Create a test experiment session',
        )
        parser.add_argument(
            '--test-game',
            action='store_true',
            help='Run a test game round',
        )
        parser.add_argument(
            '--test-ai',
            action='store_true',
            help='Test AI captain functionality',
        )

    def handle(self, *args, **options):
        if options['create_session']:
            self.create_test_session()
        
        if options['test_game']:
            self.test_game_logic()
        
        if options['test_ai']:
            self.test_ai_captain()

    def create_test_session(self):
        """Create a test experiment session"""
        self.stdout.write('Creating test experiment session...')
        
        try:
            # Create a test session
            session = ExperimentSession.objects.create(
                pressure='high',
                complexity='low',
                captain_type='human',
                seed=12345
            )
            
            # Create test crew
            crew = Crew.objects.create(
                session=session,
                room_id='test_crew_001',
                current_system='Alpha'
            )
            
            # Create test participants
            captain = Participant.objects.create(
                otree_participant_id=1,  # This would need a real oTree participant
                role='captain',
                crew=crew,
                consent_given=True,
                comprehension_correct=True
            )
            
            navigator = Participant.objects.create(
                otree_participant_id=2,
                role='navigator',
                crew=crew,
                consent_given=True,
                comprehension_correct=True
            )
            
            driller = Participant.objects.create(
                otree_participant_id=3,
                role='driller',
                crew=crew,
                consent_given=True,
                comprehension_correct=True
            )
            
            # Update crew with participants
            crew.captain = captain
            crew.navigator = navigator
            crew.driller = driller
            crew.save()
            
            # Create test asteroids
            asteroids = [
                {'name': 'Alpha', 'max_minerals': 75, 'shallow_cost': 1, 'deep_cost': 2, 'travel_cost': 0},
                {'name': 'Beta', 'max_minerals': 90, 'shallow_cost': 2, 'deep_cost': 3, 'travel_cost': 1},
                {'name': 'Gamma', 'max_minerals': 110, 'shallow_cost': 1, 'deep_cost': 2, 'travel_cost': 2},
                {'name': 'Omega', 'max_minerals': 130, 'shallow_cost': 2, 'deep_cost': 3, 'travel_cost': 3}
            ]
            
            for asteroid_data in asteroids:
                Asteroid.objects.create(
                    session=session,
                    **asteroid_data
                )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully created test session {session.id} with crew {crew.id}'
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating test session: {str(e)}')
            )

    def test_game_logic(self):
        """Test the game logic engine"""
        self.stdout.write('Testing game logic...')
        
        try:
            # Get the first crew
            crew = Crew.objects.first()
            if not crew:
                self.stdout.write(
                    self.style.WARNING('No crew found. Create a test session first.')
                )
                return
            
            # Create game engine
            game_engine = GameEngine(crew)
            
            # Start a new round
            round_state = game_engine.start_round(0)
            self.stdout.write(f'Started round {round_state.round_number}')
            
            # Test action submission
            success, message = game_engine.submit_action(
                crew.navigator,
                'send_probe',
                'Beta',
                1
            )
            
            if success:
                self.stdout.write(f'Action submitted: {message}')
            else:
                self.stdout.write(f'Action failed: {message}')
            
            # Test another action
            success, message = game_engine.submit_action(
                crew.driller,
                'deploy_robot',
                'Beta',
                1
            )
            
            if success:
                self.stdout.write(f'Robot deployed: {message}')
            else:
                self.stdout.write(f'Robot deployment failed: {message}')
            
            # Move to result stage
            game_engine.start_result_stage(round_state)
            self.stdout.write('Moved to result stage')
            
            # Get game summary
            summary = game_engine.get_game_summary()
            self.stdout.write(f'Game summary: {summary}')
            
            self.stdout.write(
                self.style.SUCCESS('Game logic test completed successfully')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error testing game logic: {str(e)}')
            )

    def test_ai_captain(self):
        """Test the AI captain functionality"""
        self.stdout.write('Testing AI captain...')
        
        try:
            # Get a crew with LLM captain
            crew = Crew.objects.filter(session__captain_type='llm').first()
            if not crew:
                self.stdout.write(
                    self.style.WARNING('No LLM captain crew found. Create one first.')
                )
                return
            
            # Create AI captain
            ai_captain = AICaptain(crew)
            
            # Get visible state
            state = ai_captain.get_visible_state()
            self.stdout.write(f'AI captain state: {state}')
            
            # Generate coordination message
            message = ai_captain.generate_coordination_message('navigator')
            self.stdout.write(f'Navigator message: {message}')
            
            message = ai_captain.generate_coordination_message('driller')
            self.stdout.write(f'Driller message: {message}')
            
            # Get AI status
            status = ai_captain.get_ai_status()
            self.stdout.write(f'AI status: {status}')
            
            self.stdout.write(
                self.style.SUCCESS('AI captain test completed successfully')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error testing AI captain: {str(e)}')
            )




