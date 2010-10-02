if has('gui_running')
    amenu &Gdb.Start\ Gdb               :call gdb#gdb#Init()<CR>
    amenu &Gdb.Show\ Command\ Window    :call gdb#gdb#ShowCmdWindow()<CR>

    amenu &Gdb.&Step        :call gdb#gdb#Step()<CR>
    amenu &Gdb.&Next        :call gdb#gdb#Next()<CR>
    amenu &Gdb.&Finish      :call gdb#gdb#Finish()<CR>
    amenu &Gdb.&Until       :call gdb#gdb#Until()<CR>
    amenu &Gdb.&Run         :call gdb#gdb#Run()<CR>
    amenu &Gdb.&Continue    :call gdb#gdb#Continue()<CR>
    amenu &Gdb.&Interrupt   :call gdb#gdb#Interrupt()<CR>
    amenu &Gdb.&Kill        :call gdb#gdb#Kill()<CR>

    amenu &Gdb.-sep00-      <Nop>

    amenu &Gdb.&Up\ Stack               :call gdb#gdb#FrameUp()<CR>
    amenu &Gdb.&Down\ Stack             :call gdb#gdb#FrameDown()<CR>
    amenu &Gdb.&Goto\ Frame             :call gdb#gdb#FrameN(-1)<CR>
    amenu &Gdb.Sho&w\ Stack             :call gdb#gdb#ShowStack()<CR>
    amenu &Gdb.Expand\ Full\ Stack      :call gdb#gdb#ExpandStack(9999)<CR>
    amenu &Gdb.Goto\ Current\ Frame     :call gdb#gdb#GotoCurFrame()<CR>

    amenu &Gdb.-sep01-      <Nop>

    amenu &Gdb.&Toggle\ Breakpoint      :call gdb#gdb#ToggleBreakPoint()<CR>

    amenu &Gdb.-sep1- <Nop>

    " print value at cursor
    nmenu &Gdb.&Print\ Value :call gdb#gdb#RunCommand("print " . expand("<cword>"))<CR>
    vmenu &Gdb.&Print\ Value y:call gdb#gdb#RunCommand("print <C-R>"")<CR>
    amenu &Gdb.Run\ Command  :call gdb#gdb#RunCommand('')<CR>

    amenu &Gdb.-sep2- <Nop>

    amenu &Gdb.&Attach :call gdb#gdb#Attach('')<CR>

    amenu &Gdb.-sep3- <Nop>

    amenu &Gdb.Handle\ SIGSEGV :call gdb#gdb#RunCommand('handle SIGSEGV stop print')<CR>
    amenu &Gdb.Ignore\ SIGSEGV :call gdb#gdb#RunCommand('handle SIGSEGV nostop noprint')<CR>
    
    amenu &Gdb.-sep4- <Nop>
    amenu &Gdb.Panic! :call gdb#gdb#Panic()<CR>

    amenu 80.5 PopUp.Run\ to\ cursor\ (GDB) :call gdb#gdb#Until()<CR>
    amenu 80.5 PopUp.Jump\ to\ cursor\ (GDB) :call gdb#gdb#Jump()<CR>
    amenu 80.6 PopUp.Examine\ Data\ (GDB)   :call gdb#gdb#AddGdbVar('')<CR>
    amenu 80.7 PopUp.-sep-gdb0- <Nop>
endif

com! -nargs=1 GDB :call gdb#gdb#RunOrResume(<q-args>)
com! -nargs=? GDBEX :call gdb#gdb#AddGdbVar(<q-args>)

augroup GdbRestoreSessionBreakPoints
    au SessionLoadPost * call gdb#gdb#RestoreSessionBreakPoints()
augroup END

" vim: fdm=marker
