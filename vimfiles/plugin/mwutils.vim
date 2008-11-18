" ==============================================================================
" A common place for all the utility scripts. The actual body lies in the
" autoload/ directory.
" ============================================================================== 

command! -nargs=1 -complete=dir DWithOther :call mw#sbtools#DiffWithOther(<f-args>)
command! -nargs=1 -complete=dir SWithOther :call mw#sbtools#SplitWithOther(<f-args>)
command! -nargs=1 -complete=dir DiffSandbox1 :call mw#sbtools#DiffWriteable1(<f-args>)
command! -nargs=+ -complete=dir DiffSandbox2 :call mw#sbtools#DiffWriteable2(<f-args>)
command! -nargs=* -complete=file DiffSubmitFile :call mw#sbtools#DiffSubmitFile(<f-args>)
command! -nargs=0 -range ReplaceOldNodesWithnew :call mw#node#ReplaceOldNodesWithNew()
command! -nargs=0 -range NumbersToDotty :'<, '> call mw#num2dot#DoIt()
command! -nargs=0 -range AddHeaderProtection :call mw#addHeaderProtection#DoIt()

command! -nargs=0 InitCppCompletion :call cpp_omni#Init()

com! -nargs=1 -bang -complete=customlist,EditFileComplete
       \ EditFile call EditFileUsingLocate(<q-args>)
let g:EditFileComplete_Debug = ''
let s:lastArg = ''
fun! EditFileComplete(A,L,P)
    " let g:EditFileComplete_Debug .= "called with '".a:A."', lastArg = '".s:lastArg."'\n"

    let alreadyFiltered = 0
    if s:lastArg != '' && a:A =~ '^'.s:lastArg
        let files = s:lastFiles
        let alreadyFiltered = 1
    else
        let g:EditFileComplete_Debug .= "doing sblocate\n"
        let files = split(system('sblocate '.a:A), "\n")
    end
    " let g:EditFileComplete_Debug .= "files = ".join(files, "\n")."\n"

    if alreadyFiltered == 0
        call filter(files, 'v:val !~ "CVS"')
        call filter(files, 'v:val =~ "\\(cpp\\|hpp\\|m\\)$"')
        " call filter(files, 'v:val =~ "matlab/\\(src/\\(cg_ir\\|rtwcg\\|simulink\\)\\|toolbox/stateflow\\|test/tools/sfeml\\)"')
        call filter(files, 'v:val =~ "/'.a:A.'[^/]*$"')
        call map(files, 'matchstr(v:val, "'.a:A.'[^/]*$")') 
    else
        call filter(files, 'v:val =~ "^'.a:A.'"')
    endif

    let s:lastArg = a:A
    let s:lastFiles = files
    return files
endfun

fun! EditFileUsingLocate(file)
    let files = split(system('sblocate '.a:file), "\n")
    for f in files
        if filereadable(f) && f =~ a:file.'$'
            exec 'drop '.f
            return
        endif
    endfor
endfun

if !has('gui_running')
    finish
endif

amenu &Mathworks.Diff\ current\ file\ with\ other\ sandbox :DWithOther
amenu &Mathworks.Split\ current\ file\ with\ other\ sandbox :SWithOther
amenu &Mathworks.Diff\ current\ sandbox\ with\ other\ sandbox :DiffSandbox1
amenu &Mathworks.Diff\ two\ sandboxes :DiffSandbox2
amenu &Mathworks.Diff\ Sandboxes\ using\ submit\ file :DiffSubmitFile
amenu &Mathworks.Add\ current\ file\ to\ submit\ list :!add.py %:p<CR>
amenu &Mathworks.-sep-sandbox- <Nop>
amenu &Mathworks.Replace\ old\ node\ defs\ with\ new :ReplaceOldNodesWithnew<CR>
vmenu &Mathworks.Convert\ connections\ to\ dotty :NumbersToDotty<CR>
amenu &Mathworks.Add\ header\ protection :AddHeaderProtection<CR>
amenu &Mathworks.-sep-sandbox2- <Nop>
amenu &Mathworks.Initialize\ C++\ Completion :InitCppCompletion<CR>

