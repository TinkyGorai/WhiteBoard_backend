from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Room, RoomParticipant, Drawing, ChatMessage, WhiteboardSession

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class RoomParticipantSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = RoomParticipant
        fields = ['id', 'user', 'permission', 'joined_at']

class RoomSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    participants = RoomParticipantSerializer(many=True, read_only=True)
    participant_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Room
        fields = [
            'id', 'room_code', 'name', 'description', 'is_public', 'created_by', 
            'created_at', 'updated_at', 'max_participants', 
            'participants', 'participant_count'
        ]
    
    def get_participant_count(self, obj):
        return obj.participants.count()

class RoomCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ['id', 'room_code', 'name', 'description', 'is_public', 'max_participants']
    
    def create(self, validated_data):
        # Only set created_by if user is authenticated
        if self.context['request'].user.is_authenticated:
            validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)

class DrawingSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Drawing
        fields = ['id', 'room', 'user', 'tool_type', 'color', 'stroke_width', 'data', 'created_at']
        read_only_fields = ['user']
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

class ChatMessageSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = ChatMessage
        fields = ['id', 'room', 'user', 'message', 'created_at']
        read_only_fields = ['user']
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

class WhiteboardSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhiteboardSession
        fields = ['id', 'room', 'is_active', 'started_at', 'last_activity'] 