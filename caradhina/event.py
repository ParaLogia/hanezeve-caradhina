from enum import Enum, auto


# class Event():
#     def __init__(self, *, line: str, eventtype):
#         self.line = line
#         self.eventtype = eventtype


class EventType(Enum):
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


class EventSubType():
    def __init__(self, eventtype: EventType):
        self.eventtype = eventtype


class EventResponse(Enum):
    CONTINUE = auto()
    UNBIND = auto()


def trimcolon(s: str):
    """
    :param s: string with possible leading colon.
    :return: a copy of s with a single leading colon removed,
             if one is found. Otherwise returns s as-is.
    """
    return s[1:] if s.startswith(':') else s


def parseline(line: str):
    """
    Splits a line into event and parameter tokens, and returns a corresponding
    Event object (if one is found), and a dict of keyword args for event listeners.

    :param line: line of text that has been read from the irc socket.
    :return: a tuple of form (event, kwargs)
             If the event does not correspond to an Event member,
             the first element of the tuple will be a string instead.
    """
    line = line.rstrip('\r\n')
    try:
        source, event, params = line.split(' ', 2)
    except ValueError:
        source, event, params = '', *line.split(' ', 1)

    # In some cases, source is omitted
    if source.isalnum() and source.isupper():
        source, event, params = '', *line.split(' ', 1)

    source = trimcolon(source)

    # Keyword args to be pass to event listeners
    kwargs = {'source': source}

    if event == 'NOTICE':
        target, message = params.split(' ', 1)
        kwargs['target'] = target
        kwargs['message'] = trimcolon(message)

    elif event == 'JOIN':
        channel = trimcolon(params)
        kwargs['channel'] = channel

    elif event == 'QUIT':
        reason = trimcolon(params)
        kwargs['reason'] = reason

    elif event == 'PART':
        channel, reason = params.split(' ', 1)
        kwargs['channel'] = channel
        kwargs['reason'] = trimcolon(reason)

    elif event == 'NICK':
        nick = trimcolon(params)
        kwargs['nick'] = nick

    elif event == 'MODE':
        try:
            channel, modes, param = params.split(' ', 2)
            kwargs['channel'] = channel
            kwargs['modes'] = modes
            kwargs['param'] = param
        except ValueError:
            channel, modes = params.split(' ')
            kwargs['channel'] = channel
            kwargs['modes'] = modes

    elif event == 'KICK':
        channel, nick, reason = params.split(' ', 2)
        kwargs['channel'] = channel
        kwargs['nick'] = nick
        kwargs['reason'] = trimcolon(reason)

    elif event == 'PRIVMSG':
        target, message = params.split(' ', 1)
        kwargs['target'] = target
        kwargs['message'] = trimcolon(message)

    elif event == 'INVITE':
        target, channel = params.split(' ', 1)
        kwargs['target'] = target
        kwargs['channel'] = trimcolon(channel)

    elif event == 'TOPIC':
        channel, topic = params.split(' ', 1)
        kwargs['channel'] = channel
        kwargs['topic'] = trimcolon(topic)

    elif event == 'ERROR':
        message = trimcolon(params)
        kwargs['message'] = message

    else:
        try:
            code = int(event)
            event = 'NUMERIC'
            target, message = params.split(' ', 1)
            kwargs['code'] = code
            kwargs['target'] = target
            kwargs['message'] = trimcolon(message)
        except ValueError:
            print('Unrecognized event in line:', line)
            kwargs['params'] = params

    try:
        # Get enum of event
        event = EventType[event]
    except KeyError:
        # Allows for inconsistent return types,
        # but allows for undocumented events
        pass

    return event, kwargs