#include <stdio.h>

void foo(double a)
{
    int tmp = (int) a;
    printf("a = %g\n", a);
}

void bar(double a)
{
    foo(a);
}

int main()
{
    foo(2.5);
    bar(3.5);
    foo(4.5);
    bar(5.5);
}
