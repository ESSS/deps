from __future__ import unicode_literals
from click.testing import CliRunner
import pytest


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

    def _piped_shell_execute(command):
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
        stdout, stderr = process.communicate()
        click.secho(stdout.decode('utf-8'))
        return process
    shell_execute = mocker.patch(
        'deps.deps_cli.shell_execute',
        new=_piped_shell_execute,
    )
    return shell_execute

