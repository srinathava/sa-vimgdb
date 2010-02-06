from GdbServer import GdbServer
import os
import sys
from threading import Thread
import commands
try:
    import vim
except:
    pass

class VimGdbServer(GdbServer):
    def __init__(self, vimServerName, runningInVim):
        GdbServer.__init__(self, runningInVim)
        self.vimServerName = vimServerName

    def onResume(self):
        self.debug('sending onResume command to VIM')

        if self.vimServerName:
            cmd = "vim --servername %s --remote-expr 'gdb#gdb#OnResume()'" % self.vimServerName
            commands.getoutput(cmd)
        else:
            vim.eval('gdb#gdb#OnResume()')

        self.debug('done receiving reply from VIM about onResume')

class VimServerThread(Thread):
    def __init__(self, vimServerName):
        Thread.__init__(self)
        self.server = VimGdbServer(vimServerName, True)

    def run(self):
        self.server.run()

def startVimServerThread(serverName):
    import time
    s = VimServerThread(serverName)
    s.start()
    # wait a bit for the server to start serving.
    time.sleep(0.4)

if __name__ == '__main__':
    s = VimGdbServer(sys.argv[1], False)
    s.run()
