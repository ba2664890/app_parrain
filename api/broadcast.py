"""
Helper de broadcast temps réel — AMSEN Parrainage
Envoie un event à tous les clients WebSocket connectés via Django Channels.
Équivalent de src/lib/broadcast.ts (Next.js).

Usage (dans une vue synchrone) :
    from .broadcast import broadcast
    broadcast("stats:update", stats_dict)
"""
import asyncio
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

GROUP_NAME = "amsen_broadcast"


def broadcast(event: str, data) -> None:
    """
    Envoie l'événement à tous les consumers connectés.
    Silencieux en cas d'erreur (channel layer down, etc.).
    """
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            GROUP_NAME,
            {
                "type": "amsen_event",  # doit correspondre à la méthode du consumer
                "event": event,
                "data": data,
            },
        )
    except Exception:
        pass  # Ne jamais bloquer la réponse HTTP si le WS est down

