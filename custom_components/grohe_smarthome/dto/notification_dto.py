from dataclasses import dataclass

from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class Notification:
    appliance_id: str
    id: str
    category: int
    is_read: bool
    timestamp: str
    type: int
    threshold_quantity: str
    threshold_type: str
    notification_text: str | None = None
    notification_type: str | None = None
