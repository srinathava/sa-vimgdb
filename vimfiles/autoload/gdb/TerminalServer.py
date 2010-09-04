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

class TerminalServer:
    def __init__(self, cmd='gdb'):
        self.reader = None
        self.socket = None
        self.conn = None
        self.stopReading = False
        self.newDataTotal = ''
        self.newDataForClient = ''
        self.resumeOnReaderDone = True
        self.shell = None
        self.cmd = cmd

        self.logger = logging.getLogger(self.getLoggerName())

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
        self.debug('Starting server....')

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
        self.shell = mypexpect.spawn(self.cmd)

        # read initial declaration from GDB.
        self.readToPrompt()

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

            if not re.match('INT|SYNC|ASYNC|ISBUSY|DIE|FLUSH', mode):
                if not self.isValidMode(mode):
                    self.closeConnection('WRONG_MODE')
                    continue

            # let overloaded classes have a go at figuring out how to
            # handle the command.
            if self.handleCmd(mode, command):
                continue

            # client wants us to go away...
            if mode == 'DIE':
                self.debug('Client wants us to go away...')
                break

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
                    self.interrupt()
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

        self.shell.terminate()
        self.closeConnection('BYE')

    def interrupt(self):
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
        self.shell.sendintr()
        # Wait for the async read thread to finish.
        if self.reader:
            self.reader.join()
            self.reader = None

    def flush(self): 
        sendData(self.conn, self.newDataForClient)
        self.newDataForClient = ''

    def onNewData(self, data):
        self.debug('data = %s' % repr(data))
        if self.conn:
            sendData(self.conn, data)
        else:
            self.newDataForClient += data

        if self.needsUserInput(self.newDataTotal):
            if self.conn:
                # If connection is alive, we assume that the client is
                # going to give us the answer.
                reply = self.conn.recv(1024)
            else:
                reply = self.getUserInput(self.newDataTotal)
            self.write(reply.strip() + '\n')

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

    def write(self, cmd):
        self.shell.send(cmd)

    def readToPrompt(self):
        self.newDataForClient = ''
        self.newDataTotal = ''

        while not self.stopReading:
            try:
                data = self.shell.read_nonblocking(size=1024, timeout=0.2)
                self.newDataTotal += data
            except mypexpect.TIMEOUT:
                continue
            except mypexpect.EOF:
                return total

            self.onNewData(data)

            if self.hasPromptArrived(self.newDataTotal):
                return self.newDataTotal

        return total

    def getReply(self, cmd):
        self.newDataTotal = ''
        self.write(cmd + '\n')
        return self.readToPrompt()

    # Methods which need to be over-written
    def isValidMode(self, mode):
        return False

    def handleCmd(self, mode, cmd):
        pass

    def getLoggerName(self):
        return ''

    def hasPromptArrived(self, data):
        return False

    def needsUserInput(self, data):
        return False

    def getUserInput(self, data):
        return ''

    def onResume(self):
        pass


