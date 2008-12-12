from threading import Thread, Timer
import socket
import pty, tty, select, os, sys
import re
import time
from sockutils import *
import traceback

class ReaderThread(Thread):
    def __init__(self, server, cmd):
        Thread.__init__(self)
        self.server = server
        self.cmd = cmd

    def run(self):
        self.server.getReply(self.cmd)
        self.server.onReaderAboutToBeDone()

class GdbServer:
    def __init__(self):
        self.gdbPromptPat = re.compile(r'prompt')
        self.queryPat = re.compile(r'pre-query\r\n(?P<query>.*)\r\nquery', re.DOTALL)

        self.reader = None
        self.socket = None
        self.conn = None
        self.stopReading = False
        self.newDataTotal = ''

        self.logfile = '/tmp/gdbmi.log'

    def printDebug(self, msg):
        f = open(self.logfile, 'a')
        print >> f, msg
        f.close()

    def printException(self, maxTBlevel=5):
        traceback.print_exc(file=open(self.logfile, 'a'))

    def closeConnection(self, reason):
        if self.conn:
            sendData(self.conn, reason+'\n')

            # print 'Server shutting down connection'
            self.conn.shutdown(2)
            self.conn.close()
            del self.conn
            self.conn = None

    def run(self):
        self.printDebug('Starting GDB debugging ....')

        # Bind to port.
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # The magic line below prevents the socket from throwing the
        # "socket already in use" address which results in a timeout of
        # about 30 seconds between successive invocations of this program.
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('127.0.0.1', 50007))

        # Start GDB shell.
        self.startGdbShell()
        # read initial declaration from GDB.
        self.readToGdbPrompt()

        # Now wait for someone to ask us to do something...
        while 1:
            try:
                self.socket.listen(1)
                self.conn, addr = self.socket.accept()
            except:
                self.printDebug('Socket listening threw an exception!')
                self.printException()
                continue

            try:
                data = self.conn.recv(1024)
            except:
                self.printDebug('Socket accept threw an exception')
                self.printException()
                break

            tokens = data.split(' ', 1)
            mode = tokens[0]
            command = ''.join(tokens[1:])

            if not re.match('INT|SETQA|SYNC|ASYNC|ISBUSY|DIE', mode):
                self.closeConnection('WRONG_MODE')
                continue

            # client wants us to go away...
            if mode == 'DIE':
                self.printDebug('Client wants us to go away...')
                break

            if mode == 'SETQA':
                self.queryAnswer = command
                continue

            if ('SYNC' in mode) and (command == ''):
                self.closeConnection('WRONG_FORMAT')
                continue

            isBusy = self.reader and self.reader.isAlive() 
            if mode == 'INT':
                if isBusy:
                    self.interruptGdb()
            elif isBusy:
                self.closeConnection('BUSY')
            elif mode == 'SYNC':
                self.getReply(command)
            elif mode == 'ASYNC':
                self.reader = ReaderThread(self, command)
                self.reader.start()

            self.closeConnection('')

        self.printDebug('Done with main server loop...')

        # Done main server loop... Do cleanup...
        if self.reader and self.reader.isAlive():
            # print 'Closing child reader threads...'
            self.stopReading = True
            self.reader.join()
            self.reader = None
            self.stopReading = False

        if self.pid:
            # print 'Killing GDB process...'
            os.kill(self.pid, 9)
            self.pid = 0
            
        self.closeConnection('BYE')
        self.socket.shutdown(2)
        self.socket.close()
        del self.socket
        self.socket = None

    def interruptGdb(self):
        """
        Sends an interrupt key to the pseudo-TTY. This in turn should make
        GDB interrupt the process it is running and fall back onto the GDB
        prompt.
        """
        try:
            self.write(self.intr_key)
        except KeyboardInterrupt:
            pass

        # takes a little while to "take"
        time.sleep(0.5)

    def startGdbShell(self):
        self.pid, self.fd = pty.fork( )

        self.outd = self.fd
        self.ind  = self.fd
        self.errd = self.fd

        if self.pid == 0:
            attrs = tty.tcgetattr( 1 )
            attrs[ 6 ][ tty.VMIN ]  = 1
            attrs[ 6 ][ tty.VTIME ] = 0
            attrs[ 0 ] = attrs[ 0 ] | tty.BRKINT
            attrs[ 0 ] = attrs[ 0 ] & tty.IGNBRK
            attrs[ 3 ] = attrs[ 3 ] & ~tty.ICANON & ~tty.ECHO
            tty.tcsetattr( 1, tty.TCSANOW, attrs )

            # os.execlp('./test_echo')
            os.execlp('gdb', 'gdb', '--annotate', '3')

        else:
            try:
                attrs = tty.tcgetattr( 1 )
                termios_keys = attrs[ 6 ]

            except:
                return

            self.eof_key   = termios_keys[ tty.VEOF ]
            self.eol_key   = termios_keys[ tty.VEOL ]
            self.erase_key = termios_keys[ tty.VERASE ]
            self.intr_key  = termios_keys[ tty.VINTR ]
            self.kill_key  = termios_keys[ tty.VKILL ]
            self.susp_key  = termios_keys[ tty.VSUSP ]

    def getQueryAnswer(self, data):
        # If there is an alive connection, then just use that connection to
        # get the answer. Otherwise, return 'y'.
        if self.conn:
            retval = self.conn.recv(1024)
        else:
            retval = 'y'

        return retval

    def onNewData(self, data):
        # sys.stdout.write(data)
        if self.conn:
            sendData(self.conn, data)

        self.newDataTotal += data
        m = self.queryPat.search(self.newDataTotal)
        if m:
            query = m.group('query')
            reply = self.getQueryAnswer(query)
            self.write(reply + '\n')
            self.newDataTotal = ''

    def onReaderAboutToBeDone(self):
        t = Timer(0.01, self.waitForReaderToBeDone)
        t.start()

    def waitForReaderToBeDone(self):
        if self.reader:
            self.reader.join()
            self.onResume()

    def onResume(self):
        pass

    def write(self, cmd):
        os.write(self.ind, cmd)

    def read(self, pat):
        total = ''
        while not self.stopReading:
            r, w, e = select.select( [ self.outd ], [], [], 0.05 )

            if not r:
                if pat.search(total):
                    return total

            for file_iter in r:
                data = os.read( self.outd, 32 )
                if data == '':
                    break

                self.onNewData(data)

                total += data

        return total

    def readToGdbPrompt(self):
        return self.read(self.gdbPromptPat)

    def getReply(self, cmd):
        self.onNewData(cmd + '\n')
        self.write(cmd + '\n')
        return self.readToGdbPrompt()

if __name__ == "__main__":
    s = GdbServer()
    s.run()

