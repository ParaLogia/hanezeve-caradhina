import datetime
import re
from time import sleep
import logging
from caradhina.caradhina import IRCManager
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

        if message == '!ping':
            irc.sendmsg('\1PING 458315181\1', target=name)
            # TODO set timer and check for response

        if message == '!stop':
            name = name.lower()
            if name == adminname or context is channel and channel.hasmode(name, 'o'):
                irc.sendmsg('Bye!', context)
                irc.quit()
                exit(0)

    irc.join_on_launch(chan_name)
    irc.launch()




if __name__ == '__main__':
    main()
