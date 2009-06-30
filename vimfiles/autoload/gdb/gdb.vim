" ==============================================================================
" File          : gdb.vim
" Author        : Srinath Avadhanula <srinathava AT google's email service>
" Description   :
" ============================================================================== 

" Do not want to re-source this file because then the state stored in the
" script-local variables gets trashed.
if exists('s:doneSourcingFile')
    finish
endif
let s:doneSourcingFile = 1

" ==============================================================================
" User preferences
" ============================================================================== 
" gdb#gdb#Let: safely assign to a variable {{{
" Description: 
function! gdb#gdb#Let(varName, value)
    if !exists('g:'.a:varName)
        let g:{a:varName} = a:value
    endif
endfunction " }}}
call gdb#gdb#Let('GdbCmdWinName', '_GDB_Command_Window_')
call gdb#gdb#Let('GdbStackWinName', '_GDB_Stack_Window_')
call gdb#gdb#Let('GdbVarWinName', '_GDB_Variables_Window')
call gdb#gdb#Let('GdbShowAsyncOutputWindow', 1)

" ==============================================================================
" Script local variables
" ============================================================================== 
let s:userIsBusy = 0
let s:gdbStarted = 0
let s:scriptDir = expand('<sfile>:p:h')

let s:GdbCmdWinName = g:GdbCmdWinName
let s:GdbStackWinName = g:GdbStackWinName
let s:GdbVarWinName = g:GdbVarWinName

let s:GdbCmdWinBufNum = -1
let s:GdbStackWinBufNum = -1
let s:gdbNametoBufNumMap = {}

let s:userMappings = {}

" s:GdbInitWork: does the actual work of initialization {{{
" Description: 
function! s:GdbInitWork( )
    " Cannot start multiple GDB sessions from a single VIM session.
    if s:gdbStarted == 1
        echohl Search
        echomsg "Gdb is already started!"
        echohl None
        return
    endif

    let s:gdbStarted = 1
    let s:GdbCmdWinBufNum = gdb#gdb#GdbOpenWindow(s:GdbCmdWinName)
    setlocal filetype=gdbvim

    python import sys
    python import vim
    exec 'python sys.path += [r"'.s:scriptDir.'"]'

    " Start the GDBMI server...
    " We have a choice here... We can either start a separate xterm which
    " shows the contents
    if g:GdbShowAsyncOutputWindow
        silent! exec '!xterm -T GDB -e python '.s:scriptDir.'/VimGdbServer.py '.v:servername.' &'
        silent! sleep 2
    else
        python from VimGdbServer import startVimServerThread
        exec 'python startVimServerThread("'.v:servername.'")'
    endif

    python from VimGdbClient import VimGdbClient
    python gdbClient = VimGdbClient()
    python gdbClient.getReply('FLUSH')
    
    " delete all empty lines.
    exec 'g/^\s*$/d_'

    " prevent stupid press <return> to continue prompts.
    call gdb#gdb#RunCommand('set height 0')
    call gdb#gdb#RedoAllBreakpoints()

    augroup TerminateGdb
        au!
        au VimLeavePre * :call gdb#gdb#Terminate()
    augroup END

    augroup MarkGdbUserBusy
        au!
        au CursorMoved  * :let s:userIsBusy = 1
        au CursorMovedI * :let s:userIsBusy = 1
        au CmdWinEnter  * :let s:userIsBusy = 1

        au CursorHold   * :let s:userIsBusy = 0
        au CursorHoldI  * :let s:userIsBusy = 0
        au CmdWinLeave  * :let s:userIsBusy = 0
    augroup END

    set balloonexpr=gdb#gdb#BalloonExpr()
    set ballooneval
    set balloondelay=500
    set updatetime=500

    call s:CreateGdbMaps()

    wincmd w
endfunction " }}}
" gdb#gdb#Init: {{{
function! gdb#gdb#Init()
    keepalt call s:GdbInitWork()
endfunction " }}}
" gdb#gdb#GdbOpenWindow: opens one of the GDB windows {{{
" Description: Open a new GDB window with the given name. We first attempt to
" see if any GDB window is currently open. If there is one, then we will
" vertically split a new window from it. Otherwise we horizontally split a new
" window at the very top of the window.

" We use a map with a constant value of 1 to simulate a set.
function! gdb#gdb#GdbOpenWindow(bufName)
    let bufnum = get(s:gdbNametoBufNumMap, a:bufName, -1)

    if bufnum == -1
        " bufnr(name, 1) sometimes creates new buffers with the same name
        " if the local directory changes etc. The presence of multiple
        " buffers with the same name really confuses things.
        let bufnum = bufnr(a:bufName, 1)
        let s:gdbNametoBufNumMap[a:bufName] = bufnum
    endif

    let winnum = bufwinnr(bufnum)
    if winnum != -1
        exec winnum.' wincmd w'
    else
        for n in values(s:gdbNametoBufNumMap)
            " the bizzare dual nature of Vim's data types. Yuck!
            let winnum = bufwinnr(n+0)
            if winnum != -1
                exec winnum.' wincmd w'
                exec 'vert split '.a:bufName
                break
            endif
        endfor
        if winnum == -1
            exec 'top split #'.bufnum
            resize 10
        endif
    endif

    call setbufvar(bufnum, '&swapfile', 0)
    call setbufvar(bufnum, '&buflisted', 0)
    call setbufvar(bufnum, '&buftype', 'nofile')
    call setbufvar(bufnum, '&ts', 8)

    return bufnum
endfunction " }}}
" s:CloseAllGdbWindows: closes all open GDB windows {{{
" Description: 
function! s:CloseAllGdbWindows()
    for n in values(s:gdbNametoBufNumMap)
        exec 'silent! bdelete '.n
    endfor
endfunction " }}}
" s:CreateMap: creates a map safely {{{
" Description: 
function! s:CreateMap(key, rhs, mode)
    let s:userMappings[a:mode . a:key] = maparg(a:key, a:mode)
    exec a:mode.'map <silent> '.a:key.' '.a:rhs
endfunction " }}}
" s:RestoreUserMaps: restores user mappings {{{
" Description: 
function! s:RestoreUserMaps()
    for item in keys(s:userMappings)
        let mode = item[0]
        let lhs = item[1:]
        let rhs = s:userMappings[item]
        if rhs != ''
            exec mode.'map <silent> '.lhs.' '.rhs
        else
            exec mode.'unmap '.lhs
        endif
    endfor
endfunction " }}}
" s:CreateGdbMaps: creates GDB specific mappings {{{
" Description: 
function! s:CreateGdbMaps()
    call s:CreateMap('<C-c>',   ':call gdb#gdb#Interrupt()<CR>', 'n')
    call s:CreateMap('<F5>',    ':call gdb#gdb#Continue()<CR>', 'n')
    call s:CreateMap('<S-F5>',  ':call gdb#gdb#Kill()<CR>', 'n')
    call s:CreateMap('<C-F5>',  ':call gdb#gdb#Interrupt()<CR>', 'n')
    call s:CreateMap('<F10>',   ':call gdb#gdb#Next()<CR>', 'n')
    call s:CreateMap('<F11>',   ':call gdb#gdb#Step()<CR>', 'n')
    call s:CreateMap('<S-F11>', ':call gdb#gdb#Finish()<CR>', 'n')
    call s:CreateMap('U',       ':call gdb#gdb#FrameUp()<CR>', 'n')
    call s:CreateMap('D',       ':call gdb#gdb#FrameDown()<CR>', 'n')
    call s:CreateMap('<F9>',    ':call gdb#gdb#ToggleBreakPoint()<CR>', 'n')
    call s:CreateMap('<C-P>',   ':call gdb#gdb#PrintExpr()<CR>', 'n')
    call s:CreateMap('<C-P>',   'y:call gdb#gdb#RunCommand("print <C-R>"")<CR>', 'v')
endfunction " }}}
" gdb#gdb#Panic: If something went wrong {{{
" Description: 
" Even with my best efforts, strange server-client errors seem to keep
" happening. At this point, the GDB thread has died from underneath us.
" Therefore, a fresh restart is necessary.
function! gdb#gdb#Panic()
    let ch = confirm('You should only panic if you see client-server errors. Are you sure you want to panic?', "&Panic\n&Dont", 1)
    if ch == 1
        call s:CloseAllGdbWindows()
        sign unplace 1
        set balloonexpr=
        let s:gdbStarted = 0
    endif
endfunction " }}}

" ==============================================================================
" Updating the _GDB_ window dynamically.
" ============================================================================== 
" gdb#gdb#IsUserBusy: returns 1 if cursor moved etc. {{{
" Description: 
function! gdb#gdb#IsUserBusy()
    return s:userIsBusy || mode() != 'n'
endfunction " }}}
" gdb#gdb#UpdateCmdWin: {{{
function! gdb#gdb#UpdateCmdWin()
    " This function gets called by the thread which is monitoring for
    " control to get back to the GDB process. This is called when the
    " program is still running but GDB has produced some output.

    let presWinNr = winnr()

    " If the Gdb command window is not open, don't do anything.
    let gdbWinNr = bufwinnr(s:GdbCmdWinBufNum)
    if gdbWinNr == -1
        return
    endif

    exec gdbWinNr.' wincmd w'
    python gdbClient.printNewLines()
    normal! G

    if gdbWinNr != presWinNr
        wincmd w
    endif

    redraw
endfunction " }}}
" gdb#gdb#OnResume: {{{
function! gdb#gdb#OnResume()
    " This function gets called when the background GDB process regains
    " control and is ready to process commands once again. We should
    " probably just go to the current frame when this happens.
    " call Debug('+gdb#gdb#OnResume', 'gdb')

    set balloonexpr=gdb#gdb#BalloonExpr()

    " We want to make sure that the command window shows the latest stuff
    " when we are given control. Too bad if the user is busy typing
    " something while this is going on.
    python gdbClient.getReply('FLUSH')
    call gdb#gdb#UpdateCmdWin()
    call gdb#gdb#GotoCurFrame()

    let pos = getpos('.')
    let bufnum = bufnr('%')

    call gdb#gdb#RefreshStack()
    call gdb#gdb#RefreshGdbVars()

    exec bufwinnr(bufnum).' wincmd w'
    call setpos('.', pos)

    call foreground()
    redraw
endfunction " }}}
" gdb#gdb#GetQueryAnswer:  {{{
" Description: 
function! gdb#gdb#GetQueryAnswer()
    python gdbClient.getQueryAnswer()
    return retval
endfunction " }}}

" ==============================================================================
" Miscellaneous GDB commands
" ============================================================================== 
" s:GdbGetCommandOutputSilent: gets the output of the command {{{
" Description: 
function! s:GdbGetCommandOutputSilent(cmd)
    if s:GdbWarnIfBusy()
        return ''
    endif

    python gdbClient.updateWindow = False
    exec 'python gdbClient.getCommandOutput("""'.a:cmd.' """, "retval")'
    python gdbClient.updateWindow = True
    return retval
endfunction " }}}
" s:GdbGetCommandOutput: gets the output of the command {{{
" Description: 
function! s:GdbGetCommandOutput(cmd)
    if s:GdbWarnIfBusy()
        return ''
    endif

    let pos = s:GetCurPos()
    exec 'python gdbClient.getCommandOutput("""'.a:cmd.' """, "retval")'
    call s:SetCurPos(pos)

    return retval
endfunction " }}}
" gdb#gdb#RunCommand: runs the given GDB command {{{
" Description: should only be used to run commands which do not transfer
" control back to the inferior program. Otherwise, the main VIM window
" itself will hang till an interrupt is sent to the inferior.
function! gdb#gdb#RunCommand(cmd)
    if s:GdbWarnIfBusy()
        return
    endif
    if a:cmd == ''
        let cmd = input('Enter GDB command to run: ')
    else
        let cmd = a:cmd
    endif

    let pos = s:GetCurPos()
    exec 'python gdbClient.runCommand("""'.cmd.'""")'
    call s:SetCurPos(pos)
endfunction " }}}
" gdb#gdb#Terminate: terminates the running GDB thread {{{
function! gdb#gdb#Terminate()
    if s:gdbStarted == 1
        python gdbClient.terminate()
        call s:RestoreUserMaps()
        call s:CloseAllGdbWindows()
        let s:gdbStarted = 0
    end
endfunction " }}}
" gdb#gdb#PlaceSign: places a sign at a given location {{{
" Description:  

let s:currentSignNumber = 1
sign define gdbCurFrame text==> texthl=Search linehl=Search
function! gdb#gdb#PlaceSign(file, lnum)

    " Goto the window showing this file or the first listed buffer.
    call s:OpenFile(a:file)

    " Now goto the correct cursor location and place the sign.
    call cursor(a:lnum, 1)
    exec 'sign place 1 name=gdbCurFrame line='.a:lnum.' file='.a:file
endfunction " }}}
" gdb#gdb#IsBusy: tells if inferior program is running {{{
" Description: 
function! gdb#gdb#IsBusy()
    py vim.command('let retval = %s' % gdbClient.isBusy())
    return retval
endfunction " }}}
" s:GdbWarnIfNotStarted: warns if GDB has not been started {{{
" Description:  
function! s:GdbWarnIfNotStarted( )
    if s:gdbStarted == 0
        echohl Error
        echomsg "Gdb is not started. Start it and then run commands"
        echohl None
        return 1
    endif
    return 0
endfunction " }}}
" s:GdbWarnIfBusy: warns if GDB is busy {{{
" Description:  
function! s:GdbWarnIfBusy()
    if s:GdbWarnIfNotStarted()
        return 1
    endif
    if gdb#gdb#IsBusy()
        echohl Search
        echomsg "Gdb is busy. Interrupt the program or try again later."
        echohl None
        return 1
    endif
    return 0
endfunction " }}}
" gdb#gdb#RunOrResume: runs or resumes a GDB command {{{
" Description: This function tries to figure out whether the given command
" returns control back to GDB and if so uses ResumeProgram rather than run.
function! gdb#gdb#RunOrResume(arg)
    if a:arg =~ '^start$'
        call gdb#gdb#Init()
    elseif a:arg =~ '^\(r\%[un]\|re\%[turn]\|co\%[ntinue]\|fi\%[nish]\|st\%[epi]\|ne\%[xti]\)\>'
        call gdb#gdb#ResumeProgram(a:arg)
    else
        call gdb#gdb#RunCommand(a:arg)
    endif
endfunction " }}}
" gdb#gdb#SetQueryAnswer: sets an answer for future queries {{{
" Description: 
function! gdb#gdb#SetQueryAnswer(ans)
    if a:ans != ''
        exec 'py gdbClient.queryAnswer = "'.a:ans.'"'
    else
        exec 'py gdbClient.queryAnswer = None'
    endif
endfunction " }}}

" ==============================================================================
" Stack manipulation and information
" ============================================================================== 
" gdb#gdb#GotoCurFrame: places cursor at current frame {{{
" Description: 
function! gdb#gdb#GotoCurFrame()
    if s:GdbWarnIfBusy()
        return
    endif

    sign unplace 1
    python gdbClient.gotoCurrentFrame()
    redraw
endfunction " }}}
" gdb#gdb#FrameUp: goes up the stack (i.e., to caller function) {{{
" Description:  
function! gdb#gdb#FrameUp()
    if s:GdbWarnIfBusy()
        return
    endif

    call gdb#gdb#RunCommand('up')
    call gdb#gdb#GotoCurFrame()
endfunction " }}}
" gdb#gdb#FrameDown: goes up the stack (i.e., to caller function) {{{
" Description:  
function! gdb#gdb#FrameDown()
    if s:GdbWarnIfBusy()
        return
    endif

    call gdb#gdb#RunCommand('down')
    call gdb#gdb#GotoCurFrame()
endfunction " }}}
" gdb#gdb#FrameN: goes to the n^th frame {{{
" Description:  
function! gdb#gdb#FrameN(frameNum)
    if s:GdbWarnIfBusy()
        return
    endif

    if a:frameNum < 0
        let frameNum = input('Enter frame number to go to: ')
    else
        let frameNum = a:frameNum
    endif
    call s:GdbGetCommandOutputSilent('frame '.frameNum)
    call gdb#gdb#GotoCurFrame()
endfunction " }}}
" gdb#gdb#GotoSelectedFrame: goes to the selected frame {{{
function! gdb#gdb#GotoSelectedFrame()
    let frameNum = matchstr(getline('.'), '\d\+')
    if frameNum != ''
        call gdb#gdb#FrameN(frameNum)
    else
        call gdb#gdb#FrameN(-1)
    endif
endfunction " }}}
" gdb#gdb#ExpandStack:  {{{
" Description: 
function! gdb#gdb#ExpandStack(numFrames)
    exec 'python gdbClient.expandStack('.a:numFrames.')'
    setlocal nomod
endfunction " }}}
" gdb#gdb#ShowStack: shows current GDB stack {{{
" Description:  

function! gdb#gdb#ShowStack()
    if s:GdbWarnIfBusy()
        return
    endif

    let s:GdbStackWinBufNum = gdb#gdb#GdbOpenWindow(s:GdbStackWinName)
    " remove original stuff.
    % d _
    python gdbClient.expandStack(10)
    " Remove all empty lines.
    g/^\s*$/d_

    setlocal nowrap
    setlocal nomod

    " set up a local map to go to the required frame.
    exec "nmap <buffer> <silent> <CR>           :call gdb#gdb#GotoSelectedFrame()<CR>"
    exec "nmap <buffer> <silent> <2-LeftMouse>  :call gdb#gdb#GotoSelectedFrame()<CR>"
    exec "nmap <buffer> <silent> <tab> :call gdb#gdb#ExpandStack(10)<CR>"
    exec "nmap <buffer> <silent> <C-tab> :call gdb#gdb#ExpandStack(9999)<CR>"
endfunction " }}}
" gdb#gdb#RefreshStack: refreshes stack trace shown {{{
" Description: 
function! gdb#gdb#RefreshStack()
    if bufwinnr(s:GdbStackWinBufNum) != -1
        call gdb#gdb#ShowStack()
    endif
endfunction " }}}

" ==============================================================================
" Break-point stuff.
" ============================================================================== 
" gdb#gdb#SetBreakPoint: {{{

let s:numBreakPoints = 0

exec 'sign define gdbBreakPoint text=!! icon='.s:scriptDir.'/bp.png texthl=Error'
function! gdb#gdb#SetBreakPoint()
    call s:SetBreakPointAt(expand('%:p'), line('.'), gdb#gdb#GetAllBreakPoints())

    let g:GdbBreakPoints = join(gdb#gdb#GetAllBreakPoints(), "\n")
endfunction " }}}
" s:SetBreakPointAt: sets breakpoint at (file, line) {{{
" Description: 
function! s:SetBreakPointAt(fname, lnum, prevBps)
    " To fix very strange problem with setting breakpoints in files on
    " network drives.
    let fnameTail = fnamemodify(a:fname, ':t')
    
    if s:gdbStarted
        if s:GdbWarnIfBusy()
            return
        endif

        let output = s:GdbGetCommandOutput('break '.fnameTail.':'.a:lnum)
        if output !~ 'Breakpoint \d\+'
            return
        endif
    end

    let lnum = line('.')
    let spec = 'line='.a:lnum.' file='.a:fname
    let idx = index(a:prevBps, spec)
    if idx < 0
        let signId = (1024+s:numBreakPoints)

        " FIXME: Should do this only if a sign is already not placed at
        " this location.
        exec 'sign place '.signId.' name=gdbBreakPoint '.spec
        let s:numBreakPoints += 1
    endif
endfunction " }}}
" gdb#gdb#ClearBreakPoint: clears break point {{{
" Description:  
function! gdb#gdb#ClearBreakPoint()
    if s:gdbStarted == 1
        if s:GdbWarnIfBusy()
            return
        endif
        " ask GDB to clear breakpoints here.
        call gdb#gdb#RunCommand('clear '.expand('%:p:t').':'.line('.'))
    endif

    let spec = 'line='.line('.').' file='.expand('%:p')

    while 1
        let again = 0
        try
            " Ideally we would only remove breakpoints set by GDB. But
            " since I use breakpoints only set by us, it doesn't matter.
            sign unplace
            let again = 1
        catch /E159/
            " no more signs in this location
            break
        endtry
    endwhile

    let g:GdbBreakPoints = join(gdb#gdb#GetAllBreakPoints(), "\n")
endfunction " }}}
" gdb#gdb#GetAllBreakPoints: gets all breakpoints set by us {{{
" Description: 
function! gdb#gdb#GetAllBreakPoints()
    let signs = s:GetCommandOutput('sign place')

    let bps = []
    let fname = ''
    for line in split(signs, "\n")
        if line =~ 'Signs for'
            let fname = matchstr(line, 'Signs for \zs.*\ze:$')
            let fname = fnamemodify(fname, ':p')
        endif
        if line =~ 'name=gdbBreakPoint'
            let lnum = matchstr(line, 'line=\zs\d\+\ze')
            let bps += ['line='.lnum.' file='.fname]
        endif
    endfor

    return bps
endfunction " }}}
" gdb#gdb#RedoAllBreakpoints: refreshes the breakpoints {{{
" Description: 
function! gdb#gdb#RedoAllBreakpoints()
    call gdb#gdb#SetQueryAnswer('y')
    let breakPoints = gdb#gdb#GetAllBreakPoints()
    for bp in breakPoints
        let items = matchlist(bp, 'line=\(\d\+\) file=\(.*\)')
        let line = items[1]
        let fname = items[2]
        call s:SetBreakPointAt(fname, line, breakPoints)
    endfor
    call gdb#gdb#SetQueryAnswer('')
endfunction " }}}
" gdb#gdb#ToggleBreakPoint: toggle breakpoint {{{
" Description: 
function! gdb#gdb#ToggleBreakPoint()
    let signs = s:GetCommandOutput('sign place buffer='.bufnr('%'))
    for line in split(signs, '\n')
        if line =~ 'line='.line('.').'.* name=gdbBreakPoint'
            call gdb#gdb#ClearBreakPoint()
            return
        endif
    endfor
    call gdb#gdb#SetBreakPoint()
endfunction " }}}
" gdb#gdb#RestoreSessionBreakPoints:  {{{
" Description: 

let s:restoredSessionBreakPoints = 0
function! gdb#gdb#RestoreSessionBreakPoints()
    if exists('g:GdbBreakPoints') && s:restoredSessionBreakPoints == 0
        let s:restoredSessionBreakPoints = 1
        let breakPoints = split(g:GdbBreakPoints, "\n")

        for bp in breakPoints
            let signId = (1024+s:numBreakPoints)
            let fname = matchstr(bp, 'file=\zs.*\ze')
            if bufnr(fname) == -1
                let lnum = matchstr(bp, 'line=\zs\d\+\ze')
                exec 'badd +'.lnum.' '.fname
            endif
            exec 'sign place '.signId.' name=gdbBreakPoint '.bp
            let s:numBreakPoints += 1
        endfor
    endif
endfunction " }}}

" ==============================================================================
" Program execution, stepping, continuing etc.
" ============================================================================== 
" gdb#gdb#Attach: attach to a running program {{{
" Description: 
" s:GetPidFromName: gets the PID from the name of a program {{{
" Description: 
function! s:GetPidFromName(name)
    let ps = system('ps -u '.$USER.' | grep '.a:name)
    if ps == ''
        echohl ErrorMsg
        echo "No running '".a:name."' process found"
        echohl NOne
        return ''
    end

    if ps =~ '\n\s*\d\+'
        echohl ErrorMsg
        echo "Too many running '".a:name."' processes. Don't know which to attach to. Use a PID"
        echohl None
        return ''
    end
    return matchstr(ps, '^\s*\zs\d\+')
endfunction " }}}
function! gdb#gdb#Attach(pid)
    let pid = a:pid
    if pid == ''
        let input = input('Enter the PID or process name to attach to :')
        if input =~ '^\d\+$'
            let pid = input
        else
            let pid = s:GetPidFromName(input)
        endif
    endif
    if pid !~ '^\d\+$'
        return
    end
    if s:gdbStarted == 0
        call s:GdbInitWork()
    endif
    call gdb#gdb#RunCommand('attach '.pid)
endfunction " }}}
" gdb#gdb#ResumeProgram: gives control back to the inferior program {{{
" Description: This should be used for GDB commands which could potentially
" take a long time to finish.
function! gdb#gdb#ResumeProgram(cmd)
    if s:GdbWarnIfBusy()
        return
    endif
    sign unplace 1
    set balloonexpr=

    exec 'python gdbClient.resumeProgram("""'.a:cmd.'""")'
endfunction " }}}
" gdb#gdb#Run: runs the inferior program {{{
function! gdb#gdb#Run()
    call gdb#gdb#ResumeProgram('run')
endfunction " }}}
" gdb#gdb#Continue: {{{
function! gdb#gdb#Continue()
    if s:GdbWarnIfBusy()
        return
    endif
    call gdb#gdb#ResumeProgram('continue')
endfunction " }}}
" gdb#gdb#RunOrContinue: runs/continues the inferior {{{
" Description: 
function! gdb#gdb#RunOrContinue()
    let output = s:GdbGetCommandOutputSilent('info program')
    if output =~ 'not being run'
        call gdb#gdb#Run()
    else
        call gdb#gdb#Continue()
    endif
endfunction " }}}
" gdb#gdb#Next: {{{
function! gdb#gdb#Next()
    call gdb#gdb#ResumeProgram('next')
endfunction " }}}
" gdb#gdb#Step: {{{
function! gdb#gdb#Step()
    call gdb#gdb#ResumeProgram('step')
endfunction " }}}
" gdb#gdb#Return: {{{
function! gdb#gdb#Return()
    " Should we just do a gdb#gdb#RunCommand here?
    call gdb#gdb#ResumeProgram('return')
endfunction " }}}
" gdb#gdb#Finish: {{{
function! gdb#gdb#Finish()
    call gdb#gdb#ResumeProgram('finish')
endfunction " }}}
" gdb#gdb#Until: runs till cursor position {{{
" Description: 
function! gdb#gdb#Until()
    " we use Resume rather than Run because the program could potentially
    " never reach here.
    call gdb#gdb#ResumeProgram('until '.expand('%:p:t').':'.line('.'))
endfunction " }}}
" gdb#gdb#Interrupt: interrupts the inferior program {{{
function! gdb#gdb#Interrupt( )
    if s:GdbWarnIfNotStarted()
        return
    endif
    python gdbClient.interrupt()
    call gdb#gdb#OnResume()
endfunction " }}}
" gdb#gdb#Kill: kills the inferior {{{
function! gdb#gdb#Kill()
    if s:GdbWarnIfNotStarted()
        return
    endif
    if gdb#gdb#IsBusy()
        python gdbClient.interrupt()
    endif
    call gdb#gdb#RunCommand('kill')
    let progInfo = s:GdbGetCommandOutputSilent('info program')
    if progInfo =~ 'is not being run'
        sign unplace 1
        set balloonexpr=
        call gdb#gdb#Terminate()
    else
        call gdb#gdb#OnResume()
    endif
endfunction " }}}

" ==============================================================================
" Balloon expression
" ============================================================================== 
" gdb#gdb#BalloonExpr: balloonexpr for GDB {{{
function! gdb#gdb#BalloonExpr()
    if gdb#gdb#IsBusy()
        return ''
    endif
    let str = s:GetContingString(v:beval_bufnr, v:beval_lnum, v:beval_col)
    let eval = s:GdbGetCommandOutputSilent('print '.str)
    let eval =  matchstr(eval, '\$\d\+ = \zs.\{-}\ze\r')
    return str.' = '.eval
endfunction " }}}
" gdb#gdb#PrintExpr: prints the expression under cursor {{{
" Description:  
function! gdb#gdb#PrintExpr()
    let str = s:GetContingString(bufnr('%'), line('.'), col('.'))
    call gdb#gdb#RunCommand('print '.str)
endfunction " }}}
" s:GetContingString: returns the longest chain of struct refs {{{
function! s:GetContingString(bufnr, lnum, col)
    let txtlist = getbufline(a:bufnr, a:lnum)
    if len(txtlist) == 0
        return ''
    endif

    let txt = txtlist[0]
    if txt[a:col-1] !~ '\k'
        return ''
    endif

    let pretxt = strpart(txt, 0, a:col)
    let pretxt = matchstr(pretxt, '\(\w\+\(\(->\)\|\.\)\)*\w\+$')
    let posttxt = strpart(txt, a:col)
    let posttxt = matchstr(posttxt, '^\(\w\+\)')

    let matchtxt = pretxt.posttxt
    return matchtxt
endfunction " }}}

" ==============================================================================
" Variable watching and expansion
" ============================================================================== 
" gdb#gdb#AddGdbVar: adds a GDB variable {{{
" Description: 

" gdb#gdb#OpenGdbVarsWindow:  {{{
" Description: 
let s:GdbVarWinBufNum = -1
function! gdb#gdb#OpenGdbVarsWindow()
    let redoMaps = (bufwinnr(s:GdbVarWinName) == -1)
    
    let s:GdbVarWinBufNum = gdb#gdb#GdbOpenWindow(s:GdbVarWinName)

    if redoMaps
        0 put='# Press <tab> to expand/collapse the hierarchy'
        $ d _

        nmap <buffer> <silent> <tab> :call gdb#gdb#ToggleGdbVar()<CR>
        nmap <buffer> <silent> <del> :call gdb#gdb#DeleteGdbVar(0)<CR>
        nmap <buffer> <silent> <S-del> :call gdb#gdb#DeleteGdbVar(1)<CR>
        setlocal ft=gdbvars nowrap
    endif

endfunction " }}}
function! gdb#gdb#AddGdbVar(inExpr)
    if s:GdbWarnIfBusy()
        return
    endif

    if a:inExpr != ''
        let expr = a:inExpr
    else
        let expr = s:GetContingString(bufnr('%'), line('.'), col('.'))
    endif

    call gdb#gdb#OpenGdbVarsWindow()

    exec 'python gdbClient.addGdbVar("'.expr.'")'
endfunction " }}}
" gdb#gdb#ExpandGdbVar:  {{{
" Description: 
function! gdb#gdb#ExpandGdbVar()
    python gdbClient.expandGdbVar()
endfunction " }}}
" gdb#gdb#CollapseGdbVar:  {{{
" Description: 
function! gdb#gdb#CollapseGdbVar()
    python gdbClient.collapseGdbVar()

    " Now remove all lines beneath this one with greater indentation that
    " this one. This basically collapses the tree beneath this one.
    let curLine = line('.')
    let lastLine = line('$')
    let curInd = strlen(matchstr(getline('.'), '^[co ]\s*'))
    while 1
        let nextInd = strlen(matchstr(getline(curLine + 1), '^[co ]\s*'))
        if nextInd <= curInd
            break
        endif
        exec (curLine+1).' d _'
    endwhile

endfunction " }}}
" gdb#gdb#ToggleGdbVar:  {{{
" Description: 
function! gdb#gdb#ToggleGdbVar()
    if s:GdbWarnIfBusy()
        return
    endif

    if matchstr(getline('.'), '^\s*-') != ''
        call gdb#gdb#CollapseGdbVar()
    elseif matchstr(getline('.'), '^\s*+') != ''
        call gdb#gdb#ExpandGdbVar()
    endif
endfunction " }}}
" gdb#gdb#RefreshGdbVars:  {{{
" Description: 
function! gdb#gdb#RefreshGdbVars()
    if bufwinnr(s:GdbVarWinBufNum) != -1
        call gdb#gdb#OpenGdbVarsWindow()
        " remove all previous notifications.
        %s/^[^#]/ /
        python gdbClient.refreshGdbVars()
    endif
endfunction " }}}
" gdb#gdb#DeleteGdbVar:  {{{
" Description: 
function! gdb#gdb#DeleteGdbVar(wholeTree)
    if a:wholeTree == 1
        " go to the root of the tree
        if matchstr(getline('.'), '^...\w') == ''
            let found = search('^...\w', 'b')
            if found == 0
                return
            endif
        endif
    endif
    " First delete everything below.
    call gdb#gdb#CollapseGdbVar()
    " then delete itself.
    python gdbClient.deleteGdbVar()
    " then delete the current line.
    . d _
endfunction " }}}

" ==============================================================================
" utils
" ============================================================================== 
" gdb#gdb#GetLocal: returns a local variable {{{
" Description:  
function! gdb#gdb#GetLocal(varname)
    exec 'return s:'.a:varname
endfunction " }}}
" s:GetCommandOutput: gets the output of a vim command {{{
" Description: 
function! s:GetCommandOutput(cmd)
    let _a = @a
    " get a list of all signs
    redir @a
    exec 'silent! '.a:cmd
    redir END
    let output = @a
    let @a = _a

    return output
endfunction " }}}
" s:GetCurPos:  {{{
" Description: 
function! s:GetCurPos()
    let pos = getpos('.')
    let pos[0] = bufnr('%')
    return getpos('.')
endfunction " }}}
" s:SetCurPos:  {{{
" Description: 
function! s:SetCurPos(pos)
    let bufnr = a:pos[1]
    call s:OpenFile(bufname(bufnr))
    call setpos('.', a:pos)
endfunction " }}}
" s:OpenFile:  {{{
" Description: 
function! s:OpenFile(file)

    " Goto the window showing this file or the first listed buffer.
    let winnum = bufwinnr(a:file)
    if winnum == -1
        " file is not currently being shown
        " find the first listed buffer.
        let i = 1
        while i <= winnr('$')
            if getbufvar(winbufnr(i), '&buflisted') != 0 &&
                \ bufname(winbufnr(i)) !~ '_GDB_'
                let winnum = i
                break
            endif
            let i = i + 1
        endwhile
        if winnum == -1
            " no buffers are listed! Random case, just split open a new
            " window with the file.
            exec 'split '.a:file
        else
            " goto the window showing the first listed buffer and drop the
            " file onto it.
            exec winnum.' wincmd w'
            exec 'drop '.a:file
        endif
    else
        " goto the window showing the file.
        exec winnum.' wincmd w'
    endif

endfunction " }}}
" gdb#gdb#GetVar: gets script local var {{{
" Description: 
function! gdb#gdb#GetVar(varName)
    return s:{a:varName}
endfunction " }}}

" vim: fdm=marker
