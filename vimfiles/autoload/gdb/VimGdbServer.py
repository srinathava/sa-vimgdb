from GdbServer import GdbServer
import os
import sys

class VimGdbServer(GdbServer):
    def __init__(self, vimServerName):
        GdbServer.__init__(self)
        self.vimServerName = vimServerName

    def onResume(self):
        cmd = "vim --servername %s --remote-expr 'gdb#gdb#OnResume()'" % self.vimServerName
        print 'Executing [%s]' % cmd
        os.system(cmd)

if __name__ == '__main__':
    s = VimGdbServer(sys.argv[1])
    s.run()
