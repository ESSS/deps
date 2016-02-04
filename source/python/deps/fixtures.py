from __future__ import unicode_literals
from click.testing import CliRunner
import pytest


@pytest.yield_fixture
def cli_runner():
    """
    Fixture used to test click applications.
    :rtype: click.testing.CliRunner
    """
    from click import utils
    original_auto_wrap_for_ansi = utils.auto_wrap_for_ansi
    yield CliRunner()
    utils.auto_wrap_for_ansi = original_auto_wrap_for_ansi


@pytest.fixture
def piped_shell_execute(mocker):
    import click
    import subprocess

    def _piped_shell_execute(command):
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
        stdout, stderr = process.communicate()
        click.secho(stdout)
        return process
    shell_execute = mocker.patch(
        'deps.deps_cli.shell_execute',
        new=_piped_shell_execute,
    )
    return shell_execute

