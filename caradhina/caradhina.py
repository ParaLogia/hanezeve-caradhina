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


def trimcolon(s: str):
    """
    :param s: string with possible leading colon.
    :return: a copy of s with a single leading colon removed,
             if one is found. Otherwise returns s as-is.
    """
    return s[1:] if s.startswith(':') else s


def parseline(line: str):
    """
    Splits a line into event, and parameter tokens, and returns a corresponding
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
            target, mode, param = params.split(' ', 2)
            kwargs['target'] = target
            kwargs['mode'] = mode
            kwargs['param'] = param
        except ValueError:
            target, mode = params.split(' ')
            kwargs['target'] = target
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
        except BlockingIOError:
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
            listener(self, *args, **kwargs)

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
    def __init__(self, channel, irc):
        self.channel = channel
        self.irc = irc
        self.online = {}
        self.chanmodes = {}

    def join(self):
        self.irc.socket.send(bytes('JOIN ' + self.channel + '\r\n', 'UTF-8'))

        line = ''
        while 'End of /NAMES' not in line:
            line = self.irc.readline()
            tokens = line.split(' ', maxsplit=5)

            if tokens[1] == '353':
                users = tokens[5].strip(':').split(' ')

                # Check for mode prefix
                # Assumes at most one prefix/user
                for user in users:
                    user = user.lower()
                    if user[0] in prefixes:
                        self.online[user[1:]] = [prefixes[user[0]]]
                    else:
                        self.online[user] = []

    def part(self):
        self.irc.socket.send(bytes('PART ' + self.channel + '\r\n', 'UTF-8'))
        self.online = {}

    def useronline(self, user):
        return user in self.online

    def adduser(self, user):
        self.online[user] = []

    def removeuser(self, user):
        if user in self.online:
            del self.online[user]

    def addmode(self, user, mode):
        if mode not in self.online[user]:
            self.online[user].append(mode)

    def removemode(self, user, mode):
        if mode in self.online[user]:
            self.online[user].remove(mode)

    def hasmode(self, user, mode):
        return mode in self.online.get(user, [])

    def nickchange(self, user, newnick):
        if user in self.online:
            self.online[newnick] = self.online[user]
            del self.online[user]

    def __str__(self):
        return self.channel
