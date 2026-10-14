"""
WebSocket consumer — AMSEN Parrainage
Remplace le mini-service Socket.io (port 3003).

Groupe : "amsen_broadcast"
  - Les clients se connectent en WS sur ws://localhost:8000/ws/
  - Le helper broadcast() envoie des messages à ce groupe via channel_layer
  - Chaque consumer relaie le message au client WebSocket connecté
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer


class AmsenConsumer(AsyncWebsocketConsumer):
    GROUP_NAME = "amsen_broadcast"

    async def connect(self):
        await self.channel_layer.group_add(self.GROUP_NAME, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            "event": "hello",
            "data": {"message": "AMSEN realtime connected (Django Channels)"},
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.GROUP_NAME, self.channel_name)

    # Reçoit les messages envoyés depuis le groupe (via broadcast())
    async def amsen_event(self, message):
        await self.send(text_data=json.dumps({
            "event": message["event"],
            "data": message["data"],
        }))

    # Reçoit les messages texte du client (optionnel, lecture seule côté frontend)
    async def receive(self, text_data=None, bytes_data=None):
        pass

