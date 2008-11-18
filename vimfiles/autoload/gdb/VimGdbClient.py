import socket
import sys
import vim
import re
from sockutils import *

class VimGdbClient:
    def __init__(self, bufno):
        self.buffer = vim.buffers[bufno - 1]

        self.queryPat = re.compile(r'pre-query\r\n(?P<query>.*)\r\nquery', re.DOTALL)
        self.newDataTotal = ''
        self.updateWindow = True
        self.toprint = ''
        self.socket = None
        self.queryAnswer = None

    def getReply(self, input):
        HOST = '127.0.0.1'        # The remote host
        PORT = 50007              # The same port as used by the server
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((HOST, PORT))

        sendData(self.socket, input)
        while 1:
            data = self.socket.recv(1024)
            if not data:
                break

            self.onNewData(data)

        # print 'Client shutting down connection'
        self.socket.shutdown(2)
        self.socket.close()
        del self.socket
        self.socket = None

    def runCommand(self, cmd):
        self.newDataTotal = ''
        self.getReply('SYNC ' + cmd)
        return self.newDataTotal

    def resumeProgram(self, cmd):
        self.newDataTotal = ''
        self.getReply('ASYNC ' + cmd)
        return self.newDataTotal

    def interrupt(self):
        self.newDataTotal = ''
        self.getReply('INT')
        return self.newDataTotal

    def getCommandOutput(self, cmd, var):
        output = self.runCommand(cmd)
        output = re.sub('"', '\\"', output)
        vim.command('let %s = "%s"' % (var, output))

    def getQueryAnswer(self, query):
        if self.queryAnswer:
            return self.queryAnswer

        ch = vim.eval(r'confirm("%s", "&Yes\n&No")' % query)
        if ch == '1':
            retval = 'y'
        else:
            retval = 'n'
        vim.command(r'let retval = "%s\n"' % retval)
        return retval

    def onNewData(self, data):
        self.newDataTotal += data

        if self.socket:
            m = self.queryPat.search(self.newDataTotal)
            if m:
                query = m.group('query')
                reply = self.getQueryAnswer(query)
                self.newDataTotal = re.sub(self.queryPat, '', self.newDataTotal)
                sendData(self.socket, reply)

        if self.updateWindow:
            self.printNewData(data)

    def printNewData(self, data):
        self.toprint += data
        if '\n' in self.toprint:
            newline = False
            if self.toprint[-1] == '\n':
                newline = True

            lines = self.toprint.splitlines()
            lines = [line for line in lines if not re.match('', line) and line]
            if not lines:
                return

            if newline:
                self.toprint = ''
            else: 
                self.toprint = lines[-1]
                lines = lines[:-1]
            if not lines:
                return

            self.buffer.append(lines)
            vim.command('keepalt call gdb#gdb#ScrollCmdWin("%s")' % self.buffer.name)

    def gotoCurrentFrame(self):
        self.updateWindow = False
        out = self.runCommand('interpreter mi -stack-info-frame')
        self.updateWindow = True

        filem = re.search('fullname="(.*?)"', out)
        linem = re.search('line="(\d+)"', out)
        if not filem or not linem:
            return

        file = filem.group(1)
        lnum = int(linem.group(1))
        vim.eval('gdb#gdb#PlaceSign("%s", %d)' % (file, lnum))

    def isBusy(self):
        self.updateWindow = False
        self.newDataTotal = ''
        self.getReply('ISBUSY')
        self.updateWindow = True
        if 'BUSY' in self.newDataTotal:
            return 1
        else:
            return 0

    def terminate(self):
        self.getReply('DIE')
