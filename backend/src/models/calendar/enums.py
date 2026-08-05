from enum import Enum


class EventSource(str, Enum):
    """Source of the calendar event."""
    UNIVERSITY = "university"   # University calendar
    BLACKBOARD = "blackboard"   # Blackboard deadlines
    PERSONAL = "personal"       # Personal TODO items
    COURSE = "course"           # Course schedule


class Priority(str, Enum):
    """Priority level for events."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EventStatus(str, Enum):
    """Status of the event."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class ColorTag(str, Enum):
    """Color tag of the event."""
    RED = "red"
    ORANGE = "orange"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    PURPLE = "purple"
    PINK = "pink"
    WHITE = "white"
    GREY = "grey"
    BLACK = "black"
    
class EventCategory(str, Enum):
    """Category of the event."""
    BACKGROUND = "background"
    SOLID = "solid"
    SCHEDULABLE = "schedulable"
    IGNORED = "ignored"
    UNKNOWN = "unknown"


class DirtyType(str, Enum):
    """Type of dirty state for draft calendar."""
    FETCH = "fetch"     # Dirty state after fetching data
    MODIFY = "modify"   # Dirty state after modifying events
    CLEAR = "clear"     # Dirty state after clearing events
