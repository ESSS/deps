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
    assert result.exit_code == 0
    assert result.output == textwrap.dedent(
        '''\
        dep_z
        dep_b.1.1
        dep_b.1
        root_b
        '''
    )


def test_interpreter_awareness(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root_b = unicode(project_tree.join('root_b'))
    task_script = os.path.join('tasks', 'asd')
    command_args = ['-p', root_b, '-v', task_script, '{name}']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        '===============================================================================',
        'dep_z:',
        'deps: executing: *[\\/]python* tasks[\\/]asd.py dep_z',
        'deps: from:      *[\\/]test_projects0[\\/]dep_z',
        'From python script!',
        ' - sys.argv: dep_z;',
        ' - cwd: *[\\/]test_projects0[\\/]dep_z;',
        '',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_b.1.1: skipping',
        '',
        '===============================================================================',
        'dep_b.1: skipping',
        '',
        '===============================================================================',
        'root_b:',
        'deps: executing: *[\\/]python* tasks[\\/]asd.py root_b',
        'deps: from:      *[\\/]test_projects0[\\/]root_b',
        'From python script!',
        ' - sys.argv: root_b;',
        ' - cwd: *[\\/]test_projects0[\\/]root_b;',
        '',
        'deps: return code: 0',
    ])


def test_cant_find_root(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    proj_dir = unicode(project_tree.join('not_a_project'))
    command_args = ['-p', proj_dir, 'echo', 'Hi', '{name}!']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code != 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        'deps: error: could not find "environment.yml" for "*[\\/]test_projects0[\\/]not_a_project".',
    ])

    proj_dir = unicode(project_tree.join('not_a_valid_folder'))
    command_args = ['-p', proj_dir, 'echo', 'Hi', '{name}!']
    result = cli_runner.invoke(deps_cli.cli, command_args)
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
        '===============================================================================',
        'dep_z:',
        'deps: executing: python -c "name:\\ dep_z"',
        'deps: from:      *[\\/]test_projects0[\\/]dep_z',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_b.1.1:',
        'deps: executing: python -c "name:\\ dep_b.1.1"',
        'deps: from:      *[\\/]test_projects0[\\/]dep_b.1.1',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_b.1:',
        'deps: executing: python -c "name:\\ dep_b.1"',
        'deps: from:      *[\\/]test_projects0[\\/]dep_b.1',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'root_b:',
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


def test_script_execution(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root_b = unicode(project_tree.join('root_b'))
    task_script = os.path.join('tasks', 'asd')
    command_args = ['-p', root_b, '-v', task_script, '{name}', '{abs}']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        '===============================================================================',
        'dep_z:',
        'deps: executing: *[\\/]python* tasks[\\/]asd.py dep_z *[\\/]test_projects0[\\/]dep_z',
        'deps: from:      *[\\/]test_projects0[\\/]dep_z',
        'From python script!',
        ' - sys.argv: dep_z *[\\/]test_projects0[\\/]dep_z;',
        ' - cwd: *[\\/]test_projects0[\\/]dep_z;',
        '',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_b.1.1: skipping',
        '',
        '===============================================================================',
        'dep_b.1: skipping',
        '',
        '===============================================================================',
        'root_b:',
        'deps: executing: *[\\/]python* tasks[\\/]asd.py root_b *[\\/]test_projects0[\\/]root_b',
        'deps: from:      *[\\/]test_projects0[\\/]root_b',
        'From python script!',
        ' - sys.argv: root_b *[\\/]test_projects0[\\/]root_b;',
        ' - cwd: *[\\/]test_projects0[\\/]root_b;',
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
        '===============================================================================',
        'dep_z:',
        'deps: executing: tasks[\\/]does-not-exist dep_z *[\\/]test_projects0[\\/]dep_z',
        'deps: from:      *[\\/]test_projects0[\\/]dep_z',
        'deps: return code: *',
        'deps: error: Command failed',
    ])



@pytest.mark.parametrize('use_env_var', [
    True,
    False,
])
def test_script_execution_fallback(
    use_env_var,
    cli_runner,
    project_tree,
    piped_shell_execute,
    tmpdir,
):
    """
    :type use_env_var: bool
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    :type tmpdir: py.path.local
    """
    # Create a fallback.
    batch_script = textwrap.dedent(
        '''\
        @echo Fallback script for asd %*
        '''
    )
    bash_script = textwrap.dedent(
        '''\
        #!/bin/bash
        echo Fallback script for asd "$@"
        '''
    )
    tasks_dir = tmpdir.mkdir('tasks')
    script_file = tasks_dir.join('asd.bat')
    script_file.write(batch_script)
    script_file = tasks_dir.join('asd')
    script_file.write(bash_script)
    script_file = unicode(script_file)
    st = os.stat(script_file)
    os.chmod(script_file, st.st_mode | stat.S_IEXEC)
    # Prepare the invocation.
    root_a = unicode(project_tree.join('root_a'))
    task_script = os.path.join('tasks', 'asd')
    command_args = ['-p', root_a, '-v', task_script, '{name}', '{abs}']
    # Configure the fallback path.
    extra_env = {}
    if use_env_var:
        encoding = sys.getfilesystemencoding()
        extra_env[b'DEPS_FALLBACK_PATHS'] = unicode(tmpdir).encode(encoding)
    else:
        command_args.insert(0, '--fallback-paths={}'.format(unicode(tmpdir)))

    result = cli_runner.invoke(deps_cli.cli, command_args, env=extra_env)
    assert result.exit_code == 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        '===============================================================================',
        'dep_z:',
        'deps: executing: *[\\/]python* tasks[\\/]asd.py dep_z *[\\/]test_projects0[\\/]dep_z',
        'deps: from:      *[\\/]test_projects0[\\/]dep_z',
        'From python script!',
        ' - sys.argv: dep_z *[\\/]test_projects0[\\/]dep_z;',
        ' - cwd: *[\\/]test_projects0[\\/]dep_z;',
        '',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_a.1.1:',
        'deps: executing: *[\\/]test_script_execution_fallback?[\\/]tasks[\\/]asd* dep_a.1.1 *[\\/]test_projects0[\\/]dep_a.1.1',
        'deps: from:      *[\\/]test_projects0[\\/]dep_a.1.1',
        'Fallback script for asd dep_a.1.1 *[\\/]test_projects0[\\/]dep_a.1.1',
        '',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_a.1.2:',
        'deps: executing: *[\\/]test_script_execution_fallback?[\\/]tasks[\\/]asd* dep_a.1.2 *[\\/]test_projects0[\\/]dep_a.1.2',
        'deps: from:      *[\\/]test_projects0[\\/]dep_a.1.2',
        'Fallback script for asd dep_a.1.2 *[\\/]test_projects0[\\/]dep_a.1.2',
        '',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_a.1:',
        'deps: executing: *[\\/]test_script_execution_fallback?[\\/]tasks[\\/]asd* dep_a.1 *[\\/]test_projects0[\\/]dep_a.1',
        'deps: from:      *[\\/]test_projects0[\\/]dep_a.1',
        'Fallback script for asd dep_a.1 *[\\/]test_projects0[\\/]dep_a.1',
        '',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_a.2:',
        'deps: executing: *[\\/]test_script_execution_fallback?[\\/]tasks[\\/]asd* dep_a.2 *[\\/]test_projects0[\\/]dep_a.2',
        'deps: from:      *[\\/]test_projects0[\\/]dep_a.2',
        'Fallback script for asd dep_a.2 *[\\/]test_projects0[\\/]dep_a.2',
        '',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'root_a:',
        'deps: executing: *[\\/]python* tasks[\\/]asd.py root_a *[\\/]test_projects0[\\/]root_a',
        'deps: from:      *[\\/]test_projects0[\\/]root_a',
        'From python script!',
        ' - sys.argv: root_a *[\\/]test_projects0[\\/]root_a;',
        ' - cwd: *[\\/]test_projects0[\\/]root_a;',
        '',
        'deps: return code: 0',
    ])


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
            extra_env[b'DEPS_IGNORE_PROJECTS'] = b'dep_a.1,dep_z'
        else:
            command_args.insert(0, '--ignore-projects=dep_a.1,dep_z')
    root_a = unicode(project_tree.join('root_a'))
    # Prepare the invocation.
    command_args = ['-p', root_a, 'echo', 'test', '{name}']
    extra_env = {}
    configure_ignored_projects()

    result = cli_runner.invoke(deps_cli.cli, command_args, env=extra_env)
    assert result.exit_code == 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        '===============================================================================',
        'dep_a.1: ignored',
        '',
        '===============================================================================',
        'dep_z: ignored',
        '',
        '===============================================================================',
        'dep_a.2:',
        'test dep_a.2',
        '',
        '===============================================================================',
        'root_a:',
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

