from __future__ import unicode_literals

import textwrap

from _pytest.pytester import LineMatcher
from deps import deps_cli
import os
import pytest


def test_deps_help(cli_runner):
    """
    :type cli_runner: click.testing.CliRunner
    """
    result = cli_runner.invoke(deps_cli.cli, ['--help'])
    assert result.exit_code == 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        'Usage: deps [OPTIONS] [COMMAND]...',  # Basic usage.
        'Options:',  # Options header.
        '*',  # Details.
        '*',  # Details.
        '*',  # Details.
        # ...
    ])


def test_no_args(cli_runner, project_tree):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    """
    os.chdir(unicode(project_tree.join('root_b')))
    result = cli_runner.invoke(deps_cli.cli)
    assert result.exit_code == 0
    assert result.output == textwrap.dedent(
        '''\
        dep_z
        dep_b.1.1
        dep_b.1
        root_b
        '''
    )


def test_execution_on_project_dir(cli_runner, project_tree):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    """
    os.chdir(unicode(project_tree.join('root_b')))
    command_args = ['-v', '--', 'python', '-c', '"name: {name}"']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        '===============================================================================',
        'dep_z:',
        'deps: executing: python -c "name:\\ dep_z"',
        'deps: from:      *dep_z',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_b.1.1:',
        'deps: executing: python -c "name:\\ dep_b.1.1"',
        'deps: from:      *dep_b.1.1',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_b.1:',
        'deps: executing: python -c "name:\\ dep_b.1"',
        'deps: from:      *dep_b.1',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'root_b:',
        'deps: executing: python -c "name:\\ root_b"',
        'deps: from:      *root_b',
        'deps: return code: 0',
    ])


def test_here_flag(cli_runner, project_tree):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    """
    os.chdir(unicode(project_tree.join('root_b')))
    command_args = ['-v', '--here', '--', 'python', '-c', '"name: {name}"']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0
    matcher = LineMatcher(result.output.splitlines())
    # Current working directory is not changed.
    matcher.fnmatch_lines([
        '===============================================================================',
        'dep_z:',
        'deps: executing: python -c "name:\\ dep_z"',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_b.1.1:',
        'deps: executing: python -c "name:\\ dep_b.1.1"',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_b.1:',
        'deps: executing: python -c "name:\\ dep_b.1"',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'root_b:',
        'deps: executing: python -c "name:\\ root_b"',
        'deps: return code: 0',
    ])


def test_multiple_projects(cli_runner, project_tree):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    """
    projects = ['root_a', 'root_b']
    projects = [unicode(project_tree.join(name)) for name in projects]
    command_args = ['-p', ','.join(projects)]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0
    assert result.output == textwrap.dedent(
        '''\
        dep_z
        dep_a.1.1
        dep_a.1.2
        dep_a.1
        dep_a.2
        root_a
        dep_b.1.1
        dep_b.1
        root_b
        '''
    )


@pytest.fixture(scope='session')
def project_tree(tmpdir_factory):
    """
    :type tmpdir_factory: _pytest.tmpdir.TempdirFactory
    :rtype: py.path.local
    """
    test_projects = tmpdir_factory.mktemp('test_projects')
    projects = {
        'root_a': ['dep_a.1', 'dep_a.2'],
        'root_b': ['dep_b.1'],
        'dep_a.1': ['dep_a.1.1', 'dep_a.1.2'],
        'dep_a.2': ['dep_z'],
        'dep_a.1.1': ['dep_z'],
        'dep_a.1.2': ['dep_z'],
        'dep_b.1': ['dep_b.1.1'],
        'dep_b.1.1': ['dep_z'],
        'dep_z': [],
    }
    for proj, deps in projects.iteritems():
        proj_dir = test_projects.mkdir(proj)
        env_yml = proj_dir.join('environment.yml')
        env_content = ['name: {}'.format(proj), '']
        if len(deps) > 0:
            env_content.append('includes:')
            env_content.extend(
                ['  - {{{{ root }}}}/../{}/environment.yml'.format(dep) for dep in deps])
            env_content.append('')
        env_yml.write('\n'.join(env_content))
    return test_projects

