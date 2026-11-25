from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Event:
    name: str
    payload: Dict[str, Any]