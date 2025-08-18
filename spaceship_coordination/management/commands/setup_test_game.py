from django.core.management.base import BaseCommand
from django.utils import timezone
from spaceship_coordination.models import (
    ExperimentSession, Crew, Participant, Asteroid, RoundState
)
import random


class Command(BaseCommand):
    help = 'Set up a complete test game session'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session-id',
            type=str,
            default='test_session_001',
            help='Session ID for the test session'
        )

    def handle(self, *args, **options):
        session_id = options['session_id']
        
        self.stdout.write(f'Setting up test game session: {session_id}')
        
        # Create experiment session
        session, created = ExperimentSession.objects.get_or_create(
            session_id=session_id,
            defaults={
                'pressure': 'low',
                'complexity': 'low',
                'captain_type': 'human',
                'seed': random.randint(1000, 9999),
                'completed': False
            }
        )
        
        if created:
            self.stdout.write(f'Created new experiment session: {session.id}')
        else:
            self.stdout.write(f'Using existing session: {session.id}')
        
        # Create participants first
        roles = ['captain', 'navigator', 'driller']
        participants = []
        
        for i, role in enumerate(roles):
            participant, created = Participant.objects.get_or_create(
                participant_id=f'test_{role}_{i+1}',
                defaults={
                    'role': role,
                    'crew': None,  # Will set this after crew creation
                    'prolific_id': f'prolific_{i+1}',
                    'consent_given': True,
                    'comprehension_correct': True,
                    'comprehension_first_try': True,
                    'survey_completed': False,
                    'bonus_amount': 0.00
                }
            )
            
            if created:
                self.stdout.write(f'Created participant: {participant.role}')
            else:
                self.stdout.write(f'Using existing participant: {participant.role}')
            
            participants.append(participant)
        
        # Create crew with participants
        crew, created = Crew.objects.get_or_create(
            session=session,
            defaults={
                'current_system': 'Alpha',
                'current_round': 0,
                'current_stage': 'waiting',
                'stage_start_time': timezone.now(),
                'captain': participants[0],  # captain
                'navigator': participants[1],  # navigator
                'driller': participants[2],  # driller
            }
        )
        
        if created:
            self.stdout.write(f'Created new crew: {crew.id}')
        else:
            self.stdout.write(f'Using existing crew: {crew.id}')
        
        # Update participants to reference the crew
        for participant in participants:
            participant.crew = crew
            participant.save()
        
        # Create asteroids
        asteroid_names = ['Alpha', 'Beta', 'Gamma', 'Omega']
        for name in asteroid_names:
            asteroid, created = Asteroid.objects.get_or_create(
                name=name,
                session=session,
                defaults={
                    'max_minerals': random.randint(50, 200),
                    'shallow_cost': random.randint(1, 2),
                    'deep_cost': random.randint(2, 4),
                    'travel_cost': random.randint(1, 3),
                    'mined': False
                }
            )
            
            if created:
                self.stdout.write(f'Created asteroid: {asteroid.name}')
        
        # Create initial round state
        round_state, created = RoundState.objects.get_or_create(
            crew=crew,
            round_number=0,
            defaults={
                'stage': 'waiting',
                'pu_remaining': 4,
                'current_system': 'Alpha',
                'stage_start_time': timezone.now()
            }
        )
        
        if created:
            self.stdout.write(f'Created round state for round 0')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Test game setup complete!\n'
                f'📊 Session ID: {session_id}\n'
                f'👥 Crew ID: {crew.id}\n'
                f'🚀 Game URL: http://localhost:8000/spaceship/game/\n'
                f'👤 Admin URL: http://localhost:8000/admin/\n\n'
                f'To start the game:\n'
                f'1. Go to admin panel\n'
                f'2. Find your crew\n'
                f'3. Change stage from "waiting" to "briefing"\n'
                f'4. Refresh the game page'
            )
        )
