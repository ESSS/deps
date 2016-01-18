from __future__ import unicode_literals
from click.testing import CliRunner
import pytest


@pytest.fixture
def cli_runner():
    """
    Fixture used to test click applications.
    :rtype: click.testing.CliRunner
    """
    return CliRunner()

