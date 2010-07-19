from threading import Thread, Timer
import socket
import os, sys
import re
from sockutils import *
import mypexpect

import logging

class ReaderThread(Thread):
    def __init__(self, server, cmd):
        Thread.__init__(self)
        self.server = server
        self.cmd = cmd

    def run(self):
        try:
            self.run_try()
        except:
            self.server.exception('Exception in reader thread')
            raise

    def run_try(self):
        self.server.resumeOnReaderDone = True
        self.server.getReply(self.cmd)
        self.server.onReaderAboutToBeDone()

class GdbServer:
    def __init__(self, runningInVim):
        self.gdbPromptPat = re.compile(r'prompt')
        self.queryPat = re.compile(r'pre-query\r\n(?P<query>.*)\r\nquery', re.DOTALL)
        self.preCommandsPat = re.compile(r'post-prompt\r\n(?P<query>.*)\r\npre-commands\r\n', re.DOTALL)
        self.postCommandsPat = re.compile(r'pre-commands\r\n', re.DOTALL)

        self.reader = None
        self.socket = None
        self.conn = None
        self.stopReading = False
        self.newDataTotal = ''
        self.newDataForClient = ''
        self.resumeOnReaderDone = True
        self.runningInVim = runningInVim
        self.gdbShell = None

        self.logger = logging.getLogger('VimGdb.server')

    def debug(self, msg):
        self.logger.debug(msg)

    def exception(self, msg):
        self.logger.exception(msg)

    def closeConnection(self, reason):
        self.debug('closing connection, reason = "%s", conn = %s' % (reason, self.conn))
        if self.conn:
            sendData(self.conn, reason+'\n')
            sendData(self.conn, '--GDB--EXIT--\n')

            # print 'Server shutting down connection'
            self.conn.shutdown(2)
            self.conn.close()
            del self.conn
            self.conn = None

    def run(self):
        try:
            self.run_try()
        except:
            self.exception('Exception in main server loop!')
            raise

    def run_try(self):
        self.debug('Starting GDB debugging ....')

        # Bind to port.
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # The magic line below prevents the socket from throwing the
        # "socket already in use" address which results in a timeout of
        # about 30 seconds between successive invocations of this program.
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Use 0 to let the OS give us an unused port number. Otherwise, we
        # cannot have two simultaneous debugging sessions on the same
        # machine!
        self.socket.bind(('127.0.0.1', 0))

        # Start GDB shell.
        self.gdbShell = mypexpect.spawn('gdb --annotate 3')
        # read initial declaration from GDB.
        self.readToGdbPrompt()

        # Now wait for someone to ask us to do something...
        while 1:
            try:
                self.socket.listen(1)
                self.conn, addr = self.socket.accept()
            except:
                self.exception('Socket listening threw an exception!')
                continue

            try:
                data = self.conn.recv(1024)
            except:
                self.exception('Socket accept threw an exception')
                break

            tokens = data.split(' ', 1)
            mode = tokens[0]
            command = ''.join(tokens[1:])
            self.debug('getting mode = [%s], command [%s]' % (mode, command))

            if not re.match('INT|SETQA|SYNC|ASYNC|ISBUSY|DIE|FLUSH', mode):
                self.closeConnection('WRONG_MODE')
                continue

            # client wants us to go away...
            if mode == 'DIE':
                self.debug('Client wants us to go away...')
                break

            if mode == 'SETQA':
                self.queryAnswer = command
                continue

            if ('SYNC' in mode) and (command == ''):
                self.closeConnection('WRONG_FORMAT')
                continue

            if 'FLUSH' in mode:
                self.flush()
                self.closeConnection('')
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
                # important to close the connection before we star the
                # reader thread otherwise the reader thread can try to send
                # data over an invalid connection.
                self.closeConnection('')
                self.reader = ReaderThread(self, command)
                self.reader.start()

            self.closeConnection('')

        self.debug('Done with main server loop...')

        # Done main server loop... Do cleanup...
        if self.reader and self.reader.isAlive():
            # print 'Closing child reader threads...'
            self.resumeOnReaderDone = False
            self.stopReading = True
            self.reader.join()
            self.reader = None
            self.stopReading = False

        self.gdbShell.terminate()
        self.closeConnection('BYE')

    def interruptGdb(self):
        """
        Sends an interrupt key to the pseudo-TTY. This in turn should make
        GDB interrupt the process it is running and fall back onto the GDB
        prompt.
        """

        # When we are interrupted by the client, do NOT do onResume. If we
        # do, it results in multiple simultaneous connections being made to
        # the GDB server, one by the onResume() and then by the client code
        # which comes after the interrupt. The second connection will just
        # hang till the first one is processed and done. 
        self.resumeOnReaderDone = False
        self.gdbShell.sendintr()
        # Wait for the async read thread to finish.
        if self.reader:
            self.reader.join()
            self.reader = None

    def getQueryAnswer(self, data):
        # If there is an alive connection, then just use that connection to
        # get the answer. Otherwise, return 'y'.
        if self.conn:
            retval = self.conn.recv(1024)
        else:
            retval = 'y'

        return retval

    def getCommands(self):
        if self.conn:
            retval = self.conn.recv(1024)
        else:
            retval = 'end'
        return retval

    def flush(self): 
        # Send all the lines which the client has not yet consumed.
        if '\n' in self.newDataForClient:
            lines = self.newDataForClient.split('\n')
            sendData(self.conn, '\n'.join(lines[:-1]))
            self.newDataForClient = lines[-1]

    def onNewData(self, data):
        if not self.runningInVim:
            sys.stdout.write(data)
        if self.conn:
            sendData(self.conn, data)
        else:
            self.newDataForClient += data

        self.newDataTotal += data
        m = self.queryPat.search(self.newDataTotal)
        if m:
            query = m.group('query')
            reply = self.getQueryAnswer(query)
            self.write(reply + '\n')
            self.newDataTotal = ''

        if (self.preCommandsPat.search(self.newDataTotal) or
            self.postCommandsPat.search(self.newDataTotal)):
            reply = self.getCommands()
            self.write(reply + '\n')
            self.newDataTotal = ''

        # self.newDataTotal is used only to ensure that we catch the
        # situation where GDB is asking for user input. As such we never
        # need more than about 200 characters worth of text to figure that
        # out. If self.newDataTotal grows too large, things get reeeally
        # slow due to all the regexp matches... Hence its necessary to trim
        # it down occassionally.
        if self.gdbPromptPat.search(self.newDataTotal):
            self.newDataTotal = ''

        if len(self.newDataTotal) > 1000:
            self.newDataTotal = self.newDataTotal[-200:0]

    def onReaderAboutToBeDone(self):
        # The reason for this additional thread to be created is to ensure
        # that the reader thread is completely done by the time the
        # onResume method is called. If the onResume were called from
        # within the reader thread itself, then the client would be
        # guaranteed to get a BUSY signal when it tried to react to the
        # onResume signal.
        #
        # However, if the client is the one who is actually interrupting
        # us, then do not bother sending the onResume signal to it. Sending
        # the onResume signal on a client interrupt will cause multiple
        # simultaneous connection attempts to the server from the client
        # causing hangs/crashes.
        if self.resumeOnReaderDone:
            # the time interval is really immaterial. What is important is
            # that the timer is a separate thread which can wait for the
            # reader thread to finish.
            t = Timer(0.001, self.waitForReader)
            t.start()

    def waitForReader(self):
        self.reader.join()
        self.reader = None
        self.onResume()

    def onResume(self):
        pass

    def write(self, cmd):
        self.gdbShell.send(cmd)

    def read(self, pat):
        total = ''
        while not self.stopReading:
            try:
                data = self.gdbShell.read_nonblocking(timeout=0.05)
            except mypexpect.TIMEOUT:
                continue
            except mypexpect.EOF:
                return total

            self.onNewData(data)

            total += data
            if pat.search(total):
                return total

        return total

    def readToGdbPrompt(self):
        return self.read(self.gdbPromptPat)

    def getReply(self, cmd):
        # self.onNewData(cmd + '\n')
        self.write(cmd + '\n')
        return self.readToGdbPrompt()

if __name__ == "__main__":
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option('-d', '--debug', dest="debug")
    (opts, args) = parser.parse_args()

    if opts.debug:
        logger = logging.getLogger('VimGdb')
        handler = logging.FileHandler('/tmp/GdbServer.%s.%d.log' % (os.getenv('USER'), os.getpid()))
        formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    s = GdbServer(False)
    s.run()

