"""Point d'entrée exécutable du projet déléguant à la CLI Typer."""

from locally.cli import app


def main() -> None:
    """Point d'entrée principal invoquant l'application Typer.

    Returns:
        None.
    """
    app()


if __name__ == "__main__":
    main()
