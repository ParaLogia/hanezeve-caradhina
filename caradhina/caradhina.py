import socket
from functools import wraps
from queue import Queue, Empty
from time import sleep
import logging

from caradhina.event import Event, EventResponse

# Map user prefix => mode
prefixes = {
    '~': 'q',
    '&': 'a',
    '@': 'o',
    '%': 'h',
    '+': 'v',
}

# List of modes that can be applied to users
# I dunno which are actually visible in a channel
usermodes = [
    'q',
    'a',
    'o',
    'h',
    'v',
    'a',
]


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
            channel, mode, param = params.split(' ', 2)
            kwargs['channel'] = channel
            kwargs['mode'] = mode
            kwargs['param'] = param
        except ValueError:
            channel, mode = params.split(' ')
            kwargs['channel'] = channel
            kwargs['mode'] = mode

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
        event = Event[event]
    except KeyError:
        # Allows for inconsistent return types,
        # but allows for undocumented events
        pass

    return event, kwargs


class IRCManager:
    def __init__(self, nick, server, port):
        self.nick = nick
        self.server = server
        self.port = port

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.linequeue = Queue()
        self.nextreadprefix = ''    # rename?

        self.listeners = {event: [] for event in Event}

    def connect(self):
        self.socket.connect((self.server, self.port))
        self.socket.send(bytes('NICK {0}\r\n'.format(self.nick), 'UTF-8'))
        self.socket.send(bytes('USER {0} {0} {0} {0}\r\n'.format(self.nick), 'UTF-8'))

    def joinchannel(self, channel):
        session = Channel(channel, self)
        session.join()
        return session

    def pong(self, msg):
        self.socket.send(bytes('PONG :{0}\r\n'.format(msg), 'UTF-8'))

    def sendmsg(self, msg, target):
        self.socket.send(bytes('PRIVMSG {0} :{1}\r\n'.format(target, msg), 'UTF-8'))

    def _updatelinequeue(self):
        try:
            msg = self.socket.recv(2048).decode('UTF-8')
            lines = msg.split('\r\n')
            lines[0] = self.nextreadprefix + lines[0]
            for line in lines[:-1]:
                if len(line) > 0:
                    if line.startswith('PING :'):
                        self.pong(line[6:])
                    self.linequeue.put(line)
            self.nextreadprefix = lines[-1]
        except (BlockingIOError, socket.timeout):
            return

    def readline(self):
        if self.linequeue.empty():
            self._updatelinequeue()
        try:
            line = self.linequeue.get_nowait()
            logging.log(logging.DEBUG, line)

            event, params = parseline(line)
            self.notifylisteners(event, **params)

            return line
        except Empty:
            return ''

    def notifylisteners(self, event, *args, **kwargs):
        for listener in self.listeners.setdefault(event, []):
            listener(*args, **kwargs)

    def bindlistener(self, listener, *events):
        for event in events:
            self.listeners.setdefault(event, []).append(listener)

    def unbindlistener(self, listener, *events):
        for event in events:
            try:
                self.listeners[event].remove(listener)
            except ValueError:
                pass

    def listen(self, *events):

        def decorator(listener):

            @wraps(listener)
            def wrapper(*args, **kwargs):
                response = listener(*args, **kwargs)
                if response == EventResponse.UNBIND:
                    self.unbindlistener(wrapper, *events)
                return response

            self.bindlistener(wrapper, *events)
            return wrapper

        return decorator

    def quit(self, message='Leaving'):
        # NOTE: Message doesn't seem to work
        self.socket.send(bytes('QUIT :{0}\r\n'.format(message), 'UTF-8'))


class Channel:
    def __init__(self, channelname, irc):
        self.channelname = channelname
        self.irc = irc
        self.online = {}
        self.chanmodes = {}
        self.listeners = {}
        self.topic = ''

    def join(self):
        self._createlisteners()
        self.irc.socket.send(bytes('JOIN ' + self.channelname + '\r\n', 'UTF-8'))

    def _createlisteners(self):
        irc = self.irc

        @irc.listen(Event.NUMERIC)
        def initlistener(code, message, **kwargs):
            """
            Listens for numerics directly after joining, in order to
            initialize the topic and online user/mode list.

            Unbinds itself after reaching the end of the names list.
            """
            if code == 332:
                # TODO get topic
                pass

            elif code == 353:
                _, channel, names = message.split(' ', 2)
                namelist = trimcolon(names).split(' ')

                if channel.lower() == self.channelname:
                    # Check for mode prefixes
                    for name in namelist:
                        name = name.lower()
                        usermodes = set()
                        for i, prefix in enumerate(name):
                            if prefix in prefixes:
                                usermodes.add(prefixes[prefix])
                            else:
                                user = name[i:]
                                self.online[user] = usermodes
                                break

            elif code == 366:
                channel, _ = message.split(' ', 1)

                if channel.lower() == self.channelname:
                    print(self.online)
                    return EventResponse.UNBIND

        @irc.listen(Event.JOIN)
        def joinlistener(source, channel, **kwargs):
            if channel.lower() == self.channelname:
                name, _ = source.split('!~', 1)
                self.online[name] = set()

                print(self.online)

        @irc.listen(Event.PART)
        def partlistener(source, channel, **kwargs):
            if channel.lower() == self.channelname:
                name, _ = source.split('!~', 1)
                del self.online[name]

                print(self.online)

        @irc.listen(Event.KICK)
        def kicklistener(channel, nick, **kwargs):
            if channel.lower() == self.channelname:
                del self.online[nick]

                print(self.online)

        @irc.listen(Event.QUIT)
        def quitlistener(source, **kwargs):
            name, _ = source.split('!~', 1)
            try:
                del self.online[name]
            except KeyError:
                pass

            print(self.online)

        @irc.listen(Event.NICK)
        def nicklistener(source, nick, **kwargs):
            name, _ = source.split('!~', 1)
            try:
                self.online[nick] = self.online[name]
                del self.online[name]

                print(self.online)
            except KeyError:
                pass

        @irc.listen(Event.MODE)
        def modelistener(channel, mode, **kwargs):
            if channel.lower() == self.channelname:
                name = kwargs['param']
                change, mode = mode[0], mode[1]
                if mode in usermodes:
                    if change == '+':
                        self.online[name].add(mode)
                    elif change == '-':
                        try:
                            self.online[name].remove(mode)
                        except KeyError:
                            pass

                    print(self.online)

        self.listeners[initlistener] = Event.NUMERIC
        self.listeners[joinlistener] = Event.JOIN
        self.listeners[partlistener] = Event.PART
        self.listeners[kicklistener] = Event.KICK
        self.listeners[quitlistener] = Event.QUIT
        self.listeners[nicklistener] = Event.NICK
        self.listeners[modelistener] = Event.MODE

    def part(self):
        self.irc.socket.send(bytes('PART ' + self.channelname + '\r\n', 'UTF-8'))
        self.online = {}
        # TODO unbind listeners

    def useronline(self, user):
        return user in self.online

    def hasmode(self, user, mode):
        return mode in self.online.get(user, set())

    def __str__(self):
        return self.channelname
