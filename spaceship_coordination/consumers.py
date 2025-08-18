"""
WebSocket consumers for real-time game communication
"""

import json
import logging
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from .models import *
from .game_logic import GameEngine
from .ai_captain import AICaptain

logger = logging.getLogger(__name__)


class GameConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time game updates"""
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.crew_id = self.scope['url_route']['kwargs']['crew_id']
        self.crew_group_name = f'crew_{self.crew_id}'
        
        # Join crew group
        await self.channel_layer.group_add(
            self.crew_group_name,
            self.channel_name
        )
        
        # Accept connection
        await self.accept()
        
        # Send initial game state
        await self.send_game_state()
        
        logger.info(f"WebSocket connected for crew {self.crew_id}")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave crew group
        await self.channel_layer.group_discard(
            self.crew_group_name,
            self.channel_name
        )
        
        # Handle participant disconnect
        await self.handle_disconnect()
        
        logger.info(f"WebSocket disconnected for crew {self.crew_id}")
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'action_submit':
                await self.handle_action_submit(data)
            elif message_type == 'get_game_state':
                await self.send_game_state()
            elif message_type == 'ping':
                await self.send(json.dumps({'type': 'pong'}))
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Internal server error'
            }))
    
    async def handle_chat_message(self, data):
        """Handle chat message from participant"""
        try:
            message = data.get('message', '').strip()
            to_role = data.get('to_role')
            
            if not message or not to_role:
                await self.send(json.dumps({
                    'type': 'error',
                    'message': 'Invalid chat message data'
                }))
                return
            
            # Save chat message to database
            chat_message = await self.save_chat_message(message, to_role)
            
            if chat_message:
                # Broadcast to crew group
                await self.channel_layer.group_send(
                    self.crew_group_name,
                    {
                        'type': 'chat_message',
                        'message': message,
                        'from_role': chat_message['from_role'],
                        'to_role': to_role,
                        'timestamp': chat_message['timestamp']
                    }
                )
            else:
                await self.send(json.dumps({
                    'type': 'error',
                    'message': 'Failed to save chat message'
                }))
                
        except Exception as e:
            logger.error(f"Error handling chat message: {str(e)}")
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Failed to process chat message'
            }))
    
    async def handle_action_submit(self, data):
        """Handle action submission from participant"""
        try:
            action_type = data.get('action_type')
            target_asteroid = data.get('target_asteroid')
            pu_spent = data.get('pu_spent', 0)
            
            if not action_type:
                await self.send(json.dumps({
                    'type': 'error',
                    'message': 'Action type is required'
                }))
                return
            
            # Submit action to game engine
            success, message = await self.submit_action(
                action_type, target_asteroid, pu_spent
            )
            
            if success:
                # Broadcast action to crew group
                await self.channel_layer.group_send(
                    self.crew_group_name,
                    {
                        'type': 'action_submitted',
                        'action_type': action_type,
                        'target_asteroid': target_asteroid,
                        'pu_spent': pu_spent,
                        'message': message
                    }
                )
                
                # Check if all actions are submitted
                await self.check_round_completion()
            else:
                await self.send(json.dumps({
                    'type': 'error',
                    'message': message
                }))
                
        except Exception as e:
            logger.error(f"Error handling action submit: {str(e)}")
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Failed to process action'
            }))
    
    async def chat_message(self, event):
        """Send chat message to WebSocket"""
        await self.send(json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'from_role': event['from_role'],
            'to_role': event['to_role'],
            'timestamp': event['timestamp']
        }))
    
    async def action_submitted(self, event):
        """Send action submission notification to WebSocket"""
        await self.send(json.dumps({
            'type': 'action_submitted',
            'action_type': event['action_type'],
            'target_asteroid': event['target_asteroid'],
            'pu_spent': event['pu_spent'],
            'message': event['message']
        }))
    
    async def game_state_update(self, event):
        """Send game state update to WebSocket"""
        await self.send(json.dumps({
            'type': 'game_state_update',
            'data': event['data']
        }))
    
    async def round_stage_change(self, event):
        """Send round stage change notification to WebSocket"""
        await self.send(json.dumps({
            'type': 'round_stage_change',
            'stage': event['stage'],
            'round_number': event['round_number'],
            'time_remaining': event['time_remaining']
        }))
    
    async def game_complete(self, event):
        """Send game completion notification to WebSocket"""
        await self.send(json.dumps({
            'type': 'game_complete',
            'results': event['results']
        }))
    
    async def crew_disconnect(self, event):
        """Send crew disconnect notification to WebSocket"""
        await self.send(json.dumps({
            'type': 'crew_disconnect',
            'message': 'One of your crew members has disconnected. Game will be cancelled.',
            'redirect_url': '/spaceship/cancelled/'
        }))
    
    @database_sync_to_async
    def save_chat_message(self, message, to_role):
        """Save chat message to database"""
        try:
            # Get current round state
            crew = Crew.objects.get(id=self.crew_id)
            round_state = RoundState.objects.filter(
                crew=crew,
                stage='briefing'
            ).first()
            
            if not round_state:
                return None
            
            # For now, assume the sender is the captain (this would need proper participant identification)
            from_participant = crew.captain
            to_participant = None
            
            if to_role == 'navigator':
                to_participant = crew.navigator
            elif to_role == 'driller':
                to_participant = crew.driller
            
            if not from_participant or not to_participant:
                return None
            
            # Create chat message
            chat_message = ChatMessage.objects.create(
                from_participant=from_participant,
                to_participant=to_participant,
                round_state=round_state,
                message=message,
                stage_only='briefing'
            )
            
            return {
                'from_role': from_participant.role,
                'to_role': to_role,
                'timestamp': chat_message.timestamp.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error saving chat message: {str(e)}")
            return None
    
    @database_sync_to_async
    def submit_action(self, action_type, target_asteroid, pu_spent):
        """Submit action to game engine"""
        try:
            crew = Crew.objects.get(id=self.crew_id)
            game_engine = GameEngine(crew)
            
            # For now, assume the participant is the navigator (this would need proper participant identification)
            participant = crew.navigator
            if not participant:
                participant = crew.driller
            
            if not participant:
                return False, "No participant found"
            
            # Submit action
            success, message = game_engine.submit_action(
                participant, action_type, target_asteroid, pu_spent
            )
            
            return success, message
            
        except Exception as e:
            logger.error(f"Error submitting action: {str(e)}")
            return False, f"Error: {str(e)}"
    
    @database_sync_to_async
    def check_round_completion(self):
        """Check if all participants have submitted actions"""
        try:
            crew = Crew.objects.get(id=self.crew_id)
            round_state = RoundState.objects.filter(
                crew=crew,
                stage='action'
            ).first()
            
            if not round_state:
                return
            
            # Count submitted actions
            action_count = Action.objects.filter(round_state=round_state).count()
            expected_count = 2  # Navigator and Driller
            
            if action_count >= expected_count:
                # All actions submitted, move to result stage
                game_engine = GameEngine(crew)
                game_engine.start_result_stage(round_state)
                
                # Broadcast stage change
                await self.channel_layer.group_send(
                    self.crew_group_name,
                    {
                        'type': 'round_stage_change',
                        'stage': 'result',
                        'round_number': crew.current_round,
                        'time_remaining': 15
                    }
                )
                
        except Exception as e:
            logger.error(f"Error checking round completion: {str(e)}")
    
    @database_sync_to_async
    def send_game_state(self):
        """Send current game state to WebSocket"""
        try:
            crew = Crew.objects.get(id=self.crew_id)
            
            # Get current round state
            round_state = RoundState.objects.filter(
                crew=crew
            ).order_by('-round_number').first()
            
            if not round_state:
                return
            
            # Get game summary
            game_engine = GameEngine(crew)
            game_summary = game_engine.get_game_summary()
            
            # Get visible asteroids for each role
            asteroids = Asteroid.objects.filter(session=crew.session)
            asteroid_info = []
            
            for asteroid in asteroids:
                info = {
                    'name': asteroid.name,
                    'travel_cost': asteroid.travel_cost,
                    'max_minerals': None,
                    'shallow_cost': None,
                    'deep_cost': None,
                    'mined': asteroid.mined
                }
                
                # Show intel based on complexity
                if crew.session.complexity == 'low':
                    # Low complexity: share all discovered intel
                    if asteroid.discovered_by:
                        info['max_minerals'] = asteroid.max_minerals
                        info['auto_populated'] = True
                    
                    # Check if robot has been deployed
                    robot_deployed = Action.objects.filter(
                        round_state__crew=crew,
                        action_type='deploy_robot',
                        target_asteroid=asteroid.name
                    ).exists()
                    
                    if robot_deployed:
                        info['shallow_cost'] = asteroid.shallow_cost
                        info['deep_cost'] = asteroid.deep_cost
                        info['auto_populated'] = True
                else:
                    # High complexity: intel remains private
                    # This would need to be filtered based on the specific participant
                    pass
                
                asteroid_info.append(info)
            
            game_state = {
                'crew_id': crew.id,
                'current_round': crew.current_round,
                'current_stage': crew.current_stage,
                'current_system': crew.current_system,
                'pu_remaining': round_state.pu_remaining if round_state else 4,
                'asteroids': asteroid_info,
                'game_summary': game_summary,
                'session_config': {
                    'pressure': crew.session.pressure,
                    'complexity': crew.session.complexity,
                    'captain_type': crew.session.captain_type
                }
            }
            
            await self.send(json.dumps({
                'type': 'game_state',
                'data': game_state
            }))
            
        except Exception as e:
            logger.error(f"Error sending game state: {str(e)}")
    
    @database_sync_to_async
    def handle_disconnect(self):
        """Handle participant disconnect"""
        try:
            crew = Crew.objects.get(id=self.crew_id)
            
            # Log disconnect event
            SystemEvent.objects.create(
                crew=crew,
                event_type='disconnect',
                details={'timestamp': datetime.now().isoformat()}
            )
            
            # Check if this should trigger game cancellation
            # For now, just log the event
            
        except Exception as e:
            logger.error(f"Error handling disconnect: {str(e)}")


class AdminConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for admin monitoring"""
    
    async def connect(self):
        """Handle admin WebSocket connection"""
        # Check if user is admin (this would need proper authentication)
        if not self.scope['user'].is_staff:
            await self.close()
            return
        
        self.admin_group_name = 'admin_monitoring'
        
        # Join admin group
        await self.channel_layer.group_add(
            self.admin_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send current system status
        await self.send_system_status()
        
        logger.info("Admin WebSocket connected")
    
    async def disconnect(self, close_code):
        """Handle admin WebSocket disconnection"""
        await self.channel_layer.group_discard(
            self.admin_group_name,
            self.channel_name
        )
        
        logger.info("Admin WebSocket disconnected")
    
    async def receive(self, text_data):
        """Handle admin commands"""
        try:
            data = json.loads(text_data)
            command = data.get('command')
            
            if command == 'get_system_status':
                await self.send_system_status()
            elif command == 'get_crew_status':
                crew_id = data.get('crew_id')
                await self.send_crew_status(crew_id)
            elif command == 'pause_round':
                crew_id = data.get('crew_id')
                await self.pause_round(crew_id)
            elif command == 'kick_user':
                crew_id = data.get('crew_id')
                user_id = data.get('user_id')
                await self.kick_user(crew_id, user_id)
            else:
                await self.send(json.dumps({
                    'type': 'error',
                    'message': 'Unknown command'
                }))
                
        except Exception as e:
            logger.error(f"Error processing admin command: {str(e)}")
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Internal server error'
            }))
    
    @database_sync_to_async
    def send_system_status(self):
        """Send overall system status to admin"""
        try:
            # Get system statistics
            total_crews = Crew.objects.count()
            active_crews = Crew.objects.filter(current_stage__in=['briefing', 'action', 'result']).count()
            total_participants = Participant.objects.count()
            active_sessions = ExperimentSession.objects.filter(completed=False).count()
            
            status = {
                'total_crews': total_crews,
                'active_crews': active_crews,
                'total_participants': total_participants,
                'active_sessions': active_sessions,
                'timestamp': datetime.now().isoformat()
            }
            
            await self.send(json.dumps({
                'type': 'system_status',
                'data': status
            }))
            
        except Exception as e:
            logger.error(f"Error sending system status: {str(e)}")
    
    @database_sync_to_async
    def send_crew_status(self, crew_id):
        """Send specific crew status to admin"""
        try:
            crew = Crew.objects.get(id=crew_id)
            
            # Get crew details
            crew_status = {
                'id': crew.id,
                'room_id': crew.room_id,
                'current_round': crew.current_round,
                'current_stage': crew.current_stage,
                'current_system': crew.current_system,
                'created_at': crew.created_at.isoformat(),
                'participants': {
                    'captain': crew.captain.role if crew.captain else None,
                    'navigator': crew.navigator.role if crew.navigator else None,
                    'driller': crew.driller.role if crew.driller else None
                }
            }
            
            await self.send(json.dumps({
                'type': 'crew_status',
                'data': crew_status
            }))
            
        except Crew.DoesNotExist:
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Crew not found'
            }))
        except Exception as e:
            logger.error(f"Error sending crew status: {str(e)}")
    
    @database_sync_to_async
    def pause_round(self, crew_id):
        """Pause a specific crew's round"""
        try:
            crew = Crew.objects.get(id=crew_id)
            
            # Log pause event
            SystemEvent.objects.create(
                crew=crew,
                event_type='pause_round',
                details={'timestamp': datetime.now().isoformat(), 'admin_action': True}
            )
            
            await self.send(json.dumps({
                'type': 'round_paused',
                'crew_id': crew_id,
                'message': 'Round paused successfully'
            }))
            
        except Crew.DoesNotExist:
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Crew not found'
            }))
        except Exception as e:
            logger.error(f"Error pausing round: {str(e)}")
    
    @database_sync_to_async
    def kick_user(self, crew_id, user_id):
        """Kick a user from a crew"""
        try:
            crew = Crew.objects.get(id=crew_id)
            participant = Participant.objects.get(id=user_id, crew=crew)
            
            # Log kick event
            SystemEvent.objects.create(
                crew=crew,
                event_type='kick_user',
                participant=participant,
                details={'timestamp': datetime.now().isoformat(), 'admin_action': True}
            )
            
            await self.send(json.dumps({
                'type': 'user_kicked',
                'crew_id': crew_id,
                'user_id': user_id,
                'message': 'User kicked successfully'
            }))
            
        except (Crew.DoesNotExist, Participant.DoesNotExist):
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Crew or user not found'
            }))
        except Exception as e:
            logger.error(f"Error kicking user: {str(e)}")




