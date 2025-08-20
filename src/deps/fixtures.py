from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner
from pytest_mock import MockerFixture


@pytest.yield_fixture
def cli_runner() -> Iterator[CliRunner]:
    """
    Fixture used to test click applications.
    :rtype: click.testing.CliRunner
    """
    yield CliRunner()


@pytest.fixture
def piped_shell_execute(mocker: MockerFixture) -> None:
    import click
    import subprocess

    def _piped_shell_execute(
        command: str, cwd: str | Path, buffer_output: bool = False
    ) -> Any:
        # This version always makes the pipe regardless of the buffer_output value and always
        # redirects everything for stdout.
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            text=True,
            cwd=cwd,
        )
        stdout, stderr = process.communicate()
        click.secho(stdout)
        return process, stdout, stderr, 0

    mocker.patch(
        "deps.deps_cli.shell_execute",
        new=_piped_shell_execute,
    )
