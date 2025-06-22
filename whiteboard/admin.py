from django.contrib import admin
from .models import Room, RoomParticipant, Drawing, ChatMessage, WhiteboardSession

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'is_public', 'created_at', 'participant_count']
    list_filter = ['is_public', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    def participant_count(self, obj):
        return obj.participants.count()
    participant_count.short_description = 'Participants'

@admin.register(RoomParticipant)
class RoomParticipantAdmin(admin.ModelAdmin):
    list_display = ['user', 'room', 'permission', 'joined_at']
    list_filter = ['permission', 'joined_at']
    search_fields = ['user__username', 'room__name']

@admin.register(Drawing)
class DrawingAdmin(admin.ModelAdmin):
    list_display = ['tool_type', 'user', 'room', 'color', 'created_at']
    list_filter = ['tool_type', 'created_at']
    search_fields = ['user__username', 'room__name']
    readonly_fields = ['created_at']

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['user', 'room', 'message', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'room__name', 'message']
    readonly_fields = ['created_at']

@admin.register(WhiteboardSession)
class WhiteboardSessionAdmin(admin.ModelAdmin):
    list_display = ['room', 'is_active', 'started_at', 'last_activity']
    list_filter = ['is_active', 'started_at']
    search_fields = ['room__name']
    readonly_fields = ['started_at', 'last_activity']
