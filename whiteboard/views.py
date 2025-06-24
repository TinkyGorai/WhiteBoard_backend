from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.models import User
from django.db import models
from .models import Room, RoomParticipant, Drawing, ChatMessage
from .serializers import (
    RoomSerializer, RoomCreateSerializer, DrawingSerializer, 
    ChatMessageSerializer, RoomParticipantSerializer
)
from django.http import JsonResponse, HttpResponse
from .consumers import room_history
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import uuid
import random
import string

def home(request):
    """Simple home page for testing"""
    return render(request, 'whiteboard/home.html')

class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.all()
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_permissions(self):
        """Allow anonymous users to create rooms"""
        if self.action == 'create':
            return [permissions.AllowAny()]
        return super().get_permissions()
    
    def get_serializer_class(self):
        if self.action == 'create':
            return RoomCreateSerializer
        return RoomSerializer
    
    def get_queryset(self):
        """Filter rooms based on user permissions"""
        user = self.request.user
        if user.is_authenticated:
            # Show public rooms and rooms where user is a participant
            return Room.objects.filter(
                models.Q(is_public=True) | 
                models.Q(participants__user=user)
            ).distinct()
        else:
            # Show only public rooms for anonymous users
            return Room.objects.filter(is_public=True)
    
    def perform_create(self, serializer):
        # Allow room creation for both authenticated and anonymous users
        if self.request.user.is_authenticated:
            room = serializer.save(created_by=self.request.user)
            # Add creator as admin participant only if authenticated
            RoomParticipant.objects.create(
                room=room,
                user=self.request.user,
                permission='admin'
            )
        else:
            # For anonymous users, create room without a creator
            room = serializer.save(created_by=None)
        
        print(f"🎯 Created room: {room.name}, ID: {room.id}, room_code: {room.room_code}")
        return room
    
    def check_user_permission(self, room, user, required_permission='view'):
        """Check if user has required permission for the room"""
        if not user.is_authenticated:
            return False
        
        # Room creator has all permissions (only if created_by is not None)
        if room.created_by and room.created_by == user:
            return True
        
        # Check participant permissions
        try:
            participant = room.participants.get(user=user)
            permission_levels = {'view': 1, 'edit': 2, 'admin': 3}
            required_level = permission_levels.get(required_permission, 1)
            user_level = permission_levels.get(participant.permission, 0)
            return user_level >= required_level
        except RoomParticipant.DoesNotExist:
            return False
    
    @action(detail=True, methods=['get'])
    def check_access(self, request, pk=None):
        """Check if user can access the room and what permissions they have"""
        # Try to find room by UUID first, then by room_code
        try:
            room = self.get_object()
        except:
            # If UUID lookup fails, try room_code
            try:
                room = Room.objects.get(room_code=pk)
            except Room.DoesNotExist:
                return Response({
                    'can_access': False,
                    'permission': None,
                    'message': 'Room not found'
                }, status=status.HTTP_404_NOT_FOUND)
        
        user = request.user
        
        if not user.is_authenticated:
            if room.is_public:
                return Response({
                    'can_access': True,
                    'permission': 'view',
                    'message': 'Public room access granted'
                })
            else:
                return Response({
                    'can_access': False,
                    'permission': None,
                    'message': 'Private room requires authentication'
                })
        
        # Check if user is creator
        if room.created_by and room.created_by == user:
            return Response({
                'can_access': True,
                'permission': 'admin',
                'message': 'Room creator access'
            })
        
        # Check if user is participant
        try:
            participant = room.participants.get(user=user)
            return Response({
                'can_access': True,
                'permission': participant.permission,
                'message': f'Participant with {participant.permission} permission'
            })
        except RoomParticipant.DoesNotExist:
            if room.is_public:
                return Response({
                    'can_access': True,
                    'permission': 'view',
                    'message': 'Public room access granted'
                })
            else:
                return Response({
                    'can_access': False,
                    'permission': None,
                    'message': 'Private room access denied'
                })
    
    @action(detail=True, methods=['post'])
    def join(self, request, pk=None):
        room = self.get_object()
        user = request.user
        
        if not user.is_authenticated:
            return Response({'message': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check if room is public or user has been invited
        if not room.is_public:
            # For private rooms, check if user has been invited
            if not room.participants.filter(user=user).exists():
                return Response({'message': 'Private room access denied'}, status=status.HTTP_403_FORBIDDEN)
        
        # Check if user is already a participant
        if room.participants.filter(user=user).exists():
            return Response({'message': 'Already a participant'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if room is full
        if room.participants.count() >= room.max_participants:
            return Response({'message': 'Room is full'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Add user as participant with default permission
        default_permission = 'edit' if room.is_public else 'view'
        RoomParticipant.objects.create(
            room=room,
            user=user,
            permission=default_permission
        )
        
        return Response({'message': 'Joined room successfully'}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        room = self.get_object()
        user = request.user
        
        if not user.is_authenticated:
            return Response({'message': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Remove user from participants
        room.participants.filter(user=user).delete()
        
        return Response({'message': 'Left room successfully'}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def update_participant_permission(self, request, pk=None):
        """Update participant permission (admin only)"""
        room = self.get_object()
        user = request.user
        
        if not user.is_authenticated:
            return Response({'message': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check if user is admin or creator
        if not self.check_user_permission(room, user, 'admin'):
            return Response({'message': 'Admin permission required'}, status=status.HTTP_403_FORBIDDEN)
        
        participant_id = request.data.get('participant_id')
        new_permission = request.data.get('permission')
        
        if not participant_id or not new_permission:
            return Response({'message': 'participant_id and permission required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            participant = room.participants.get(id=participant_id)
            participant.permission = new_permission
            participant.save()
            return Response({'message': 'Permission updated successfully'}, status=status.HTTP_200_OK)
        except RoomParticipant.DoesNotExist:
            return Response({'message': 'Participant not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'])
    def invite_user(self, request, pk=None):
        """Invite user to private room (admin only)"""
        room = self.get_object()
        user = request.user
        
        if not user.is_authenticated:
            return Response({'message': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check if user is admin or creator
        if not self.check_user_permission(room, user, 'admin'):
            return Response({'message': 'Admin permission required'}, status=status.HTTP_403_FORBIDDEN)
        
        username = request.data.get('username')
        permission = request.data.get('permission', 'view')
        
        if not username:
            return Response({'message': 'username required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            invited_user = User.objects.get(username=username)
            
            # Check if already a participant
            if room.participants.filter(user=invited_user).exists():
                return Response({'message': 'User already a participant'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Add user as participant
            RoomParticipant.objects.create(
                room=room,
                user=invited_user,
                permission=permission
            )
            
            return Response({'message': f'User {username} invited successfully'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'message': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'])
    def drawings(self, request, pk=None):
        room = self.get_object()
        
        # Check if user has view permission
        if not self.check_user_permission(room, request.user, 'view'):
            return Response({'message': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        
        drawings = room.drawings.all()
        serializer = DrawingSerializer(drawings, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        room = self.get_object()
        
        # Check if user has view permission
        if not self.check_user_permission(room, request.user, 'view'):
            return Response({'message': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        
        messages = room.messages.all()
        serializer = ChatMessageSerializer(messages, many=True)
        return Response(serializer.data)

class DrawingViewSet(viewsets.ModelViewSet):
    queryset = Drawing.objects.all()
    serializer_class = DrawingSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        room_id = self.request.query_params.get('room_id')
        if room_id:
            return Drawing.objects.filter(room_id=room_id)
        return Drawing.objects.all()
    
    def perform_create(self, serializer):
        # Check if user has edit permission for the room
        room = serializer.validated_data.get('room')
        if not self.check_user_permission(room, self.request.user, 'edit'):
            raise permissions.PermissionDenied("Edit permission required")
        
        serializer.save(user=self.request.user)
    
    def check_user_permission(self, room, user, required_permission='view'):
        """Check if user has required permission for the room"""
        if not user.is_authenticated:
            return False
        
        # Room creator has all permissions
        if room.created_by == user:
            return True
        
        # Check participant permissions
        try:
            participant = room.participants.get(user=user)
            permission_levels = {'view': 1, 'edit': 2, 'admin': 3}
            required_level = permission_levels.get(required_permission, 1)
            user_level = permission_levels.get(participant.permission, 0)
            return user_level >= required_level
        except RoomParticipant.DoesNotExist:
            return room.is_public and required_permission == 'view'
    
    @action(detail=False, methods=['delete'])
    def clear_room(self, request):
        room_id = request.query_params.get('room_id')
        if room_id:
            try:
                room = Room.objects.get(id=room_id)
                # Check if user has admin permission
                if not self.check_user_permission(room, request.user, 'admin'):
                    return Response({'message': 'Admin permission required'}, status=status.HTTP_403_FORBIDDEN)
                
                Drawing.objects.filter(room_id=room_id).delete()
                return Response({'message': 'Room drawings cleared'}, status=status.HTTP_200_OK)
            except Room.DoesNotExist:
                return Response({'message': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'error': 'room_id required'}, status=status.HTTP_400_BAD_REQUEST)

class ChatMessageViewSet(viewsets.ModelViewSet):
    queryset = ChatMessage.objects.all()
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        room_id = self.request.query_params.get('room_id')
        if room_id:
            return ChatMessage.objects.filter(room_id=room_id)
        return ChatMessage.objects.all()
    
    def perform_create(self, serializer):
        # Check if user has view permission for the room (to send messages)
        room = serializer.validated_data.get('room')
        if not self.check_user_permission(room, self.request.user, 'view'):
            raise permissions.PermissionDenied("Access denied")
        
        serializer.save(user=self.request.user)
    
    def check_user_permission(self, room, user, required_permission='view'):
        """Check if user has required permission for the room"""
        if not user.is_authenticated:
            return False
        
        # Room creator has all permissions
        if room.created_by == user:
            return True
        
        # Check participant permissions
        try:
            participant = room.participants.get(user=user)
            permission_levels = {'view': 1, 'edit': 2, 'admin': 3}
            required_level = permission_levels.get(required_permission, 1)
            user_level = permission_levels.get(participant.permission, 0)
            return user_level >= required_level
        except RoomParticipant.DoesNotExist:
            return room.is_public and required_permission == 'view'

class RoomParticipantViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RoomParticipant.objects.all()
    serializer_class = RoomParticipantSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        room_id = self.request.query_params.get('room_id')
        if room_id:
            return RoomParticipant.objects.filter(room_id=room_id)
        return RoomParticipant.objects.all()

def check_room_exists(request, room_id):
    """
    Check if a room with the given ID exists in our in-memory history.
    """
    exists = room_id in room_history
    return JsonResponse({'exists': exists})

@api_view(['GET'])
def test_view(request):
    """Simple test view to check if the app is working"""
    return Response({
        'message': 'Django app is working!',
        'status': 'success'
    })

@csrf_exempt
def root_message(request):
    return HttpResponse("This is the API server. No frontend here.", status=200)

@csrf_exempt
def favicon(request):
    return HttpResponse(status=204)
