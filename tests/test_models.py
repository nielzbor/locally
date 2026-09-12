from datetime import datetime

import pytest
from pydantic import ValidationError

from locally.models import ReleveBancaire, TransactionExtraite


@pytest.mark.parametrize(
    "debit, credit, is_valid, expected_error_msg",
    [
        # --- Cas valides : soit débit, soit crédit ---
        (50.0, None, True, None),
        (None, 1500.0, True, None),
        (0.0, None, True, None),
        (None, 0.0, True, None),
        (12.34, None, True, None),
        (None, 99.99, True, None),
        # --- Cas invalides : débit ET crédit simultanément ---
        (
            50.0,
            100.0,
            False,
            "Une transaction ne peut pas contenir à la fois un débit et un crédit.",
        ),
        (
            0.0,
            0.0,
            False,
            "Une transaction ne peut pas contenir à la fois un débit et un crédit.",
        ),
        # --- Cas invalides : ni débit ni crédit (les deux à None) ---
        (
            None,
            None,
            False,
            "Une transaction doit avoir soit un débit soit un crédit.",
        ),
        # --- Cas invalides : montants négatifs (contrainte ge=0.0 de Field) ---
        (
            -10.0,
            None,
            False,
            "greater than or equal to 0",
        ),
        (
            None,
            -25.5,
            False,
            "greater than or equal to 0",
        ),
    ],
)
def test_transaction_extraite_debit_credit_exclusivity(
    debit: float | None,
    credit: float | None,
    is_valid: bool,
    expected_error_msg: str | None,
):
    """Teste l'exclusivité stricte entre débit et crédit sur TransactionExtraite."""
    base_data = {
        "date": datetime(2025, 6, 5),
        "valeur": datetime(2025, 6, 6),
        "carte_date_reelle": None,
        "page_number": 1,
        "tx_type": "CARTE",
        "sepa_emetteur": None,
        "sepa_mandat": None,
        "sepa_reference": None,
        "motif": None,
        "raw_merchant_text": "CARREFOUR MARKET",
        "debit": debit,
        "credit": credit,
    }

    if is_valid:
        tx = TransactionExtraite(**base_data)
        assert tx.debit == debit
        assert tx.credit == credit
    else:
        with pytest.raises(ValidationError) as exc_info:
            TransactionExtraite(**base_data)
        if expected_error_msg:
            assert expected_error_msg in str(exc_info.value)


# ==============================================================================
# Helpers & Fixtures pour ReleveBancaire
# ==============================================================================
def _make_tx(
    debit: float | None = None, credit: float | None = None
) -> TransactionExtraite:
    return TransactionExtraite(
        date=datetime(2025, 6, 5),
        valeur=datetime(2025, 6, 6),
        carte_date_reelle=None,
        page_number=1,
        tx_type="CARTE" if debit else "VIREMENT",
        sepa_emetteur=None,
        sepa_mandat=None,
        sepa_reference=None,
        motif=None,
        raw_merchant_text="TEST TRANSACTION",
        debit=debit,
        credit=credit,
    )


# ==============================================================================
# Tests pour la réconciliation mathématique globale : Solde Initial + Crédits - Débits == Solde Final
# ==============================================================================
@pytest.mark.parametrize(
    "solde_initial, total_credit, total_debit, solde_final, is_valid, expected_err",
    [
        # --- Cas nominaux valides ---
        (1000.0, 500.0, 300.0, 1200.0, True, None),
        (0.0, 100.0, 100.0, 0.0, True, None),
        (500.0, 0.0, 700.0, -200.0, True, None),  # Solde final débiteur négatif
        (1000.55, 200.40, 100.25, 1100.70, True, None),
        # --- Incohérences de calcul ---
        (
            1000.0,
            500.0,
            300.0,
            1500.0,
            False,
            "Incohérence des soldes",
        ),
        (
            100.0,
            50.0,
            20.0,
            129.0,  # 1 centime d'écart au-delà de la tolérance
            False,
            "Incohérence des soldes",
        ),
        # --- Valeurs partielles / None : pas de blocage si des champs sont absents ---
        (1000.0, None, 300.0, None, True, None),
        (None, None, None, None, True, None),
    ],
)
def test_releve_bancaire_soldes_reconciliation(
    solde_initial: float | None,
    total_credit: float | None,
    total_debit: float | None,
    solde_final: float | None,
    is_valid: bool,
    expected_err: str | None,
):
    """Vérifie la formule : solde_initial + total_credit - total_debit = solde_final."""
    data = {
        "filename": "releve_juin_2025.pdf",
        "statement_date": "2025-06-30",
        "solde_initial": solde_initial,
        "total_credit": total_credit,
        "total_debit": total_debit,
        "solde_final": solde_final,
        "transactions": [],
    }

    if is_valid:
        releve = ReleveBancaire(**data)
        assert releve.solde_final == solde_final
    else:
        with pytest.raises(ValidationError) as exc_info:
            ReleveBancaire(**data)
        if expected_err:
            assert expected_err in str(exc_info.value)


# ==============================================================================
# Tests pour la cohérence de la somme des transactions individuelles
# ==============================================================================
@pytest.mark.parametrize(
    "tx_amounts, declared_debit, declared_credit, is_valid, expected_err",
    [
        # --- Cas valides : somme exacte ---
        (
            [{"debit": 50.0}, {"debit": 150.0}, {"credit": 500.0}],
            200.0,
            500.0,
            True,
            None,
        ),
        (
            [{"debit": 12.34}, {"debit": 56.78}, {"credit": 100.0}],
            69.12,
            100.0,
            True,
            None,
        ),
        # Liste vide de transactions avec totaux None
        ([], None, None, True, None),
        # --- Incohérence somme des débits ---
        (
            [{"debit": 50.0}, {"debit": 50.0}],
            150.0,  # Déclaré 150 au lieu de 100
            None,
            False,
            "Incohérence de la somme des débits",
        ),
        # --- Incohérence somme des crédits ---
        (
            [{"credit": 200.0}, {"credit": 300.0}],
            None,
            600.0,  # Déclaré 600 au lieu de 500
            False,
            "Incohérence de la somme des crédits",
        ),
    ],
)
def test_releve_bancaire_transactions_sum_consistency(
    tx_amounts: list[dict],
    declared_debit: float | None,
    declared_credit: float | None,
    is_valid: bool,
    expected_err: str | None,
):
    """Vérifie que la somme des transactions correspond aux totaux déclarés."""
    transactions = [
        _make_tx(debit=item.get("debit"), credit=item.get("credit"))
        for item in tx_amounts
    ]

    # Calcul automatique du solde_final pour ne pas déclencher l'erreur de solde si valide
    initial = 1000.0
    final = (
        initial + (declared_credit or 0.0) - (declared_debit or 0.0)
        if (declared_credit is not None and declared_debit is not None)
        else None
    )

    data = {
        "filename": "releve_test.pdf",
        "statement_date": "2025-06-30",
        "solde_initial": initial if final is not None else None,
        "total_credit": declared_credit,
        "total_debit": declared_debit,
        "solde_final": final,
        "transactions": transactions,
    }

    if is_valid:
        releve = ReleveBancaire(**data)
        assert len(releve.transactions) == len(transactions)
    else:
        with pytest.raises(ValidationError) as exc_info:
            ReleveBancaire(**data)
        if expected_err:
            assert expected_err in str(exc_info.value)
