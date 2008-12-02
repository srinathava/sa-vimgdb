import socket
import sys
import vim
import re
from sockutils import *
from GdbMiParser import parseGdbMi

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
        retval = 'y' if (ch == 1) else 'n'
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

    def getSilentMiOutput(self, cmd):
        self.updateWindow = False
        out = self.runCommand('interpreter mi "%s"' % cmd)
        self.updateWindow = True

        # Get the first line after >>post-prompt which starts with \^
        lines = out.splitlines()
        for i in range(len(lines)):
            if re.match('^\^', lines[i]):
                return lines[i]

        return ''

    def getParsedGdbMiOutput(self, cmd):
        return parseGdbMi(self.getSilentMiOutput(cmd))

    def gotoCurrentFrame(self):
        try:
            out = self.getParsedGdbMiOutput('-stack-info-frame')
            file = out.frame.fullname
            line = out.frame.line
            # ^done,frame={level="0",addr="0x00002aaab80758c5",func="cdr_transform_driver_pre_core",file="cdr/cdr_transform_driver.cpp",fullname="/mathworks/devel/sandbox/savadhan/Acgirb/matlab/toolbox/stateflow/src/stateflow/cdr/cdr_transform_driver.cpp",line="263"}
        except:
            return


        vim.eval('gdb#gdb#PlaceSign("%s", %d)' % (file, line))

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
        m = re.search(r'^(\s*)\+.*{(\S+)}$', curLine)
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
        m = re.search(r'^(\s*)-.*{(\S+)}$', curLine)
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
            value = change.value
            if in_scope == 'true':
                vim.command(r'g/{%s}$/s/<.\{-}>/<%s>/' % (varname, value))
                vim.command(r'g/{%s}$/s/^ /c/' % varname)
            elif in_scope == 'false':
                vim.command(r'g/{%s}$/s/^ /o/' % varname)
            elif in_scope == 'invalid':
                vim.command(r'g/{%s}$/d_' % varname)
                self.getSilentMiOutput('-var-delete %s' % varname)

    def expandStack(self, num, skipUnknownFrames=True):

        isEmpty = len(vim.current.buffer) == 1 and vim.current.buffer[-1] == ''

        lastShownFrame = 0
        if not isEmpty:
            m_last = re.search(r'last shown frame = (\d+)', vim.current.buffer[-1])
            if m_last:
                lastShownFrame = int(m_last.group(1))
            else:
                return

        obj = self.getParsedGdbMiOutput('-stack-list-frames %d %d' % (lastShownFrame, lastShownFrame+num-1))
        # ^done,stack=[frame={level="0",addr="0x0000000000400a1c",func="foo",file="vartest.cpp",fullname="/mathworks/home/savadhan/code/gdbmiserver/test/vartest.cpp",line="26"},frame={level="1",addr="0x0000000000400d01",func="main",file="vartest.cpp",fullname="/mathworks/home/savadhan/code/gdbmiserver/test/vartest.cpp",line="52"}]


        lastIsKnown = isEmpty or (not re.match(r'...skipping', vim.current.buffer[-2]))

        lines = []
        for item in obj.stack:
            frame = item.frame
            if 'fullname' in frame.__dict__:
                lines.append('#%-3d %s(...) at %s:%d' % (frame.level, frame.func, frame.fullname, frame.line))
                lastIsKnown = True

            else:
                if skipUnknownFrames:
                    if lastIsKnown:
                        lines.append('...skipping frames with no source information...')

                elif 'from' in frame.__dict__:
                    lines.append('#%-3d ?? from ...%s' % (frame.level, frame.__dict__['from'][-20:]))

                else:
                    lines.append('#%-3d ??' % frame.level)

                lastIsKnown = False

        # remove the last line. We'll replace it with the updated lastShownFrame
        vim.current.buffer[-1:] = []
        if lines:
            vim.current.buffer.append(lines)
        if len(obj.stack) == num:
            vim.current.buffer.append('" Press <tab> for more frames... (last shown frame = %d)' % (lastShownFrame + num - 1))

