Deps
====

[![link](https://img.shields.io/conda/vn/conda-forge/deps.svg)](https://anaconda.org/conda-forge/deps)
[![link](https://github.com/ESSS/deps/workflows/build/badge.svg)](https://github.com/ESSS/deps/actions)
[![link](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

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

Usage
=====

Program to list dependencies of a project, or to execute a command for each dependency:

    deps [OPTIONS] [COMMAND]...

To list dependency projects, one per line (if "-p directory" is omitted, it will use the current, or will find the first ancestor directory containing an `environment.devenv.yml` file):

    deps -p mylib10 -p myotherlib20

This may be used in combination with shell commands (useful for `source`ing files), e.g., to iterate on dependencies in windows (cmd):

    for %%i in ('deps -p mylib10') do <something> %%i [...]

To iterate on dependencies in unix (bash):

    deps | xargs -0 -I {} <something> {} [...]

To use deps to execute a command for each dependency (will spawn a new shell for each dependency):

    deps [parameters] <command>

To prevent deps to process any option or flags passed to command a "--" can be used:

    deps [parameters] -- <command> --with --flags

`<command>` may contain some variables:

* {name}: The dependency bare name (ex.: eden)
* {abs}:  The dependency absolute path (ex.: X:\ws\eden)

If the option --require-file is used dependencies not having a file named as this relative to the given dependency root directory are skipped:

    deps --require-file Makefile -- make clean

When passing parameters that can be used multiple times through environment variable use the operational system path separator (windows=";", linux=":") to separate multiple entries:

* Windows: `set DEPS_IGNORE_PROJECT=old_project;fuzzy_project`
* Linux: `export DEPS_IGNORE_PROJECT=old_project:fuzzy_project`

This is equivalent to pass `--ignore-project=old_project --ignore-project=fuzzy_project`.

Options Description:

  * `--version`

    Show the version and exit.

  * `-p, --project PATH`

    Project to find dependencies of (can be used multiple times).

  * `-pp, --pretty-print`

    Pretty print dependencies in a tree.

  * `-f, --require-file TEXT`

    Only run the command if the file exists (relative to dependency working directory).

  * `--here`

    Do not change working dir.

  * `-n, --dry-run`

    Do not execute, only print what will be executed.

  * `-v, --verbose`

    Print more information.

  * `--continue-on-failure`

    Continue processing commands even when one fail (if some command fail the return value will be non zero).

  * `-i, --ignore-project PATH`

    Project name to ignore when looking for dependencies and will not recurse into those projects. Instead of passing this option an environment variable with the name `DEPS_IGNORE_PROJECT` can be used (can be used multiple times).

  * `-s, --skip-project PATH`

    Project name to skip execution but still look for its dependencies. Instead of passing this option an environment variable with the name `DEPS_SKIP_PROJECT` can be used (can be used multiple times).

  * `--force-color / --no-force-color`

    Always use colors on output (by default it is detected if running on a terminal). If file redirection is used ANSI escape sequences are output even on windows. Instead of passing this option an environment variable with the name `DEPS_FORCE_COLOR` can be used.

  * `--repos`

    Instead of projects the enumeration procedure will use the containing repositories instead of projects them selves.

  * `-j, --jobs INTEGER`

    Run commands in parallel using multiple processes.

  * `--jobs-unordered`

    Will run jobs without any specific order (useful if dependencies are not important and jobs > 1 to run more jobs concurrently).

  * `--deps-reversed`

    Will run with a reversed dependency (only used if --jobs=1). Useful to identify where the order is important.

  * `--help`

    Show this message and exit.

License
========

Free software: MIT license
