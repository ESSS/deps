#!/usr/bin/env python
from __future__ import print_function, unicode_literals
from collections import namedtuple
from contextlib import contextmanager
import click
import io
import os
import platform
import subprocess
import sys


PROG_NAME = 'deps'
PROG_MSG_PREFIX = PROG_NAME + ': '
MAX_LINE_LENGTH = 79


def echo_verbose_msg(*args, **kwargs):
    '''
    For "verbose" messages.
    '''
    click.echo(PROG_MSG_PREFIX, nl=False, file=sys.stderr)
    kwargs.update(file=sys.stderr)
    click.echo(*args, **kwargs)


def echo_error(*args, **kwargs):
    '''
    For "error" messages.
    '''
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


#=========================================================================
# Customizations
#=========================================================================

FILE_WITH_DEPENDENCIES = 'environment.yml'


def get_shallow_dependencies_directories(base_directory):
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


#=========================================================================
# Common code
#=========================================================================
Dep = namedtuple('Dep', 'name,abspath,relpath,deps')


def create_new_dep_from_directory(directory, relative_to):
    '''
    :rtype: Dep
    '''
    directory = os.path.abspath(directory)
    return Dep(
        name=os.path.split(directory)[1],
        abspath=directory,
        relpath=os.path.relpath(directory, relative_to),
        deps=[],
    )


def find_ancestor_dir_with(filename, directory_inside, begin_in=None):
    '''
    Look in current and ancestor directories (parent, parent of parent, ...) for a file.

    :param unicode filename: file to find
    :param unicode directory_inside: relative directory to be appended (where file must be)
    :param unicode begin_in: directory to start searching

    :rtype: unicode
    :return: absolute path to directory where file is located
    '''
    if begin_in is None:
        begin_in = os.curdir

    base_directory = os.path.abspath(begin_in)
    while True:
        directory = os.path.join(base_directory, directory_inside)
        if os.path.exists(os.path.join(directory, filename)):
            return directory

        parent_base_directory, current_dir_name = os.path.split(base_directory)
        if len(current_dir_name) == 0:
            return None
        assert len(parent_base_directory) != 0
        base_directory = parent_base_directory


def find_directories(raw_directories):
    '''
    Find ancestor directories that contain the FILE_WITH_DEPENDENCIES file.
    Also returns the path from the directory to the current dir (if the current dir is inside any
    of them).

    :type raw_directories: sequence(unicode)
    :rtype: list(unicode), unicode
    :returns: list of directories, and the relative path to reach current directory
    '''
    raw_directories = list(raw_directories)
    directory_inside = None

    if len(raw_directories) == 0:
        raw_directories.append(os.path.curdir)

    directories = []

    for raw_dir in raw_directories:
        directory = find_ancestor_dir_with(FILE_WITH_DEPENDENCIES, raw_dir)
        if directory is None:
            echo_error('could not find "{}" for "{}".'.format(
                FILE_WITH_DEPENDENCIES, raw_dir))
            sys.exit(1)
        directories.append(directory)
        if directory_inside is None:
            relative_path_to_here = os.path.relpath(os.path.curdir, directory)
            if not relative_path_to_here.startswith(os.path.pardir):
                directory_inside = relative_path_to_here

    if directory_inside is None:
        directory_inside = os.path.curdir

    return directories, directory_inside


def is_executable_and_get_suffix(filename):
    '''
    :returns: (False, None) if filename is not an executable, or (True, ext), where ext is a suffix
    to append to the filename to get the executable full name (or '' if it is not needed).
    '''
    if platform.system() != 'Windows':
        return (os.path.isfile(filename) and os.access(filename, os.X_OK)), ''

    if os.path.isfile(filename):
        name, ext = os.path.splitext(filename)
        if ext.lower() in (x.lower() for x in os.environ['PATHEXT'].split(';')):
            return True, ''
    else:
        for ext in os.environ['PATHEXT'].split(';'):
            if os.path.isfile(''.join((filename, ext))):
                return True, ext

    return False, None


@click.command(name=PROG_NAME)
@click.argument('command', nargs=-1)
@click.version_option('1.0')
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
def cli(command, projects, pretty_print, ignore_filter, if_exist, here, dry_run, verbose):
    # ------------------------------------------------------------------------
    '''
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
          * {dir}:  The dependency relative path (ex.: ../eden)
          * {abs}:  The dependency absolute path (ex.: X:\\ws\\eden)

      Note that if the first command word is an existing executable file
      relative to the current directory, it will automatically skip
      dependencies that do not have this file inside.
    '''
    # ------------------------------------------------------------------------
    directories, directory_inside = find_directories(projects.split(','))

    # find dependencies recursively for each directory
    # (if we ever need something fancier, there is "pycosat" or "networkx" to solve this stuff)
    all_deps = {}

    def add_deps_from_directories(directories, list_to_add_deps):
        for dep_directory in directories:
            if dep_directory not in all_deps:
                dep = create_new_dep_from_directory(
                    dep_directory, os.path.curdir)
                all_deps[dep_directory] = dep
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

        def print_deps(dep_list, indentation=0):
            for dep in dep_list:
                if dep.abspath not in already_printed:
                    print(' ' * (indentation * 2) + dep.name)
                    already_printed.add(dep.abspath)
                    print_deps(dep.deps, indentation + 1)
                else:
                    print(' ' * (indentation * 2) + '(' + dep.name + ')')
        print_deps(root_deps)
        sys.exit(0)

    # get dependencies in order
    already_walked = set()
    deps_in_order = []

    def walk_deps(dep_list):
        for dep in dep_list:
            if dep.abspath not in already_walked:
                already_walked.add(dep.abspath)
                if len(dep.deps) != 0 and not all(d.abspath in already_walked for d in dep.deps):
                    walk_deps(dep.deps)
                deps_in_order.append(dep)

    walk_deps(root_deps)

    if not command:
        print('\n'.join(dep.name for dep in deps_in_order))
        sys.exit(0)

    #=========================================================================
    # execution
    #=========================================================================

    if verbose:
        echo_verbose_msg('working directory: ' +
                 os.path.join('<dependency>', directory_inside))

    filter_if_exist = []
    if if_exist:
        filter_if_exist.extend(if_exist)

    # check if command is an executable relative to dependency working dir

    first_dep = root_deps[0]
    first_working_dir = os.path.abspath(
        os.path.join(first_dep.abspath, directory_inside))
    first_command = command[0]
    expanded_first_command = first_command.format(name=first_dep.name)

    is_executable, suffix = is_executable_and_get_suffix(
        os.path.join(first_working_dir, expanded_first_command))

    if is_executable:
        filter_if_exist.append(''.join((first_command, suffix)))

    if ignore_filter:
        filter_if_exist = []

    def pass_filter(dep):
        for f in filter_if_exist:
            file_to_check = os.path.join(
                dep.abspath, directory_inside, f.format(name=dep.name))
            if not os.path.isfile(file_to_check) and not os.path.isdir(file_to_check):
                return False
        return True

    # execute command for each dependency
    for dep in deps_in_order:
        working_dir = None
        if not here:
            working_dir = os.path.join(dep.abspath, directory_inside)

        click.secho('\n' + '=' * MAX_LINE_LENGTH, fg='black', bold=True)
        if not pass_filter(dep) or (working_dir and not os.path.isdir(working_dir)):
            click.secho('{}: skipping'.format(dep.name), fg='cyan')
            continue
        click.secho('{}:'.format(dep.name), fg='cyan', bold=True)

        format_dict = {
            'name': dep.name, 'dir': dep.relpath, 'abs': dep.abspath}

        def _format(s, format_dict):
            for key, item in format_dict.iteritems():
                s = s.replace('{' + key + '}', item)
            return s

        formatted_command = [_format(a, format_dict) for a in command]

        if verbose or dry_run:
            command_to_print = ' '.join(
                arg.replace(' ', '\\ ') for arg in formatted_command)
            echo_verbose_msg('executing: ' + command_to_print)
            if working_dir:
                echo_verbose_msg('from:      ' + working_dir)

        if not dry_run:
            # Note: could use something like this for more robustness:
            # http://stackoverflow.com/questions/13243807/popen-waiting-for-child-process-even-when-the-immediate-child-has-terminated/13256908#13256908

            with cd(working_dir):
                process = subprocess.Popen(formatted_command, shell=True)
                process.communicate()

            if verbose:
                echo_verbose_msg('return code: {}'.format(process.returncode))


if __name__ == '__main__':
    cli()
