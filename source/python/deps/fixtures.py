import pytest
from click.testing import CliRunner


@pytest.yield_fixture
def cli_runner():
    """
    Fixture used to test click applications.
    :rtype: click.testing.CliRunner
    """
    yield CliRunner()


@pytest.fixture
def piped_shell_execute(mocker):
    import click
    import subprocess

    def _piped_shell_execute(command, cwd, buffer_output=False):
        # This version always makes the pipe regardless of the buffer_output value and always
        # redirects everything for stdout.
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, cwd=cwd)
        stdout, stderr = process.communicate()
        stdout = stdout.decode()
        click.secho(stdout)
        return process, stdout, stderr, 0
    shell_execute = mocker.patch(
        'deps.deps_cli.shell_execute',
        new=_piped_shell_execute,
    )
    return shell_execute
