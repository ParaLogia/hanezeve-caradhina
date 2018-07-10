import socket
from functools import wraps
from queue import Queue, Empty
from time import sleep
import logging

from caradhina.event import EventType, EventResponse, parseline, trimcolon

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


class IRCManager:
    def __init__(self, nick, server, port):
        self.nick = nick
        self.server = server
        self.port = port

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.linequeue = Queue()
        self.nextreadprefix = ''    # rename?

        self.listeners = {event: [] for event in EventType}

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

                # TODO rework (not elegant right now) -- Use flags param?
                if 'unbind' in kwargs and kwargs['unbind']:
                    self.unbindlistener(wrapper, *events)
                    return EventResponse.UNBIND

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
        self.listeners = []
        self.topic = ''

    def join(self):
        self._createlisteners()
        self.irc.socket.send(bytes('JOIN ' + self.channelname + '\r\n', 'UTF-8'))

    def _createlisteners(self):
        irc = self.irc

        @irc.listen(EventType.NUMERIC)
        def initlistener(code, message, **kwargs):
            """
            Listens for numerics directly after joining, in order to
            initialize the topic and online user/mode list.

            Unbinds itself after reaching the end of the names list.
            """
            if code == 332:
                channel, topic = message.split(' ', 1)
                if channel.lower() == self.channelname:
                    self.topic = trimcolon(topic)

                    print(self.topic)

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

        @irc.listen(EventType.JOIN)
        def joinlistener(source, channel, **kwargs):
            if channel.lower() == self.channelname:
                name, _ = source.split('!~', 1)
                self.online[name] = set()

                print(self.online)

        @irc.listen(EventType.PART)
        def partlistener(source, channel, **kwargs):
            if channel.lower() == self.channelname:
                name, _ = source.split('!~', 1)
                del self.online[name]

                print(self.online)

        @irc.listen(EventType.KICK)
        def kicklistener(channel, nick, **kwargs):
            if channel.lower() == self.channelname:
                del self.online[nick]

                print(self.online)

        @irc.listen(EventType.QUIT)
        def quitlistener(source, **kwargs):
            name, _ = source.split('!~', 1)
            try:
                del self.online[name]
            except KeyError:
                pass

            print(self.online)

        @irc.listen(EventType.NICK)
        def nicklistener(source, nick, **kwargs):
            name, _ = source.split('!~', 1)
            try:
                self.online[nick] = self.online[name]
                del self.online[name]

                print(self.online)
            except KeyError:
                pass

        @irc.listen(EventType.MODE)
        def modelistener(channel, modes, **kwargs):
            if channel.lower() == self.channelname:
                change, modes = modes[0], modes[1:]
                for mode in modes:
                    if mode in usermodes:
                        name = kwargs['param']
                        if change == '+':
                            self.online[name].add(mode)
                        elif change == '-':
                            try:
                                self.online[name].remove(mode)
                            except KeyError:
                                pass

                        print(self.online)

        @irc.listen(EventType.TOPIC)
        def topiclistener(channel, topic, **kwargs):
            if channel.lower() == self.channelname:
                self.topic = topic

            print(self.topic)

        self.listeners.extend([
            initlistener,
            joinlistener,
            partlistener,
            kicklistener,
            quitlistener,
            nicklistener,
            modelistener,
            topiclistener,
        ])

    def part(self):
        self.irc.socket.send(bytes('PART ' + self.channelname + '\r\n', 'UTF-8'))
        self.online = {}
        self.topic = ''
        for listener in self.listeners:
            listener(unbind=True)

    def useronline(self, user):
        return user in self.online

    def hasmode(self, user, mode):
        return mode in self.online.get(user, set())

    def __str__(self):
        return self.channelname
