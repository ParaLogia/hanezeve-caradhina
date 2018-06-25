import datetime
import re
from time import sleep
import logging
from ircmanager import IRCManager


def setloggerhandler():
    datetime_str = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    formatter = logging.Formatter('[%(asctime)s] %(message)s', '%H:%M:%S')

    debuglog = 'logs/debug {}.log'.format(datetime_str)
    debughandler = logging.FileHandler(debuglog)
    debughandler.setFormatter(formatter)
    debughandler.setLevel(logging.DEBUG)

    # chatlog = 'logs/chat {}.log'.format(datetime_str)
    # chathandler = logging.FileHandler(chatlog)
    # chathandler.setFormatter(formatter)
    # chathandler.setLevel(logging.INFO)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(debughandler)
    # logger.addHandler(chathandler)


def main():
    nick = 'parabotia'
    # server = 'irc.choopa.net'
    server = 'chat.freenode.net'
    port = 6667
    channel = '#paratest'
    adminname = 'paralogia'
    exitcode = '!stop'
    shy = False

    setloggerhandler()

    irc = IRCManager(nick, server, port)
    irc.connect()

    # Check for initial PING before joining channel (necessary for choopa.net)
    line = irc.readline()
    while 'NOTICE' in line:
        line = irc.readline()

    channel = irc.joinchannel(channel)

    irc.socket.setblocking(False)

    while True:
        line = irc.readline()
        if not line:
            sleep(0.05)
            continue

        if ' PRIVMSG ' in line:
            if shy:
                irc.quit()
                return

            name = line.split('!', 1)[0][1:]
            message = line.split('PRIVMSG', 1)[1].split(':', 1)[1]

            message = message.rstrip()

            if len(name) > 16:
                continue

            greeting = r'hi|hello|howdy|good (day|morning|afternoon|evening)'
            if re.match(greeting + r'\W+' + nick + r'\b', message.lower()):
                irc.sendmsg('Hello ' + name + '!', channel)

            if message == '!ping':
                irc.sendmsg('\1PING 458315181\1', target=name)
                # TODO set timer and check for response

            if message == exitcode:
                name = name.lower()
                if name == adminname or channel.hasmode(name, 'o'):
                    irc.sendmsg('Bye!', channel)
                    irc.quit()
                    exit(0)

        # TODO update online users and modes by monitoring JOIN/QUIT/PART/MODE/NICK changes
        elif ' JOIN ' in line:
            pass

        elif ' QUIT ' in line:
            pass

        elif ' PART ' in line:
            pass

        elif ' MODE ' in line:
            pass

        elif ' NICK ' in line:
            pass


if __name__ == '__main__':
    main()
