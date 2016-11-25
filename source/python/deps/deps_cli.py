#!/usr/bin/env python
from __future__ import print_function, unicode_literals

import functools
import io
import os
import subprocess
import sys
import textwrap
from collections import namedtuple
from contextlib import contextmanager

import click

from .version import __version__

click.disable_unicode_literals_warning = True


PROG_NAME = 'deps'
PROG_MSG_PREFIX = PROG_NAME + ': '
MAX_LINE_LENGTH = 119

_click_echo_color = None

def echo_verbose_msg(*args, **kwargs):
    """
    For "verbose" messages.
    """
    click.echo(PROG_MSG_PREFIX, nl=False, file=sys.stderr, color=_click_echo_color)
    kwargs.update(file=sys.stderr)
    kwargs.update(color=_click_echo_color)
    click.echo(*args, **kwargs)


def echo_error(*args, **kwargs):
    """
    For "error" messages.
    """
    click.secho(
        PROG_MSG_PREFIX + 'error: ',
        nl=False,
        file=sys.stderr,
        fg='red',
        bold=True,
        color=_click_echo_color,
    )
    kwargs.update(file=sys.stderr)
    kwargs.update(fg='red')
    kwargs.update(bold=True)
    kwargs.update(color=_click_echo_color)
    click.secho(*args, **kwargs)


@contextmanager
def cd(newdir):
    if newdir is None:
        yield
    else:
        prevdir = os.getcwd()
        os.chdir(os.path.expanduser(newdir))
        try:
            yield
        finally:
            os.chdir(prevdir)


# ==================================================================================================
# Customizations
# ==================================================================================================

FILE_WITH_DEPENDENCIES = 'environment.yml'

def memoize(fun):

    cache = {}

    @functools.wraps(fun)
    def wrapper(*args, **kwargs):
        key = (args, frozenset(kwargs.items()))
        try:
            return cache[key]
        except KeyError:
            ret = cache[key] = fun(*args, **kwargs)
            return ret

    return wrapper

@memoize
def get_shallow_dependencies_directories(base_directory):
    """
    :type base_directory: unicode
    :rtype: list(unicode)
    :return: The first level (does not recursevely list dependencies of dependencies) dependencies
    of the project rooted in the given directory
    """
    import jinja2
    import yaml

    # NOTE: This is based on code in ESSS branch of conda env, if that
    #       ever changes, this code here must be updated!
    jinja_args = {'root': base_directory, 'os': os}

    with io.open(os.path.join(base_directory, FILE_WITH_DEPENDENCIES), 'r') as f:
        yaml_contents = jinja2.Template(f.read()).render(**jinja_args)

    data = yaml.load(yaml_contents)
    if 'includes' not in data:
        return []
    includes = [os.path.abspath(os.path.dirname(p)) for p in data['includes']]
    return includes


# ==================================================================================================
# Common code
# ==================================================================================================
Dep = namedtuple('Dep', 'name,abspath,deps,ignored,skipped')


def create_new_dep_from_directory(directory, ignore_projects, skipped_projects):
    """
    :param unicode directory: Root directory of a project.
    :param list[unicode] ignore_projects: A list of project names to ignore (set the `ignored` attr
    to `True`).
    :param list[unicode] skipped_projects: A list of project names that should be skipped i.e. they
    are part of dependencies but they aren't executed. Skipped has less priority than ignored, so
    if a name is in both lists it will be always ignored.
    :rtype: Dep
    """
    directory = os.path.abspath(directory)
    name = os.path.split(directory)[1]
    return Dep(
        name=name,
        abspath=directory,
        deps=[],
        ignored=name in ignore_projects,
        skipped=name in skipped_projects,
    )


def pretty_print_dependency_tree(root_deps):
    """
    Prints an indented tree for the projects (and their dependencies). A short legend is printed
    describing the decoration used.

    :param list(Dep) root_deps: The list of root dependencies.
    """
    already_printed = set()

    legend = textwrap.dedent('''\
        # - project_name: listed or target of command execution;
        # - (project_name): have already been printed in the tree;
        # - <project_name>: have been ignored (see `--ignore-project` option);
        # - {project_name}: have been skipped (see `--skipped-project` option);
    ''')
    print(legend)

    def print_formatted_dep(name, identation, name_template='{}'):
        print(identation + name_template.format(name))

    def print_deps(dep_list, indentation_size=0, indentation_string='    '):
        indentation = indentation_string * indentation_size
        next_indentation_size = indentation_size + 1
        for dep in dep_list:
            if dep.ignored:
                print_formatted_dep(dep.name, indentation, '<{}>')
                continue
            if dep.abspath not in already_printed:
                if dep.skipped:
                    print_formatted_dep(dep.name, indentation, '{{{}}}')
                else:
                    print_formatted_dep(dep.name, indentation)
                already_printed.add(dep.abspath)
                print_deps(dep.deps, next_indentation_size, indentation_string)
            else:
                print_formatted_dep(dep.name, indentation, '({})')
    print_deps(root_deps)


def find_ancestor_dir_with(filename, begin_in=None):
    """
    Look in current and ancestor directories (parent, parent of parent, ...) for a file.

    :param unicode filename: File to find.
    :param unicode begin_in: Directory to start searching.

    :rtype: unicode
    :return: Absolute path to directory where file is located.
    """
    if begin_in is None:
        begin_in = os.curdir

    base_directory = os.path.abspath(begin_in)
    while True:
        directory = base_directory
        if os.path.exists(os.path.join(directory, filename)):
            return directory

        parent_base_directory, current_dir_name = os.path.split(base_directory)
        if len(current_dir_name) == 0:
            return None
        assert len(parent_base_directory) != 0
        base_directory = parent_base_directory


def find_directories(raw_directories):
    """
    Find ancestor directories that contain the FILE_WITH_DEPENDENCIES file.

    :type raw_directories: sequence(unicode)

    :rtype: list(unicode)
    :returns: List of directories.
    """
    raw_directories = list(raw_directories)

    if len(raw_directories) == 0:
        raw_directories.append(os.path.curdir)

    directories = []

    for raw_dir in raw_directories:
        directory = find_ancestor_dir_with(FILE_WITH_DEPENDENCIES, raw_dir)
        if directory is None:
            msg = 'could not find "{}" for "{}".'.format(FILE_WITH_DEPENDENCIES, raw_dir)
            echo_error(msg)
            raise click.ClickException(msg)
        directories.append(directory)

    return directories


def obtain_all_dependecies_recursively(root_directories, ignored_projects, skipped_projects):
    """
    Creates a list with a `Dep` for each item in `root_directories` where each project is inspected
    recursively for its dependencies.

    :param sequence[unicode] root_directories: The root directories identifying projects.
    :param sequence[unicode] ignored_projects: Project names to be marked as ignored (and do not
        recurse into its dependencies).
    :param sequence[unicode] skipped_projects: Project names to be marked as skipped (it still
        recurse into its dependencies).

    :rtype: list(Dep)
    :return: The created list.
    """
    all_deps = {}

    def add_deps_from_directories(directories, list_to_add_deps):
        """
        A data structure (`Dep`) is created for each project rooted in the given directories.

        :param sequence(unicode) directories: Projects' roots to use.
        :param list(Dep) list_to_add_deps: A list to be populated with the created `Dep`s
        processed `Dep`s (in case multiple projects have the same dependency).
        """
        for dep_directory in directories:
            if dep_directory not in all_deps:
                dep = create_new_dep_from_directory(dep_directory, ignored_projects, skipped_projects)
                all_deps[dep_directory] = dep
                if not dep.ignored:
                    current_dep_directories = get_shallow_dependencies_directories(
                        dep_directory)
                    add_deps_from_directories(current_dep_directories, dep.deps)
            else:
                dep = all_deps[dep_directory]
            list_to_add_deps.append(dep)

    root_deps = []
    add_deps_from_directories(root_directories, root_deps)
    return root_deps


def obtain_repos(dep_list):
    """
    Obtaim the repos for the given projects and their dependencies.
    :param list(Dep) dep_list:
    :rtype: list(Dep)
    """
    all_repos = {}

    def obtain_repo_from_dep(dep):
        """
        :param Dep dep: A project.
        :rtype: Dep
        :return: The repository for the given project. Conserve the `ignored` property.
        """
        directory = find_ancestor_dir_with('.git', dep.abspath)
        directory = os.path.abspath(directory)
        repo_key = (directory, dep.ignored)
        if repo_key not in all_repos:
            all_repos[repo_key] = Dep(
                name=directory,
                abspath=directory,
                deps=[],
                ignored=dep.ignored,
                skipped=dep.skipped,
            )
        return all_repos[repo_key]

    visited_deps = []

    def convert_deps_to_repos(deps, list_of_repos, parent):
        """
        :param list(Dep) deps:
        :param list(Dep) list_of_repos: This list will contain the converted repos (is changed).
        :param unicode|None parent: The parent's name of the given deps (used to break infinite
            recursion due cyclic dependencies without loosing declared dependencies).
        """
        for dep in deps:
            if (parent, dep) in visited_deps:
                continue
            visited_deps.append((parent, dep))
            repo = obtain_repo_from_dep(dep)
            convert_deps_to_repos(dep.deps, repo.deps, dep.name)
            if repo not in list_of_repos:
                list_of_repos.append(repo)

        # Avoid to list a repo as ignored/skipped and not ignored/skipped in the same list. Note
        # there is a precedence: if any project in repo is normal (i.e. not ignored/skipped), it
        # will make repo normal; if any project is skipped, repo is skipped unless there is a
        # normal project; repo only ignored if all projects are ignored.
        precedence = {}
        for i, repo_dep in enumerate(list_of_repos):
            if repo_dep.name not in precedence:
                precedence[repo_dep.name] = repo_dep

            if not repo_dep.ignored and not repo_dep.skipped:
                precedence[repo_dep.name] = repo_dep
            elif repo_dep.skipped:
                saved = precedence[repo_dep.name]
                if saved.ignored:
                    precedence[repo_dep.name] = repo_dep

        precedence_values = list(precedence.values())
        for repo_dep in list_of_repos[:]:
            if repo_dep not in precedence_values:
                list_of_repos.remove(repo_dep)

    root_repos = []
    convert_deps_to_repos(dep_list, root_repos, None)
    return root_repos


def obtain_dependencies_ordered_for_execution(root_deps):
    """
    Return a list of the dependencies.

    Ordering:

    - A root project will be present after it's dependencies;
    - The root projects will have the same order that the one they are passed (the exception is when
      a root project is a dependency of a previously listed root project, it will be listed as a
      dependency and not listed again);
    - No project is listed more than once;

    :param list(Dep) root_deps: A list of the root projects.
    :rtype: list(Dep)
    :return: A list of all projects target to execution.
    """
    from collections import OrderedDict

    def get_all_deps(dep):
        """
        List all dependencies (and sub dependencies) of the given dep.
        :param Dep dep:
        :rtype: `OrderedDict`
        """
        result = OrderedDict()
        other_deps = dep.deps[:]
        while other_deps:
            next_dep = other_deps.pop()
            if next_dep.abspath in result:
                continue
            result[next_dep.abspath] = next_dep
            # Not `reversed` results in equally valid results.
            # But `reversed` results in a more intuitive result IMO.
            other_deps.extend(reversed(next_dep.deps))
        return result

    def count_deps(dep):
        """
        Count all dependencies (and sub dependencies) of the given dep.
        :param Dep dep:
        :rtype: int
        """
        already_visited = {dep.abspath}
        other_deps = dep.deps[:]
        count = 0
        while other_deps:
            next_dep = other_deps.pop()
            if next_dep.abspath in already_visited:
                continue
            count += 1
            other_deps.extend(next_dep.deps)
            already_visited.add(next_dep.abspath)
        return count

    deps = []
    already_counted_deps = set()
    for root in root_deps:
        if root.abspath in already_counted_deps:
            continue
        all_deps = get_all_deps(root)
        # root's deps count.
        deps_counts = [(root, len(all_deps))]
        already_counted_deps.add(root.abspath)
        # sub deps' deps count.
        for sub_dep_key, sub_dep in all_deps.items():
            if sub_dep_key in already_counted_deps:
                continue
            # Any of `append(...)` and `insert(0, ...)` result in equally valid results.
            # But `insert(0, ...)` results in a more intuitive result IMO.
            deps_counts.insert(0, (sub_dep, count_deps(sub_dep)))
            already_counted_deps.add(sub_dep_key)
        # use dep count as key and rely on stable sort.
        deps.extend(sorted(deps_counts, key=lambda v: v[1]))
    return [dep_element for dep_element, dep_count in deps]


def format_command(command, dep):
    """
    Process the variables in command.

    :type command: unicode | sequence(unicode)
    :type dep: Dep

    :rtype: unicode | list(unicode)
    """
    format_dict = {
        'name': dep.name,
        'abs': dep.abspath,
    }

    def _format(s, format_dict):
        """
        :type s: unicode
        :type format_dict: dict(unicode,unicode)

        :rtype: unicode
        """
        for key, item in format_dict.items():
            s = s.replace('{' + key + '}', item)
        return s

    if isinstance(command, (list, tuple)):
        return [_format(a, format_dict) for a in command]
    else:
        return _format(command, format_dict)


def execute_command_in_dependencies(
    command,
    dependencies,
    required_files_filter=None,
    dry_run=False,
    verbose=False,
    continue_on_failure=False,
    here=False,
):
    """
    Execute the given command for the given dependencies.

    :param list(unicode) command: The commando to be executed.
    :param list(Dep) dependencies: The list of dependencies for which execute the command.
    :param callable required_files_filter: A list os files required in a dependency root directory
        to execute the command.
    :param bool dry_run: Does all the checks and most output normally but does not actually execute
        the command.
    :param bool verbose: Prints extra information.
    :param bool continue_on_failure: When this is `False` the first command with a non zero return
        code makes the dependency processing to stop and this function returns, when it is `True`
        all dependencies are always processed.
    :param bool here: Does not change the working dir to the root of the dependency when executing
        the command.

    :rtype: list(int)
    :return: The exit code of the commands executed so far (may be smaller than `dependencies` list
        when `continue_on_failure` is false).
    """
    exit_codes = []

    for dep in dependencies:
        click.secho('\n' + '=' * MAX_LINE_LENGTH, fg='black', bold=True, color=_click_echo_color)

        # Checks before execution.
        if dep.ignored:
            click.secho(dep.name, fg='blue', bold=True, color=_click_echo_color, nl=False)
            click.secho(' ignored', fg='yellow', color=_click_echo_color)
            continue

        if dep.skipped:
            click.secho(dep.name, fg='blue', bold=True, color=_click_echo_color, nl=False)
            click.secho(' skipped', fg='magenta', color=_click_echo_color)
            continue

        if not required_files_filter(dep, quiet=False):
            continue

        formatted_command = format_command(command, dep)

        working_dir = None
        if not here:
            working_dir = dep.abspath

        click.secho(dep.name, fg='blue', bold=True, color=_click_echo_color)
        if verbose or dry_run:
            command_to_print = ' '.join(
                arg.replace(' ', '\\ ') for arg in formatted_command)
            echo_verbose_msg('executing: ' + command_to_print)
            if working_dir:
                echo_verbose_msg('from:      ' + working_dir)

        if not dry_run:
            if not sys.platform.startswith('win'):
                import pipes
                for index, item in enumerate(formatted_command):
                    formatted_command[index] = pipes.quote(item)
                formatted_command = ' '.join(formatted_command)

            with cd(working_dir):
                process = shell_execute(formatted_command)
            exit_codes.append(process.returncode)

            if verbose:
                echo_verbose_msg('return code: {}'.format(process.returncode))
            if process.returncode != 0:
                echo_error('Command failed')
                if not continue_on_failure:
                    break
    return exit_codes


@click.command(name=PROG_NAME)
@click.argument('command', nargs=-1)
@click.version_option(__version__)
@click.option(
    '--project', '-p', default='.', type=click.Path(), multiple=True,
    help="Project to find dependencies of (can be used multiple times).")
@click.option(
    '--pretty-print', '-pp', is_flag=True,
    help='Pretty print dependencies in a tree.')
@click.option(
    '--require-file', '-f', multiple=True,
    help='Only run the command if the file exists (relative to dependency working directory).')
@click.option(
    '--here', is_flag=True,
    help='Do not change working dir.')
@click.option(
    '--dry-run', '-n', is_flag=True,
    help='Do not execute, only print what will be executed.')
@click.option(
    '--verbose', '-v', is_flag=True,
    help='Print more information.')
@click.option(
    '--continue-on-failure', is_flag=True,
    help='Continue processing commands even when one fail (if some command fail the return value'
         ' will be non zero).')
@click.option(
    '--ignore-project', '-i', type=click.Path(), multiple=True, envvar='DEPS_IGNORE_PROJECT',
    help='Project name to ignore when looking for dependencies and will not recurse'
         ' into those projects. Instead of passing this option an environment variable with the'
         ' name DEPS_IGNORE_PROJECT can be used (can be used multiple times).')
@click.option(
    '--skip-project', '-s', type=click.Path(), multiple=True, envvar='DEPS_SKIP_PROJECT',
    help='Project name to skip execution but still look for its dependencies. Instead of passing this option an '
         'environment variable with the name DEPS_SKIP_PROJECT can be used (can be used multiple times).')
@click.option(
    '--force-color/--no-force-color', is_flag=True, envvar='DEPS_FORCE_COLOR',
    help='Always use colors on output (by default it is detected if running on a terminal). If file'
         ' redirection is used ANSI escape sequences are output even on windows. Instead of passing'
         ' this option an environment variable with the name DEPS_FORCE_COLOR can be used.')
@click.option(
    '--repos', is_flag=True,
    help='Instead of projects the enumeration procedure will use the containing repositories'
         ' instead of projects them selves')
def cli(
    command,
    project,
    pretty_print,
    require_file,
    here,
    dry_run,
    verbose,
    continue_on_failure,
    ignore_project,
    skip_project,
    force_color,
    repos,
):
    """
    Program to list dependencies of a project, or to execute a command for
    each dependency.

    To list dependency projects, one per line (if "-p directory" is omitted,
    it will use the current, or will find the first ancestor directory
    containing an `environment.yml` file):

          deps -p mylib10 -p myotherlib20

      This may be used in combination with shell commands (useful for
      `source`ing files), e.g., to iterate on dependencies in windows (cmd):

          for %%i in ('deps -p mylib10') do <something> %%i [...]

      To iterate on dependencies in unix (bash):

          deps | xargs -0 -I {} <something> {} [...]

    To use deps to execute a command for each dependency (will spawn a new
    shell for each dependency):

          deps [parameters] <command>

      To prevent deps to process any option or flags passed to command a "--" can be used

          deps [parameters] -- <command> --with --flags

      \b
        <command> may contain some variables:
          * {name}: The dependency bare name (ex.: eden)
          * {abs}:  The dependency absolute path (ex.: X:\\ws\\eden)

    If the option --require-file is used dependencies not having a file named as this relative to
    the given dependency root directory are skipped:

          deps --require-file Makefile -- make clean

    When passing parameters that can be used multiple times through environment variable use the
    operational system path separator (windows=";", linux=":") to separate multiple entries:

          set DEPS_IGNORE_PROJECT=old_project;fuzzy_project (windows)
          export DEPS_IGNORE_PROJECT=old_project:fuzzy_project (linux)

      This is equivalent to pass "--ignore-project=old_project --ignore-project=fuzzy_project"
    """
    global _click_echo_color
    original_auto_wrap_for_ansi = click.utils.auto_wrap_for_ansi
    try:
        if force_color:
            _click_echo_color = True
            if sys.platform == 'win32':
                # Click always wrap the output stream on windows calling
                # `click.utils.auto_wrap_for_ansi`, setting to `None` causes ansi escape codes to
                # be output.
                click.utils.auto_wrap_for_ansi = None

        directories = find_directories(project)

        root_deps = obtain_all_dependecies_recursively(directories, ignore_project, skip_project)
        if repos:
            root_deps = obtain_repos(root_deps)

        if pretty_print:
            # We don't need them in order to pretty print.
            pretty_print_dependency_tree(root_deps)
            return 0

        def required_files_filter(dependency, quiet):
            """
            :type dependency: Dep
            :type quiet: bool

            :return: `True` if the necessary files/folders are present, `False` otherwise.
            """
            for f in require_file:
                file_to_check = os.path.join(dependency.abspath, format_command(f, dependency))
                if not os.path.isfile(file_to_check) and not os.path.isdir(file_to_check):
                    if not quiet:
                        msg = '{}: skipping since "{}" does not exist'
                        msg = msg.format(dependency.name, file_to_check)
                        click.secho(msg, fg='cyan', color=_click_echo_color)
                    return False
            return True

        deps_in_order = obtain_dependencies_ordered_for_execution(root_deps)

        if not command:
            deps_to_output = [
                dep.name for dep in deps_in_order
                if not dep.ignored and not dep.skipped and required_files_filter(dep, quiet=True)
            ]
            print('\n'.join(deps_to_output))
            return 0

        # Execution.
        execution_return = execute_command_in_dependencies(
            command,
            deps_in_order,
            required_files_filter=required_files_filter,
            dry_run=dry_run,
            verbose=verbose,
            continue_on_failure=continue_on_failure,
            here=here,
        )
        execution_return = sorted(execution_return, key=abs)
        sys.exit(execution_return[-1] if execution_return else 1)
    finally:
        _click_echo_color = None
        click.utils.auto_wrap_for_ansi = original_auto_wrap_for_ansi


def shell_execute(command):
    """
    Wrapper function the execute the command.
    This function exists solely to be overwritten on tests since subprocess output is not captured
    by the `click.testing.CliRunner`, in the wild the processes' output could be very large so
    piping is not an option.

    :type command: unicode | list(unicode)

    :rtype: subprocess.Popen
    :return: the process object used to run the command.
    """
    # Note: could use something like this for more robustness:
    # http://stackoverflow.com/questions/13243807/popen-waiting-for-child-process-even-when-the-immediate-child-has-terminated/13256908#13256908
    process = subprocess.Popen(command, shell=True)
    process.communicate()
    return process


def main_func():
    """
    A wrapper to call the click command with the desired parameters.
    """
    return cli(auto_envvar_prefix='DEPS')


if __name__ == '__main__':
    sys.exit(main_func())
