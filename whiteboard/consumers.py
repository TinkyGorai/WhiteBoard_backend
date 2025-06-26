import json
from channels.generic.websocket import AsyncWebsocketConsumer
import uuid
from channels.db import database_sync_to_async
from collections import defaultdict

# In-memory store for drawing history per room.
room_history = {}
redo_history = defaultdict(lambda: defaultdict(list))  # redo_history[room_id][user_id] = stack
user_cursors = {}  # Store user cursor positions
user_laser_pointers = {}  # Store laser pointer positions
user_permissions = {}  # Store user permissions per room

class WhiteboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'whiteboard_{self.room_id}'
        query_string = self.scope.get('query_string', b'').decode('utf-8')
        import urllib.parse
        query_params = urllib.parse.parse_qs(query_string)
        provided_user_id = query_params.get('user_id', [None])[0]
        self.user_id = provided_user_id or str(uuid.uuid4())
        self.username = self.scope.get('user', {}).get('username', 'Anonymous')
        
        print(f"🔌 WebSocket connecting to room: {self.room_id}")
        print(f"🔌 User ID: {self.user_id}, Username: {self.username}")
        
        # Get permission from query parameters if available
        query_string = self.scope.get('query_string', b'').decode('utf-8')
        import urllib.parse
        query_params = urllib.parse.parse_qs(query_string)
        requested_permission = query_params.get('permission', ['view'])[0] if query_params.get('permission') else 'view'
        
        print(f"🔌 Requested permission: {requested_permission}")
        
        # Initialize history for the room if it doesn't exist
        if self.room_id not in room_history:
            room_history[self.room_id] = []
            user_cursors[self.room_id] = {}
            user_laser_pointers[self.room_id] = {}
            user_permissions[self.room_id] = {}
        
        # Check user permissions
        if not await self.check_user_permissions():
            print(f"❌ Closing connection, room '{self.room_id}' not found or permission check failed.")
            await self.close(code=4004)
            return
        
        # Override permission if requested and user is not authenticated (anonymous sharing)
        if not self.scope.get('user') or not self.scope.get('user').is_authenticated:
            if requested_permission in ['view', 'edit']:
                user_permissions[self.room_id][self.user_id] = requested_permission
        
        print(f"🔌 Final permission: {user_permissions.get(self.room_id, {}).get(self.user_id, 'none')}")
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        print(f"✅ WebSocket connection accepted for room: {self.room_id}")

        # Send full board state to the newly connected user
        await self.send(text_data=json.dumps({
            'type': 'board_state',
            'history': room_history.get(self.room_id, []),
            'canUndo': len(room_history.get(self.room_id, [])) > 0,
            'canRedo': len(redo_history[self.room_id][self.user_id]) > 0,
            'user_permission': user_permissions.get(self.room_id, {}).get(self.user_id, 'view'),
        }))
        
        # Notify others that user joined
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_joined',
                'user_id': self.user_id,
                'username': self.username,
                'permission': user_permissions.get(self.room_id, {}).get(self.user_id, 'view')
            }
        )

    @database_sync_to_async
    def _get_room_from_db(self):
        """
        Asynchronously fetches a room from the database by room_code or UUID.
        This is decorated to handle running synchronous Django ORM code in an async context.
        """
        from .models import Room
        from django.core.exceptions import ValidationError

        room = None
        try:
            # Prioritize lookup by the more common room_code
            room = Room.objects.get(room_code=self.room_id)
            print(f"🔍 Found room by room_code: {room.name}")
        except (Room.DoesNotExist, ValidationError):
            try:
                # Fallback to UUID if the room_code lookup fails
                room = Room.objects.get(id=self.room_id)
                print(f"🔍 Found room by UUID: {room.name}")
            except (Room.DoesNotExist, ValidationError):
                print(f"❌ Room '{self.room_id}' not found by either code or UUID.")
                return None
        return room

    @database_sync_to_async
    def _get_participant_from_db(self, room, user):
        """
        Asynchronously fetches a participant from a room.
        """
        if not user.is_authenticated:
            return None
        from .models import RoomParticipant
        try:
            return room.participants.get(user=user)
        except RoomParticipant.DoesNotExist:
            return None

    async def check_user_permissions(self):
        """
        Asynchronously checks user permissions by calling async helper methods for DB access.
        Returns False if the room is not found, True otherwise.
        """
        room = await self._get_room_from_db()
        if room is None:
            return False

        user = self.scope.get('user')
        print(f"🔍 User: {user}, Authenticated: {user and user.is_authenticated}")

        if not user or not user.is_authenticated:
            if room.is_public:
                if not user_permissions.get(self.room_id, {}):
                    user_permissions[self.room_id][self.user_id] = 'edit'
                    print(f"🎨 First anonymous user in room {self.room_id} gets edit permission")
                else:
                    user_permissions[self.room_id][self.user_id] = 'view'
                    print(f"👁️ Subsequent anonymous user gets view permission")
            else:
                user_permissions[self.room_id][self.user_id] = 'none'
                print(f"🚫 Private room access denied for anonymous user")
        else:
            if room.created_by == user:
                user_permissions[self.room_id][self.user_id] = 'admin'
                print(f"👑 Room creator gets admin permission")
            else:
                participant = await self._get_participant_from_db(room, user)
                if participant:
                    user_permissions[self.room_id][self.user_id] = participant.permission
                    print(f"👤 Participant gets {participant.permission} permission")
                elif room.is_public:
                    user_permissions[self.room_id][self.user_id] = 'view'
                    print(f"👁️ Public room access for authenticated user")
                else:
                    user_permissions[self.room_id][self.user_id] = 'none'
                    print(f"🚫 Private room access denied for authenticated user")
        return True

    def can_edit(self):
        """Check if current user can edit the room"""
        permission = user_permissions.get(self.room_id, {}).get(self.user_id, 'none')
        return permission in ['edit', 'admin']

    def can_admin(self):
        """Check if current user has admin permissions"""
        permission = user_permissions.get(self.room_id, {}).get(self.user_id, 'none')
        return permission == 'admin'

    async def disconnect(self, close_code):
        # Remove user from cursors and laser pointers
        if self.room_id in user_cursors and self.user_id in user_cursors[self.room_id]:
            del user_cursors[self.room_id][self.user_id]
        if self.room_id in user_laser_pointers and self.user_id in user_laser_pointers[self.room_id]:
            del user_laser_pointers[self.room_id][self.user_id]
        
        # Notify others that user left
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_left',
                'user_id': self.user_id,
                'username': self.username
            }
        )
        
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'draw':
            await self.handle_draw(data)
        elif message_type == 'shape':
            await self.handle_shape(data)
        elif message_type == 'text':
            await self.handle_text(data)
        elif message_type == 'cursor_move':
            await self.handle_cursor_move(data)
        elif message_type == 'laser_pointer':
            await self.handle_laser_pointer(data)
        elif message_type == 'clear_canvas':
            await self.handle_clear_canvas(data)
        elif message_type == 'undo':
            await self.handle_undo()
        elif message_type == 'redo':
            await self.handle_redo()

    async def handle_draw(self, data):
        # Check if user has edit permissions
        if not self.can_edit():
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'You do not have permission to draw in this room'
            }))
            return
        
        event_to_broadcast = {
            'type': 'draw_message',
            'drawing_data': {
                'tool_type': data.get('tool_type', 'pen'),
                'color': data.get('color', '#000000'),
                'stroke_width': data.get('stroke_width', 2),
                'data': data.get('data', {}),
                'user_id': self.user_id
            }
        }
        event_to_store = {
            'type': 'draw',
            'drawing': event_to_broadcast['drawing_data'],
            'user_id': self.user_id
        }
        
        if self.room_id in room_history:
            room_history[self.room_id].append(event_to_store)
            redo_history[self.room_id][self.user_id].clear()
            print(f"[DEBUG] room_history[{self.room_id}] after draw: {room_history[self.room_id]}")
            print(f"[DEBUG] redo_history[{self.room_id}][{self.user_id}] cleared")

        # Broadcast the drawing action
        await self.channel_layer.group_send(self.room_group_name, event_to_broadcast)
        # Broadcast the new history status
        await self.broadcast_history_status()

    async def handle_shape(self, data):
        # Check if user has edit permissions
        if not self.can_edit():
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'You do not have permission to draw in this room'
            }))
            return
        
        event_to_broadcast = {
            'type': 'shape_message',
            'shape_data': {
                'shape_type': data.get('shape_type', 'rectangle'),
                'color': data.get('color', '#000000'),
                'stroke_width': data.get('stroke_width', 2),
                'fill_color': data.get('fill_color', 'transparent'),
                'data': data.get('data', {}),
                'user_id': self.user_id
            }
        }
        event_to_store = {
            'type': 'shape',
            'shape': event_to_broadcast['shape_data'],
            'user_id': self.user_id
        }
        
        if self.room_id in room_history:
            room_history[self.room_id].append(event_to_store)
            redo_history[self.room_id][self.user_id].clear()
            print(f"[DEBUG] room_history[{self.room_id}] after shape: {room_history[self.room_id]}")
            print(f"[DEBUG] redo_history[{self.room_id}][{self.user_id}] cleared")

        await self.channel_layer.group_send(self.room_group_name, event_to_broadcast)
        await self.broadcast_history_status()

    async def handle_text(self, data):
        # Check if user has edit permissions
        if not self.can_edit():
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'You do not have permission to add text in this room'
            }))
            return
        
        event_to_broadcast = {
            'type': 'text_message',
            'text_data': {
                'text': data.get('text', ''),
                'color': data.get('color', '#000000'),
                'font_size': data.get('font_size', 16),
                'position': data.get('position', {'x': 0, 'y': 0}),
                'user_id': self.user_id
            }
        }
        event_to_store = {
            'type': 'text',
            'text': event_to_broadcast['text_data'],
            'user_id': self.user_id
        }
        
        if self.room_id in room_history:
            room_history[self.room_id].append(event_to_store)
            redo_history[self.room_id][self.user_id].clear()
            print(f"[DEBUG] room_history[{self.room_id}] after text: {room_history[self.room_id]}")
            print(f"[DEBUG] redo_history[{self.room_id}][{self.user_id}] cleared")

        await self.channel_layer.group_send(self.room_group_name, event_to_broadcast)
        await self.broadcast_history_status()

    async def handle_cursor_move(self, data):
        # Update cursor position for this user
        if self.room_id not in user_cursors:
            user_cursors[self.room_id] = {}
        user_cursors[self.room_id][self.user_id] = {
            'x': data.get('x', 0),
            'y': data.get('y', 0),
            'username': self.username
        }
        
        # Broadcast cursor position to other users
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'cursor_move_message',
            'user_id': self.user_id,
            'cursor_data': user_cursors[self.room_id][self.user_id]
        })

    async def handle_laser_pointer(self, data):
        # Update laser pointer position for this user
        if self.room_id not in user_laser_pointers:
            user_laser_pointers[self.room_id] = {}
        user_laser_pointers[self.room_id][self.user_id] = {
            'x': data.get('x', 0),
            'y': data.get('y', 0),
            'username': self.username,
            'active': data.get('active', True)
        }
        
        # Broadcast laser pointer position to other users
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'laser_pointer_message',
            'user_id': self.user_id,
            'laser_data': user_laser_pointers[self.room_id][self.user_id]
        })

    async def handle_clear_canvas(self, data):
        # Check if user has admin permissions
        if not self.can_edit():
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'You do not have permission to clear the canvas'
            }))
            return
        
        if self.room_id in room_history:
            room_history[self.room_id] = []
            for uid in redo_history[self.room_id]:
                redo_history[self.room_id][uid].clear()
            print(f"[DEBUG] room_history[{self.room_id}] cleared")
            print(f"[DEBUG] redo_history[{self.room_id}] cleared for all users")

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'clear_canvas_message',
            'cleared_by': self.username
        })
        await self.broadcast_history_status()

    async def handle_undo(self):
        print(f"[DEBUG] handle_undo: user_id={self.user_id}, permission={user_permissions.get(self.room_id, {}).get(self.user_id)}")
        if not self.can_edit():
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'You do not have permission to undo actions'
            }))
            return
        
        if room_history.get(self.room_id):
            print(f"[DEBUG] Current history: {room_history[self.room_id]}")
            print(f"[DEBUG] Looking for user_id: {self.user_id}")
            # Find the last action by this user
            for i in range(len(room_history[self.room_id]) - 1, -1, -1):
                action = room_history[self.room_id][i]
                action_user_id = action.get('user_id')
                print(f"[DEBUG] Checking action {i}: user_id={action_user_id}, type={action.get('type')}")
                if action_user_id == self.user_id:
                    last_action = room_history[self.room_id].pop(i)
                    redo_history[self.room_id][self.user_id].append(last_action)
                    print(f"[DEBUG] Undo: moved to redo_history[{self.room_id}][{self.user_id}]")
                    print(f"[DEBUG] room_history[{self.room_id}] after undo: {room_history[self.room_id]}")
                    print(f"[DEBUG] redo_history[{self.room_id}][{self.user_id}]: {redo_history[self.room_id][self.user_id]}")
                    await self.broadcast_board_state()
                    return
            else:
                # No action found by this user
                print(f"[DEBUG] No actions found by user {self.user_id}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'No actions to undo'
                }))
                return
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'No actions to undo'
            }))
            return

    async def handle_redo(self):
        print(f"[DEBUG] handle_redo: user_id={self.user_id}, permission={user_permissions.get(self.room_id, {}).get(self.user_id)}")
        if not self.can_edit():
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'You do not have permission to redo actions'
            }))
            return
        
        if redo_history[self.room_id][self.user_id]:
            action_to_redo = redo_history[self.room_id][self.user_id].pop()
            room_history[self.room_id].append(action_to_redo)
            print(f"[DEBUG] Redo: moved back to room_history[{self.room_id}]")
            print(f"[DEBUG] room_history[{self.room_id}] after redo: {room_history[self.room_id]}")
            print(f"[DEBUG] redo_history[{self.room_id}][{self.user_id}]: {redo_history[self.room_id][self.user_id]}")
            await self.broadcast_board_state()

    async def broadcast_board_state(self):
        history = room_history.get(self.room_id, [])
        # Check if there are any actions by the current user that can be undone
        can_undo = any(action.get('user_id') == self.user_id for action in history)
        print(f"[DEBUG] broadcast_board_state: can_undo={can_undo}, history_len={len(history)}")
        can_redo = len(redo_history[self.room_id][self.user_id]) > 0
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'board_state_message',
            'history': history,
            'canUndo': can_undo,
            'canRedo': can_redo,
            'user_permission': user_permissions.get(self.room_id, {}).get(self.user_id, 'view'),
        })

    async def broadcast_history_status(self):
        history = room_history.get(self.room_id, [])
        # Check if there are any actions by the current user that can be undone
        can_undo = any(action.get('user_id') == self.user_id for action in history)
        can_redo = len(redo_history[self.room_id][self.user_id]) > 0
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'history_status_message',
            'canUndo': can_undo,
            'canRedo': can_redo,
            'user_permission': user_permissions.get(self.room_id, {}).get(self.user_id, 'view'),
        })

    # WebSocket message handlers
    async def draw_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'draw',
            'drawing': event['drawing_data']
        }))

    async def shape_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'shape',
            'shape': event['shape_data']
        }))

    async def text_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'text',
            'text': event['text_data']
        }))

    async def cursor_move_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'cursor_move',
            'user_id': event['user_id'],
            'cursor_data': event['cursor_data']
        }))

    async def laser_pointer_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'laser_pointer',
            'user_id': event['user_id'],
            'laser_data': event['laser_data']
        }))

    async def board_state_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'board_state',
            'history': event['history'],
            'canUndo': event['canUndo'],
            'canRedo': event['canRedo'],
            'user_permission': event.get('user_permission', 'view'),
        }))

    async def history_status_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'history_status',
            'canUndo': event['canUndo'],
            'canRedo': event['canRedo'],
            'user_permission': event.get('user_permission', 'view'),
        }))

    async def clear_canvas_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'clear_canvas',
            'cleared_by': event['cleared_by']
        }))

    async def user_joined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_joined',
            'user_id': event['user_id'],
            'username': event['username'],
            'permission': event['permission']
        }))

    async def user_left(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_left',
            'user_id': event['user_id'],
            'username': event['username']
        })) 