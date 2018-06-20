import datetime
import re
from time import sleep
import logging
from ircmanager import IRCManager


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
        log(line)
        line = irc.readline()
    log(line)

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

            if message.rstrip() == exitcode:
                name = name.lower()
                if name == adminname or name in online and 'o' in online[name]:
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
