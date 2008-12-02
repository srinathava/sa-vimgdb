" cpp_omni#GetLastToken: gets previous token {{{
" Description: 
function! cpp_omni#GetLastToken()
	call search('\(->\|\.\|::\|\w\+\|)\|>\|;\|{\|}\)', 'b')
	let fromhere = strpart(getline('.'), col('.')-1)
	if fromhere =~ '^\(->\|\.\|::\)'
		return '->'
	elseif fromhere =~ '^)'
		return ')'
    elseif fromhere =~ '^>'
        return '>'
    elseif fromhere =~ '^\(;\|{\|}\)' ||
        \ synIDattr(synID(line("."),col("."),1),"name") =~? 'comment'
        return ';'
	else
		return matchstr(fromhere, '^\w\+')
	endif
endfunction " }}}
" cpp_omni#GetWordType: gets type of the word under cursor {{{
" Description: 
function! cpp_omni#GetWordType(word)
	let pos = getpos('.')
	let type = cpp_omni#GetWordTypeMove(a:word)
	call setpos('.', pos)
	return type
endfunction " }}}
" cpp_omni#GetWordTypeMove: gets the type of the word {{{
function! cpp_omni#GetWordTypeMove(word)
    " we use the builtin searchdecl() function inspite of several
    " deficiencies because thats the best we got.
	if searchdecl(a:word) == 0
        " keep going back word by word till we get to the end of the
        " previous statement. The type then has to be the first succeeding
        " word.
        return cpp_omni#GetWordChain()
	else
		return []
	endif
endfunction " }}}
" cpp_omni#GetWordChain: gets the chain of operations upto the cursor {{{
" Description: 
function! cpp_omni#GetWordChain()
	let pos = getpos('.')
	let chain = cpp_omni#GetWordChainRec()
	call setpos('.', pos)
	return chain
endfunction " }}}
" cpp_omni#GetWordChainRec: gets the type of the last word {{{
" Description: 
function! cpp_omni#GetWordChainRec()
	" from
	" 	NS::foo -> bar(arg1, arg2)->baz->goo()->dee->da
	" we want to form the list
	" 	['NS', 'foo', 'bar', 'baz', 'goo', 'dee', 'da']
	"
	" Note that we want to ignore the ``right'' kind of whitespace.
	
	let thisToken = cpp_omni#GetLastToken()
    call Debug('thisToken = '.thisToken, 'omni')
    if thisToken == ';'
        return []
    elseif thisToken == ')'
		call searchpair('(', '', ')', 'b')
		let thisToken = cpp_omni#GetLastToken()
    elseif thisToken == '>'
		call searchpair('<', '', '>', 'b')
		let thisToken = cpp_omni#GetLastToken()
	elseif thisToken == '->'
		let thisToken = cpp_omni#GetLastToken()
		if thisToken == ')'
			call searchpair('(', '', ')', 'b')
			let thisToken = cpp_omni#GetLastToken()
		endif
	endif

	let prevToken = cpp_omni#GetLastToken()
    call Debug('prevToken = '.prevToken, 'omni')

	if prevToken != '->'
		return [thisToken]
	else
		let previousList = cpp_omni#GetWordChainRec()
		call extend(previousList, [thisToken])
		return previousList
	endif
endfunction " }}}
" cpp_omni#PrintVOD: prints debug info from python {{{
function! cpp_omni#PrintVOD()
    python import parsetags
    python print parsetags.vimOmniDebug 
endfunction " }}}
" cpp_omni#GetCompletions: returns the list of possible completions {{{
function! cpp_omni#GetCompletions(findstart, base)
	if a:findstart == 1
		let lineToCursor = strpart(getline('.'), 0, col('.')-1)
		let lastWord = matchstr(lineToCursor, '\w*$')
		call Debug('lastWord = '.lastWord, 'myo')
		return col('.') - strlen(lastWord) - 1
		" return col('.') - 1
	else
		call Debug('base = '.a:base, 'myo')
		exec 'python tagsCompleter.performCompletion("'.a:base.'")'
	endif
endfunction " }}}

" cpp_omni#FindDeclaration: finds the declaration of a symbol {{{
" Description: made because the builtin searchdecl() function completely
" sucks.
function! cpp_omni#FindDeclaration()
    " We are somewhat conservative. This algorithm probably is not very
    " general... What we search for is patterns of the form:
    " 
    " int a;
    " int *a;
    " foo<class> *a;
    " foo<bar<class>,baz> a;
    "
    " For the moment, we are not going to bother with function pointer
    " declarations.

    " A template class is of the form:
    "   foo<expr1,expr2,...>
    " where expr1 itself could be a template class. We build the RE for
    " this recursively.
    "
    " Since regular expressions cannot search the very general case where
    " the template classes are arbitrarily nested, we restrict ourselves to
    " only depth 3.

    let arg1 = '\w+'
    let arglist = arg1.'(\s*,\s*'.arg1.'\s*)*'
    let templ0 = '\w+\s*\<\s*'.arglist.'\s*\>'

    let arg2 = '('.arg1.'|'.templ0.')'
    let arglist2 = arg2.'(\s*,\s*'.arg2.'\s*)*'
    let templ1 = '\w+\s*\<'.arglist2.'\s*\>'

    let arg3 = '('.arg2.'|'.templ0.')'
    let arglist3 = arg3.'(\s*,'.arg3.'\s*)*'
    let templ2 = '\w+\s*\<\s*'.arglist3.'\s*\>'
    " templ2 matches an expression like:
    "
    "       foo<bar<baz<bb,cc>,bam>,boo>

    let declpat = '\v(\w+)|('.templ0.')\s+(\*)*'
    return declpat
endfunction " }}}

" cpp_omni#ProceedWithCompletion: proceeds with completion if possible {{{
" Description: 
function! cpp_omni#ProceedWithCompletion(char)
    if synIDattr(synID(line("."), col(".")-1, 1), "name") =~? 'comment'
        return a:char
    else
        if a:char == '.'
            return ".\<C-x>\<C-o>"
        elseif a:char == '>' && getline('.')[col('.')-2] == '-'
            return ">\<C-x>\<C-o>"
        elseif a:char == ':' && getline('.')[col('.')-2] == ':'
            return ":\<C-x>\<C-o>"
        else
            return a:char
        endif
    endif
endfunction " }}}
" inoremap <buffer> <expr> . cpp_omni#ProceedWithCompletion(".")
" inoremap <buffer> <expr> > cpp_omni#ProceedWithCompletion(">")
" inoremap <buffer> <expr> : cpp_omni#ProceedWithCompletion(":")

let s:scriptPath = expand('<sfile>:p:h')
" cpp_omni#Init: initialization routine {{{
function! cpp_omni#Init()
    if !exists('b:doneOnce')
        let b:doneOnce = 1

        python import sys
        execute 'python sys.path += [r"'.s:scriptPath.'"]'
        python from parsetags import VimTagsCompleter
        python tagsCompleter = VimTagsCompleter()
        setlocal omnifunc=cpp_omni#GetCompletions
    endif
endfunction " }}}

let g:Omni_Debug = ''

" vim: fdm=marker
