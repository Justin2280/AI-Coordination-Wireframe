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
from .ai_captain import AICaptain
from django.utils import timezone

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
        
        # No participant assigned, redirect to role selection
        return redirect('spaceship_coordination:role_selection')


class RoleSelectionView(View):
    """View for participants to select their role"""
    
    def get(self, request):
        """Display role selection page"""
        # Get available crews that need participants
        available_crews = []
        
        waiting_crews = Crew.objects.filter(current_stage='waiting')
        
        for crew in waiting_crews:
            # Check if this crew has any open roles
            open_roles = []
            if not crew.captain:
                open_roles.append('captain')
            if not crew.navigator:
                open_roles.append('navigator')
            if not crew.driller:
                open_roles.append('driller')
            
            if open_roles:
                # Add crew with open roles info
                crew.open_roles = open_roles
                available_crews.append(crew)
        
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
                
                # Get or create round state for current round
                try:
                    round_state = RoundState.objects.get(
                        crew=crew,
                        round_number=crew.current_round
                    )
                except RoundState.DoesNotExist:
                    # Create round state if it doesn't exist
                    round_state = RoundState.objects.create(
                        crew=crew,
                        round_number=crew.current_round,
                        stage=crew.current_stage,
                        pu_remaining=4,  # Start with 4 PU per round
                        current_system=crew.current_system,
                        briefing_time_remaining=180 if crew.session.pressure == 'low' else 90,
                        action_time_remaining=15,
                        result_time_remaining=15
                    )
                
                # Ensure round state stage matches crew stage
                if round_state.stage != crew.current_stage:
                    round_state.stage = crew.current_stage
                    round_state.save()
                
                # Calculate time remaining using the same logic as _update_timers
                now = timezone.now()
                time_elapsed = (now - round_state.stage_start_time).total_seconds()
                
                if crew.current_stage == 'briefing':
                    total_duration = 180 if crew.session.pressure == 'low' else 90
                    time_remaining = max(0, int(total_duration - time_elapsed))
                elif crew.current_stage == 'action':
                    total_duration = 15
                    time_remaining = max(0, int(total_duration - time_elapsed))
                elif crew.current_stage == 'result':
                    total_duration = 15
                    time_remaining = max(0, int(total_duration - time_elapsed))
                else:
                    time_remaining = 0
                
                # Create game summary
                game_summary = {
                    'current_round': crew.current_round,
                    'current_stage': crew.current_stage,
                    'pu_remaining': round_state.pu_remaining,
                    'total_minerals': 0,  # Will calculate this later
                    'round_progress': f"{crew.current_round}/5",
                    'stage_progress': "1/3",
                    'time_remaining': time_remaining
                }
                
                # Update timers if needed
                self._update_timers(round_state, crew)
                
                # Get available actions for this participant
                available_actions = []
                if crew.current_stage == 'action':
                    if participant.role == 'navigator':
                        available_actions = [
                            {'type': 'do_nothing', 'label': 'Do Nothing', 'pu_cost': 0},
                            {'type': 'travel', 'label': 'Travel', 'pu_cost': 1},
                            {'type': 'send_probe', 'label': 'Send Probe', 'pu_cost': 1}
                        ]
                    elif participant.role == 'driller':
                        available_actions = [
                            {'type': 'do_nothing', 'label': 'Do Nothing', 'pu_cost': 0},
                            {'type': 'mine_shallow', 'label': 'Mine Shallow', 'pu_cost': 1},
                            {'type': 'mine_deep', 'label': 'Mine Deep', 'pu_cost': 2},
                            {'type': 'deploy_robot', 'label': 'Deploy Robot', 'pu_cost': 1}
                        ]
                
                # Get asteroid information
                asteroids = []
                for asteroid_name in ['Alpha', 'Beta', 'Gamma', 'Omega']:
                    try:
                        asteroid = Asteroid.objects.get(
                            name=asteroid_name,
                            session=crew.session
                        )
                        asteroid_info = {
                            'name': asteroid.name,
                            'travel_cost': asteroid.travel_cost,
                            'max_minerals': asteroid.max_minerals,
                            'shallow_cost': asteroid.shallow_cost,
                            'deep_cost': asteroid.deep_cost,
                            'mined': asteroid.mined
                        }
                        asteroids.append(asteroid_info)
                    except Asteroid.DoesNotExist:
                        pass
                
                # Communication status - Captain can send to anyone, Navigator/Driller can send to Captain
                if crew.current_stage == 'briefing':
                    if participant.role == 'captain':
                        can_communicate = True  # Captain can send to anyone
                    else:
                        can_communicate = True  # Navigator/Driller can send to Captain
                else:
                    can_communicate = False  # No communication outside briefing
                
                # All participants can receive messages during briefing
                can_receive_messages = (crew.current_stage == 'briefing')
                
                # Debug logging
                logger.info(f"Participant {participant.id} ({participant.role}) can_communicate: {can_communicate}")
                logger.info(f"Participant {participant.id} ({participant.role}) can_receive_messages: {can_receive_messages}")
                logger.info(f"Crew {crew.id} current_stage: {crew.current_stage}")
                
                # Get chat messages for this crew and round - be more explicit about broadcast messages
                chat_messages = ChatMessage.objects.filter(
                    round_state=round_state
                ).order_by('timestamp')
                
                # Debug logging for chat messages
                logger.info(f"Found {chat_messages.count()} chat messages for crew {crew.id}, round {crew.current_round}")
                logger.info(f"RoundState ID: {round_state.id}, Round Number: {round_state.round_number}")
                
                for msg in chat_messages:
                    logger.info(f"Chat message: id={msg.id}, from={msg.from_participant.role}, to_participant={msg.to_participant}, is_broadcast={msg.is_broadcast}, message='{msg.message[:50]}...'")
                
                # Format chat messages for display - simplify the logic
                formatted_messages = []
                for msg in chat_messages:
                    # For broadcast messages (to_participant=None), show to everyone
                    # For direct messages, show to sender and recipient
                    if msg.to_participant is None:  # Broadcast message
                        is_visible = True
                        logger.info(f"Broadcast message '{msg.message[:30]}...' is visible to {participant.role}")
                    elif msg.to_participant == participant or msg.from_participant == participant:
                        is_visible = True
                        logger.info(f"Direct message '{msg.message[:30]}...' is visible to {participant.role}")
                    else:
                        is_visible = False
                        logger.info(f"Message '{msg.message[:30]}...' is NOT visible to {participant.role}")
                    
                    if is_visible:
                        formatted_messages.append({
                            'sender': msg.from_participant.role.title(),
                            'message': msg.message,
                            'timestamp': msg.timestamp.strftime('%H:%M:%S'),
                            'is_own': msg.from_participant == participant
                        })
                
                logger.info(f"Formatted {len(formatted_messages)} messages for participant {participant.role}")
                
                # Additional debug info for Captain
                if participant.role == 'captain':
                    logger.info(f"Captain {participant.id} - Total messages: {chat_messages.count()}")
                    logger.info(f"Captain {participant.id} - Formatted messages: {len(formatted_messages)}")
                    for i, msg in enumerate(chat_messages):
                        logger.info(f"  Message {i+1}: from={msg.from_participant.role}, to={msg.to_participant.role if msg.to_participant else 'ALL'}, text='{msg.message[:30]}...'")
                
            except Exception as e:
                logger.error(f"Game engine error: {str(e)}")
                # Fallback if game engine fails
                game_summary = {
                    'current_round': crew.current_round,
                    'current_stage': crew.current_stage,
                    'pu_remaining': 4,
                    'total_minerals': 0,
                    'round_progress': f"{crew.current_round}/5",
                    'stage_progress': "1/3",
                    'time_remaining': 0
                }
                available_actions = []
                asteroids = []
                can_communicate = False
            
            context = {
                'participant': participant,
                'crew': crew,
                'game_summary': game_summary,
                'available_actions': available_actions,
                'asteroids': asteroids,
                'can_communicate': can_communicate,
                'can_receive_messages': can_receive_messages,
                'session_config': {
                    'pressure': crew.session.pressure,
                    'complexity': crew.session.complexity,
                    'captain_type': crew.session.captain_type
                },
                'chat_messages': formatted_messages
            }
            
            return render(request, 'spaceship_coordination/game.html', context)
            
        except Participant.DoesNotExist:
            return redirect('spaceship_coordination:waiting_room')
        except Exception as e:
            logger.error(f"Game view error: {str(e)}")
            return redirect('spaceship_coordination:waiting_room')
    
    def _update_timers(self, round_state, crew):
        """Update stage timers and advance stages when time runs out"""
        now = timezone.now()
        
        # Ensure crew and round_state are in sync
        if crew.current_stage != round_state.stage:
            round_state.stage = crew.current_stage
            round_state.stage_start_time = now
            round_state.save()
            logger.info(f"Crew {crew.id} stage synchronized: {crew.current_stage}")
        
        # Calculate time elapsed since stage start
        time_elapsed = (now - round_state.stage_start_time).total_seconds()
        
        # Get the total duration for current stage
        if crew.current_stage == 'briefing':
            total_duration = 180 if crew.session.pressure == 'low' else 90
            time_remaining = max(0, int(total_duration - time_elapsed))
            
            # Only advance when time actually runs out
            if time_remaining <= 0:
                crew.current_stage = 'action'
                crew.save()
                round_state.stage = 'action'
                round_state.stage_start_time = now
                round_state.action_time_remaining = 15
                round_state.save()
                logger.info(f"Crew {crew.id} advanced from briefing to action stage after {int(time_elapsed)}s")
            else:
                # Update the stored time remaining
                round_state.briefing_time_remaining = time_remaining
                round_state.save()
        
        elif crew.current_stage == 'action':
            total_duration = 15
            time_remaining = max(0, int(total_duration - time_elapsed))
            
            # Only advance when time actually runs out
            if time_remaining <= 0:
                crew.current_stage = 'result'
                crew.save()
                round_state.stage = 'result'
                round_state.stage_start_time = now
                round_state.result_time_remaining = 15
                round_state.save()
                logger.info(f"Crew {crew.id} advanced from action to result stage after {int(time_elapsed)}s")
            else:
                # Update the stored time remaining
                round_state.action_time_remaining = time_remaining
                round_state.save()
        
        elif crew.current_stage == 'result':
            total_duration = 15
            time_remaining = max(0, int(total_duration - time_elapsed))
            
            # Only advance when time actually runs out
            if time_remaining <= 0:
                if crew.current_round < 5:
                    crew.current_round += 1
                    crew.current_stage = 'briefing'
                    crew.save()
                    
                    # Create new round state with proper initial times
                    new_round_state = RoundState.objects.create(
                        crew=crew,
                        round_number=crew.current_round,
                        stage='briefing',
                        pu_remaining=4,
                        current_system=crew.current_system,
                        briefing_time_remaining=180 if crew.session.pressure == 'low' else 90,
                        action_time_remaining=15,
                        result_time_remaining=15,
                        stage_start_time=now
                    )
                    logger.info(f"Crew {crew.id} advanced to round {crew.current_round}")
                else:
                    # Game complete
                    crew.current_stage = 'completed'
                    crew.save()
                    logger.info(f"Crew {crew.id} completed the game")
            else:
                # Update the stored time remaining
                round_state.result_time_remaining = time_remaining
                round_state.save()


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
    """API endpoint for submitting game actions"""
    
    def post(self, request, crew_id):
        """Process action submission"""
        try:
            # Get participant from session
            participant_id = request.session.get('participant_id')
            if not participant_id:
                return JsonResponse({'success': False, 'error': 'No participant found'})
            
            participant = Participant.objects.get(participant_id=participant_id)
            crew = participant.crew
            
            if crew.id != crew_id:
                return JsonResponse({'success': False, 'error': 'Access denied'})
            
            # Parse action data
            data = json.loads(request.body)
            action_type = data.get('action_type')
            target_asteroid = data.get('target_asteroid')
            
            # Check if we're in action stage
            try:
                round_state = RoundState.objects.get(
                    crew=crew,
                    round_number=crew.current_round
                )
            except RoundState.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'No active round state'})
            
            if round_state.stage != 'action':
                return JsonResponse({'success': False, 'error': 'No active action stage'})
            
            # Calculate PU cost for the action
            pu_spent = 0
            if action_type == 'travel':
                pu_spent = 1
            elif action_type == 'send_probe':
                pu_spent = 1
            elif action_type == 'mine_shallow':
                pu_spent = 1
            elif action_type == 'mine_deep':
                pu_spent = 2
            elif action_type == 'deploy_robot':
                pu_spent = 1
            elif action_type == 'do_nothing':
                pu_spent = 0
            else:
                return JsonResponse({'success': False, 'error': 'Invalid action type'})
            
            # Check if participant has enough PU
            if round_state.pu_remaining < pu_spent:
                return JsonResponse({'success': False, 'error': f'Not enough PU. Required: {pu_spent}, Available: {round_state.pu_remaining}'})
            
            # Check sequential action order: Navigator first, then Driller
            if participant.role == 'driller':
                # Check if navigator has acted first
                navigator_action = Action.objects.filter(
                    round_state=round_state,
                    participant__role='navigator'
                ).first()
                
                if not navigator_action:
                    return JsonResponse({'success': False, 'error': 'Navigator must act first before Driller can act'})
            
            # Create the action
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
            
            # Process specific actions
            if action_type == 'travel' and target_asteroid:
                crew.current_system = target_asteroid
                crew.save()
                round_state.current_system = target_asteroid
                round_state.save()
                logger.info(f"Navigator {participant.id} traveled to {target_asteroid}")
            elif action_type == 'send_probe' and target_asteroid:
                logger.info(f"Navigator {participant.id} sent probe to {target_asteroid}")
            elif action_type == 'deploy_robot' and target_asteroid:
                logger.info(f"Driller {participant.id} deployed robot to {target_asteroid}")
            elif action_type == 'mine_shallow' and target_asteroid:
                try:
                    asteroid = Asteroid.objects.get(
                        name=target_asteroid,
                        session=crew.session
                    )
                    if not asteroid.mined:
                        # Mark asteroid as mined
                        asteroid.mined = True
                        asteroid.mined_round = crew.current_round
                        asteroid.save()
                        
                        # Create outcome (simplified for now)
                        Outcome.objects.create(
                            round_state=round_state,
                            asteroid=asteroid,
                            participant=participant,
                            action=action,
                            minerals_gained=asteroid.max_minerals // 2,  # Simplified
                            full_extraction=False,
                            partial_fraction=0.5,
                            probability_basis={},
                            depth='shallow',
                            intel_combo='none'
                        )
                        logger.info(f"Driller {participant.id} mined {target_asteroid} (shallow)")
                except Asteroid.DoesNotExist:
                    pass
            elif action_type == 'mine_deep' and target_asteroid:
                try:
                    asteroid = Asteroid.objects.get(
                        name=target_asteroid,
                        session=crew.session
                    )
                    if not asteroid.mined:
                        # Mark asteroid as mined
                        asteroid.mined = True
                        asteroid.mined_round = crew.current_round
                        asteroid.save()
                        
                        # Create outcome (simplified for now)
                        Outcome.objects.create(
                            round_state=round_state,
                            asteroid=asteroid,
                            action=action,
                            minerals_gained=asteroid.max_minerals,  # Full extraction for deep mining
                            full_extraction=True,
                            partial_fraction=1.0,
                            probability_basis={},
                            depth='deep',
                            intel_combo='none'
                        )
                        logger.info(f"Driller {participant.id} mined {target_asteroid} (deep)")
                except Asteroid.DoesNotExist:
                    pass
            elif action_type == 'do_nothing':
                logger.info(f"{participant.role.title()} {participant.id} chose to do nothing")
            
            # If this was the navigator's action, enable driller actions
            if participant.role == 'navigator':
                logger.info(f"Navigator {participant.id} completed action, driller can now act")
            elif participant.role == 'driller':
                logger.info(f"Driller {participant.id} completed action, round actions complete")
            
            return JsonResponse({
                'success': True,
                'action_id': action.id,
                'pu_remaining': round_state.pu_remaining,
                'message': f'{participant.role.title()} action completed successfully'
            })
                
        except Participant.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Participant not found'})
        except Exception as e:
            logger.error(f"Action submission error: {str(e)}")
            return JsonResponse({'success': False, 'error': 'An error occurred'})


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
            try:
                round_state = RoundState.objects.get(
                    crew=crew,
                    round_number=crew.current_round
                )
                logger.info(f"ChatMessageView: Found RoundState ID={round_state.id}, round_number={round_state.round_number}, crew={crew.id}")
            except RoundState.DoesNotExist:
                logger.error(f"ChatMessageView: No RoundState found for crew {crew.id}, round {crew.current_round}")
                return JsonResponse({'error': 'No active round state'}, status=400)
            
            # Check if we're in briefing stage
            if crew.current_stage != 'briefing':
                logger.error(f"ChatMessageView: Not in briefing stage, current_stage={crew.current_stage}")
                return JsonResponse({'error': 'No active briefing stage'}, status=400)
            
            # Create chat message based on to_role
            if to_role == 'all':
                # Broadcast message - visible to all team members
                chat_message = ChatMessage.objects.create(
                    from_participant=from_participant,
                    to_participant=None,  # None means visible to all
                    round_state=round_state,
                    message=message,
                    stage_only='briefing'
                )
            elif to_role == 'captain':
                # Direct message to Captain
                captain = crew.participant_set.filter(role='captain').first()
                if captain:
                    chat_message = ChatMessage.objects.create(
                        from_participant=from_participant,
                        to_participant=captain,  # Direct to Captain
                        round_state=round_state,
                        message=message,
                        stage_only='briefing'
                    )
                else:
                    return JsonResponse({'error': 'Captain not found'}, status=400)
            elif to_role == 'navigator':
                # Direct message to Navigator
                navigator = crew.participant_set.filter(role='navigator').first()
                if navigator:
                    chat_message = ChatMessage.objects.create(
                        from_participant=from_participant,
                        to_participant=navigator,  # Direct to Navigator
                        round_state=round_state,
                        message=message,
                        stage_only='briefing'
                    )
                else:
                    return JsonResponse({'error': 'Navigator not found'}, status=400)
            elif to_role == 'driller':
                # Direct message to Driller
                driller = crew.participant_set.filter(role='driller').first()
                if driller:
                    chat_message = ChatMessage.objects.create(
                        from_participant=from_participant,
                        to_participant=driller,  # Direct to Driller
                        round_state=round_state,
                        message=message,
                        stage_only='briefing'
                    )
                else:
                    return JsonResponse({'error': 'Driller not found'}, status=400)
            else:
                return JsonResponse({'error': f'Invalid to_role: {to_role}. Valid values are: all, captain, navigator, driller'}, status=400)
            
            # Debug logging - test the is_broadcast property
            logger.info(f"Created chat message: id={chat_message.id}, from={from_participant.role}, to_participant={chat_message.to_participant}, is_broadcast={chat_message.is_broadcast}, message='{message[:50]}...'")
            logger.info(f"Direct property check: to_participant is None = {chat_message.to_participant is None}")
            
            # Verify the message was created correctly
            chat_message.refresh_from_db()
            logger.info(f"After refresh: to_participant={chat_message.to_participant}, is_broadcast={chat_message.is_broadcast}")
            
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
    
    def get(self, request, crew_id):
        """Get chat messages for a crew"""
        try:
            # Get participant from session
            participant_id = request.session.get('participant_id')
            if not participant_id:
                return JsonResponse({'error': 'Not authenticated'}, status=401)
            
            participant = Participant.objects.get(participant_id=participant_id)
            crew = participant.crew
            
            if crew.id != crew_id:
                return JsonResponse({'error': 'Access denied'}, status=403)
            
            # Get current round state
            try:
                round_state = RoundState.objects.get(
                    crew=crew,
                    round_number=crew.current_round
                )
            except RoundState.DoesNotExist:
                return JsonResponse({'error': 'No active round state'}, status=400)
            
            # Get chat messages for this crew and round
            chat_messages = ChatMessage.objects.filter(
                round_state=round_state
            ).order_by('timestamp')
            
            # Format chat messages for display
            formatted_messages = []
            for msg in chat_messages:
                # For broadcast messages (to_participant=None), show to everyone
                # For direct messages, show to sender and recipient
                if msg.to_participant is None:  # Broadcast message
                    is_visible = True
                elif msg.to_participant == participant or msg.from_participant == participant:
                    is_visible = True
                else:
                    is_visible = False
                
                if is_visible:
                    formatted_messages.append({
                        'sender': msg.from_participant.role.title(),
                        'message': msg.message,
                        'timestamp': msg.timestamp.strftime('%H:%M:%S'),
                        'is_own': msg.from_participant == participant
                    })
            
            return JsonResponse({
                'success': True,
                'messages': formatted_messages
            })
            
        except Participant.DoesNotExist:
            return JsonResponse({'error': 'Participant not found'}, status=404)
        except Exception as e:
            logger.error(f"Error getting chat messages: {str(e)}")
            return JsonResponse({'error': 'Internal server error'}, status=500)


class RoundStatusView(View):
    """API endpoint for round status"""
    
    def get(self, request, crew_id, round_number):
        """Get status of a specific round"""
        try:
            crew = get_object_or_404(Crew, id=crew_id)
            round_state = RoundState.objects.get(
                crew=crew,
                round_number=round_number
            )
            
            # Get actions for this round
            actions = Action.objects.filter(round_state=round_state)
            
            return JsonResponse({
                'round_number': round_number,
                'stage': round_state.stage,
                'pu_remaining': round_state.pu_remaining,
                'current_system': round_state.current_system,
                'actions': [
                    {
                        'participant': action.participant.role,
                        'action_type': action.action_type,
                        'target': action.target_asteroid,
                        'pu_spent': action.pu_spent
                    }
                    for action in actions
                ]
            })
            
        except (Crew.DoesNotExist, RoundState.DoesNotExist):
            return JsonResponse({'error': 'Round not found'}, status=404)
        except Exception as e:
            logger.error(f"Round status error: {str(e)}")
            return JsonResponse({'error': 'Internal server error'}, status=500)


class NavigatorStatusView(View):
    """API endpoint to check if navigator has acted"""
    
    def get(self, request, crew_id):
        """Check if navigator has submitted an action in current round"""
        try:
            crew = get_object_or_404(Crew, id=crew_id)
            
            # Get current round state
            try:
                round_state = RoundState.objects.get(
                    crew=crew,
                    round_number=crew.current_round
                )
            except RoundState.DoesNotExist:
                return JsonResponse({'navigator_acted': False})
            
            # Check if navigator has submitted any action
            navigator_action = Action.objects.filter(
                round_state=round_state,
                participant__role='navigator'
            ).first()
            
            return JsonResponse({
                'navigator_acted': navigator_action is not None,
                'navigator_action': navigator_action.action_type if navigator_action else None
            })
            
        except Crew.DoesNotExist:
            return JsonResponse({'error': 'Crew not found'}, status=404)
        except Exception as e:
            logger.error(f"Navigator status error: {str(e)}")
            return JsonResponse({'error': 'Internal server error'}, status=500)


class CrewStatusView(View):
    """API endpoint to get current crew status for timer system"""
    
    def get(self, request, crew_id):
        """Get current crew status without full page refresh"""
        try:
            crew = get_object_or_404(Crew, id=crew_id)
            
            return JsonResponse({
                'current_stage': crew.current_stage,
                'current_round': crew.current_round,
                'current_system': crew.current_system
            })
            
        except Crew.DoesNotExist:
            return JsonResponse({'error': 'Crew not found'}, status=404)
        except Exception as e:
            logger.error(f"Crew status error: {str(e)}")
            return JsonResponse({'error': 'Internal server error'}, status=500)


class TimerSyncView(View):
    """API endpoint to get synchronized timer information"""
    
    def get(self, request, crew_id):
        """Get synchronized timer info for all players"""
        try:
            crew = get_object_or_404(Crew, id=crew_id)
            
            # Get current round state
            try:
                round_state = RoundState.objects.get(
                    crew=crew,
                    round_number=crew.current_round
                )
            except RoundState.DoesNotExist:
                return JsonResponse({'error': 'No active round state'}, status=404)
            
            # Update timers first
            game_view = GameView()
            game_view._update_timers(round_state, crew)
            
            # Refresh crew and round_state after potential updates
            crew.refresh_from_db()
            round_state.refresh_from_db()
            
            # Calculate remaining time using the same logic as _update_timers
            now = timezone.now()
            time_elapsed = (now - round_state.stage_start_time).total_seconds()
            
            if crew.current_stage == 'briefing':
                total_duration = 180 if crew.session.pressure == 'low' else 90
                time_remaining = max(0, int(total_duration - time_elapsed))
            elif crew.current_stage == 'action':
                total_duration = 15
                time_remaining = max(0, int(total_duration - time_elapsed))
            elif crew.current_stage == 'result':
                total_duration = 15
                time_remaining = max(0, int(total_duration - time_elapsed))
            else:
                time_remaining = 0
            
            return JsonResponse({
                'current_stage': crew.current_stage,
                'current_round': crew.current_round,
                'time_remaining': time_remaining,
                'stage_start_time': round_state.stage_start_time.isoformat(),
                'pu_remaining': round_state.pu_remaining
            })
            
        except Crew.DoesNotExist:
            return JsonResponse({'error': 'Crew not found'}, status=404)
        except Exception as e:
            logger.error(f"Timer sync error: {str(e)}")
            return JsonResponse({'error': 'Internal server error'}, status=500)


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


