#include <dlfcn.h>
#include <stdio.h>

int main(int argc, char** argv) {
  void* h = dlopen(argc > 1 ? argv[1] : "./libsample.so", RTLD_NOW);
  if (!h) { fprintf(stderr, "%s\n", dlerror()); return 1; }
  int (*run)(const char*) = (int (*)(const char*))dlsym(h, "sample_run");
  int r = run("7");
  printf("sample_run = %d\n", r);
  return r == 25 ? 0 : 2;
}
