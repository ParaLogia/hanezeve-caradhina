from enum import Enum, auto


class Event():
    def __init__(self, *, line: str, source='', call=''):
        self.line = line
        self.source = source
        self.call = call


# Event calls representing different categories of server messages
NOTICE = 'NOTICE'
JOIN = 'JOIN'
QUIT = 'QUIT'
PART = 'PART'
NICK = 'NICK'
MODE = 'MODE'
KICK = 'KICK'
PRIVMSG = 'PRIVMSG'
INVITE = 'INVITE'
TOPIC = 'TOPIC'
ERROR = 'ERROR'
NUMERIC = 'NUMERIC'


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
    Parses a message from the server into an Event object.

    :param line: line of text that has been read from the irc socket.
    :return: a tuple of form (event, kwargs)
             If the event does not correspond to an Event member,
             the first element of the tuple will be a string instead.
    """
    line = line.rstrip('\r\n')
    try:
        source, call, params = line.split(' ', 2)
    except ValueError:
        call, params = line.split(' ', 1)
        source = ''

    # In some cases, source is omitted--first token is the CALL
    if source.isalnum() and source.isupper():
        call, params = source, f'{call} {params}'
        source = ''

    source = trimcolon(source)

    event = Event(line=line, source=source, call=call)

    if call == NOTICE:
        target, message = params.split(' ', 1)
        event.target = target
        event.message = trimcolon(message)

    elif call == JOIN:
        channel = trimcolon(params)
        event.channel = channel

    elif call == QUIT:
        reason = trimcolon(params)
        event.reason = reason

    elif call == PART:
        channel, _, reason = params.partition(' ')
        event.channel = channel
        event.reason = trimcolon(reason)

    elif call == NICK:
        nick = trimcolon(params)
        event.nick = nick

    elif call == MODE:
        try:
            channel, modes, param = params.split(' ', 2)
            event.channel = channel
            event.modes = modes
            event.param = param
        except ValueError:
            channel, modes = params.split(' ')
            event.channel = channel
            event.modes = modes

    elif call == KICK:
        channel, nick, reason = params.split(' ', 2)
        event.channel = channel
        event.nick = nick
        event.reason = trimcolon(reason)

    elif call == PRIVMSG:
        target, message = params.split(' ', 1)
        event.target = target
        event.message = trimcolon(message)

    elif call == INVITE:
        target, channel = params.split(' ', 1)
        event.target = target
        event.channel = trimcolon(channel)

    elif call == TOPIC:
        channel, topic = params.split(' ', 1)
        event.channel = channel
        event.topic = trimcolon(topic)

    elif call == ERROR:
        message = trimcolon(params)
        event.message = message

    else:
        try:
            code = int(call)
            event.call = 'NUMERIC'
            target, message = params.split(' ', 1)
            event.code = code
            event.target = target
            event.message = trimcolon(message)
        except ValueError:
            print('Unrecognized event in line:', line)
            event.params = params

    return event
