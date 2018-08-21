import socket
from functools import update_wrapper
from queue import Queue, Empty
from time import sleep
import logging
from collections import defaultdict

from caradhina import events
from caradhina.events import EventResponse, parseline, trimcolon


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

        # queue of channels to join on launch
        self.joinqueue = []
        # mapping of channel names to Channel objects
        self.channels = {}

        self.listeners = defaultdict(list)

    def launch(self):
        """
        Launches the bot. Connects to the IRC server and begins an infinite read loop.
        """
        self.socket.connect((self.server, self.port))
        self.socket.send(bytes(f'NICK {self.nick}\r\n', 'UTF-8'))
        self.socket.send(bytes('USER {0} {0} {0} {0}\r\n'.format(self.nick), 'UTF-8'))

        # Check for initial PING before joining any channels (necessary for choopa.net)
        line = self.readline()
        while 'NOTICE' in line:
            line = self.readline()

        # Join queued channels
        self.channels = {channel: self._joinchannel(channel) for channel in self.joinqueue}

        # TODO other on-connect listeners

        self.socket.settimeout(0.05)

        # Begin loop
        while True:
            self.readline()

    def join_on_launch(self, *channels):
        self.joinqueue.extend(channels)

    def _joinchannel(self, channel):
        session = Channel(channel, self)
        session.join()
        return session

    def pong(self, msg):
        self.socket.send(bytes(f'PONG :{msg}\r\n', 'UTF-8'))

    def sendmsg(self, msg, target):
        self.socket.send(bytes(f'PRIVMSG {target} :{msg}\r\n', 'UTF-8'))

    def sendnotice(self, msg, target):
        self.socket.send(bytes(f'NOTICE {target} :{msg}\r\n', 'UTF-8'))

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
            print(line)

            event = parseline(line)
            self.notifylisteners(event)

            return line
        except Empty:
            return ''

    def notifylisteners(self, event):
        for listener in self.listeners[event.call]:
            listener(event)

    def bindlistener(self, listener, *calls):
        for call in calls:
            self.listeners[call].append(listener)

    def unbindlistener(self, listener, *calls):
        for call in calls:
            try:
                self.listeners[call].remove(listener)
            except ValueError:
                pass

    def listen(self, *calls):
        def decorator(func):
            listener = Listener(func, calls, self)
            update_wrapper(listener, func)
            return listener
        return decorator

    def quit(self, message='Leaving'):
        # NOTE: Message doesn't seem to work
        self.socket.send(bytes(f'QUIT :{message}\r\n', 'UTF-8'))


class Listener:
    def __init__(self, func, calls, irc):
        self.func = func
        self.calls = calls
        self.irc = irc

        irc.bindlistener(self, *calls)

    def __call__(self, *args, **kwargs):
        response = self.func(*args, **kwargs)
        if response == EventResponse.UNBIND:
            self.irc.unbindlistener(self, *self.calls)
        return response

    def unbind(self):
        self.irc.unbindlistener(self, *self.calls)


class Channel:
    def __init__(self, channelname, irc):
        self.chan_name = channelname
        self.irc = irc
        self.online = {}
        self.chan_modes = {}
        self.listeners = []
        self.topic = ''

    def join(self):
        self._createlisteners()
        self.irc.socket.send(bytes(f'JOIN {self.chan_name}\r\n', 'UTF-8'))

    def _createlisteners(self):
        irc = self.irc

        @irc.listen(events.NUMERIC)
        def initlistener(event):
            """
            Listens for numerics directly after joining, in order to
            initialize the topic and online user/mode list.

            Unbinds itself after reaching the end of the names list.
            """
            code, message = event.code, event.message
            if code == 332:
                channel, topic = message.split(' ', 1)
                if channel.lower() == self.chan_name:
                    self.topic = trimcolon(topic)

                    print(self.topic)

            elif code == 353:
                _, channel, names = message.split(' ', 2)
                namelist = trimcolon(names).split(' ')

                if channel.lower() == self.chan_name:
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

                if channel.lower() == self.chan_name:
                    print(self.online)
                    return EventResponse.UNBIND

        @irc.listen(events.JOIN)
        def joinlistener(event):
            source, channel = event.source, event.channel
            if channel.lower() == self.chan_name:
                name, _ = source.split('!~', 1)
                self.online[name] = set()

                print(self.online)

        @irc.listen(events.PART)
        def partlistener(event):
            source, channel = event.source, event.channel
            if channel.lower() == self.chan_name:
                name, _ = source.split('!~', 1)
                del self.online[name]

                print(self.online)

        @irc.listen(events.KICK)
        def kicklistener(event):
            channel, nick = event.channel, event.nick
            if channel.lower() == self.chan_name:
                del self.online[nick]

                if nick == self.irc.nick:
                    self.clear()

                print(self.online)

        @irc.listen(events.QUIT)
        def quitlistener(event):
            source = event.source
            name, _ = source.split('!~', 1)
            try:
                del self.online[name]
            except KeyError:
                pass

            print(self.online)

        @irc.listen(events.NICK)
        def nicklistener(event):
            source, nick = event.source, event.nick
            name, _ = source.split('!~', 1)
            try:
                self.online[nick] = self.online[name]
                del self.online[name]

                print(self.online)
            except KeyError:
                pass

        @irc.listen(events.MODE)
        def modelistener(event):
            channel, modes = event.channel, event.modes
            if channel.lower() == self.chan_name:
                change, modes = modes[0], modes[1:]
                for mode in modes:
                    if mode in usermodes:
                        name = event.param
                        if change == '+':
                            self.online[name].add(mode)
                        elif change == '-':
                            try:
                                self.online[name].remove(mode)
                            except KeyError:
                                pass

                        print(self.online)

        @irc.listen(events.TOPIC)
        def topiclistener(event):
            channel, topic = event.channel, event.topic
            if channel.lower() == self.chan_name:
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
        self.irc.socket.send(bytes('PART {self.chan_name}\r\n', 'UTF-8'))
        self.clear()

    def clear(self):
        self.online = {}
        self.topic = ''
        for listener in self.listeners:
            listener.unbind()
        self.listeners.clear()

    def useronline(self, user):
        return user in self.online

    def hasmode(self, user, mode):
        return mode in self.online.get(user, set())

    def __str__(self):
        return self.chan_name
