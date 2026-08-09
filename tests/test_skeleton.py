from typer.testing import CliRunner

from cykelombord.cli import app


def test_cli_displays_help() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "bicycle-friendly public transport" in result.output
