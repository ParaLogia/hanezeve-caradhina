import socket
from queue import Queue, Empty
from time import sleep
import logging

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
    :param s: string with possible leading colon
    :return: a copy of s with a single leading colon removed,
             if one is found. Otherwise returns s as-is.
    """
    return s[1:] if s.startswith(':') else s


def parseline(line: str):
    """
    Splits a line into source, event, and parameter tokens
    :param line: line of text read from the irc socket
    :return: a tuple of form (source, event, params), where params
             is a tuple of all the parameters relevant to the event
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

    if event == 'NOTICE':
        target, message = params.split(' ', 1)
        params = target, trimcolon(message)

    elif event == 'JOIN':
        channel = trimcolon(params)
        params = channel,

    elif event == 'QUIT':
        reason = trimcolon(params)
        params = reason,

    elif event == 'PART':
        channel, reason = params.split(' ', 1)
        params = channel, trimcolon(reason)

    elif event == 'NICK':
        nick = trimcolon(params)
        params = nick,

    elif event == 'MODE':
        try:
            target, mode, param = params.split(' ', 2)
            params = target, mode, param
        except ValueError:
            target, mode = params.split(' ')
            params = target, mode

    elif event == 'KICK':
        channel, nick, reason = params.split(' ', 2)
        params = channel, nick, trimcolon(reason)

    elif event == 'PRIVMSG':
        target, message = params.split(' ', 1)
        params = target, trimcolon(message)

    elif event == 'INVITE':
        target, channel = params.split(' ', 1)
        params = target, trimcolon(channel)

    elif event == 'TOPIC':
        channel, topic = params.split(' ', 1)
        params = channel, trimcolon(topic)

    elif event == 'ERROR':
        message = trimcolon(params)
        params = message,

    else:
        try:
            event = int(event)
            target, message = params.split(' ', 1)
            params = target, trimcolon(message)
        except ValueError:
            print('Unrecognized line format:', line)

    return source, event, params


class IRCManager:
    def __init__(self, nick, server, port):
        self.nick = nick
        self.server = server
        self.port = port

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.linequeue = Queue()
        self.nextreadprefix = ''    # rename?

    def connect(self):
        self.socket.connect((self.server, self.port))
        self.socket.send(bytes('NICK {0}\r\n'.format(self.nick), 'UTF-8'))
        sleep(0.1)
        self.socket.send(bytes('USER {0} {0} {0} {0}\r\n'.format(self.nick), 'UTF-8'))

    def joinchannel(self, channel):
        session = Channel(channel, self)
        session.join()
        return session

    def pong(self, msg):
        self.socket.send(bytes('PONG :{0}\r\n'.format(msg), 'UTF-8'))

    def sendmsg(self, msg, target):
        self.socket.send(bytes('PRIVMSG {0} :{1}\r\n'.format(target, msg), 'UTF-8'))

    def updatelinequeue(self):
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
            self.updatelinequeue()
        try:
            line = self.linequeue.get_nowait()
            logging.log(logging.DEBUG, line)

            # TODO parse line and call handlers
            return line
        except Empty:
            return ''

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
