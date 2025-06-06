import os
import stat
import sys
import textwrap
from builtins import str
from pathlib import Path

import pytest
from _pytest.pytester import LineMatcher

from deps import deps_cli


@pytest.fixture(autouse=True)
def cleanup_env(monkeypatch):
    """
    Remove the GITHUB_WORKSPACE from the testing environment, otherwise the presence of this
    variable will cause all section outputs to contain ::group:: when running inside GH actions itself.
    """
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)


@pytest.fixture(scope="session")
def project_tree(tmpdir_factory):
    """
    :type tmpdir_factory: _pytest.tmpdir.TempdirFactory
    :rtype: py.path.local
    """
    test_projects = tmpdir_factory.mktemp("test_projects")
    projects = {
        "root_a": ["dep_a.1", "dep_a.2"],
        "root_b": ["bs/dep_b.1"],
        "dep_a.1": ["dep_a.1.1", "dep_a.1.2"],
        "dep_a.2": ["dep_z"],
        "dep_a.1.1": ["dep_z"],
        "dep_a.1.2": ["dep_z"],
        "bs/dep_b.1": ["dep_b.1.1"],
        "bs/dep_b.1.1": ["../dep_z"],
        "dep_z": [],
        "root_c": ["cs1/dep_c1.1"],
        "cs1/dep_c1.1": ["dep_c1.2"],
        "cs1/dep_c1.2": ["dep_c1.3", "dep_c1.1"],
        "cs1/dep_c1.3": ["dep_c1.1", "../cs2/dep_c2.1"],
        "cs2/dep_c2.1": ["../cs1/dep_c1.2"],
        "root_d": ["d/d1", "d/d2", "d/d3"],
        "d/d1": [],
        "d/d2": [],
        "d/d3": [],
    }
    for proj, deps in projects.items():
        proj_path = proj.split("/")
        proj_dir = test_projects.ensure(*proj_path, dir=True)
        test_projects.ensure(proj_path[0], ".git", dir=True)  # Fake git repo.
        env_yml = proj_dir.join("environment.devenv.yml")
        env_content = ["name: {}".format(proj), ""]
        if len(deps) > 0:
            env_content.append("includes:")
            env_content.extend(
                [
                    "  - {{{{ root }}}}/../{}/environment.devenv.yml".format(dep)
                    for dep in deps
                ]
            )
            env_content.append("")
        env_yml.write("\n".join(env_content))
    # Add a non-project folder.
    test_projects.mkdir("not_a_project")
    # Add test scripts to some projects.
    batch_script = textwrap.dedent(
        """\
        @echo Sample script %*
        """
    )
    bash_script = textwrap.dedent(
        """\
        #!/bin/bash
        echo Sample script "$@"
        """
    )
    python_script = textwrap.dedent(
        """\
        import os
        import sys
        print "From python script!"
        print " - sys.argv: {};".format(' '.join(sys.argv[1:]))
        print " - cwd: {};".format(os.getcwd())
        """
    )
    for proj in ["root_a", "root_b", "dep_z"]:
        tasks_dir = test_projects.join(proj).mkdir("tasks")
        script_file = tasks_dir.join("asd.bat")
        script_file.write(batch_script)

        script_file = tasks_dir.join("asd")
        script_file.write(bash_script)
        script_file = str(script_file)
        st = os.stat(script_file)
        os.chmod(script_file, st.st_mode | stat.S_IEXEC)

        script_file = tasks_dir.join("asd.py")
        script_file.write(python_script)

    return test_projects


def test_deps_help(cli_runner):
    """
    :type cli_runner: click.testing.CliRunner
    """
    result = cli_runner.invoke(deps_cli.cli, ["--help"])
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "Usage: deps [OPTIONS] [COMMAND]...",  # Basic usage.
            "Options:",  # Options header.
            "*",  # Details.
            "*",  # Details.
            "*",  # Details.
            # ...
        ]
    )


def test_no_args(cli_runner, project_tree, monkeypatch):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type monkeypatch: _pytest.monkeypatch
    """
    monkeypatch.chdir(project_tree.join("root_b"))
    result = cli_runner.invoke(deps_cli.cli)
    assert result.exit_code == 0, result.output
    assert result.output == textwrap.dedent(
        """\
        dep_z
        dep_b.1.1
        dep_b.1
        root_b
        """
    )


def test_no_args_cyclic_deps(cli_runner, project_tree, monkeypatch):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type monkeypatch: _pytest.monkeypatch
    """
    monkeypatch.chdir(project_tree.join("root_c"))
    result = cli_runner.invoke(deps_cli.cli)
    assert result.exit_code == 0, result.output
    assert result.output == textwrap.dedent(
        """\
        dep_c2.1
        dep_c1.3
        dep_c1.2
        dep_c1.1
        root_c
        """
    )


def test_cant_find_root(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    proj_dir = str(project_tree.join("not_a_project"))
    command_args = ["-p", proj_dir, "echo", "Hi", "{name}!"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code != 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            'deps: error: could not find "environment.devenv.yml" for "*[\\/]test_projects0[\\/]not_a_project".',
        ]
    )

    proj_dir = str(project_tree.join("not_a_valid_folder"))
    command_args = ["-p", proj_dir, "echo", "Hi", "{name}!"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code != 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            'deps: error: could not find "environment.devenv.yml" for "*[\\/]test_projects0[\\/]not_a_valid_folder".',
        ]
    )


@pytest.mark.parametrize("on_github", [True, False])
def test_execution_on_project_dir(cli_runner, project_tree, monkeypatch, on_github):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type monkeypatch: _pytest.monkeypatch
    """
    if on_github:
        monkeypatch.setenv("GITHUB_WORKSPACE", "some/path")
        expected_prefix = "::group::"
    else:
        expected_prefix = ""
    monkeypatch.chdir(project_tree.join("root_b"))
    command_args = ["-v", "--", "python", "-c", '"name: {name}"']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            f"{expected_prefix}dep_z (1/4)",
            'deps: executing: python -c "name:\\ dep_z"',
            "deps: from:      *[\\/]test_projects0[\\/]dep_z",
            "deps: return code: 0",
            f"{expected_prefix}dep_b.1.1 (2/4)",
            'deps: executing: python -c "name:\\ dep_b.1.1"',
            "deps: from:      *[\\/]test_projects0[\\/]bs[\\/]dep_b.1.1",
            "deps: return code: 0",
            f"{expected_prefix}dep_b.1 (3/4)",
            'deps: executing: python -c "name:\\ dep_b.1"',
            "deps: from:      *[\\/]test_projects0[\\/]bs[\\/]dep_b.1",
            "deps: return code: 0",
            f"{expected_prefix}root_b (4/4)",
            'deps: executing: python -c "name:\\ root_b"',
            "deps: from:      *[\\/]test_projects0[\\/]root_b",
            "deps: return code: 0",
        ]
    )
    if on_github:
        matcher.fnmatch_lines("::endgroup::")


def test_here_flag(cli_runner, project_tree, monkeypatch):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type monkeypatch: _pytest.monkeypatch
    """
    monkeypatch.chdir(project_tree.join("root_b"))
    command_args = ["-v", "--here", "--", "python", "-c", '"name: {name}"']
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    # Current working directory is not changed.
    matcher.fnmatch_lines(
        [
            "dep_z (1/4)",
            'deps: executing: python -c "name:\\ dep_z"',
            "deps: return code: 0",
            "dep_b.1.1 (2/4)",
            'deps: executing: python -c "name:\\ dep_b.1.1"',
            "deps: return code: 0",
            "dep_b.1 (3/4)",
            'deps: executing: python -c "name:\\ dep_b.1"',
            "deps: return code: 0",
            "root_b (4/4)",
            'deps: executing: python -c "name:\\ root_b"',
            "deps: return code: 0",
        ]
    )


def test_multiple_projects(cli_runner, project_tree):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    """
    projects = ["root_a", "root_b"]
    projects = [str(project_tree.join(name)) for name in projects]
    command_args = [("--project={}".format(project)) for project in projects]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    assert result.output == textwrap.dedent(
        """\
        dep_z
        dep_a.1.2
        dep_a.1.1
        dep_a.2
        dep_a.1
        root_a
        dep_b.1.1
        dep_b.1
        root_b
        """
    )


def test_script_execution(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root_b = str(project_tree.join("root_b"))
    task_script = os.path.join("tasks", "asd")
    command_args = [
        "-p",
        root_b,
        "-v",
        "-f",
        "tasks/asd",
        task_script,
        "{name}",
        "{abs}",
    ]
    result = cli_runner.invoke(deps_cli.cli, command_args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "dep_z (1/4)",
            "deps: executing: tasks[\\/]asd dep_z *[\\/]test_projects0[\\/]dep_z",
            "deps: from:      *[\\/]test_projects0[\\/]dep_z",
            "Sample script dep_z *[\\/]test_projects0[\\/]dep_z",
            "",
            "deps: return code: 0",
            'dep_b.1.1: skipping since "*[\\/]tasks[\\/]asd" does not exist',
            'dep_b.1: skipping since "*[\\/]tasks[\\/]asd" does not exist',
            "root_b (4/4)",
            "deps: executing: tasks[\\/]asd root_b *[\\/]test_projects0[\\/]root_b",
            "deps: from:      *[\\/]test_projects0[\\/]root_b",
            "Sample script root_b *[\\/]test_projects0[\\/]root_b",
            "",
            "deps: return code: 0",
        ]
    )


def test_script_return_code(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root_b = str(project_tree.join("root_b"))
    task_script = os.path.join("tasks", "does-not-exist")
    command_args = ["-p", root_b, "-v", task_script, "{name}", "{abs}"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code != 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "dep_z (1/4)",
            "deps: executing: tasks[\\/]does-not-exist dep_z *[\\/]test_projects0[\\/]dep_z",
            "deps: from:      *[\\/]test_projects0[\\/]dep_z",
            "deps: return code: *",
            "deps: error: Command failed (project: dep_z)",
        ]
    )


def skip_if_linux(reason):
    """
    Create a skipif mark to skip when in linux with the given `reason`.

    :type reason: str
    :return: a `pytest.mark.skipif`
    """
    return pytest.mark.skipif(sys.platform == "linux", reason=reason)


@pytest.mark.parametrize(
    "force",
    [
        True,
        pytest.param(
            False,
            marks=skip_if_linux("no color is not an option on linux"),
        ),
    ],
)
@pytest.mark.parametrize(
    "use_env_var",
    [
        True,
        False,
    ],
)
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
    root_b = str(project_tree.join("root_b"))
    # Prepare the invocation.
    command_args = ["-v", "-p", root_b, "echo", "test", "{name}"]
    extra_env = {}
    if use_env_var:
        extra_env["DEPS_FORCE_COLOR"] = "1" if force else "0"
    else:
        command_args.insert(0, "--force-color" if force else "--no-force-color")

    # Since `CliRunner.invoke` captures the output the stdout/stderr is not a tty.
    result = cli_runner.invoke(
        deps_cli.cli, command_args, env=extra_env, color=False, catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    output_repr = repr(result.output)
    # CSI for Control Sequence Introducer (or Control Sequence Initiator).
    ansi_csi_repr = "\\x1b["
    assert (ansi_csi_repr in output_repr) == force


@pytest.mark.parametrize(
    "use_env_var",
    [
        True,
        False,
    ],
)
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
            extra_env["DEPS_IGNORE_PROJECT"] = str("dep_a.1{}dep_z".format(os.pathsep))
        else:
            command_args.insert(0, "--ignore-project=dep_a.1")
            command_args.insert(1, "--ignore-project=dep_z")

    root_a = str(project_tree.join("root_a"))
    # Prepare the invocation.
    command_args = ["-p", root_a, "echo", "test", "{name}"]
    extra_env = {}
    configure_ignored_projects()

    result = cli_runner.invoke(deps_cli.cli, command_args, env=extra_env)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "dep_a.1 ignored",
            "dep_z ignored",
            "dep_a.2 (3/4)",
            "test dep_a.2",
            "root_a (4/4)",
            "test root_a",
        ]
    )

    # Prepare the invocation.
    command_args = ["-p", root_a]
    extra_env = {}
    configure_ignored_projects()

    result = cli_runner.invoke(deps_cli.cli, command_args, env=extra_env)
    assert result.exit_code == 0, result.output
    assert result.output == textwrap.dedent(
        """\
        dep_a.2
        root_a
        """
    )


@pytest.mark.parametrize(
    "use_env_var",
    [
        True,
        False,
    ],
)
def test_skip_projects(
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

    def configure_skipped_projects():
        if use_env_var:
            extra_env["DEPS_SKIP_PROJECT"] = str("dep_a.1{}dep_z".format(os.pathsep))
        else:
            command_args.insert(0, "--skip-project=dep_a.1")
            command_args.insert(1, "--skip-project=dep_z")

    root_a = str(project_tree.join("root_a"))
    # Prepare the invocation.
    command_args = ["-p", root_a, "echo", "test", "{name}"]
    extra_env = {}
    configure_skipped_projects()

    result = cli_runner.invoke(deps_cli.cli, command_args, env=extra_env)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "dep_z skipped",
            "dep_a.1.2 (2/6)",
            "test dep_a.1.2",
            "dep_a.1.1 (3/6)",
            "test dep_a.1.1",
            "dep_a.2 (4/6)",
            "test dep_a.2",
            "dep_a.1 skipped",
            "root_a (6/6)",
            "test root_a",
        ]
    )

    # Prepare the invocation.
    command_args = ["-p", root_a]
    extra_env = {}
    configure_skipped_projects()

    result = cli_runner.invoke(deps_cli.cli, command_args, env=extra_env)
    assert result.exit_code == 0, result.output
    assert result.output == textwrap.dedent(
        """\
        dep_a.1.2
        dep_a.1.1
        dep_a.2
        root_a
        """
    )


@pytest.mark.parametrize(
    "use_env_var",
    [
        True,
        False,
    ],
)
def test_conflict_ignore_skip_projects(
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

    def configure_skipped_projects():
        if use_env_var:
            extra_env["DEPS_SKIP_PROJECT"] = "dep_a.1"
            extra_env["DEPS_IGNORE_PROJECT"] = "dep_a.1"
        else:
            command_args.insert(0, "--skip-project=dep_a.1")
            command_args.insert(0, "--ignore-project=dep_a.1")

    root_a = str(project_tree.join("root_a"))
    # Prepare the invocation.
    command_args = ["-p", root_a, "echo", "test", "{name}"]
    extra_env = {}
    configure_skipped_projects()

    result = cli_runner.invoke(deps_cli.cli, command_args, env=extra_env)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "dep_a.1 ignored",
            "dep_z (2/4)",
            "test dep_z",
            "dep_a.2 (3/4)",
            "test dep_a.2",
            "root_a (4/4)",
            "test root_a",
        ]
    )

    # Prepare the invocation.
    command_args = ["-p", root_a]
    extra_env = {}
    configure_skipped_projects()

    result = cli_runner.invoke(deps_cli.cli, command_args, env=extra_env)
    assert result.exit_code == 0, result.output
    assert result.output == textwrap.dedent(
        """\
        dep_z
        dep_a.2
        root_a
        """
    )


def test_require_file(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root_b = str(project_tree.join("root_b"))
    base_args = ["-p", root_b, "--require-file", "tasks/asd"]

    command_args = base_args + ["-v", "echo", "This", "is", "{name}"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "dep_z (1/4)",
            "deps: executing: echo This is dep_z",
            "deps: from:      *[\\/]test_projects0[\\/]dep_z",
            "This is dep_z",
            "deps: return code: 0",
            'dep_b.1.1: skipping since "*[\\/]test_projects0[\\/]bs[\\/]dep_b.1.1[\\/]tasks[\\/]asd" does not exist',
            'dep_b.1: skipping since "*[\\/]test_projects0[\\/]bs[\\/]dep_b.1[\\/]tasks[\\/]asd" does not exist',
            "root_b (4/4)",
            "deps: executing: echo This is root_b",
            "deps: from:      *[\\/]test_projects0[\\/]root_b",
            "This is root_b",
            "deps: return code: 0",
        ]
    )

    command_args = ["-p", root_b, "--require-file", "tasks/asd"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    assert result.output == textwrap.dedent(
        """\
        dep_z
        root_b
        """
    )


def test_continue_on_failure(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root_b = str(project_tree.join("root_b"))
    base_args = ["--continue-on-failure", "-p", root_b]

    # All fail.
    command_args = base_args + ["does-not-exist"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code != 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "dep_z (1/4)",
            "Finished: dep_z in *s",
            "deps: error: Command failed (project: dep_z)",
            "dep_b.1.1 (2/4)",
            "Finished: dep_b.1.1 in *s",
            "deps: error: Command failed (project: dep_b.1.1)",
            "dep_b.1 (3/4)",
            "Finished: dep_b.1 in *s",
            "deps: error: Command failed (project: dep_b.1)",
            "root_b (4/4)",
            "Finished: root_b in *s",
            "deps: error: Command failed (project: root_b)",
            # Final report.
            "deps: error: Command failed (project: dep_z)",
            "deps: error: Command failed (project: dep_b.1.1)",
            "deps: error: Command failed (project: dep_b.1)",
            "deps: error: Command failed (project: root_b)",
            "Total time: *s",
        ]
    )

    # Some fail.
    if sys.platform.startswith("win"):
        dir_or_ls = "dir"
    else:
        dir_or_ls = "ls"
    command_args = base_args + [dir_or_ls, os.path.join("tasks", "asd.py")]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code != 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "dep_z (1/4)",
            "Finished: dep_z in *s",
            "dep_b.1.1 (2/4)",
            "Finished: dep_b.1.1 in *s",
            "deps: error: Command failed (project: dep_b.1.1)",
            "dep_b.1 (3/4)",
            "Finished: dep_b.1 in *s",
            "deps: error: Command failed (project: dep_b.1)",
            "root_b (4/4)",
            "Finished: root_b in *s",
            # Final report.
            "deps: error: A list of all errors follow:",
            "deps: error: Command failed (project: dep_b.1.1)",
            "deps: error: Command failed (project: dep_b.1)",
            "Total time: *s",
        ]
    )

    # None fail.
    command_args = base_args + ["echo", "This", "is", "{name}"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    assert "deps: error: Command failed" not in result.output


def test_list_repos(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root = str(project_tree.join("root_c"))
    base_args = ["-p", root, "--repos"]

    command_args = base_args
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "*[\\/]test_projects0[\\/]cs2",
            "*[\\/]test_projects0[\\/]cs1",
            "*[\\/]test_projects0[\\/]root_c",
        ]
    )

    base_args = ["-p", root, "--repos"]
    # Test pretty print.
    command_args = base_args + ["-pp"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "*[\\/]test_projects0[\\/]root_c",
            "    *[\\/]test_projects0[\\/]cs1",
            "        (*[\\/]test_projects0[\\/]cs1)",
            "        *[\\/]test_projects0[\\/]cs2",
            "            (*[\\/]test_projects0[\\/]cs1)",
        ]
    )


def test_list_repos_with_ignored_project(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root = str(project_tree.join("root_c"))
    base_args = ["-p", root, "--repos"]

    # Test pretty print.
    command_args = base_args + ["--ignore-project=dep_c1.3", "-pp"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "*[\\/]test_projects0[\\/]root_c",
            "    *[\\/]test_projects0[\\/]cs1",
            "        (*[\\/]test_projects0[\\/]cs1)",
        ]
    )

    # Test pretty print.
    command_args = base_args + ["--ignore-project=dep_c2.1", "-pp"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "*[\\/]test_projects0[\\/]root_c",
            "    *[\\/]test_projects0[\\/]cs1",
            "        (*[\\/]test_projects0[\\/]cs1)",
            "        <*[\\/]test_projects0[\\/]cs2>",
        ]
    )


def test_list_repos_with_skipped_project(cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root = str(project_tree.join("root_c"))
    base_args = ["-p", root, "--repos"]

    # Test pretty print.
    command_args = base_args + ["--skip-project=dep_c1.3", "-pp"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "*[\\/]test_projects0[\\/]root_c",
            "    *[\\/]test_projects0[\\/]cs1",
            "        (*[\\/]test_projects0[\\/]cs1)",
            "        *[\\/]test_projects0[\\/]cs2",
            "            (*[\\/]test_projects0[\\/]cs1)",
        ]
    )

    # Test pretty print.
    command_args = base_args + ["--skip-project=dep_c2.1", "-pp"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "*[\\/]test_projects0[\\/]root_c",
            "    *[\\/]test_projects0[\\/]cs1",
            "        (*[\\/]test_projects0[\\/]cs1)",
            "        {*[\\/]test_projects0[\\/]cs2}",
            "            (*[\\/]test_projects0[\\/]cs1)",
        ]
    )


def test_list_repos_conflict_skipped_ignored_project(
    cli_runner, project_tree, piped_shell_execute
):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root = str(project_tree.join("root_c"))
    base_args = ["-p", root, "--repos"]

    # Test pretty print.
    command_args = base_args + [
        "--skip-project=dep_c1.3",
        "--ignore-project=dep_c1.3",
        "-pp",
    ]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "*[\\/]test_projects0[\\/]root_c",
            "    *[\\/]test_projects0[\\/]cs1",
            "        (*[\\/]test_projects0[\\/]cs1)",
        ]
    )

    # Test pretty print.
    command_args = base_args + [
        "--skip-project=dep_c2.1",
        "--ignore-project=dep_c2.1",
        "-pp",
    ]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "*[\\/]test_projects0[\\/]root_c",
            "    *[\\/]test_projects0[\\/]cs1",
            "        (*[\\/]test_projects0[\\/]cs1)",
            "        <*[\\/]test_projects0[\\/]cs2>",
        ]
    )


@pytest.mark.parametrize("mode", ["normal", "skipped"])
def test_list_repos_precedence(mode, cli_runner, project_tree, piped_shell_execute):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    root = str(project_tree.join("root_d"))
    base_args = ["-p", root, "--repos"]

    command_args = base_args + ["-pp", "--ignore-project=d1", "--ignore-project=d2"]
    if mode == "skipped":
        command_args.append("--skip-project=d3")
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    if mode == "skipped":
        matcher.fnmatch_lines(
            [
                "*[\\/]test_projects0[\\/]root_d",
                "    {*[\\/]test_projects0[\\/]d}",
            ]
        )
    else:
        assert mode == "normal"
        matcher.fnmatch_lines(
            [
                "*[\\/]test_projects0[\\/]root_d",
                "    *[\\/]test_projects0[\\/]d",
            ]
        )


def test_deps_parallel_unordered(cli_runner, project_tree, monkeypatch):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    monkeypatch.chdir(project_tree.join("root_b"))
    command_args = [
        "--jobs=2",
        "--jobs-unordered",
        "--",
        "python",
        "-c",
        '"name: {name}"',
    ]

    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines_random(
        [
            "=======================================================================================================================",
            "dep_z, dep_b.1.1, dep_b.1, root_b (4/4)",
            "Finished: dep_z in *",
            "Finished: dep_b.1.1 in *",
            "Finished: root_b in *",
            "Finished: dep_b.1 in *",
        ]
    )


def test_deps_parallel_unordered_error(
    cli_runner, project_tree, monkeypatch, piped_shell_execute
):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    task_script = os.path.join("tasks", "does-not-exist")

    monkeypatch.chdir(project_tree.join("root_b"))
    command_args = ["-v", "--jobs=2", "--jobs-unordered", task_script]

    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code != 0
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines_random(
        [
            "dep_z, dep_b.1.1, dep_b.1, root_b (4/4)",
            # We know that this will fail (it'll be the first). Others may fail or may be cancelled, we
            # can't guarantee.
            "deps: error: Command failed (project: dep_z)",
        ]
    )


def test_deps_parallel(cli_runner, project_tree, monkeypatch):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    monkeypatch.chdir(project_tree.join("root_b"))
    command_args = ["--jobs=2", "--", "python", "-c", '"name: {name}"']

    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines_random(
        [
            "=======================================================================================================================",
            "dep_z (1/4)",
            "Finished: dep_z in *",
            "=======================================================================================================================",
            "dep_b.1.1 (2/4)",
            "Finished: dep_b.1.1 in *",
            "=======================================================================================================================",
            "dep_b.1 (3/4)",
            "Finished: dep_b.1 in *",
            "=======================================================================================================================",
            "root_b (4/4)",
            "Finished: root_b in *",
        ]
    )


def test_deps_parallel_2(cli_runner, project_tree, monkeypatch):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    monkeypatch.chdir(project_tree.join("root_a"))
    command_args = ["--jobs=2", "--", "python", "-c", '"name: {name}"']

    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines_random(
        [
            "=======================================================================================================================",
            "dep_z (1/6)",
            "Finished: dep_z in *",
            "=======================================================================================================================",
            "dep_a.2, dep_a.1.1, dep_a.1.2 (4/6)",
            "Finished: dep_a.2 in *",
            "Finished: dep_a.1.1 in *",
            "Finished: dep_a.1.2 in *",
            "=======================================================================================================================",
            "dep_a.1 (5/6)",
            "Finished: dep_a.1 in *",
            "=======================================================================================================================",
            "root_a (6/6)",
            "Finished: root_a in *",
        ]
    )


def test_deps_parallel_3(cli_runner, project_tree, monkeypatch):
    """
    :type cli_runner: click.testing.CliRunner
    :type project_tree: py.path.local
    :type piped_shell_execute: mocker.patch
    """
    monkeypatch.chdir(project_tree.join("root_a"))
    command_args = ["--jobs=2", "--", "python", "-c", 'import sys;print("foo")']

    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    assert result.output.count("=== STDOUT ===") == 6
    assert result.output.count("foo") == 6


def test_no_expected_env_file(cli_runner, tmpdir_factory, piped_shell_execute):
    test_projects = tmpdir_factory.mktemp("test_projects")
    projects = {
        "expected_env_file": (
            "environment.devenv.yml",
            ["../unexpected_env_file/foo_environment.devenv.yml"],
        ),
        "unexpected_env_file": ("foo_environment.devenv.yml", []),
    }
    for proj, (env_filename, deps) in projects.items():
        proj_path = proj.split("/")
        proj_dir = test_projects.ensure(*proj_path, dir=True)
        env_yml = proj_dir.join(env_filename)
        env_content = ["name: {}".format(proj), ""]
        if len(deps) > 0:
            env_content.append("includes:")
            env_content.extend(["  - {{{{ root }}}}/{}".format(dep) for dep in deps])
            env_content.append("")
        env_yml.write("\n".join(env_content))

    root = str(test_projects.join("expected_env_file"))
    # Prepare the invocation.
    command_args = ["-p", root, "echo", "test", "{name}"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output

    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "unexpected_env_file (1/2)",
            "test unexpected_env_file",
            "expected_env_file (2/2)",
            "test expected_env_file",
        ]
    )


def test_empty_environment(cli_runner, tmpdir_factory, piped_shell_execute):
    test_project = tmpdir_factory.mktemp("test_empty_environment")
    proj_dir = test_project.ensure("project_with_empty_environment", dir=True)
    env_yml = proj_dir.join("environment.devenv.yml")
    env_yml.write("")

    root = str(proj_dir)
    command_args = ["-p", root, "echo", "test", "{name}"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output

    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "project_with_empty_environment (1/1)",
        ]
    )


def test_empty_includes(cli_runner, tmpdir_factory, piped_shell_execute):
    test_project = tmpdir_factory.mktemp("test_empty_includes")
    proj_dir = test_project.ensure("project_with_empty_includes", dir=True)
    env_yml = proj_dir.join("environment.devenv.yml")
    env_yml.write("includes:")

    root = str(proj_dir)
    command_args = ["-p", root, "echo", "test", "{name}"]
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output

    matcher = LineMatcher(result.output.splitlines())
    matcher.fnmatch_lines(
        [
            "project_with_empty_includes (1/1)",
        ]
    )


def test_work_dir(cli_runner, project_tree, monkeypatch, capfd):
    # Use Python to get the work directory and just write a file to it (contents do not matter).
    command_args = [
        "--",
        "python",
        "-c",
        "import os;"
        "from pathlib import Path;"
        "d=Path(os.environ['DEPS_WORK_DIR']);"
        "print(d);"
        "d.joinpath('foo').write_text('hello')",
    ]
    monkeypatch.chdir(project_tree.join("root_b"))
    result = cli_runner.invoke(deps_cli.cli, command_args)
    assert result.exit_code == 0, result.output
    lines = [x.strip() for x in capfd.readouterr().out.splitlines()]
    # Ensure each project printed the work directory, and ensure they all used the same one.
    assert len(lines) == 4
    assert len(set(lines)) == 1
    # Ensure the work directory no longer exists at this point.
    assert not Path(lines[0]).is_dir()
