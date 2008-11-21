#include <iostream>

struct Foo {
    const char* foo1;

    struct Bar {
        int bar1;
        int bar2;
    } foo2;

    struct Baz {
        int baz1;
        struct Bam {
            int bam1;
            int bam2;
        } baz2;
        int baz3;
    } foo3;

    double foo4;
};

void foo(struct Foo f)
{
    (void)f;
}

void bar(struct Foo f)
{
    foo(f);
}

int main()
{
    struct Foo f = {
        "hello world",
        {2, 3},
        {4, {5, 6}, 7},
        8.0
    };

    struct Foo g = {
        "goodbye world",
        {2+1, 3+1},
        {4+1, {5+1, 6+1}, 7+1},
        8+1.0
    };

    while (1) {
        foo(f);
        bar(f);
        foo(g);
        bar(f);
        foo(f);

        std::string yesno;
        std::cout << "Press y<enter> to continue...";
        std::cin >> yesno; 
        if (yesno == "n") {
            break;
        }
    }
}

