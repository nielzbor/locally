"""Tests unitaires de l'interface en ligne de commande (Typer)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
from typer.testing import CliRunner

from locally.cli import app
from locally.models import ReleveBancaire

runner = CliRunner()


def test_cli_help() -> None:
    """Vérifie que l'aide principale de la CLI s'affiche correctement."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "locally" in result.stdout
    assert "extract" in result.stdout
    assert "enrich" in result.stdout
    assert "categorize" in result.stdout
    assert "process" in result.stdout


def test_cli_extract_no_args() -> None:
    """Vérifie qu'extract échoue proprement sans arguments."""
    result = runner.invoke(app, ["extract"])
    assert result.exit_code == 1
    assert "Veuillez spécifier un fichier" in result.stdout


def test_cli_process_no_args() -> None:
    """Vérifie que process échoue proprement sans arguments."""
    result = runner.invoke(app, ["process"])
    assert result.exit_code == 1
    assert "Veuillez spécifier un fichier" in result.stdout


@patch("locally.cli.process_statement_service")
def test_cli_process_file_skip_llm(mock_process: MagicMock, tmp_path: Path) -> None:
    """Vérifie l'exécution de la commande process avec l'option --skip-llm.

    Args:
        mock_process: Mock de la fonction process_statement_service.
        tmp_path: Répertoire temporaire pytest.
    """
    dummy_pdf = tmp_path / "dummy_2025-08-08.pdf"
    dummy_pdf.write_text("PDF content")

    mock_df = pd.DataFrame([{"operation": "TEST", "debit": 10.0}])
    mock_releve = MagicMock(spec=ReleveBancaire)
    mock_process.return_value = (mock_df, mock_releve)

    result = runner.invoke(app, ["process", "-f", str(dummy_pdf), "--skip-llm"])

    assert result.exit_code == 0
    assert "Traitement terminé avec succès" in result.stdout
    mock_process.assert_called_once_with(dummy_pdf, skip_llm=True)


@patch("locally.cli.extract_statement_service")
def test_cli_extract_file(mock_extract: MagicMock, tmp_path: Path) -> None:
    """Vérifie l'exécution de la commande extract avec un fichier valide.

    Args:
        mock_extract: Mock de la fonction extract_statement_service.
        tmp_path: Répertoire temporaire pytest.
    """
    dummy_pdf = tmp_path / "dummy_2025-08-08.pdf"
    dummy_pdf.write_text("PDF content")

    mock_df = pd.DataFrame([{"date": "2025-08-01", "debit": 15.0}])
    mock_extract.return_value = (mock_df, {}, tmp_path / "interim_dummy")

    result = runner.invoke(app, ["extract", "-f", str(dummy_pdf)])

    assert result.exit_code == 0
    assert "Extraction réussie" in result.stdout
    mock_extract.assert_called_once_with(dummy_pdf, output_dir=None, save_interim=True)
