from GdbServer import GdbServer
import os
import sys
from threading import Thread
import commands

class VimGdbServer(GdbServer):
    def __init__(self, vimServerName):
        GdbServer.__init__(self)
        self.vimServerName = vimServerName

    def onResume(self):
        cmd = "vim --servername %s --remote-expr 'gdb#gdb#OnResume()'" % self.vimServerName
        commands.getoutput(cmd)

class VimServerThread(Thread):
    def __init__(self, vimServerName):
        Thread.__init__(self)
        self.server = VimGdbServer(vimServerName)

    def run(self):
        self.server.run()

def startVimServerThread(serverName):
    import time
    s = VimServerThread(serverName)
    s.start()
    # wait a bit for the server to start serving.
    time.sleep(0.4)

if __name__ == '__main__':
    s = VimGdbServer(sys.argv[1])
    s.run()
