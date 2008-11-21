" Vim syntax file
" Language:	gdbvars syntax file
" Maintainer:	<srinathava at googles email service>

if exists("b:current_syntax")
    finish
endif

syn match UnchangedVarLine /^ .*/ contains=Varname
syn match ChangedVarLine /^c.*/ contains=Varname,VarChangedToken

syn match Header /^#.*$/

syn match VarName /{[^{}]*}$/ contained
syn match VarChangedToken /^c/ contained

hi def link VarName Ignore
hi def link VarChangedToken Ignore
hi def link ChangedVarLine Search
hi def link Header Comment
