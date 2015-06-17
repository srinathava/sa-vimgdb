import socket
import sys
import vim
import re
import errno
from sockutils import *
from GdbMiParser import parseGdbMi
import cStringIO
import time
import os

import logging

def initLogging(logVerbose):
    try:
        logger = logging.getLogger('VimGdb')
        handler = logging.FileHandler('/tmp/VimGdb.%s.log' % os.getenv('USER'), mode='w')
        formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        if logVerbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.ERROR)
    except:
        pass

class VimGdbClient:
    def __init__(self, portNum):
        self.queryPat = re.compile(r'pre-query\r\n(?P<query>.*)\r\nquery', re.DOTALL)
        self.preCommandsPat = re.compile(r'pre-commands\r\n(?P<query>.*)\r\ncommands\r\n', re.DOTALL)
        self.newDataTotal = ''
        self.updateWindow = True
        self.toprint = ''
        self.socket = None
        self.queryAnswer = None
        self.isFlushing = False
        self.portNum = portNum
        self.newLines = []

        self.logger = logging.getLogger('VimGdb.client')

    def debug(self, msg):
        if self.logger:
            self.logger.debug(msg)

    def exception(self, msg):
        if self.logger:
            self.logger.exception(msg)

    def getReply(self, input):
        try:
            return self.getReply_try(input)
        except:
            self.exception('Exception in getting reply!')
            # raise
    
    def tryConnect(self):
        HOST = '127.0.0.1'        # The remote host
        PORT = self.portNum       # The same port as used by the server
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        numAttempts = 0
        while numAttempts < 3:
            try:
                self.socket.connect((HOST, PORT))
                return
            except socket.error, (en, msg):
                self.debug('Getting connection error %s (%s)' % (en, msg))

            time.sleep(0.1)
            numAttempts += 1


    def getReply_try(self, input):
        self.tryConnect()

        # If there's an empty packet, we keep trying 3 times after the
        # first empty packet just to ensure that the server is _really_
        # done sending everything it wants to.
        maxEmptyPackets = 3
        nEmptyPackets = 0

        self.debug('Sending message [%s]' % input)
        sendData(self.socket, input)
        self.stopReading = False
        while not self.stopReading:
            try:
                data = self.socket.recv(1024)
                if not data:
                    self.debug('Timing out before receiving end marker')
                    nEmptyPackets = nEmptyPackets + 1
                    if nEmptyPackets > maxEmptyPackets:
                        self.debug('Too many empty packets recd. Breaking out of loop...')
                        break
                    else:
                        # Try again after lazing around for a bit.
                        time.sleep(0.1)
                        continue
                else:
                    nEmptyPackets = 0
            except socket.error,(en, msg):
                if en == errno.EINTR:
                    continue
                else:
                    # Since we are trying to repeatedly ask for more data
                    # even after the socket might be closed by the server,
                    # we need to account for unforseen errors.
                    self.exception('Socket error reading from the server... breaking out of read loop')
                    break

            self.onNewData(data)

        self.debug('Done getting reply from server... Closing socket')
        self.socket.shutdown(2)
        self.socket.close()
        del self.socket
        self.socket = None

    def runCommand(self, cmd):
        self.newDataTotal = ''
        self.debug('+runCommand: %s' % cmd)
        self.getReply('SYNC ' + cmd)
        self.debug('-runCommand: reply = %s' % self.newDataTotal)
        return self.newDataTotal

    def resumeProgram(self, cmd):
        self.newDataTotal = ''
        self.debug('+resumeProgram: %s' % cmd)
        self.getReply('ASYNC ' + cmd)
        self.debug('-resumeProgram: [%s]' % self.newDataTotal)
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

        ch = int(vim.eval(r'confirm("%s", "&Yes\n&No")' % query.replace(r'"', r'\"')))
        self.debug('getting answer for query [%s] = %s' % (query, ch))
        if (ch == 1):
            retval = 'y'
        else:
            retval = 'n'
        vim.command(r'let retval = "%s\n"' % retval)
        return retval

    def getCommands(self, query=''):
        ans = vim.eval('input("%s")' % query)
        return ans

    def onNewData(self, data):
        self.debug('onNewData: data: %s' % repr(data))
        self.newDataTotal += data

        if self.updateWindow:
            self.printNewData(data)

        if (not self.isFlushing) and self.socket:
            m = self.queryPat.search(self.newDataTotal)
            if m:
                query = m.group('query')
                reply = self.getQueryAnswer(query)
                self.newDataTotal = re.sub(self.queryPat, '', self.newDataTotal)
                sendData(self.socket, reply)
            m = self.preCommandsPat.search(self.newDataTotal)
            if m:
                reply = self.getCommands(m.group('query'))
                self.newDataTotal = re.sub(self.preCommandsPat, '', self.newDataTotal)
                sendData(self.socket, reply)

        if self.newDataTotal.endswith('--GDB--EXIT--\n'):
            self.stopReading = True

    def printNewData(self, data):
        def isLinePrintable(line):
            if not line:
                return False

            if (line.startswith('') or line.startswith('--GDB--EXIT--')):
                return False

            return True

        self.toprint += data

        lines = self.toprint.splitlines()

        # If the last line doesn't end with '\n', we cannot assume that it
        # is full, it might only be partially transmitted.
        if self.toprint.endswith('\n'):
            fullLines = lines
            rest = ''
        else:
            fullLines = lines[:-1]
            rest = lines[-1]

        self.newLines = [line for line in fullLines if isLinePrintable(line)]
        self.toprint = rest

        if self.newLines:
            vim.command('call gdb#gdb#UpdateCmdWin()')
            
    def printNewLines(self):
        if self.newLines:
            vim.current.buffer.append(self.newLines)
            self.newLines = []

    def getSilentMiOutput(self, cmd):
        self.updateWindow = False
        out = self.runCommand('interpreter mi "%s"' % cmd)
        self.updateWindow = True

        # Get the first line after >>post-prompt which starts with \^
        lines = out.splitlines()
        for i in range(len(lines)):
            if re.match('^\^', lines[i]):
                self.debug("Getting output for '%s':\n%s\n" % (cmd, lines[i]))
                return lines[i]

        return ''

    def getParsedGdbMiOutput(self, cmd):
        return parseGdbMi(self.getSilentMiOutput(cmd))

    def isBusy(self):
        if self.socket:
            # This function can sometimes get called when we are actually
            # already in the middle of a conversation with the server. This
            # mostly happens when the balloonexpr is being evaluated.
            return 1

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

    def flush(self):
        self.isFlushing = True
        self.getReply('FLUSH')
        self.isFlushing = False

    # ======================================================
    # Variable stuff
    # ======================================================
    def addGdbVar(self, expr):
        obj = self.getParsedGdbMiOutput('-var-create - @ %s' % expr)
        # ^done,name="var1",numchild="1",type="class CG::Scope *"

        if obj.numchild > 0:
            str = ' + '
        else:
            str = '   '

        str += '%s <%s> {%s}' % (expr, obj.value, obj.name)

        vim.current.buffer.append(str)
        vim.command('redraw')

    def expandGdbVar(self):
        curLine = vim.current.line
        m = re.search(r'^(c?\s*)\+.*{(\S+)}$', curLine)
        if m:
            curLine = re.sub(r'\+', '-', curLine, 1)
            vim.current.line = curLine

            lead_space = m.group(1)
            varname = m.group(2)

            obj = self.getParsedGdbMiOutput('-var-list-children 1 %s' % varname)
            # ^done,numchild="1",children=[child={name="var1.CG_Scope",exp="CG_Scope",numchild="2",value="{...}",type="CG_Scope"}]
            children = obj.children

            lines = []
            for ch in children:
                child = ch.child

                str = (lead_space + '  ')
                if child.numchild > 0:
                    str += '+ '
                else:
                    str += '  '

                str += '%s <%s> {%s}' % (child.exp, child.value, child.name)

                lines.append(str)

            curLineNum = int(vim.eval('line(".")'))
            vim.current.buffer[curLineNum:curLineNum] = lines

    def collapseGdbVar(self):
        curLine = vim.current.line
        m = re.search(r'^(c?\s*)-.*{(\S+)}$', curLine)
        if m:
            curLine = re.sub(r'-', '+', curLine, 1)
            vim.current.line = curLine

            varname = m.group(2)
            obj = self.getParsedGdbMiOutput('-var-delete -c %s' % varname)

    def deleteGdbVar(self):
        m = re.search(r'{(\S+)}$', vim.current.line)
        if m:
            varname = m.group(1)
            self.getSilentMiOutput('-var-delete %s' % varname)

    def refreshGdbVars(self):
        if len(vim.current.buffer) == 1:
            return

        obj = self.getParsedGdbMiOutput('-var-update 1 *')
        # ^done,changelist=[{name="var1.public.foo1",value="0x401018 \"hello world\"",in_scope="true",type_changed="false"},{name="var1.public.foo4",value="8",in_scope="true",type_changed="false"}]
        
        changelist = obj.changelist
        for change in changelist:
            varname = change.name
            in_scope = change.in_scope
            if in_scope == 'true':
                # escaping / is necessary otherwise the vim command fails
                # silently!
                value = str(change.value).replace('/', r'\/')
                vim.command(r'g/{%s}$/s/<.\{-}>/<%s>/' % (varname, value))
                vim.command(r'g/{%s}$/s/^ /c/' % varname)
            elif in_scope == 'false':
                vim.command(r'g/{%s}$/s/^ /o/' % varname)
            elif in_scope == 'invalid':
                vim.command(r'g/{%s}$/d_' % varname)
                self.getSilentMiOutput('-var-delete %s' % varname)

    # ======================================================
    # Stack stuff
    # ======================================================
    def gotoCurrentFrame(self):
        try:
            out = self.getParsedGdbMiOutput('-stack-info-frame')
            file = out.frame.fullname
            line = out.frame.line
            level = out.frame.level
            # ^done,frame={level="0",addr="0x00002aaab80758c5",func="cdr_transform_driver_pre_core",file="cdr/cdr_transform_driver.cpp",fullname="/mathworks/devel/sandbox/savadhan/Acgirb/matlab/toolbox/stateflow/src/stateflow/cdr/cdr_transform_driver.cpp",line="263"}
        except:
            return

        vim.eval('gdb#gdb#RefreshStackPtr(%d)' % level)
        vim.eval('gdb#gdb#PlaceSign("%s", %d)' % (file, line))

    def expandStack(self, num, skipUnknownFrames=True):

        isEmpty = len(vim.current.buffer) == 1 and vim.current.buffer[-1] == ''

        nextFrameToShow = 0
        if not isEmpty:
            m_last = re.search(r'next frame to show = (\d+)', vim.current.buffer[-1])
            if m_last:
                nextFrameToShow = int(m_last.group(1))
            else:
                return

        obj = self.getParsedGdbMiOutput('-stack-list-frames %d %d' % (nextFrameToShow, nextFrameToShow+num-1))
        # ^done,stack=[frame={level="0",addr="0x0000000000400a1c",func="foo",file="vartest.cpp",fullname="/mathworks/home/savadhan/code/gdbmiserver/test/vartest.cpp",line="26"},frame={level="1",addr="0x0000000000400d01",func="main",file="vartest.cpp",fullname="/mathworks/home/savadhan/code/gdbmiserver/test/vartest.cpp",line="52"}]

        lastIsKnown = isEmpty or (not re.match(r'...skipping', vim.current.buffer[-2]))

        lines = []
        for item in obj.stack:
            frame = item.frame
            filename = ''
            if 'fullname' in frame.__dict__:
                filename = frame.fullname
            elif 'file' in frame.__dict__:
                filename = frame.file

            if filename:
                lines.append('  #%-3d %s(...) at %s:%d' % (frame.level, frame.func, filename, frame.line))
                lastIsKnown = True

            else:
                if skipUnknownFrames:
                    if lastIsKnown:
                        lines.append('...skipping frames with no source information...')

                elif 'from' in frame.__dict__:
                    lines.append('  #%-3d ?? from ...%s' % (frame.level, frame.__dict__['from'][-20:]))

                else:
                    lines.append('  #%-3d ??' % frame.level)

                lastIsKnown = False

        # remove the last line. We'll replace it with the updated nextFrameToShow
        vim.current.buffer[-1:] = []
        if lines:
            vim.current.buffer.append(lines)
        if len(obj.stack) == num:
            vim.current.buffer.append('" Press <tab> for more frames... (next frame to show = %d)' % (nextFrameToShow + num))

