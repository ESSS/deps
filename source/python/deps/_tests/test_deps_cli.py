from __future__ import unicode_literals
from _pytest.pytester import LineMatcher
from deps import deps_cli
import os
import pytest
import stat
import sys
import textwrap


@pytest.fixture(scope='session')
def project_tree(tmpdir_factory):
    """
    :type tmpdir_factory: _pytest.tmpdir.TempdirFactory
    :rtype: py.path.local
    """
    test_projects = tmpdir_factory.mktemp('test_projects')
    projects = {
        'root_a': ['dep_a.1', 'dep_a.2'],
        'root_b': ['bs/dep_b.1'],
        'dep_a.1': ['dep_a.1.1', 'dep_a.1.2'],
        'dep_a.2': ['dep_z'],
        'dep_a.1.1': ['dep_z'],
        'dep_a.1.2': ['dep_z'],
        'bs/dep_b.1': ['dep_b.1.1'],
        'bs/dep_b.1.1': ['../dep_z'],
        'dep_z': [],
        'root_c': ['cs1/dep_c1.1'],
        'cs1/dep_c1.1': ['dep_c1.2'],
        'cs1/dep_c1.2': ['dep_c1.3', 'dep_c1.1'],
        'cs1/dep_c1.3': ['dep_c1.1', '../cs2/dep_c2.1'],
        'cs2/dep_c2.1': ['../cs1/dep_c1.2'],
    }
    for proj, deps in projects.iteritems():
        proj_path = proj.split('/')
        proj_dir = test_projects.ensure(*proj_path, dir=True)
        test_projects.ensure(proj_path[0], '.git', dir=True)  # Fake git repo.
        env_yml = proj_dir.join('environment.yml')
        env_content = ['name: {}'.format(proj), '']
        if len(deps) > 0:
            env_content.append('includes:')
            env_content.extend(
                ['  - {{{{ root }}}}/../{}/environment.yml'.format(dep) for dep in deps])
            env_content.append('')
        env_yml.write('\n'.join(env_content))
    # Add a non-project folder.
    test_projects.mkdir('not_a_project')
    # Add test scripts to some projects.
    batch_script = textwrap.dedent(
        '''\
        @echo Sample script %*
        '''
    )
    bash_script = textwrap.dedent(
        '''\
        #!/bin/bash
        echo Sample script "$@"
        '''
    )
    python_script = textwrap.dedent(
        '''\
        import os
        import sys
        print "From python script!"
        print " - sys.argv: {};".format(' '.join(sys.argv[1:]))
        print " - cwd: {};".format(os.getcwd())
        '''
    )
    for proj in ['root_a', 'root_b', 'dep_z']:
        tasks_dir = test_projects.join(proj).mkdir('tasks')
        script_file = tasks_dir.join('asd.bat')
        script_file.write(batch_script)

        script_file = tasks_dir.join('asd')
        script_file.write(bash_script)
        script_file = unicode(script_file)
        st = os.stat(script_file)
        os.chmod(script_file, st.st_mode | stat.S_IEXEC)

        script_file = tasks_dir.join('asd.py')
        script_file.write(python_script)

    return test_projects


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


def test_no_args(cli_runner, project_tree, monkeypatch):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type monkeypatch: _pytest.monkeypatch
    """
    monkeypatch.chdir(project_tree.join('root_b'))
    result = cli_runner.invoke(deps_cli.cli)
    assert result.exit_code == 0, result.output
    assert result.output == textwrap.dedent(
        '''\
        dep_z
        dep_b.1.1
        dep_b.1
        root_b
        '''
    )


def test_cant_find_root(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    proj_dir = unicode(project_tree.join('not_a_project'))
    command_args = ['-p', proj_dir, 'echo', 'Hi', '{name}!']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code != 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        'deps: error: could not find "environment.yml" for "*[\\/]test_projects0[\\/]not_a_project".',
    ])

    proj_dir = unicode(project_tree.join('not_a_valid_folder'))
    command_args = ['-p', proj_dir, 'echo', 'Hi', '{name}!']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code != 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        'deps: error: could not find "environment.yml" for "*[\\/]test_projects0[\\/]not_a_valid_folder".',
    ])


def test_execution_on_project_dir(cli_runner, project_tree, monkeypatch):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type monkeypatch: _pytest.monkeypatch
    """
    monkeypatch.chdir(project_tree.join('root_b'))
    command_args = ['-v', '--', 'python', '-c', '"name: {name}"']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        'dep_z',
        'deps: executing: python -c "name:\\ dep_z"',
        'deps: from:      *[\\/]test_projects0[\\/]dep_z',
        'deps: return code: 0',

        'dep_b.1.1',
        'deps: executing: python -c "name:\\ dep_b.1.1"',
        'deps: from:      *[\\/]test_projects0[\\/]bs[\\/]dep_b.1.1',
        'deps: return code: 0',

        'dep_b.1',
        'deps: executing: python -c "name:\\ dep_b.1"',
        'deps: from:      *[\\/]test_projects0[\\/]bs[\\/]dep_b.1',
        'deps: return code: 0',

        'root_b',
        'deps: executing: python -c "name:\\ root_b"',
        'deps: from:      *[\\/]test_projects0[\\/]root_b',
        'deps: return code: 0',
    ])


def test_here_flag(cli_runner, project_tree, monkeypatch):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type monkeypatch: _pytest.monkeypatch
    """
    monkeypatch.chdir(project_tree.join('root_b'))
    command_args = ['-v', '--here', '--', 'python', '-c', '"name: {name}"']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0
    matcher = LineMatcher(result.output.splitlines())
    # Current working directory is not changed.
    matcher.fnmatch_lines([
        'dep_z',
        'deps: executing: python -c "name:\\ dep_z"',
        'deps: return code: 0',

        'dep_b.1.1',
        'deps: executing: python -c "name:\\ dep_b.1.1"',
        'deps: return code: 0',

        'dep_b.1',
        'deps: executing: python -c "name:\\ dep_b.1"',
        'deps: return code: 0',

        'root_b',
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
    command_args = [('--project=%s' % (project,)) for project in projects]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
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


def test_script_execution(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root_b = unicode(project_tree.join('root_b'))
    task_script = os.path.join('tasks', 'asd')
    command_args = ['-p', root_b, '-v', '-f', 'tasks/asd', task_script, '{name}', '{abs}']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        'dep_z',
        'deps: executing: tasks[\\/]asd dep_z *[\\/]test_projects0[\\/]dep_z',
        'deps: from:      *[\\/]test_projects0[\\/]dep_z',
        'Sample script dep_z *[\\/]test_projects0[\\/]dep_z',
        '',
        'deps: return code: 0',

        'dep_b.1.1: skipping since "*[\\/]tasks[\\/]asd" does not exist',

        'dep_b.1: skipping since "*[\\/]tasks[\\/]asd" does not exist',

        'root_b',
        'deps: executing: tasks[\\/]asd root_b *[\\/]test_projects0[\\/]root_b',
        'deps: from:      *[\\/]test_projects0[\\/]root_b',
        'Sample script root_b *[\\/]test_projects0[\\/]root_b',
        '',
        'deps: return code: 0',
    ])


def test_script_return_code(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root_b = unicode(project_tree.join('root_b'))
    task_script = os.path.join('tasks', 'does-not-exist')
    command_args = ['-p', root_b, '-v', task_script, '{name}', '{abs}']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code != 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        'dep_z',
        'deps: executing: tasks[\\/]does-not-exist dep_z *[\\/]test_projects0[\\/]dep_z',
        'deps: from:      *[\\/]test_projects0[\\/]dep_z',
        'deps: return code: *',
        'deps: error: Command failed',
    ])


@pytest.mark.parametrize('force', [
    True,
    False,
])
@pytest.mark.parametrize('use_env_var', [
    True,
    False,
])
def test_force_color(
    use_env_var,
    force,
    cli_runner,
    project_tree,
    piped_shell_execute,
):
    """
    :type use_env_var: bool
    :type force: bool
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    def configure_force_color():
        if use_env_var:
            extra_env[b'DEPS_FORCE_COLOR'] = b'1' if force else b'0'
        else:
            command_args.insert(0, '--force-color' if force else '--no-force-color')

    root_b = unicode(project_tree.join('root_b'))
    # Prepare the invocation.
    command_args = ['-v', '-p', root_b, 'echo', 'test', '{name}']
    extra_env = {}
    configure_force_color()

    # Since `CliRunner.invoke` captures the output the stdout/stderr is not a tty.
    result = cli_runner.invoke(deps_cli.cli, command_args, env=extra_env, color=None)
    assert result.exit_code == 0, result.output
    output_repr = repr(result.output)
    # CSI for Control Sequence Introducer (or Control Sequence Initiator).
    ansi_csi_repr = '\\x1b['
    assert (ansi_csi_repr in output_repr) == force


@pytest.mark.parametrize('use_env_var', [
    True,
    False,
])
def test_ignore_projects(
    use_env_var,
    cli_runner,
    project_tree,
    piped_shell_execute,
):
    """
    :type use_env_var: bool
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    def configure_ignored_projects():
        if use_env_var:
            extra_env[b'DEPS_IGNORE_PROJECT'] = b'dep_a.1%sdep_z' % (os.pathsep,)
        else:
            command_args.insert(0, '--ignore-project=dep_a.1')
            command_args.insert(1, '--ignore-project=dep_z')
    root_a = unicode(project_tree.join('root_a'))
    # Prepare the invocation.
    command_args = ['-p', root_a, 'echo', 'test', '{name}']
    extra_env = {}
    configure_ignored_projects()

    result = cli_runner.invoke(deps_cli.cli, command_args, env=extra_env)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        'dep_a.1 ignored',

        'dep_z ignored',

        'dep_a.2',
        'test dep_a.2',

        'root_a',
        'test root_a',
    ])

    # Prepare the invocation.
    command_args = ['-p', root_a]
    extra_env = {}
    configure_ignored_projects()

    result = cli_runner.invoke(deps_cli.cli, command_args, env=extra_env)
    assert result.exit_code == 0
    assert result.output == textwrap.dedent(
        '''\
        dep_a.2
        root_a
        '''
    )


def test_require_file(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root_b = unicode(project_tree.join('root_b'))
    base_args = ['-p', root_b, '--require-file', 'tasks/asd']

    command_args = base_args + ['-v', 'echo', 'This', 'is', '{name}']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        'dep_z',
        'deps: executing: echo This is dep_z',
        'deps: from:      *[\\/]test_projects0[\\/]dep_z',
        'This is dep_z',
        'deps: return code: 0',

        'dep_b.1.1: skipping since "*[\\/]test_projects0[\\/]bs[\\/]dep_b.1.1[\\/]tasks[\\/]asd" does not exist',

        'dep_b.1: skipping since "*[\\/]test_projects0[\\/]bs[\\/]dep_b.1[\\/]tasks[\\/]asd" does not exist',

        'root_b',
        'deps: executing: echo This is root_b',
        'deps: from:      *[\\/]test_projects0[\\/]root_b',
        'This is root_b',
        'deps: return code: 0',
    ])

    command_args = ['-p', root_b, '--require-file', 'tasks/asd']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    assert result.output == textwrap.dedent(
        '''\
        dep_z
        root_b
        '''
    )


def test_continue_on_failue(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root_b = unicode(project_tree.join('root_b'))
    base_args = ['--continue-on-failure', '-p', root_b]

    # All fail.
    command_args = base_args + ['does-not-exist']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code != 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        'dep_z',
        'deps: error: Command failed',

        'dep_b.1.1',
        'deps: error: Command failed',

        'dep_b.1',
        'deps: error: Command failed',

        'root_b',
        'deps: error: Command failed',
    ])

    # Some fail.
    if sys.platform.startswith('win'):
        dir_or_ls = 'dir'
    else:
        dir_or_ls = 'ls'
    command_args = base_args + [dir_or_ls, os.path.join('tasks', 'asd.py')]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code != 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        'dep_z',

        'dep_b.1.1',
        'deps: error: Command failed',

        'dep_b.1',
        'deps: error: Command failed',

        'root_b',
    ])

    # None fail.
    command_args = base_args + ['echo', 'This', 'is', '{name}']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    assert 'deps: error: Command failed' not in result.output


def test_list_repos(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root = unicode(project_tree.join('root_c'))
    base_args = ['-p', root, '--repos']

    command_args = base_args
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        '*[\\/]test_projects0[\\/]cs2',
        '*[\\/]test_projects0[\\/]cs1',
        '*[\\/]test_projects0[\\/]root_c',
    ])


    base_args = ['-p', root, '--repos']
    # Test pretty print.
    command_args = base_args + ['-pp']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        '# - project_name: listed or target of command execution;',
        '# - (project_name): have already been printed in the tree;',
        '# - <project_name>: have been ignored (see `--ignored-projects` option);',
        '*[\\/]test_projects0[\\/]root_c',
        '    *[\\/]test_projects0[\\/]cs1',
        '        *[\\/]test_projects0[\\/]cs2',
        '        (*[\\/]test_projects0[\\/]cs1)',
    ])


def test_list_repos_with_ignored_project(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root = unicode(project_tree.join('root_c'))
    base_args = ['-p', root, '--repos']

    base_args = ['-p', root, '--repos', '--ignore-project=dep_c1.3']
    # Test pretty print.
    command_args = base_args + ['-pp']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        '# - project_name: listed or target of command execution;',
        '# - (project_name): have already been printed in the tree;',
        '# - <project_name>: have been ignored (see `--ignored-projects` option);',
        '*[\\/]test_projects0[\\/]root_c',
        '    *[\\/]test_projects0[\\/]cs1',
        '        <*[\\/]test_projects0[\\/]cs1>',
    ])

