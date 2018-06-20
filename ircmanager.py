import socket
from queue import Queue, Empty
from time import sleep
import logging


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
        self.socket.send(bytes('JOIN ' + channel + '\r\n', 'UTF-8'))

        # prefix : mode
        modes = {
            '~': 'q',
            '&': 'a',
            '@': 'o',
            '%': 'h',
            '+': 'v',
        }

        # online user : user mode(s)
        usermodes = {}

        while True:
            line = self.readline()

            if 'End of /NAMES' in line:
                break
            tokens = line.split(' ', maxsplit=5)
            if tokens[1] == '353':
                users = tokens[5].strip(':').split(' ')

                # Check for mode prefixes
                for user in users:
                    user = user.lower()
                    if user[0] in modes:
                        usermodes[user[1:]] = [modes[user[0]]]
                    else:
                        usermodes[user] = []

        return usermodes

    def pong(self, msg):
        self.socket.send(bytes('PONG :' + msg + '\r\n', 'UTF-8'))

    def sendmsg(self, msg, target):
        self.socket.send(bytes('PRIVMSG ' + target + ' :' + msg + '\r\n', 'UTF-8'))

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
        # Message doesn't seem to show
        self.socket.send(bytes('QUIT :{0}\r\n'.format(message), 'UTF-8'))
        self.socket.close()
