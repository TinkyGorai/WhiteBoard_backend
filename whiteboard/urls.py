from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'rooms', views.RoomViewSet)
router.register(r'drawings', views.DrawingViewSet)
router.register(r'messages', views.ChatMessageViewSet)
router.register(r'participants', views.RoomParticipantViewSet)

urlpatterns = [
    path('api/room/exists/<str:room_id>/', views.check_room_exists, name='check_room_exists'),
    path('', views.home, name='home'),
    path('api/', include(router.urls)),
] 