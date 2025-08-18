"""
WebSocket URL routing for Spaceship Coordination Experiment
"""

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/game/(?P<crew_id>\w+)/$', consumers.GameConsumer.as_asgi()),
    re_path(r'ws/admin/$', consumers.AdminConsumer.as_asgi()),
]




