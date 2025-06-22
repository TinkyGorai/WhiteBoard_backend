from django.urls import path
from . import consumers
 
websocket_urlpatterns = [
    path('ws/whiteboard/<str:room_id>/', consumers.WhiteboardConsumer.as_asgi()),
] 