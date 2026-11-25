from queue import Empty, Queue
from typing import Any, Dict, Optional

from core.events import Event


class EventBus:
    def __init__(self) -> None:
        self._queue: Queue[Event] = Queue()

    def publish(self, event_name: str, payload: Dict[str, Any]) -> None:
        event = Event(event_name, payload.copy())
        self._queue.put(event)

    def poll(self) -> Optional[Event]:
        try:
            return self._queue.get_nowait()
        except Empty:
            return None