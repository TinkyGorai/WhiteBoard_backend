from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import root_message

router = DefaultRouter()
router.register(r'rooms', views.RoomViewSet)
router.register(r'drawings', views.DrawingViewSet)
router.register(r'messages', views.ChatMessageViewSet)
router.register(r'participants', views.RoomParticipantViewSet)

urlpatterns = [
    path('', root_message),
    path('api/room/exists/<str:room_id>/', views.check_room_exists, name='check_room_exists'),
    path('', views.home, name='home'),
    path('api/', include(router.urls)),
    path('api/rooms/', views.RoomViewSet.as_view({'get': 'list', 'post': 'create'}), name='room-list'),
    path('api/rooms/<str:room_code>/', views.RoomViewSet.as_view({'get': 'retrieve'}), name='room-detail'),
    path('api/test/', views.test_view, name='test'),
    path('api/check-room/<str:room_id>/', views.check_room_exists, name='check-room'),
] 