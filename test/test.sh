#!/usr/bin/env bash

make
if [ "${VIM}" == "" ]; then
    VIM="vim"
fi
${VIM} -g -f -S test.vim
cat /tmp/vim_test.log
