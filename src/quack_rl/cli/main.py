import typer

from quack_rl import __version__

app = typer.Typer(no_args_is_help=True, help="Quack RL: play, simulate, replay and verify games.")


@app.callback()
def main() -> None:
    """Quack RL command line."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)
