from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid

class Room(models.Model):
    """Model for whiteboard rooms"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room_code = models.CharField(max_length=6, unique=True, null=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_rooms')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    max_participants = models.IntegerField(default=10)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.id})"
    
    def save(self, *args, **kwargs):
        # Generate room_code if not provided
        if not self.room_code:
            import random
            import string
            while True:
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                if not Room.objects.filter(room_code=code).exists():
                    self.room_code = code
                    print(f"🎯 Generated room_code: {code} for room: {self.name}")
                    break
        super().save(*args, **kwargs)

class RoomParticipant(models.Model):
    """Model for room participants"""
    PERMISSION_CHOICES = [
        ('view', 'View Only'),
        ('edit', 'Can Edit'),
        ('admin', 'Admin'),
    ]
    
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='room_participations')
    permission = models.CharField(max_length=10, choices=PERMISSION_CHOICES, default='edit')
    joined_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['room', 'user']
    
    def __str__(self):
        return f"{self.user.username} in {self.room.name}"

class Drawing(models.Model):
    """Model for storing drawing data"""
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='drawings')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='drawings')
    tool_type = models.CharField(max_length=50)  # pen, rectangle, circle, text, eraser
    color = models.CharField(max_length=7, default='#000000')  # hex color
    stroke_width = models.IntegerField(default=2)
    data = models.JSONField()  # Store drawing coordinates and properties
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.tool_type} by {self.user.username} in {self.room.name}"

class ChatMessage(models.Model):
    """Model for chat messages in rooms"""
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.user.username}: {self.message[:50]}"

class WhiteboardSession(models.Model):
    """Model for tracking active whiteboard sessions"""
    room = models.OneToOneField(Room, on_delete=models.CASCADE, related_name='session')
    is_active = models.BooleanField(default=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Session for {self.room.name}"
