from enum import Enum, auto


class Event(Enum):
    NOTICE = auto()
    JOIN = auto()
    QUIT = auto()
    PART = auto()
    NICK = auto()
    MODE = auto()
    KICK = auto()
    PRIVMSG = auto()
    INVITE = auto()
    TOPIC = auto()
    ERROR = auto()
    NUMERIC = auto()


class EventResponse(Enum):
    CONTINUE = auto()
    UNBIND = auto()
