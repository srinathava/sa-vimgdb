from TerminalServer import TerminalServer

import logging
import sys

class GdbServer(TerminalServer):
    def __init__(self, cmd='gdb --annotate=3'):
        TerminalServer.__init__(self, cmd)
        self.queryAnswer = ''

    def getLoggerName(self):
        return 'VimGdb.Server'

    def isValidMode(self, mode):
        return (mode == 'SETQA')

    def handleCmd(self, mode, cmd):
        if mode == 'SETQA':
            self.queryAnswer = cmd

    def hasPromptArrived(self, data):
        return data.endswith('prompt\r\n')

    def needsUserInput(self, data):
        return (data.endswith('query\r\n') or
                data.endswith('commands\r\n'))

    def getUserInput(self, data):
        if data.endswith('query\r\n'):
            if self.queryAnswer:
                return self.queryAnswer
            else:
                return 'y'

        if data.endswith('commands\r\n'):
            return 'end'

        assert False, 'Illegal data input for getUserInput'

    def onResume(self):
        pass

if __name__ == "__main__":
    from optparse import OptionParser
    import os

    parser = OptionParser()
    parser.add_option('-d', '--debug', dest="debug", action="store_true", default=False)
    parser.add_option('', '--gdbcmd', dest="gdbcmd", default="gdb --annotate=3")
    (opts, args) = parser.parse_args()

    if opts.debug:
        logger = logging.getLogger('VimGdb')
        handler = logging.FileHandler('/tmp/GdbServer.%s.log' % (os.getenv('USER')))
        formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    else:
        logging.basicConfig()

    s = GdbServer(opts.gdbcmd)
    s.run()

