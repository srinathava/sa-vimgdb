from pyparsing import Literal, Word, Group, alphanums, delimitedList, \
        Forward, dblQuotedString, Regex

import types
import re

def getGdbMiParser():
    equals   = Literal('=').suppress()
    lcbrack  = Literal('{')
    rcbrack  = Literal('}').suppress()
    lsbrack  = Literal('[')
    rsbrack  = Literal(']').suppress()

    result_class = Literal("done") | Literal("running") | Literal("error") | Literal("exit")

    value = Forward()

    var     = Regex(r'[a-zA-Z0-9_-]+')
    result  = Group(var + equals + value)

    list = Group( Literal("[]") | 
                  (lsbrack + delimitedList(value) + rsbrack) |
                  (lsbrack + delimitedList(result) + rsbrack)
                )
    tuple = Group( Literal("{}") |
                   (lcbrack + delimitedList(result) + rcbrack) 
                 )

    value << (dblQuotedString | tuple | list)

    result_record = (Literal("^") + result_class + Literal(",")).suppress() + delimitedList(result)

    return result_record

class GdbMiResult:
    pass

def parseTreeToObj(parseTree):
    if type(parseTree) is types.StringType:
        m = re.match(r'"(\d+)"', parseTree)
        if m:
            return int(m.group(1))
        else:
            return parseTree[1:-1]

    if type(parseTree[0]) is types.ListType:
        retval = []
        for tok in parseTree:
            retval.append(parseTreeToObj(tok))
        return retval

    if parseTree[0] == '{':
        obj = GdbMiResult()
        for tok in parseTree[1:]:
            key = tok[0]
            val = parseTreeToObj(tok[1])

            setattr(obj, key, val)

        return obj

    if parseTree[0] == '[':
        ret = []
        for tok in parseTree[1:]:
            ret.append(parseTreeToObj(tok))
        return ret

    if parseTree[0] == '[]':
        return []
    
    if parseTree[0] == '{}':
        return {}

    obj = GdbMiResult()
    setattr(obj, parseTree[0], parseTreeToObj(parseTree[1]))
    return obj

def convertTopListToObj(list):
    obj = GdbMiResult()
    for item in list:
        firstKey = item.__dict__.keys()[0]
        setattr(obj, firstKey, item.__dict__[firstKey])

    return obj

parser = getGdbMiParser()
def parseGdbMi(input):
    global parser

    bnf_out = parser.parseString(input)
    return convertTopListToObj(parseTreeToObj(bnf_out.asList()))

if __name__ == '__main__':
    input = '''^done,children=[child={name="var1",numchild="3"}]'''
    obj = parseGdbMi(input)
    print obj.children[0].child.name

    input = '''^done,children=[{name="var1",numchild="3"}]'''
    obj = parseGdbMi(input)
    print obj.children[0].name

    input = '^done,name="var1",numchild="1",type="class CG::Scope *"'
    obj = parseGdbMi(input)
    print obj.type

    input = '^done,numchild="1",children=[child={name="var1.CG_Scope",exp="CG_Scope",numchild="2",type="CG_Scope"}]'
    obj = parseGdbMi(input)
    children = obj.children
    for ch in children:
        print ch.child.name, ch.child.numchild

    input = '^done,numchild="1",children=[child={name="var1.CG_Scope",exp="CG_Scope",numchild="2",value="{...}",type="CG_Scope",thread-id="5"}]'
    obj = parseGdbMi(input)
    children = obj.children
    for ch in children:
        print ch.child.name, ch.child.numchild

    input = r'^done,changelist=[{name="var1.public.foo1",value="0x401018 \"hello world\"",in_scope="true",type_changed="false"},{name="var1.public.foo4",value="8",in_scope="true",type_changed="false"}]'
    obj = parseGdbMi(input)
    changelist = obj.changelist
    for change in changelist:
        print change.name, 'changed to', change.value

    input = r'^done,changelist=[]'
    obj = parseGdbMi(input)
    changelist = obj.changelist
    for change in changelist:
        print change.name, 'changed to', change.value

    input = r'^done,stack=[frame={level="190",addr="0x00002b8254e1dd17",func="??",from="/mathworks/devel/sandbox/savadhan/Acgirb/matlab/bin/glnxa64/../../bin/glnxa64/libmwmcr.so"},frame={level="191",addr="0x00002b8254e1e0d4",func="??",from="/mathworks/devel/sandbox/savadhan/Acgirb/matlab/bin/glnxa64/../../bin/glnxa64/libmwmcr.so"},frame={level="192",addr="0x0000000000402958",func="boost::function0<void, std::allocator<boost::function_base> >::(function0)",file="//mathworks/hub/3rdparty/R2009a/77023/glnxa64/boost/include/boost-1_35/boost/function/function_template.hpp",fullname="/mathworks/hub/3rdparty/R2009a/77023/glnxa64/boost/include/boost-1_35/boost/function/function_template.hpp",line="825"},frame={level="193",addr="0x00000000004024cc",func="mcrMain",file="matlab.cpp",fullname="/mathworks/BLR/devel/bat/Aslrtw/build/matlab/src/main/matlab.cpp",line="141"},frame={level="194",addr="0x00002b8254e4131c",func="??",from="/mathworks/devel/sandbox/savadhan/Acgirb/matlab/bin/glnxa64/../../bin/glnxa64/libmwmcr.so"},frame={level="195",addr="0x00002b82562c8f1a",func="start_thread",from="/lib/libpthread.so.0"},frame={level="196",addr="0x00002b82564a1602",func="clone",from="/lib/libc.so.6"},frame={level="197",addr="0x0000000000000000",func="??"}]'
    obj = parseGdbMi(input)

    skipUnknownFrames = True
    lastIsKnown = True
    lines = []
    for item in obj.stack:
        frame = item.frame
        if 'fullname' in frame.__dict__:
            lines.append('#%-3d %s(...) at %s:%d' % (frame.level, frame.func, frame.fullname, frame.line))
        
        elif skipUnknownFrames:
            if lastIsKnown:
                lines.append('... [skipping frames with no source information] ...')
                lastIsKnown = False

        elif 'from' in frame.__dict__:
            lines.append('#%-3d ?? from ...%s' % (frame.level, frame.__dict__['from'][-20:]))

        else:
            lines.append('#%-3d ??' % frame.level)

    print '============='
    print '\n'.join(lines)
