from GdbServer import GdbServer
import os
import sys
from threading import Thread
from subprocess import Popen, PIPE

try:
    import vim
except:  # noqa: E722
    pass

try:
    from subprocess import getoutput
except ImportError:
    from commands import getoutput


class VimGdbServer(GdbServer):
    def __init__(self, vimServerName, gdbcmd):
        GdbServer.__init__(self, gdbcmd)
        self.vimServerName = vimServerName

    def getQueryAnswer(self, query):
        self.debug('sending GetQueryAnswer for [%s] command to VIM' % query)

        if self.vimServerName:
            ans = Popen(['vim', '--servername', self.vimServerName,
                         '--remote-expr',
                         'gdb#gdb#GetQueryAnswer("%s")' % query],
                        stdout=PIPE).communicate()[0]
            ans = ans.decode()
        else:
            ans = vim.eval('gdb#gdb#GetQueryAnswer("%s")' % query)

        self.debug("done receiving reply '%s' from VIM about GetQueryAnswer" % ans)
        return ans

    def onResume(self):
        self.debug('sending onResume command to VIM')

        if self.vimServerName:
            cmd = "vim --servername %s --remote-expr 'gdb#gdb#OnResume()'" % self.vimServerName
            getoutput(cmd)
        else:
            vim.eval('gdb#gdb#OnResume()')

        self.debug('done receiving reply from VIM about onResume')


class VimServerThread(Thread):
    def __init__(self, vimServerName, gdbcmd):
        Thread.__init__(self)
        self.server = VimGdbServer(vimServerName, gdbcmd)

    def run(self):
        self.server.run()


def startVimServerThread(serverName, gdbcmd):
    s = VimServerThread(serverName, gdbcmd)
    s.start()
    return s.server.socket.getsockname()[1]


if __name__ == '__main__':
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option('-d', '--debug', dest="debug")
    parser.add_option('', '--gdbcmd', dest="gdbcmd", default="gdb")
    (opts, args) = parser.parse_args()

    if opts.debug:
        import logging

        logger = logging.getLogger('VimGdb')
        handler = logging.FileHandler('/tmp/VimGdbServer.%s.%d.log' % (os.getenv('USER'), os.getpid()))
        formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    s = VimGdbServer(sys.argv[1], opts.gdbcmd)
    s.run()
