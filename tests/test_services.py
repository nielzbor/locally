"""Tests unitaires pour la couche service de pipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from locally.models import ReleveBancaire
from locally.services.pipeline import (
    categorize_statement_service,
    enrich_statement_service,
    extract_statement_service,
)


def test_extract_statement_service_file_not_found(tmp_path: Path) -> None:
    """Vérifie que l'extraction lève FileNotFoundError si le PDF est inexistant.

    Args:
        tmp_path: Répertoire temporaire pytest.
    """
    non_existent = tmp_path / "absent_2025-08-08.pdf"
    with pytest.raises(FileNotFoundError):
        extract_statement_service(non_existent)


@patch("locally.services.pipeline.extract_pdf_to_dataframe")
def test_extract_statement_service_success(
    mock_extract: MagicMock,
    tmp_path: Path,
) -> None:
    """Vérifie le fonctionnement nominal du service d'extraction.

    Args:
        mock_extract: Mock de la fonction de parsing PDF.
        tmp_path: Répertoire temporaire pytest.
    """
    fake_pdf = tmp_path / "RLV_2025-08-08.pdf"
    fake_pdf.write_text("fake pdf")

    raw_df = pd.DataFrame(
        [
            {
                "date": "08.08",
                "valeur": "08.08",
                "operation": "PAIEMENT CB 0708 TEST",
                "debit": "10,50",
                "credit": "",
            }
        ]
    )
    summary = {
        "solde_initial": "100,00",
        "total_debit": "10,50",
        "total_credit": "0,00",
        "solde_final": "89,50",
    }
    mock_extract.return_value = (raw_df, summary)

    df, _out_summary, saved_path = extract_statement_service(
        fake_pdf,
        output_dir=tmp_path,
        save_interim=True,
    )

    assert len(df) == 1
    assert df["debit"].iloc[0] == 10.5
    assert df.attrs["statement_date"] == "2025-08-08"
    assert saved_path is not None
    assert (tmp_path / "releve_de_compte_bnp_tmp_dt=2025-08-08.parquet").exists()


def test_enrich_statement_service_success(tmp_path: Path) -> None:
    """Vérifie que le service d'enrichissement calcule les features et valide le ReleveBancaire.

    Args:
        tmp_path: Répertoire temporaire pytest.
    """
    df = pd.DataFrame(
        [
            {
                "date": pd.to_datetime("2025-08-08"),
                "valeur": pd.to_datetime("2025-08-08"),
                "nature": "PAIEMENT PAR CARTE DU 070825 MONOPRIX PARIS",
                "debit": 25.0,
                "credit": None,
                "page_number": 1,
            }
        ]
    )
    df.attrs = {
        "original_filename": "test.pdf",
        "statement_date": "2025-08-08",
        "solde_initial": 100.0,
        "total_debit": 25.0,
        "total_credit": 0.0,
        "solde_final": 75.0,
    }

    _df_clean, releve, _saved_path = enrich_statement_service(
        df,
        output_dir=tmp_path,
        save_interim=True,
    )

    assert isinstance(releve, ReleveBancaire)
    assert releve.solde_final == 75.0
    assert len(releve.transactions) == 1
    assert (tmp_path / "releve_de_compte_bnp_enriched_dt=2025-08-08.parquet").exists()


@patch("locally.services.pipeline.assign_txs_labels_with_llm")
def test_categorize_statement_service(
    mock_assign: MagicMock,
    tmp_path: Path,
) -> None:
    """Vérifie le bon fonctionnement du service de catégorisation.

    Args:
        mock_assign: Mock de l'appel LLM.
        tmp_path: Répertoire temporaire pytest.
    """
    df_clean = pd.DataFrame(
        [{"operation": "CARTE TEST", "debit": 10.0, "credit": None}]
    )
    mock_releve = MagicMock(spec=ReleveBancaire)
    mock_releve.statement_date = "2025-08-08"

    df_expected = df_clean.copy()
    df_expected["marchand"] = "TEST"
    df_expected["categorie"] = "Alimentation"
    mock_assign.return_value = df_expected

    df_cat, _saved_path = categorize_statement_service(
        df_clean,
        mock_releve,
        output_dir=tmp_path,
        client=MagicMock(),
        save_processed=True,
    )

    assert "marchand" in df_cat.columns
    assert (tmp_path / "releve_de_compte_bnp_cat_dt=2025-08-08.parquet").exists()
