import datetime
import re
from time import time
import logging
from caradhina.caradhina import IRCManager, usermodes
from caradhina import events


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
    nick = 'hanezeve'
    server = 'irc.choopa.net'
    # server = 'chat.freenode.net'
    port = 6667
    chan_name = '#paratest'
    adminname = 'paralogia'
    shy = False

    greeting = r'hi|hello|howdy|good (day|morning|afternoon|evening)'
    greetingpattern = re.compile(fr'{greeting}\W+{nick}\b')

    setloggerhandler()

    irc = IRCManager(nick, server, port)

    @irc.listen(events.PRIVMSG)
    def msglistener(event):
        if shy:
            irc.quit()

        name, *_ = event.source.partition('!')
        message = event.message.rstrip()
        target = event.target

        try:
            channel = irc.channels[target]
            context = channel
        except KeyError:
            channel = None
            context = name

        if greetingpattern.match(message.lower()):
            irc.sendmsg(f'Hello {name}!', context)

        if message == '!stop':
            name = name.lower()
            if name == adminname or context is channel and channel.hasmode(name, 'o'):
                irc.sendmsg('Bye!', context)
                irc.quit()
                exit(0)

        elif message == '!ping':
            payload = int(time())
            irc.sendmsg(f'\1PING {payload}\1', target=name)

        # Check CTCP messages
        elif len(message) > 2 and message[0] == '\1' == message[-1]:
            ctcp = message[1:-1]

            if ctcp == 'VERSION':
                irc.sendnotice('VERSION hanezeve 0.5.1', target=name)

            elif ctcp.startswith('PING'):
                payload = ctcp[5:]
                irc.sendnotice(f'\1PING {payload}\1', target=name)

    @irc.listen(events.NOTICE)
    def noticelistener(event):
        name, *_ = event.source.partition('!')
        message = event.message.rstrip()

        if len(message) > 2 and message[0] == '\1' == message[-1]:
            ctcp = message[1:-1]

            if ctcp.startswith('PING'):
                payload = int(ctcp[5:])
                diff = time() - payload
                irc.sendnotice(f'Ping reply took {diff} seconds', target=name)

    @irc.listen(events.MODE)
    def modelistener(event):
        channel, modes = event.channel, event.modes
        change, modes = modes[0], modes[1:]
        for mode in modes:
            if mode in usermodes:
                name = event.param
                if name == irc.nick:
                    if change == '+':
                        irc.sendmsg('My power grows!', channel)
                    elif change == '-':
                        irc.sendmsg("My power drains...", channel)

    irc.join_on_launch(chan_name)
    irc.launch()


if __name__ == '__main__':
    main()
