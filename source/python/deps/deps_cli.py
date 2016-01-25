#!/usr/bin/env python
from __future__ import print_function, unicode_literals
from collections import namedtuple
from contextlib import contextmanager
import click
import io
import os
import subprocess
import sys
import textwrap


PROG_NAME = 'deps'
PROG_MSG_PREFIX = PROG_NAME + ': '
MAX_LINE_LENGTH = 79


def echo_verbose_msg(*args, **kwargs):
    """
    For "verbose" messages.
    """
    click.echo(PROG_MSG_PREFIX, nl=False, file=sys.stderr)
    kwargs.update(file=sys.stderr)
    click.echo(*args, **kwargs)


def echo_error(*args, **kwargs):
    """
    For "error" messages.
    """
    click.secho(
        PROG_MSG_PREFIX + 'error: ', nl=False, file=sys.stderr, fg='red', bold=True)
    kwargs.update(file=sys.stderr)
    kwargs.update(fg='red')
    kwargs.update(bold=True)
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


def get_shallow_dependencies_directories(base_directory):
    """
    :type base_directory: unicode
    :rtype: list(unicode)
    :return: the first level (does not recursevely list dependencies of dependencies) dependencies
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
Dep = namedtuple('Dep', 'name,abspath,deps,ignored')


def create_new_dep_from_directory(directory, ignore_projects):
    """
    :param unicode directory: root directory of a project
    :param list(unicode) ignore_projects: a list of project names to ignore (set the `ignored` attr
    to `True`.)
    :rtype: Dep
    """
    directory = os.path.abspath(directory)
    name=os.path.split(directory)[1]
    return Dep(
        name=name,
        abspath=directory,
        deps=[],
        ignored=name in ignore_projects,
    )


def find_ancestor_dir_with(filename, begin_in=None):
    """
    Look in current and ancestor directories (parent, parent of parent, ...) for a file.

    :param unicode filename: file to find
    :param unicode begin_in: directory to start searching

    :rtype: unicode
    :return: absolute path to directory where file is located
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
    :returns: list of directories
    """
    raw_directories = list(raw_directories)

    if len(raw_directories) == 0:
        raw_directories.append(os.path.curdir)

    directories = []

    for raw_dir in raw_directories:
        directory = find_ancestor_dir_with(FILE_WITH_DEPENDENCIES, raw_dir)
        if directory is None:
            echo_error('could not find "{}" for "{}".'.format(
                FILE_WITH_DEPENDENCIES, raw_dir))
            raise click.ClickException()
        directories.append(directory)

    return directories


def is_executable_and_get_interpreter(folders, filename):
    """
    Checks if a file is "executable" and return the interpreter to run the file.

    When no interpreter is required to run the file and empty string is returned, the know files
    that may require an interpreter are:

    - .py: `sys.executable` is used as interpreter, if python can not determine how it is executed
        the file is not interpreted as python script and will undergo further heuristics;

    :type folders: sequence(unicode)
    :type filename: unicode
    :rtype: tuple(bool, unicode)
    :returns: A tuple indicating if the file is to be considered executable and the interpreter
    used to run the file. The interpreter could be an empty unicode it the file is not executable
    or no interpreter is require(or know) to run the file.
    """
    name, ext = os.path.splitext(filename)
    if ext == '.py':
        # Python file.
        interpreter = sys.executable or ''
        if interpreter:
            for folder in folders:
                fullname = os.path.join(folder, filename)

                if os.path.isfile(fullname):
                    return True, interpreter

    if not sys.platform.startswith('win'):
        # Linux.
        for folder in folders:
            fullname = os.path.join(folder, filename)

            if os.path.isfile(fullname) and os.access(fullname, os.X_OK):
                return True, ''

    else:
        # Windows.
        for folder in folders:
            fullname = os.path.join(folder, filename)

            executable_extensions = os.environ['PATHEXT'].lower().split(';')
            if os.path.isfile(fullname) and ext.lower() in executable_extensions:
                return True, ''
            for ext in executable_extensions:
                if os.path.isfile(''.join((fullname, ext))):
                    return True, ''

    return False, ''


@click.command(name=PROG_NAME)
@click.argument('command', nargs=-1)
@click.version_option('0.2')
@click.option(
    '--projects', '-p', default='.',
    help="List of projects, separated by ',' (without spaces).")
@click.option(
    '--pretty-print', '-pp', is_flag=True,
    help='Pretty print dependencies in a tree.')
@click.option(
    '--ignore-filter', '-i', is_flag=True,
    help='Always run the command, ignoring the check for relative executable existence.')
@click.option(
    '--if-exist', '-f', multiple=True,
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
    '--fallback-paths', default='', envvar='DEPS_FALLBACK_PATHS',
    help="List of paths, separated by ',' (without spaces) where to look for the executable task if"
         " it is not found in the project. Instead of passing this option an environment variable"
         " with the name DEPS_FALLBACK_PATHS can be used.")
@click.option(
    '--ignore-projects', default='', envvar='DEPS_IGNORE_PROJECTS',
    help="List of project names, separated by ',' (without spaces), of projects to ignore when"
         " looking for dependencies and will not recurse into those projects. Instead of passing"
         " this option an environment variable with the name DEPS_IGNORE_PROJECTS can be used.")
def cli(
    command,
    projects,
    pretty_print,
    ignore_filter,
    if_exist,
    here,
    dry_run,
    verbose,
    fallback_paths,
    ignore_projects,
):
    """
    Program to list dependencies of a project, or to execute a command for
    each dependency.

    To list dependency projects, one per line (if "-p directory" is omitted,
    it will use the current, or will find the first ancestor directory
    containing an `environment.yml` file):

          deps -p mylib10,myotherlib20

      This may be used in combination with shell commands (useful for
      `source`ing files), e.g., to iterate on dependencies in windows (cmd):

          for %%i in ('deps -p mylib10') do <something> %%i [...]

      To iterate on dependencies in unix (bash):

          deps | xargs -0 -I {} <something> {} [...]

    To use deps to execute a command for each dependency (will spawn a new
    shell for each dependency):

          deps [parameters] <command>

        \b
        <command> may contain some variables:
          * {name}: The dependency bare name (ex.: eden)
          * {abs}:  The dependency absolute path (ex.: X:\\ws\\eden)

      Note that if the first command word is an existing executable file
      relative to the current directory, it will automatically skip
      dependencies that do not have this file inside.
    """
    # Parse arguments that are lists.
    def get_list_from_argument(value, separator):
        """
        :type value: unicode
        :type separator: unicode
        :rtype: list(unicode)
        :return: The list obtained from `value` (can be empty if `value` is empty).
        """
        return value.split(',') if len(separator) > 0 else []

    directories = find_directories(get_list_from_argument(projects, ','))
    fallback_paths = get_list_from_argument(fallback_paths, ',')
    ignore_projects = get_list_from_argument(ignore_projects, ',')

    # find dependencies recursively for each directory
    # (if we ever need something fancier, there is "pycosat" or "networkx" to solve this stuff)
    all_deps = {}

    def add_deps_from_directories(directories, list_to_add_deps):
        """
        A data structure (`Dep`) is created for each project rooted in the given directories.

        :param sequence(unicode) directories: projects' roots to use
        :param list(Dep) list_to_add_deps: a list to be populated with the created `Dep`s
        processed `Dep`s (in case multiple projects have the same dependency)
        """
        for dep_directory in directories:
            if dep_directory not in all_deps:
                dep = create_new_dep_from_directory(dep_directory, ignore_projects)
                all_deps[dep_directory] = dep
                if not dep.ignored:
                    current_dep_directories = get_shallow_dependencies_directories(
                        dep_directory)
                    add_deps_from_directories(current_dep_directories, dep.deps)
            else:
                dep = all_deps[dep_directory]
            list_to_add_deps.append(dep)

    root_deps = []
    add_deps_from_directories(directories, root_deps)

    if pretty_print:
        already_printed = set()

        legend = textwrap.dedent('''\
            # - project_name: listed or target of command execution;
            # - (project_name): have already been printed in the tree;
            # - <project_name>: have been ignored (see `--ignored-projects` option);
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
                    print_formatted_dep(dep.name, indentation)
                    already_printed.add(dep.abspath)
                    print_deps(dep.deps, next_indentation_size, indentation_string)
                else:
                    print_formatted_dep(dep.name, indentation, '({})')
        print_deps(root_deps)
        sys.exit(0)

    # get dependencies in order
    already_walked = set()
    deps_in_order = []

    def walk_deps(dep_list):
        """
        Recursively list the given `Dep`s' dependencies populating `deps_in_order` from the deepest
        dependency to the root project, no dependency/project is added twice.
        :param sequence(Dep) dep_list: the dependencies/projects to list dependencies (recursively)
        """
        for dep in dep_list:
            if dep.abspath not in already_walked:
                already_walked.add(dep.abspath)
                if len(dep.deps) != 0 and not all(d.abspath in already_walked for d in dep.deps):
                    walk_deps(dep.deps)
                deps_in_order.append(dep)

    walk_deps(root_deps)

    if not command:
        print('\n'.join(dep.name for dep in deps_in_order if not dep.ignored))
        sys.exit(0)

    #=========================================================================
    # execution
    #=========================================================================

    filter_if_exist = []
    if if_exist:
        filter_if_exist.extend(if_exist)

    def format_command(command, dep):
        """
        Process the variables in command.
        :type command: unicode | sequence(unicode)
        :type dep: Dep
        :rtype: unicode | list(unicode)
        """
        format_dict = {
            'name': dep.name, 'abs': dep.abspath}

        def _format(s, format_dict):
            """
            :type s: unicode
            :type format_dict: dict(unicode,unicode)
            :rtype: unicode
            """
            for key, item in format_dict.iteritems():
                s = s.replace('{' + key + '}', item)
            return s

        if isinstance(command, (list, tuple)):
            return [_format(a, format_dict) for a in command]
        else:
            return _format(command, format_dict)

    # check if command is an executable relative to dependency working dir

    first_dep = root_deps[0]
    first_working_dir = first_dep.abspath
    first_command = command[0]
    expanded_first_command = format_command(first_command, first_dep)

    command_must_be_executable, interpreter = is_executable_and_get_interpreter(
        [first_working_dir] + fallback_paths,
        expanded_first_command,
    )
    if ignore_filter:
        command_must_be_executable = False
        filter_if_exist = []

    def pass_filter(dep):
        """
        :type dep: Dep
        :return: `True` if the necessary files/folders are present, `False` otherwise.
        """
        for f in filter_if_exist:
            file_to_check = os.path.join(dep.abspath, format_command(f, dep))
            if not os.path.isfile(file_to_check) and not os.path.isdir(file_to_check):
                return False
        return True

    # execute command for each dependency
    for dep in deps_in_order:
        click.secho('\n' + '=' * MAX_LINE_LENGTH, fg='black', bold=True)
        if dep.ignored:
            click.secho('{}: ignored'.format(dep.name), fg='cyan')
            continue

        working_dir = None
        if not here:
            working_dir = dep.abspath

        formatted_command = format_command(command, dep)

        is_executable, interpreter = is_executable_and_get_interpreter(
            [dep.abspath], formatted_command[0])

        skip = not pass_filter(dep) or (working_dir and not os.path.isdir(working_dir))
        if (
                not skip and  # Just if not already skipping.
                command_must_be_executable and
                not is_executable  # Will need fallback.
        ):
            for fallback in fallback_paths:
                is_executable, interpreter = is_executable_and_get_interpreter(
                    [fallback], formatted_command[0])
                if is_executable:
                    formatted_command[0] = os.path.join(fallback, formatted_command[0])
                    break
            else:
                skip = True  # No fallback found, skip.
        if skip:
            click.secho('{}: skipping'.format(dep.name), fg='cyan')
            continue
        click.secho('{}:'.format(dep.name), fg='cyan', bold=True)

        if interpreter:
            formatted_command.insert(0, interpreter)

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

            if verbose:
                echo_verbose_msg('return code: {}'.format(process.returncode))
            if process.returncode != 0:
                echo_error('Command failed')
                sys.exit(process.returncode)


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

