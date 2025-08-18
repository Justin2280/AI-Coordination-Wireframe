"""
Views for Spaceship Coordination Experiment
"""

import json
import logging
from datetime import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from .models import *
from .game_logic import GameEngine
from .ai_captain import AICaptain

logger = logging.getLogger(__name__)


class IndexView(View):
    """Index view for the main page"""
    
    def get(self, request):
        """Display the main index page"""
        return render(request, 'spaceship_coordination/index.html')


class WaitingRoomView(View):
    """Waiting room view for participants"""
    
    def get(self, request):
        """Display waiting room"""
        # Check if user already has a participant assigned
        participant_id = request.session.get('participant_id')
        
        if participant_id:
            try:
                participant = Participant.objects.get(participant_id=participant_id)
                crew = participant.crew
                
                # Check if game has started
                if crew.current_stage != 'waiting':
                    # Game has started, redirect to game
                    return redirect('spaceship_coordination:game')
                else:
                    # Still waiting
                    return render(request, 'spaceship_coordination/waiting_room.html', {
                        'message': f'Welcome {participant.role.title()}! Waiting for game to start...',
                        'participant': participant,
                        'crew': crew
                    })
            except Participant.DoesNotExist:
                # Clear invalid session
                request.session.pop('participant_id', None)
        
        # No participant assigned, show role selection
        return render(request, 'spaceship_coordination/role_selection.html')


class RoleSelectionView(View):
    """View for participants to select their role"""
    
    def get(self, request):
        """Display role selection page"""
        # Get available crews that need participants
        available_crews = Crew.objects.filter(
            current_stage='waiting'
        ).exclude(
            captain__isnull=False,
            navigator__isnull=False,
            driller__isnull=False
        )
        
        context = {
            'available_crews': available_crews
        }
        return render(request, 'spaceship_coordination/role_selection.html', context)
    
    def post(self, request):
        """Assign participant to a role"""
        crew_id = request.POST.get('crew_id')
        role = request.POST.get('role')
        
        if not crew_id or not role:
            messages.error(request, "Please select both a crew and a role.")
            return redirect('spaceship_coordination:role_selection')
        
        try:
            crew = Crew.objects.get(id=crew_id)
            
            # Check if role is available
            if role == 'captain' and crew.captain:
                messages.error(request, "Captain role is already taken.")
                return redirect('spaceship_coordination:role_selection')
            elif role == 'navigator' and crew.navigator:
                messages.error(request, "Navigator role is already taken.")
                return redirect('spaceship_coordination:role_selection')
            elif role == 'driller' and crew.driller:
                messages.error(request, "Driller role is already taken.")
                return redirect('spaceship_coordination:role_selection')
            
            # Create participant
            participant = Participant.objects.create(
                participant_id=f'user_{request.session.session_key}_{role}',
                role=role,
                crew=crew,
                prolific_id=f'prolific_{role}',
                consent_given=True,
                comprehension_correct=True,
                comprehension_first_try=True,
                survey_completed=False,
                bonus_amount=0.00
            )
            
            # Assign to crew
            if role == 'captain':
                crew.captain = participant
            elif role == 'navigator':
                crew.navigator = participant
            elif role == 'driller':
                crew.driller = participant
            crew.save()
            
            # Store in session
            request.session['participant_id'] = participant.participant_id
            
            messages.success(request, f"Welcome! You are now the {role.title()}.")
            return redirect('spaceship_coordination:waiting_room')
            
        except Crew.DoesNotExist:
            messages.error(request, "Selected crew not found.")
            return redirect('spaceship_coordination:role_selection')
        except Exception as e:
            logger.error(f"Error assigning role: {str(e)}")
            messages.error(request, "An error occurred while assigning your role.")
            return redirect('spaceship_coordination:role_selection')


class GameView(View):
    """Main game view"""
    
    def get(self, request):
        """Display the main game interface"""
        # Get participant from session
        participant_id = request.session.get('participant_id')
        
        if not participant_id:
            return redirect('spaceship_coordination:waiting_room')
        
        try:
            participant = Participant.objects.get(participant_id=participant_id)
            crew = participant.crew
            
            # Check if game has started
            if crew.current_stage == 'waiting':
                return redirect('spaceship_coordination:waiting_room')
            
            # Get current game state
            try:
                game_engine = GameEngine(crew)
                game_summary = game_engine.get_game_summary()
            except:
                # Fallback if game engine fails
                game_summary = {
                    'current_round': crew.current_round,
                    'current_stage': crew.current_stage,
                    'pu_remaining': 4,
                    'total_minerals': 0
                }
            
            # Get visible asteroids for the current user
            asteroids = crew.session.asteroid_set.all()
            
            context = {
                'participant': participant,
                'crew': crew,
                'game_summary': game_summary,
                'asteroids': asteroids,
                'session_config': {
                    'pressure': crew.session.pressure,
                    'complexity': crew.session.complexity,
                    'captain_type': crew.session.captain_type
                }
            }
            
            return render(request, 'spaceship_coordination/game.html', context)
            
        except Participant.DoesNotExist:
            request.session.pop('participant_id', None)
            return redirect('spaceship_coordination:waiting_room')
        except Exception as e:
            logger.error(f"Error in game view: {str(e)}")
            messages.error(request, "An error occurred while loading the game.")
            return redirect('spaceship_coordination:waiting_room')


class GameCancelledView(View):
    """Game cancelled view"""
    
    def get(self, request):
        """Display game cancellation message"""
        return render(request, 'spaceship_coordination/cancelled.html', {
            'message': 'Unfortunately, one of your crew members has abandoned the game. You will be redirected to Prolific shortly.'
        })


# API Views
class CrewStatusView(View):
    """API endpoint for crew status"""
    
    def get(self, request, crew_id):
        """Get current crew status"""
        try:
            crew = get_object_or_404(Crew, id=crew_id)
            
            # Get current round state
            round_state = RoundState.objects.filter(
                crew=crew
            ).order_by('-round_number').first()
            
            status = {
                'crew_id': crew.id,
                'current_round': crew.current_round,
                'current_stage': crew.current_stage,
                'current_system': crew.current_system,
                'pu_remaining': round_state.pu_remaining if round_state else 4,
                'stage_start_time': crew.stage_start_time.isoformat() if crew.stage_start_time else None,
                'participants': {
                    'captain': crew.captain.role if crew.captain else None,
                    'navigator': crew.navigator.role if crew.navigator else None,
                    'driller': crew.driller.role if crew.driller else None
                }
            }
            
            return JsonResponse(status)
            
        except Exception as e:
            logger.error(f"Error getting crew status: {str(e)}")
            return JsonResponse({'error': 'Failed to get crew status'}, status=500)


class ParticipantStatusView(View):
    """API endpoint for participant status"""
    
    def get(self, request):
        """Get current participant status"""
        participant_id = request.session.get('participant_id')
        
        if not participant_id:
            return JsonResponse({'error': 'No participant found'}, status=401)
        
        try:
            participant = Participant.objects.get(participant_id=participant_id)
            crew = participant.crew
            
            status = {
                'participant_id': participant.participant_id,
                'role': participant.role,
                'crew_id': crew.id,
                'current_stage': crew.current_stage,
                'current_round': crew.current_round,
                'game_started': crew.current_stage != 'waiting'
            }
            
            return JsonResponse(status)
            
        except Participant.DoesNotExist:
            request.session.pop('participant_id', None)
            return JsonResponse({'error': 'Participant not found'}, status=404)
        except Exception as e:
            logger.error(f"Error getting participant status: {str(e)}")
            return JsonResponse({'error': 'Failed to get participant status'}, status=500)


class ActionSubmitView(View):
    """API endpoint for action submission"""
    
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request, crew_id):
        """Submit an action for a participant"""
        try:
            data = json.loads(request.body)
            action_type = data.get('action_type')
            target_asteroid = data.get('target_asteroid')
            pu_spent = data.get('pu_spent', 0)
            
            if not action_type:
                return JsonResponse({'error': 'Action type is required'}, status=400)
            
            # Get participant from session
            participant_id = request.session.get('participant_id')
            if not participant_id:
                return JsonResponse({'error': 'Not authenticated'}, status=401)
            
            participant = Participant.objects.get(participant_id=participant_id)
            crew = participant.crew
            
            if crew.id != crew_id:
                return JsonResponse({'error': 'Access denied'}, status=403)
            
            # Submit action to game engine
            try:
                game_engine = GameEngine(crew)
                success, message = game_engine.submit_action(
                    participant, action_type, target_asteroid, pu_spent
                )
                
                if success:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'pu_remaining': crew.roundstate_set.last().pu_remaining if crew.roundstate_set.exists() else 4
                    })
                else:
                    return JsonResponse({'error': message}, status=400)
            except Exception as e:
                logger.error(f"Game engine error: {str(e)}")
                return JsonResponse({'error': 'Game engine error'}, status=500)
                
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error submitting action: {str(e)}")
            return JsonResponse({'error': 'Internal server error'}, status=500)


class ChatMessageView(View):
    """API endpoint for chat messages"""
    
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request, crew_id):
        """Send a chat message"""
        try:
            data = json.loads(request.body)
            message = data.get('message', '').strip()
            to_role = data.get('to_role')
            
            if not message or not to_role:
                return JsonResponse({'error': 'Message and to_role are required'}, status=400)
            
            # Get participant from session
            participant_id = request.session.get('participant_id')
            if not participant_id:
                return JsonResponse({'error': 'Not authenticated'}, status=401)
            
            from_participant = Participant.objects.get(participant_id=participant_id)
            crew = from_participant.crew
            
            if crew.id != crew_id:
                return JsonResponse({'error': 'Access denied'}, status=403)
            
            # Get current round state
            round_state = RoundState.objects.filter(
                crew=crew,
                stage='briefing'
            ).first()
            
            if not round_state:
                return JsonResponse({'error': 'No active briefing stage'}, status=400)
            
            # Find recipient
            to_participant = None
            if to_role == 'captain':
                to_participant = crew.captain
            elif to_role == 'navigator':
                to_participant = crew.navigator
            elif to_role == 'driller':
                to_participant = crew.driller
            
            if not to_participant:
                return JsonResponse({'error': 'Invalid participant roles'}, status=400)
            
            # Create chat message
            chat_message = ChatMessage.objects.create(
                from_participant=from_participant,
                to_participant=to_participant,
                round_state=round_state,
                message=message,
                stage_only='briefing'
            )
            
            return JsonResponse({
                'success': True,
                'message_id': chat_message.id,
                'timestamp': chat_message.timestamp.isoformat()
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error sending chat message: {str(e)}")
            return JsonResponse({'error': 'Internal server error'}, status=500)


class RoundStatusView(View):
    """API endpoint for round status"""
    
    def get(self, request, crew_id, round_number):
        """Get status of a specific round"""
        try:
            crew = get_object_or_404(Crew, id=crew_id)
            
            # Get round state
            round_state = RoundState.objects.filter(
                crew=crew,
                round_number=round_number
            ).first()
            
            if not round_state:
                return JsonResponse({'error': 'Round not found'}, status=404)
            
            # Get actions for this round
            actions = Action.objects.filter(round_state=round_state)
            action_data = []
            
            for action in actions:
                action_data.append({
                    'participant_role': action.participant.role,
                    'action_type': action.action_type,
                    'target_asteroid': action.target_asteroid,
                    'pu_spent': action.pu_spent,
                    'auto_do_nothing': action.auto_do_nothing,
                    'timestamp': action.timestamp.isoformat()
                })
            
            # Get outcomes for this round
            outcomes = Outcome.objects.filter(round_state=round_state)
            outcome_data = []
            
            for outcome in outcomes:
                outcome_data.append({
                    'asteroid': outcome.asteroid.name,
                    'minerals_gained': outcome.minerals_gained,
                    'full_extraction': outcome.full_extraction,
                    'depth': outcome.depth,
                    'intel_combo': outcome.intel_combo
                })
            
            status = {
                'round_number': round_number,
                'stage': round_state.stage,
                'pu_remaining': round_state.pu_remaining,
                'current_system': round_state.current_system,
                'stage_start_time': round_state.stage_start_time.isoformat(),
                'actions': action_data,
                'outcomes': outcome_data
            }
            
            return JsonResponse(status)
            
        except Exception as e:
            logger.error(f"Error getting round status: {str(e)}")
            return JsonResponse({'error': 'Failed to get round status'}, status=500)


# Admin Views
class AdminCrewListView(View):
    """Admin view for listing all crews"""
    
    @method_decorator(user_passes_test(lambda u: u.is_staff))
    def get(self, request):
        """Display list of all crews"""
        crews = Crew.objects.all().order_by('-created_at')
        
        context = {
            'crews': crews,
            'total_crews': crews.count(),
            'active_crews': crews.filter(current_stage__in=['briefing', 'action', 'result']).count()
        }
        
        return render(request, 'spaceship_coordination/admin/crew_list.html', context)


class AdminCrewDetailView(View):
    """Admin view for crew details"""
    
    @method_decorator(user_passes_test(lambda u: u.is_staff))
    def get(self, request, crew_id):
        """Display detailed crew information"""
        crew = get_object_or_404(Crew, id=crew_id)
        
        # Get game summary
        game_engine = GameEngine(crew)
        game_summary = game_engine.get_game_summary()
        
        # Get all round states
        round_states = RoundState.objects.filter(crew=crew).order_by('round_number')
        
        # Get all actions
        actions = Action.objects.filter(round_state__crew=crew).order_by('round_state__round_number')
        
        # Get all outcomes
        outcomes = Outcome.objects.filter(round_state__crew=crew).order_by('round_state__round_number')
        
        # Get system events
        system_events = SystemEvent.objects.filter(crew=crew).order_by('-timestamp')
        
        context = {
            'crew': crew,
            'game_summary': game_summary,
            'round_states': round_states,
            'actions': actions,
            'outcomes': outcomes,
            'system_events': system_events
        }
        
        return render(request, 'spaceship_coordination/admin/crew_detail.html', context)


class AdminSessionListView(View):
    """Admin view for listing all sessions"""
    
    @method_decorator(user_passes_test(lambda u: u.is_staff))
    def get(self, request):
        """Display list of all sessions"""
        sessions = ExperimentSession.objects.all().order_by('-created_at')
        
        context = {
            'sessions': sessions,
            'total_sessions': sessions.count(),
            'active_sessions': sessions.filter(completed=False).count()
        }
        
        return render(request, 'spaceship_coordination/admin/session_list.html', context)


class AdminAnalyticsView(View):
    """Admin view for system analytics"""
    
    @method_decorator(user_passes_test(lambda u: u.is_staff))
    def get(self, request):
        """Display system analytics"""
        # Get overall statistics
        total_crews = Crew.objects.count()
        total_participants = Participant.objects.count()
        total_sessions = ExperimentSession.objects.count()
        
        # Get condition distribution
        condition_stats = {}
        for session in ExperimentSession.objects.all():
            key = f"{session.pressure}_{session.complexity}_{session.captain_type}"
            condition_stats[key] = condition_stats.get(key, 0) + 1
        
        # Get recent activity
        recent_actions = Action.objects.all().order_by('-timestamp')[:50]
        recent_outcomes = Outcome.objects.all().order_by('-round_state__timestamp')[:50]
        
        context = {
            'total_crews': total_crews,
            'total_participants': total_participants,
            'total_sessions': total_sessions,
            'condition_stats': condition_stats,
            'recent_actions': recent_actions,
            'recent_outcomes': recent_outcomes
        }
        
        return render(request, 'spaceship_coordination/admin/analytics.html', context)


# Game Management Views
class StartGameView(View):
    """View for starting a new game"""
    
    @method_decorator(user_passes_test(lambda u: u.is_staff))
    def post(self, request, crew_id):
        """Start a new game for a crew"""
        try:
            crew = get_object_or_404(Crew, id=crew_id)
            
            # Start the game
            game_engine = GameEngine(crew)
            round_state = game_engine.start_round(0)  # Start with training round
            
            return JsonResponse({
                'success': True,
                'message': 'Game started successfully',
                'round_number': 0,
                'stage': 'briefing'
            })
            
        except Exception as e:
            logger.error(f"Error starting game: {str(e)}")
            return JsonResponse({'error': 'Failed to start game'}, status=500)


class NextStageView(View):
    """View for advancing to next stage"""
    
    @method_decorator(user_passes_test(lambda u: u.is_staff))
    def post(self, request, crew_id):
        """Advance to next stage"""
        try:
            crew = get_object_or_404(Crew, id=crew_id)
            current_stage = crew.current_stage
            
            # Get current round state
            round_state = RoundState.objects.filter(
                crew=crew,
                round_number=crew.current_round
            ).first()
            
            if not round_state:
                return JsonResponse({'error': 'No active round'}, status=400)
            
            game_engine = GameEngine(crew)
            
            if current_stage == 'briefing':
                game_engine.start_action_stage(round_state)
                next_stage = 'action'
            elif current_stage == 'action':
                game_engine.start_result_stage(round_state)
                next_stage = 'result'
            elif current_stage == 'result':
                # Move to next round
                next_round = crew.current_round + 1
                if next_round <= 5:  # Max 6 rounds (0-5)
                    round_state = game_engine.start_round(next_round)
                    next_stage = 'briefing'
                else:
                    # Game complete
                    crew.current_stage = 'completed'
                    crew.save()
                    return JsonResponse({
                        'success': True,
                        'message': 'Game completed',
                        'stage': 'completed'
                    })
            
            return JsonResponse({
                'success': True,
                'message': f'Advanced to {next_stage} stage',
                'stage': next_stage
            })
            
        except Exception as e:
            logger.error(f"Error advancing stage: {str(e)}")
            return JsonResponse({'error': 'Failed to advance stage'}, status=500)


class PauseGameView(View):
    """View for pausing a game"""
    
    @method_decorator(user_passes_test(lambda u: u.is_staff))
    def post(self, request, crew_id):
        """Pause a game"""
        try:
            crew = get_object_or_404(Crew, id=crew_id)
            
            # Log pause event
            SystemEvent.objects.create(
                crew=crew,
                event_type='pause_round',
                details={'timestamp': datetime.now().isoformat(), 'admin_action': True}
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Game paused successfully'
            })
            
        except Exception as e:
            logger.error(f"Error pausing game: {str(e)}")
            return JsonResponse({'error': 'Failed to pause game'}, status=500)


# Results and Analytics Views
class GameResultsView(View):
    """View for displaying game results"""
    
    def get(self, request, crew_id):
        """Display game results"""
        crew = get_object_or_404(Crew, id=crew_id)
        
        # Get game summary
        game_engine = GameEngine(crew)
        game_summary = game_engine.get_game_summary()
        
        # Get analytics data
        analytics = AnalyticsSnapshot.objects.filter(crew=crew).order_by('round_number')
        
        context = {
            'crew': crew,
            'game_summary': game_summary,
            'analytics': analytics
        }
        
        return render(request, 'spaceship_coordination/results.html', context)


class CrewAnalyticsView(View):
    """View for crew analytics"""
    
    def get(self, request, crew_id):
        """Display crew analytics"""
        crew = get_object_or_404(Crew, id=crew_id)
        
        # Get analytics data
        analytics = AnalyticsSnapshot.objects.filter(crew=crew).order_by('round_number')
        
        # Prepare chart data
        rounds = [a.round_number for a in analytics]
        minerals = [a.cumulative_minerals for a in analytics]
        pu_used = [a.cumulative_pu_team for a in analytics]
        
        context = {
            'crew': crew,
            'analytics': analytics,
            'chart_data': {
                'rounds': rounds,
                'minerals': minerals,
                'pu_used': pu_used
            }
        }
        
        return render(request, 'spaceship_coordination/analytics.html', context)


# Survey and Completion Views
class SurveyView(View):
    """View for the debrief survey"""
    
    def get(self, request, crew_id):
        """Display survey form"""
        crew = get_object_or_404(Crew, id=crew_id)
        
        context = {
            'crew': crew,
            'industries': [
                'Architecture & Engineering',
                'Arts/Design/Media',
                'Business & Finance',
                'Education',
                'Healthcare',
                'Information Technology',
                'Legal',
                'Manufacturing',
                'Marketing & Sales',
                'Research & Development',
                'Transportation & Material Moving'
            ]
        }
        
        return render(request, 'spaceship_coordination/survey.html', context)
    
    def post(self, request, crew_id):
        """Process survey submission"""
        try:
            crew = get_object_or_404(Crew, id=crew_id)
            
            # Get survey data
            survey_data = {
                'difficulty_rating': request.POST.get('difficulty_rating'),
                'gender': request.POST.get('gender'),
                'gender_other': request.POST.get('gender_other', ''),
                'age': request.POST.get('age'),
                'education': request.POST.getlist('education'),
                'employment_status': request.POST.get('employment_status'),
                'industry': request.POST.get('industry'),
                'years_experience': request.POST.get('years_experience'),
                'job_title': request.POST.get('job_title'),
                'annual_income': request.POST.get('annual_income'),
                'open_comments': request.POST.get('open_comments', '')
            }
            
            # For now, assume the participant is the navigator (this would need proper participant identification)
            participant = crew.navigator
            if not participant:
                participant = crew.driller
            
            if participant:
                # Create survey record
                Survey.objects.create(
                    participant=participant,
                    **survey_data
                )
                
                participant.survey_completed = True
                participant.save()
            
            return redirect('spaceship_coordination:complete', crew_id=crew_id)
            
        except Exception as e:
            logger.error(f"Error processing survey: {str(e)}")
            messages.error(request, "An error occurred while processing your survey.")
            return redirect('spaceship_coordination:survey', crew_id=crew_id)


class GameCompleteView(View):
    """View for game completion"""
    
    def get(self, request, crew_id):
        """Display game completion page"""
        crew = get_object_or_404(Crew, id=crew_id)
        
        # Calculate final results
        game_engine = GameEngine(crew)
        game_summary = game_engine.get_game_summary()
        
        # Calculate bonus
        final_minerals = game_summary.get('cumulative_minerals', 0)
        total_pu = game_summary.get('cumulative_pu_used', 0)
        
        bonus = max(0, (final_minerals * 0.1) - (total_pu * 0.05))
        bonus = min(bonus, 3.00)  # Cap at £3.00
        
        context = {
            'crew': crew,
            'final_minerals': final_minerals,
            'total_pu': total_pu,
            'bonus': bonus,
            'prolific_completion_url': 'https://app.prolific.co/submissions/complete?cc=XXXXX'
        }
        
        return render(request, 'spaceship_coordination/complete.html', context)


