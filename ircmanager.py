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


# TODO idea : list of channels as listeners
class IRCManager:
    def __init__(self, nick, server, port):
        self.nick = nick
        self.server = server
        self.port = port

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.linequeue = Queue()
        self.nextreadprefix = ''    # TODO rename?

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
            return line
        except Empty:
            return None

    def quit(self, message='Leaving'):
        # NOTE: Message doesn't seem to work
        self.socket.send(bytes('QUIT :{0}\r\n'.format(message), 'UTF-8'))


class Channel:
    def __init__(self, channel, irc):
        self.channel = channel
        self.irc = irc
        self.online = {}

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
        return mode in self.online.get(user, default=[])

    def nickchange(self, user, newnick):
        if user in self.online:
            self.online[newnick] = self.online[user]
            del self.online[user]

    def __str__(self):
        return self.channel
