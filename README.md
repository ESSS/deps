Deps
====

[![link](https://img.shields.io/conda/vn/conda-forge/deps.svg)](https://anaconda.org/conda-forge/deps)
[![link](https://github.com/ESSS/deps/workflows/build/badge.svg)](https://github.com/ESSS/deps/actions)

Deps is a utility to execute commands on multiple projects.

It is meant to be used along with `conda devenv`: https://github.com/ESSS/conda-devenv, as such,
it reads the contents of the `includes` sections of `environment.devenv.yml`, which contains
the relative paths of the dependencies where commands should be executed.

Examples
=========

`deps inv codegen` will run `inv codegen` on the projects and its dependencies sequentially, respecting dependencies.

`deps inv codegen -j 16` will run `inv codegen` on the projects and its dependencies with paralelization,
but respecting dependencies (so, it'll only run in parallel commands after their own requisites have been fullfiled).

`deps inv codegen -j 16 --jobs-unordered` will run `inv codegen` on the projects and its dependencies
with full-paralelization, without respecting any particular order.

License
========

Free software: MIT license
