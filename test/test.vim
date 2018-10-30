" VimTest_Log:  {{{
" Description: 
function! VimTest_Log(msg)
    call writefile([a:msg], '/tmp/vim_test.log')
endfunction " }}}

" VimTest_Fail: fails the current test by raising an exception {{{
" Description: 
function! VimTest_Fail(msg)
    call VimTest_Log(a:msg)
    throw 'TestError: '.a:msg
endfunction " }}}

" VimTest_GetCommandOutput: gets the output of a vim command {{{
" Description: 
function! VimTest_GetCommandOutput(cmd)
    let _a = @a
    " get a list of all signs
    redir @a
    exec 'silent! '.a:cmd
    redir END
    let output = @a
    let @a = _a

    return output
endfunction " }}}

" GdbTest_WaitForGdb: waits for GDB to not be busy {{{
function! GdbTest_WaitForGdb()
    let n = 0
    while gdb#gdb#IsBusy()
        sleep 100 m
        let n = n + 1
        if n == 20
            break
        endif
    endwhile
    sleep 100 m
    redraw!
endfunction " }}}

" Test_GetSigns:  {{{
function! Test_GetSigns()
    return VimTest_GetCommandOutput('sign place file=testit.cpp')
endfunction " }}}

" Test_Main: {{{
function! Test_main()
    edit testit.cpp
    let g:GdbCmd = 'gdb --annotate=3'

    " Set a breakpoint at line 4
    4
    exec "normal \<F9>"
    if Test_GetSigns() !~ 'line=4[^\n]*name=gdbBreakPoint'
        call VimTest_Fail('FAILED to set sign for breakpoint')
    endif

    GDB start
    GDB file /tmp/vim_test.bin

    " Run and ensure breakpoint is hit
    GDB run
    call GdbTest_WaitForGdb()
    if Test_GetSigns() !~ 'line=4[^\n]*name=gdbCurFrame'
        call VimTest_Fail('FAILED to run to current breakpoint')
    endif

    " Attempt to restart from beginning
    call gdb#gdb#SetQueryAnswer('y')
    GDB run
    call GdbTest_WaitForGdb()
    if Test_GetSigns() !~ 'line=4[^\n]*name=gdbCurFrame'
        call VimTest_Fail('FAILED to restart and run to current breakpoint')
    endif

    " Navigate up the stack
    normal U
    if Test_GetSigns() !~ 'line=8[^\n]*name=gdbCurFrame'
        call VimTest_Fail('FAILED to go up the stack')
    endif

    " Navigate down the stack
    normal D
    if Test_GetSigns() !~ 'line=4[^\n]*name=gdbCurFrame'
        call VimTest_Fail('FAILED to go down the stack')
    endif

    exec "normal /x\<CR>"
    exec "normal \<C-P>"
    let txt = gdb#gdb#BalloonExpr()
    if txt !~ "= 3"
        call VimTest_Fail('FAILED to evaluate balloonexpr for current position')
    endif
    let txt = join(getbufline(bufnr('_GDB_Command_Window_'), 1, '$'), "\n")
    if txt !~ 'print x'
        call VimTest_Fail('FAILED to see value of variable in GDB window')
    endif

    " Kill GDB
    call gdb#gdb#SetQueryAnswer('y')
    call gdb#gdb#Kill()
    if bufwinnr('_GDB_Command_Window_') != -1
        call VimTest_Fail('FAILED to close GDB window on kill')
    endif
endfunction " }}}

" Test_Wrapper {{{
function! Test_Wrapper()
    " Initialize log
    call VimTest_Log('START')
    try
        call Test_main()
    catch /TestError/
        echomsg "Test FAILED!"
        echomsg v:exception
        return
    endtry

    call VimTest_Log('SUCCESS')
    quitall!
endfunction " }}}

call Test_Wrapper()
