import datetime
import socket
import re
from time import sleep
import logging
from queue import Queue, Empty


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

        # Read initial NOTICEs and respond to initial PING before return
        # Necessary for choopa.net
        line = self.readline()
        while 'NOTICE' in line:
            log(line)
            line = self.readline()
        log(line)

    def joinchannel(self, channel):
        self.socket.send(bytes('JOIN ' + channel + '\r\n', 'UTF-8'))

        modes = {
            '~': 'q',
            '&': 'a',
            '@': 'o',
            '%': 'h',
            '+': 'v',
        }
        users = []
        while True:
            line = self.readline()
            log(line)

            if 'End of /NAMES' in line:
                break
            tokens = line.split(' ', maxsplit=5)
            if tokens[1] == '353':
                users += tokens[5].strip(':').split(' ')

        usermodes = {}
        for user in users:
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
            return self.linequeue.get_nowait()
        except Empty:
            return None

    def quit(self, message='Leaving'):
        # Message doesn't seem to show
        self.socket.send(bytes('QUIT :{0}\r\n'.format(message), 'UTF-8'))
        self.socket.close()


def setloggerhandler():
    datetime_str = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    logfile = 'logs/{}.log'.format(datetime_str)
    handler = logging.FileHandler(logfile)
    formatter = logging.Formatter('[%(asctime)s] %(message)s', '%H:%M:%S')
    logger = logging.getLogger()

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def log(text):
    text = text.strip('\r\n')
    logging.info(text)
    print(text)


def main():
    nick = 'parabotia'
    server = 'irc.choopa.net'
    # server = 'chat.freenode.net'
    port = 6667
    channel = '#triviacafe'
    adminname = 'paralogia'
    exitcode = '!stop'
    shy = True

    setloggerhandler()

    irc = IRCManager(nick, server, port)
    irc.connect()
    online = irc.joinchannel(channel)
    print(online)

    irc.socket.setblocking(False)

    while True:
        line = irc.readline()
        if not line:
            sleep(0.05)
            continue

        log(line)

        if ' PRIVMSG ' in line:
            if shy:
                irc.quit()
                return

            name = line.split('!', 1)[0][1:]
            message = line.split('PRIVMSG', 1)[1].split(':', 1)[1]

            if len(name) > 16:
                continue

            greeting = r'hi|hello|howdy|good (day|morning|afternoon|evening)'
            if re.match(greeting + r'\W+' + nick + r'\b', message.lower()):
                irc.sendmsg('Hello ' + name + '!', channel)
            if name.lower() == adminname.lower() and message.rstrip() == exitcode:
                irc.sendmsg('Bye!', channel)
                irc.quit()
                return

        # TODO update online users and modes by monitoring JOIN/QUIT/PART/MODE changes
        elif ' JOIN ' in line:
            pass
        elif ' QUIT ' in line:
            pass
        elif ' PART ' in line:
            pass
        elif ' MODE ' in line:
            pass




if __name__ == '__main__':
    main()
