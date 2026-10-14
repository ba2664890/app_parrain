from django.urls import path
from .consumers import AmsenConsumer

websocket_urlpatterns = [
    path("ws/", AmsenConsumer.as_asgi()),
]

