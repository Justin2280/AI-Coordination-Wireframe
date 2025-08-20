"""
Django management command to create a test experiment session
"""

from django.core.management.base import BaseCommand
from spaceship_coordination.models import ExperimentSession
import random


class Command(BaseCommand):
    help = 'Create a test experiment session with automatic setup'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session-id',
            type=str,
            default=f'test_session_{random.randint(1000, 9999)}',
            help='Session ID for the test session'
        )
        parser.add_argument(
            '--pressure',
            type=str,
            choices=['high', 'low'],
            default='high',
            help='Communication pressure level'
        )
        parser.add_argument(
            '--complexity',
            type=str,
            choices=['high', 'low'],
            default='low',
            help='Information complexity level'
        )
        parser.add_argument(
            '--captain-type',
            type=str,
            choices=['human', 'llm'],
            default='human',
            help='Captain type'
        )

    def handle(self, *args, **options):
        session_id = options['session_id']
        pressure = options['pressure']
        complexity = options['complexity']
        captain_type = options['captain_type']
        
        # Check if session already exists
        if ExperimentSession.objects.filter(session_id=session_id).exists():
            self.stdout.write(
                self.style.WARNING(f'Session {session_id} already exists. Use --session-id to specify a different ID.')
            )
            return
        
        # Create the session (this will automatically trigger the signal to create default setup)
        session = ExperimentSession.objects.create(
            session_id=session_id,
            pressure=pressure,
            complexity=complexity,
            captain_type=captain_type,
            seed=random.randint(1, 999999)
        )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created session {session_id}')
        )
        
        # Verify the default setup was created
        crew_count = session.crew_set.count()
        asteroid_count = session.asteroid_set.count()
        
        self.stdout.write(f'  - Crews created: {crew_count}')
        self.stdout.write(f'  - Asteroids created: {asteroid_count}')
        
        if crew_count > 0:
            crew = session.crew_set.first()
            self.stdout.write(f'  - Crew room ID: {crew.room_id}')
            self.stdout.write(f'  - Crew stage: {crew.current_stage}')
        
        if asteroid_count > 0:
            asteroids = session.asteroid_set.all()
            self.stdout.write('  - Asteroids:')
            for asteroid in asteroids:
                self.stdout.write(f'    * {asteroid.name}: {asteroid.max_minerals} minerals, travel cost: {asteroid.travel_cost} PU')
        
        self.stdout.write(
            self.style.SUCCESS(f'\nSession {session_id} is ready for use!')
        )

