from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from locally.models import (
    BatchCategorisation,
    CategorieDepense,
    ReleveBancaire,
    TransactionCategorisee,
    TransactionExtraite,
)
from locally.processors.llm_processors import assign_txs_labels_with_llm


@pytest.fixture
def sample_releve_and_df():
    """Génère un DataFrame et un ReleveBancaire de 3 transactions pour les tests."""
    df = pd.DataFrame(
        [
            {
                "nature": "DU 050625 CARREFOUR MARKET PARIS",
                "raw_merchant_text": "CARREFOUR MARKET PARIS",
                "debit": 45.50,
                "credit": None,
                "tx_type": "CARTE",
            },
            {
                "nature": "PRLV SEPA NETFLIX",
                "raw_merchant_text": "NETFLIX",
                "debit": 17.99,
                "credit": None,
                "tx_type": "PRELEVEMENT",
            },
            {
                "nature": "VIR SEPA RECU SALAIRE EMPLOYEUR",
                "raw_merchant_text": "SALAIRE EMPLOYEUR",
                "debit": None,
                "credit": 2500.00,
                "tx_type": "VIREMENT",
            },
        ]
    )

    transactions = [
        TransactionExtraite(
            date=datetime(2025, 6, 5),
            valeur=datetime(2025, 6, 6),
            page_number=1,
            tx_type="CARTE",
            raw_merchant_text="CARREFOUR MARKET PARIS",
            debit=45.50,
            credit=None,
        ),
        TransactionExtraite(
            date=datetime(2025, 6, 10),
            valeur=datetime(2025, 6, 11),
            page_number=1,
            tx_type="PRELEVEMENT",
            raw_merchant_text="NETFLIX",
            debit=17.99,
            credit=None,
        ),
        TransactionExtraite(
            date=datetime(2025, 6, 28),
            valeur=datetime(2025, 6, 28),
            page_number=1,
            tx_type="VIREMENT",
            raw_merchant_text="SALAIRE EMPLOYEUR",
            debit=None,
            credit=2500.00,
        ),
    ]

    releve = ReleveBancaire(
        filename="releve_juin_2025.pdf",
        statement_date="2025-06-30",
        solde_initial=1000.00,
        total_debit=63.49,
        total_credit=2500.00,
        solde_final=3436.51,
        transactions=transactions,
    )

    return df, releve


def test_assign_txs_labels_with_llm_success(sample_releve_and_df):
    """Teste la catégorisation complète avec un mock retournant les catégories attendues."""
    df, releve = sample_releve_and_df

    # Création de la réponse simulée du LLM (Instructor)
    mock_batch_response = BatchCategorisation(
        transactions=[
            TransactionCategorisee(
                id=0,
                marchand_clean="Carrefour Market",
                categorie=CategorieDepense.ALIMENTATION,
            ),
            TransactionCategorisee(
                id=1,
                marchand_clean="Netflix",
                categorie=CategorieDepense.ABONNEMENT,
            ),
            TransactionCategorisee(
                id=2,
                marchand_clean="Employeur",
                categorie=CategorieDepense.REVENU,
            ),
        ]
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_batch_response

    # Exécution de la fonction
    result_df = assign_txs_labels_with_llm(
        df=df,
        releve_complet=releve,
        client=mock_client,
        batch_size=10,
    )

    # Vérifications
    assert mock_client.chat.completions.create.call_count == 1
    assert result_df.loc[0, "marchand_clean"] == "Carrefour Market"
    assert result_df.loc[0, "categorie"] == CategorieDepense.ALIMENTATION.value
    assert result_df.loc[1, "marchand_clean"] == "Netflix"
    assert result_df.loc[1, "categorie"] == CategorieDepense.ABONNEMENT.value
    assert result_df.loc[2, "marchand_clean"] == "Employeur"
    assert result_df.loc[2, "categorie"] == CategorieDepense.REVENU.value


def test_assign_txs_labels_with_llm_batching(sample_releve_and_df):
    """Teste le découpage en plusieurs batches (batch_size=2 pour 3 transactions)."""
    df, releve = sample_releve_and_df

    # Réponses pour le batch 1 (id 0 et 1) puis le batch 2 (id 2)
    batch_1 = BatchCategorisation(
        transactions=[
            TransactionCategorisee(
                id=0,
                marchand_clean="Carrefour",
                categorie=CategorieDepense.ALIMENTATION,
            ),
            TransactionCategorisee(
                id=1,
                marchand_clean="Netflix",
                categorie=CategorieDepense.ABONNEMENT,
            ),
        ]
    )
    batch_2 = BatchCategorisation(
        transactions=[
            TransactionCategorisee(
                id=2,
                marchand_clean="Salaire",
                categorie=CategorieDepense.REVENU,
            ),
        ]
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [batch_1, batch_2]

    result_df = assign_txs_labels_with_llm(
        df=df,
        releve_complet=releve,
        client=mock_client,
        batch_size=2,
    )

    assert mock_client.chat.completions.create.call_count == 2
    assert result_df.loc[0, "marchand_clean"] == "Carrefour"
    assert result_df.loc[2, "marchand_clean"] == "Salaire"


def test_assign_txs_labels_with_llm_error_handling(sample_releve_and_df):
    """Vérifie qu'en cas d'erreur de l'API LLM, l'application ne crashe pas et conserve le DataFrame."""
    df, releve = sample_releve_and_df

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError(
        "Ollama connection timeout"
    )

    result_df = assign_txs_labels_with_llm(
        df=df,
        releve_complet=releve,
        client=mock_client,
        batch_size=5,
    )

    # Le DataFrame retourné doit contenir les colonnes avec des valeurs None sans lever d'exception
    assert "categorie" in result_df.columns
    assert "marchand_clean" in result_df.columns
    assert result_df["categorie"].isna().all()
    assert result_df["marchand_clean"].isna().all()
