import pytest

from locally.parsers.bnp_parser import (
    _parse_summary_words,
    _split_words_by_totals,
)


# ==============================================================================
# Tests pour _split_words_by_totals
# ==============================================================================
def test_split_words_by_totals_full_page():
    """Teste la séparation entre transactions et résumés sur une page complète (Solde + Transactions + Total)."""
    words = [
        # En-tête / Solde initial en haut (Y: 100 à 110)
        {"text": "SOLDE", "top": 100, "bottom": 110, "x0": 50, "x1": 90},
        {"text": "CREDITEUR", "top": 100, "bottom": 110, "x0": 95, "x1": 150},
        {"text": "1 500,00", "top": 100, "bottom": 110, "x0": 450, "x1": 500},
        # Transactions au milieu (Y: 150 à 250)
        {"text": "05.06", "top": 150, "bottom": 160, "x0": 50, "x1": 80},
        {"text": "CARREFOUR", "top": 150, "bottom": 160, "x0": 100, "x1": 180},
        {"text": "45,00", "top": 150, "bottom": 160, "x0": 380, "x1": 420},
        {"text": "06.06", "top": 200, "bottom": 210, "x0": 50, "x1": 80},
        {"text": "RESTO", "top": 200, "bottom": 210, "x0": 100, "x1": 150},
        {"text": "25,00", "top": 200, "bottom": 210, "x0": 380, "x1": 420},
        # Ligne de totaux en bas (Y: 300 à 310)
        {"text": "TOTAL", "top": 300, "bottom": 310, "x0": 50, "x1": 90},
        {"text": "DES", "top": 300, "bottom": 310, "x0": 95, "x1": 120},
        {"text": "MOUVEMENTS", "top": 300, "bottom": 310, "x0": 125, "x1": 200},
        {"text": "70,00", "top": 300, "bottom": 310, "x0": 380, "x1": 420},
    ]

    tx_words, summary_words = _split_words_by_totals(words, y_margin_thresh=2)

    # Vérification des transactions (seulement celles entre Y=112 et Y=298)
    tx_texts = [w["text"] for w in tx_words]
    assert tx_texts == ["05.06", "CARREFOUR", "45,00", "06.06", "RESTO", "25,00"]

    # Vérification des résumés (Solde en haut + Total en bas)
    summary_texts = [w["text"] for w in summary_words]
    assert "SOLDE" in summary_texts
    assert "1 500,00" in summary_texts
    assert "TOTAL" in summary_texts
    assert "70,00" in summary_texts


def test_split_words_by_totals_single_page_statement():
    """Teste un relevé complet tenant sur une seule page :
    - Solde initial en haut (avant transactions)
    - Transactions au milieu
    - Ligne TOTAL des opérations en bas
    - Ligne SOLDE final sous le TOTAL
    """
    words = [
        # 1. Solde initial en haut (Y: 80 à 90)
        {"text": "SOLDE", "top": 80, "bottom": 90, "x0": 68, "x1": 100},
        {"text": "CREDITEUR", "top": 80, "bottom": 90, "x0": 105, "x1": 150},
        {"text": "AU", "top": 80, "bottom": 90, "x0": 155, "x1": 170},
        {"text": "01.07.2025", "top": 80, "bottom": 90, "x0": 175, "x1": 218},
        {"text": "2 000,00", "top": 80, "bottom": 90, "x0": 510, "x1": 545},
        # 2. Transactions (Y: 130 à 180)
        {"text": "05.07", "top": 130, "bottom": 140, "x0": 50, "x1": 80},
        {"text": "MONOPRIX", "top": 130, "bottom": 140, "x0": 100, "x1": 150},
        {"text": "50,00", "top": 130, "bottom": 140, "x0": 380, "x1": 420},
        {"text": "10.07", "top": 170, "bottom": 180, "x0": 50, "x1": 80},
        {"text": "SALAIRE", "top": 170, "bottom": 180, "x0": 100, "x1": 150},
        {"text": "1 500,00", "top": 170, "bottom": 180, "x0": 510, "x1": 550},
        # 3. Ligne TOTAL (Y: 280 à 285)
        {"text": "TOTAL", "top": 280, "bottom": 285, "x0": 68, "x1": 100},
        {"text": "DES", "top": 280, "bottom": 285, "x0": 105, "x1": 125},
        {"text": "OPERATIONS", "top": 280, "bottom": 285, "x0": 130, "x1": 182},
        {"text": "50,00", "top": 280, "bottom": 285, "x0": 410, "x1": 445},
        {"text": "1 500,00", "top": 280, "bottom": 285, "x0": 510, "x1": 545},
        # 4. Ligne SOLDE final sous le TOTAL (Y: 300 à 305)
        {"text": "SOLDE", "top": 300, "bottom": 305, "x0": 68, "x1": 100},
        {"text": "CREDITEUR", "top": 300, "bottom": 305, "x0": 105, "x1": 150},
        {"text": "AU", "top": 300, "bottom": 305, "x0": 155, "x1": 170},
        {"text": "31.07.2025", "top": 300, "bottom": 305, "x0": 175, "x1": 218},
        {"text": "3 450,00", "top": 300, "bottom": 305, "x0": 510, "x1": 545},
    ]

    tx_words, summary_words = _split_words_by_totals(words, y_margin_thresh=2)

    # Les transactions doivent exclure le solde initial ET tout ce qui est à partir du TOTAL
    assert [w["text"] for w in tx_words] == [
        "05.07",
        "MONOPRIX",
        "50,00",
        "10.07",
        "SALAIRE",
        "1 500,00",
    ]

    summary_texts = [w["text"] for w in summary_words]
    # Doit contenir les deux lignes SOLDE et la ligne TOTAL
    assert summary_texts.count("SOLDE") == 2
    assert "2 000,00" in summary_texts
    assert "TOTAL" in summary_texts
    assert "3 450,00" in summary_texts


def test_split_words_by_totals_last_page():
    """Teste la dernière page d'un relevé : pas de solde initial en haut, transactions, puis TOTAL et SOLDE final en bas."""
    words = [
        # Opérations en haut et au milieu de la page (sans solde initial au-dessus)
        {"text": "07.07", "top": 80, "bottom": 90, "x0": 50, "x1": 80},
        {"text": "MACIF", "top": 80, "bottom": 90, "x0": 100, "x1": 150},
        {"text": "21,07", "top": 80, "bottom": 90, "x0": 380, "x1": 420},
        {"text": "08.07", "top": 120, "bottom": 130, "x0": 50, "x1": 80},
        {"text": "PAYPAL", "top": 120, "bottom": 130, "x0": 100, "x1": 150},
        {"text": "15,00", "top": 120, "bottom": 130, "x0": 380, "x1": 420},
        {"text": "08.07", "top": 160, "bottom": 170, "x0": 50, "x1": 80},
        {"text": "VIR", "top": 160, "bottom": 170, "x0": 100, "x1": 150},
        {"text": "400,00", "top": 160, "bottom": 170, "x0": 380, "x1": 420},
        # Ligne de TOTAL des opérations (Y: 285)
        {"text": "TOTAL", "top": 285, "bottom": 286, "x0": 68, "x1": 100},
        {"text": "DES", "top": 285, "bottom": 286, "x0": 105, "x1": 125},
        {"text": "OPERATIONS", "top": 285, "bottom": 286, "x0": 130, "x1": 182},
        {"text": "4 474,68", "top": 285, "bottom": 286, "x0": 410, "x1": 445},
        {"text": "4 010,64", "top": 285, "bottom": 286, "x0": 510, "x1": 545},
        # Ligne de SOLDE final sous le TOTAL (Y: 301)
        {"text": "SOLDE", "top": 301, "bottom": 302, "x0": 68, "x1": 100},
        {"text": "CREDITEUR", "top": 301, "bottom": 302, "x0": 105, "x1": 150},
        {"text": "AU", "top": 301, "bottom": 302, "x0": 155, "x1": 170},
        {"text": "08.07.2025", "top": 301, "bottom": 302, "x0": 175, "x1": 218},
        {"text": "1 999,29", "top": 301, "bottom": 302, "x0": 510, "x1": 545},
    ]

    tx_words, summary_words = _split_words_by_totals(words, y_margin_thresh=2)

    # Vérification que toutes les transactions au-dessus du TOTAL sont bien extraites
    tx_texts = [w["text"] for w in tx_words]
    assert tx_texts == [
        "07.07",
        "MACIF",
        "21,07",
        "08.07",
        "PAYPAL",
        "15,00",
        "08.07",
        "VIR",
        "400,00",
    ]

    # Vérification que le TOTAL et le SOLDE final sont tous les deux dans summary_words
    summary_texts = [w["text"] for w in summary_words]
    assert "TOTAL" in summary_texts
    assert "4 474,68" in summary_texts
    assert "SOLDE" in summary_texts
    assert "1 999,29" in summary_texts


def test_split_words_by_totals_first_page_without_totals():
    """Teste une première page typique : solde initial en haut, des transactions, mais pas de ligne TOTAL en bas."""
    words = [
        # Solde initial en haut
        {"text": "SOLDE", "top": 80, "bottom": 90, "x0": 68, "x1": 100},
        {"text": "CREDITEUR", "top": 80, "bottom": 90, "x0": 105, "x1": 150},
        {"text": "2 000,00", "top": 80, "bottom": 90, "x0": 510, "x1": 545},
        # Transactions
        {"text": "09.06", "top": 120, "bottom": 130, "x0": 50, "x1": 80},
        {"text": "ACHAT", "top": 120, "bottom": 130, "x0": 100, "x1": 150},
        {"text": "50,00", "top": 120, "bottom": 130, "x0": 380, "x1": 420},
    ]

    tx_words, summary_words = _split_words_by_totals(words, y_margin_thresh=2)

    assert [w["text"] for w in tx_words] == ["09.06", "ACHAT", "50,00"]
    assert [w["text"] for w in summary_words] == ["SOLDE", "CREDITEUR", "2 000,00"]


def test_split_words_by_totals_page_without_solde_or_total():
    """Teste une page intermédiaire contenant uniquement des transactions."""
    words = [
        {"text": "05.06", "top": 100, "bottom": 110, "x0": 50, "x1": 80},
        {"text": "VIREMENT", "top": 100, "bottom": 110, "x0": 100, "x1": 160},
        {"text": "100,00", "top": 100, "bottom": 110, "x0": 450, "x1": 490},
    ]

    tx_words, summary_words = _split_words_by_totals(words)

    assert len(tx_words) == 3
    assert len(summary_words) == 0


def test_split_words_by_totals_empty_words():
    """Teste une liste de mots vide."""
    tx_words, summary_words = _split_words_by_totals([])
    assert tx_words == []
    assert summary_words == []


# ==============================================================================
# Tests pour _parse_summary_words
# ==============================================================================
@pytest.fixture
def mock_col_boundaries():
    """Limites standard de colonnes : date, nature, valeur, debit, credit."""
    return {
        "date": (30, 80),
        "nature": (80, 300),
        "valeur": (300, 370),
        "debit": (370, 440),
        "credit": (440, 520),
    }


def test_parse_summary_words_full(mock_col_boundaries):
    """Teste l'extraction complète : Solde initial, Totaux Débit/Crédit et Nouveau Solde."""
    summary_words = [
        # 1. Ligne Solde Initial (Créditeur)
        {"text": "SOLDE", "top": 100, "x0": 90},
        {"text": "CREDITEUR", "top": 100, "x0": 130},
        {"text": "AU", "top": 100, "x0": 190},
        {"text": "01.06.2025", "top": 100, "x0": 210},
        {"text": "4 474,68", "top": 100, "x0": 450},  # Dans la colonne crédit (440-520)
        # 2. Ligne Total des mouvements (Débit et Crédit)
        {"text": "TOTAL", "top": 500, "x0": 90},
        {"text": "DES", "top": 500, "x0": 130},
        {"text": "MOUVEMENTS", "top": 500, "x0": 155},
        {"text": "1 250,50", "top": 500, "x0": 380},  # Dans la colonne débit (370-440)
        {"text": "3 000,00", "top": 500, "x0": 450},  # Dans la colonne crédit (440-520)
        # 3. Ligne Nouveau Solde / Solde Final
        {"text": "NOUVEAU", "top": 550, "x0": 90},
        {"text": "SOLDE", "top": 550, "x0": 140},
        {"text": "CREDITEUR", "top": 550, "x0": 180},
        {"text": "6 224,18", "top": 550, "x0": 450},  # Dans la colonne crédit (440-520)
    ]

    summary = _parse_summary_words(summary_words, mock_col_boundaries)

    assert summary["solde_initial"] == "4 474,68"
    assert summary["total_debit"] == "1 250,50"
    assert summary["total_credit"] == "3 000,00"
    assert summary["solde_final"] == "6 224,18"


def test_parse_summary_words_debit_initial_and_final(mock_col_boundaries):
    """Teste l'extraction avec un solde initial et final débiteur."""
    summary_words = [
        # Solde débiteur initial
        {"text": "SOLDE", "top": 100, "x0": 90},
        {"text": "DEBITEUR", "top": 100, "x0": 130},
        {"text": "250,00", "top": 100, "x0": 380},  # Dans la colonne débit
        # Nouveau solde débiteur
        {"text": "NOUVEAU", "top": 500, "x0": 90},
        {"text": "SOLDE", "top": 500, "x0": 140},
        {"text": "500,00", "top": 500, "x0": 380},  # Dans la colonne débit
    ]

    summary = _parse_summary_words(summary_words, mock_col_boundaries)

    assert summary["solde_initial"] == "250,00"
    assert summary["total_debit"] is None
    assert summary["total_credit"] is None
    assert summary["solde_final"] == "500,00"


def test_parse_summary_words_empty(mock_col_boundaries):
    """Teste l'extraction avec une liste vide de mots de résumé."""
    summary = _parse_summary_words([], mock_col_boundaries)
    assert summary == {
        "solde_initial": None,
        "total_debit": None,
        "total_credit": None,
        "solde_final": None,
    }


def test_parse_summary_words_single_page_both_solde_lines(mock_col_boundaries):
    """Teste l'extraction sur un relevé d'une seule page où le solde final
    ne contient pas forcément 'NOUVEAU', mais simplement 'SOLDE CREDITEUR AU ...'.
    """
    summary_words = [
        # 1. Ligne Solde Initial en haut
        {"text": "SOLDE", "top": 80, "x0": 68},
        {"text": "CREDITEUR", "top": 80, "x0": 105},
        {"text": "AU", "top": 80, "x0": 155},
        {"text": "01.07.2025", "top": 80, "x0": 175},
        {"text": "2 000,00", "top": 80, "x0": 450},  # Dans la colonne crédit
        # 2. Ligne Total des opérations en bas
        {"text": "TOTAL", "top": 280, "x0": 68},
        {"text": "DES", "top": 280, "x0": 105},
        {"text": "OPERATIONS", "top": 280, "x0": 130},
        {"text": "50,00", "top": 280, "x0": 380},  # Dans la colonne débit
        {"text": "1 500,00", "top": 280, "x0": 450},  # Dans la colonne crédit
        # 3. Ligne Solde Final en bas sous le Total
        {"text": "SOLDE", "top": 300, "x0": 68},
        {"text": "CREDITEUR", "top": 300, "x0": 105},
        {"text": "AU", "top": 300, "x0": 155},
        {"text": "31.07.2025", "top": 300, "x0": 175},
        {"text": "3 450,00", "top": 300, "x0": 450},  # Dans la colonne crédit
    ]

    summary = _parse_summary_words(summary_words, mock_col_boundaries)

    assert summary["solde_initial"] == "2 000,00"
    assert summary["total_debit"] == "50,00"
    assert summary["total_credit"] == "1 500,00"
    assert summary["solde_final"] == "3 450,00"


def test_parse_summary_words_two_solde_without_total(mock_col_boundaries):
    """Teste le cas où la page contient deux lignes SOLDE (initial et final) sans ligne TOTAL intermédiaire."""
    summary_words = [
        # Ligne 1 : Solde initial
        {"text": "SOLDE", "top": 100, "x0": 90},
        {"text": "CREDITEUR", "top": 100, "x0": 130},
        {"text": "1 000,00", "top": 100, "x0": 450},
        # Ligne 2 : Solde final
        {"text": "SOLDE", "top": 400, "x0": 90},
        {"text": "CREDITEUR", "top": 400, "x0": 130},
        {"text": "1 200,00", "top": 400, "x0": 450},
    ]

    summary = _parse_summary_words(summary_words, mock_col_boundaries)

    assert summary["solde_initial"] == "1 000,00"
    assert summary["total_debit"] is None
    assert summary["total_credit"] is None
    assert summary["solde_final"] == "1 200,00"
