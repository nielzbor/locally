import numpy as np
import pandas as pd
import pytest

from locally.processors.feature_extraction import (
    _extract_carte_date,
    _get_tx_type,
    convert_to_timestamp,
    extract_nature_features,
    parse_french_amount,
)


@pytest.mark.parametrize(
    "input_val, expected",
    [
        # --- Cas nominaux : chaînes formatées à la française ---
        ("1 999,29", 1999.29),
        ("4 474,68", 4474.68),
        ("0,50", 0.5),
        ("100,00", 100.0),
        ("12,34", 12.34),
        # --- Espaces multiples et espaces insécables (\xa0) fréquents dans les PDF ---
        ("1\xa0999,29", 1999.29),
        ("  4 474,68  ", 4474.68),
        ("10  000,00", 10000.0),
        # --- Nombres déjà numériques (int, float) ---
        (100, 100.0),
        (42.5, 42.5),
        (0, 0.0),
        (0.0, 0.0),
        # --- Formats standards / anglophones avec point ---
        ("1999.29", 1999.29),
        # --- Cas limites / valeurs manquantes / None / NaN ---
        (None, None),
        ("", None),
        ("   ", None),
        (np.nan, None),
        (pd.NA, None),
        # --- Cas d'erreurs / entrées invalides ---
        ("invalid_text", None),
        ("12,34,56", None),
        ("abc123", None),
    ],
)
def test_parse_french_amount(input_val: str | float | None, expected: float | None):
    """Teste la conversion des montants au format français vers des float."""
    result = parse_french_amount(input_val)

    if expected is None:
        assert result is None
    else:
        assert isinstance(result, float)
        assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    "date_str, year, expected",
    [
        # --- Cas nominaux : formats DD.MM et années entières / chaînes ---
        ("05.06", 2025, pd.Timestamp("2025-06-05")),
        ("01.01", 2026, pd.Timestamp("2026-01-01")),
        ("31.12", 2024, pd.Timestamp("2024-12-31")),
        ("29.02", 2024, pd.Timestamp("2024-02-29")),  # Année bissextile
        ("15.08", "2025", pd.Timestamp("2025-08-15")),  # Année passée en str
        # --- Espaces autour de la chaîne ---
        (" 05.06 ", 2025, pd.Timestamp("2025-06-05")),
        ("  12.04  ", "2026", pd.Timestamp("2026-04-12")),
        # --- Formats incorrects / séparateurs non supportés ---
        ("05/06", 2025, None),
        ("05-06", 2025, None),
        ("5.6", 2025, None),
        ("05.06.2025", 2025, None),
        ("invalid", 2025, None),
        # --- Cas limites / valeurs manquantes / types invalides ---
        (None, 2025, None),
        ("", 2025, None),
        ("   ", 2025, None),
        (1234, 2025, None),
    ],
)
def test_convert_to_timestamp(
    date_str: str | None,
    year: int | str,
    expected: pd.Timestamp | None,
):
    """Teste la conversion d'une date DD.MM et d'une année en pd.Timestamp."""
    result = convert_to_timestamp(date_str, year)

    if expected is None:
        assert result is None
    else:
        assert isinstance(result, pd.Timestamp)
        assert result == expected


# ==============================================================================
# Tests pour _get_tx_type
# ==============================================================================
@pytest.mark.parametrize(
    "nature_text, expected_type",
    [
        # --- PRELEVEMENT ---
        ("PRLV SEPA NETFLIX", "PRELEVEMENT"),
        ("PRLV ASSURANCE HABITATION", "PRELEVEMENT"),
        ("prlv sepa spotify", "PRELEVEMENT"),
        ("FACTURE PRLV SEPA EDF", "PRELEVEMENT"),
        # --- CARTE ---
        ("DU 050625 CARREFOUR MARKET", "CARTE"),
        ("FACTURE(S) CARTE DU 120625 FNAC", "CARTE"),
        ("du 010125 uber eats", "CARTE"),
        # --- VIREMENT ---
        ("VIR SEPA RECU DE DUPONT", "VIREMENT"),
        ("VIREMENT EN VOTRE FAVEUR", "VIREMENT"),
        ("VIR EMIS VERS COMPTE EPARGNE", "VIREMENT"),
        # --- COMMISSION ---
        ("*COMMISSIONS COTISATION MENSUELLE", "COMMISSION"),
        ("*COMMISSIONS FRAIS DE TENUE DE COMPTE", "COMMISSION"),
        # --- RETROCESSION ---
        ("RETROCESSION COTISATION CB", "RETROCESSION"),
        # --- RETRAIT DAB ---
        ("RETRAIT DAB BNP PARIBAS PARIS 11", "RETRAIT_DAB"),
        ("retrait dab bnp", "RETRAIT_DAB"),
        # --- AUTRE / Inconnus ---
        ("CHEQUE N 1234567", "AUTRE"),
        ("REMISE DE CHEQUE", "AUTRE"),
        ("", "AUTRE"),
        (None, "AUTRE"),
    ],
)
def test_get_tx_type(nature_text: str | None, expected_type: str):
    """Teste la détection du type d'opération bancaire depuis le libellé brut."""
    assert _get_tx_type(nature_text) == expected_type


# ==============================================================================
# Tests pour _extract_carte_date
# ==============================================================================
@pytest.mark.parametrize(
    "row_data, expected_date",
    [
        # Cas nominal carte avec 'DU DDMMYY'
        (
            {"tx_type": "CARTE", "nature": "DU 050625 CB CARREFOUR MARKET"},
            pd.Timestamp("2025-06-05"),
        ),
        (
            {"tx_type": "CARTE", "nature": "FACTURE(S) CARTE DU 311224 MONOPRIX"},
            pd.Timestamp("2024-12-31"),
        ),
        # Minuscules
        (
            {"tx_type": "CARTE", "nature": "du 150825 boulangerie"},
            pd.Timestamp("2025-08-15"),
        ),
        # Type non CARTE : ne doit rien extraire même si 'DU DDMMYY' est présent
        (
            {"tx_type": "VIREMENT", "nature": "VIR DU 050625 DE MR DUPONT"},
            None,
        ),
        # CARTE mais sans motif DU valide
        (
            {"tx_type": "CARTE", "nature": "PAIEMENT CARTE SANS DATE"},
            None,
        ),
        (
            {"tx_type": "CARTE", "nature": "DU 50625 CARTE"},  # 5 chiffres au lieu de 6
            None,
        ),
        # Champs vides / None
        (
            {"tx_type": "CARTE", "nature": ""},
            None,
        ),
    ],
)
def test_extract_carte_date(row_data: dict, expected_date: pd.Timestamp | None):
    """Teste l'extraction de la date d'opération pour les paiements par carte."""
    row = pd.Series(row_data)
    result = _extract_carte_date(row)
    if expected_date is None:
        assert result is None
    else:
        assert isinstance(result, pd.Timestamp)
        assert result == expected_date


# ==============================================================================
# Tests pour extract_nature_features (Enrichissement global du DataFrame)
# ==============================================================================
@pytest.mark.parametrize(
    "nature_text, expected_features",
    [
        # 1. Prélèvement SEPA complet avec EMETTEUR, MDT, REF, et raw_merchant_text (LIB)
        (
            "PRLV SEPA EMETTEUR/FR78ZZZ123456/MDT/MANDAT001/REF/PAYPAL12345 LIB/1042735252803/PAYPAL /MOTIF ABONNEMENT MENSUEL",
            {
                "tx_type": "PRELEVEMENT",
                "carte_date_reelle": None,
                "sepa_emetteur": "FR78ZZZ123456",
                "sepa_mandat": "MANDAT001",
                "sepa_reference": "PAYPAL12345",
                "raw_merchant_text": "PAYPAL /MOTIF ABONNEMENT MENSUEL",
                "motif": "ABONNEMENT MENSUEL",
            },
        ),
        # 2. Virement avec émetteur /DE et sans LIB/REF (fallback sur nature)
        (
            "VIR SEPA RECU /DE DUPONT JEAN /MOTIF REMBOURSEMENT RESTO",
            {
                "tx_type": "VIREMENT",
                "carte_date_reelle": None,
                "sepa_emetteur": "DUPONT JEAN ",
                "sepa_mandat": None,
                "sepa_reference": None,
                "raw_merchant_text": "VIR SEPA RECU /DE DUPONT JEAN /MOTIF REMBOURSEMENT RESTO",
                "motif": "REMBOURSEMENT RESTO",
            },
        ),
        # 3. Paiement Carte avec date réelle et libellé marchand brut
        (
            "DU 050625 CB RESTAURANT LE BISTROT PARIS",
            {
                "tx_type": "CARTE",
                "carte_date_reelle": pd.Timestamp("2025-06-05"),
                "sepa_emetteur": None,
                "sepa_mandat": None,
                "sepa_reference": None,
                "raw_merchant_text": "DU 050625 CB RESTAURANT LE BISTROT PARIS",
                "motif": None,
            },
        ),
        # 4. Commission bancaire
        (
            "*COMMISSIONS COTISATION PACK FAMILLE",
            {
                "tx_type": "COMMISSION",
                "carte_date_reelle": None,
                "sepa_emetteur": None,
                "sepa_mandat": None,
                "sepa_reference": None,
                "raw_merchant_text": "*COMMISSIONS COTISATION PACK FAMILLE",
                "motif": None,
            },
        ),
    ],
)
def test_extract_nature_features(nature_text: str, expected_features: dict):
    """Teste la dérivation complète des features textuelles sur un DataFrame."""
    df_input = pd.DataFrame([{"nature": nature_text}])
    df_enriched = extract_nature_features(df_input)

    for col, expected_val in expected_features.items():
        actual_val = df_enriched.loc[0, col]
        if expected_val is None or pd.isna(expected_val):
            assert pd.isna(actual_val) or actual_val is None, (
                f"Échec pour la colonne '{col}': attendu None/NaN, obtenu '{actual_val}'"
            )
        else:
            assert actual_val == expected_val, (
                f"Échec pour la colonne '{col}': attendu '{expected_val}', obtenu '{actual_val}'"
            )
