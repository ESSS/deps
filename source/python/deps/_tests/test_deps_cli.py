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
        print " - sys.argv[1:]: {};".format(sys.argv[1:])
        print " - cwd: {};".format(os.getcwd())
        '''
    )
    for proj in ['root_b', 'dep_z']:
        tasks_dir = test_projects.join(proj).mkdir('tasks')
        script_file = tasks_dir.join('asd.bat')
        script_file.write(batch_script)

        script_file = tasks_dir.join('asd')
        script_file.write(bash_script)
        script_file = unicode(script_file)
        st = os.stat(script_file)
        os.chmod(script_file, st.st_mode | stat.S_IEXEC)

        script_file = tasks_dir.join('py_get_cwd.py')
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
        'deps: executing: tasks?asd dep_z *dep_z',
        'deps: from:      *dep_z',
        'Sample script dep_z *dep_z',
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
        'deps: executing: tasks?asd root_b *root_b',
        'deps: from:      *root_b',
        'Sample script root_b *root_b',
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
        'deps: executing: tasks?does-not-exist dep_z *test_projects0?dep_z',
        'deps: from:      *test_projects0?dep_z',
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
    mocker,
):
    """
    :type use_env_var: bool
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    :type tmpdir: py.path.local
    :type mocker: mocker
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
    if use_env_var:
        encoding = sys.getfilesystemencoding()
        env_values = {b'DEPS_FALLBACK_PATHS': unicode(tmpdir).encode(encoding)}
        mocker.patch.dict('os.environ', env_values)
    else:
        command_args.insert(0, '--fallback-paths')
        command_args.insert(1, unicode(tmpdir))

    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines([
        '===============================================================================',
        'dep_z:',
        'deps: executing: tasks?asd dep_z *test_projects0?dep_z',
        'deps: from:      *test_projects0?dep_z',
        'Sample script dep_z *test_projects0?dep_z',
        '',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_a.1.1:',
        'deps: executing: *test_script_execution_fallback??tasks?asd dep_a.1.1 *test_projects0?dep_a.1.1',
        'deps: from:      *test_projects0?dep_a.1.1',
        'Fallback script for asd dep_a.1.1 *test_projects0?dep_a.1.1',
        '',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_a.1.2:',
        'deps: executing: *test_script_execution_fallback??tasks?asd dep_a.1.2 *test_projects0?dep_a.1.2',
        'deps: from:      *test_projects0?dep_a.1.2',
        'Fallback script for asd dep_a.1.2 *test_projects0?dep_a.1.2',
        '',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_a.1:',
        'deps: executing: *test_script_execution_fallback??tasks?asd dep_a.1 *test_projects0?dep_a.1',
        'deps: from:      *test_projects0?dep_a.1',
        'Fallback script for asd dep_a.1 *test_projects0?dep_a.1',
        '',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'dep_a.2:',
        'deps: executing: *test_script_execution_fallback??tasks?asd dep_a.2 *test_projects0?dep_a.2',
        'deps: from:      *test_projects0?dep_a.2',
        'Fallback script for asd dep_a.2 *test_projects0?dep_a.2',
        '',
        'deps: return code: 0',
        '',
        '===============================================================================',
        'root_a:',
        'deps: executing: *test_script_execution_fallback??tasks?asd root_a *test_projects0?root_a',
        'deps: from:      *test_projects0?root_a',
        'Fallback script for asd root_a *test_projects0?root_a',
        '',
        'deps: return code: 0',
    ])

