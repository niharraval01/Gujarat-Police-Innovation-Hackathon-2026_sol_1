"""
bus.py — in-process pub/sub used to push live alerts to connected
dashboard WebSocket clients.

At statewide scale (~80,000 cameras, edge nodes spread ~1000km apart) this
role is played by Kafka or MQTT: edge nodes publish detection events to a
topic (`detections.raw`), stream processors consume + correlate, and
`alerts.live` is what command-centre dashboards subscribe to. Swapping
this module for a `kafka-python` or `paho-mqtt` client does not require
any change in correlation/engine.py or api/main.py — they only call
`.publish(topic, payload)` / `.subscribe(topic)`.
"""

import asyncio
from collections import defaultdict


class EventBus:
    def __init__(self):
        self._subscribers = defaultdict(list)  # topic -> [asyncio.Queue, ...]

    def subscribe(self, topic):
        q = asyncio.Queue()
        self._subscribers[topic].append(q)
        return q

    def unsubscribe(self, topic, q):
        if q in self._subscribers[topic]:
            self._subscribers[topic].remove(q)

    def publish(self, topic, payload):
        for q in self._subscribers[topic]:
            try:
                q.put_nowait(payload)
            except Exception:
                pass


bus = EventBus()
