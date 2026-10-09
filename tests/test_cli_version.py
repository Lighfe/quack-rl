from typer.testing import CliRunner

from quack_rl import __version__
from quack_rl.cli.main import app


def test_version_command_prints_package_version():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
