#include <stdio.h>

int foo(int x) {
    return x + 2;
}

int main() {
    printf("hello world %d\n", foo(3));
    return 0;
}
