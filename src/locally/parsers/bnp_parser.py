"""Ce fichier contient les fonctions utilitaires pour parser les relevés PDF de BNP Paribas."""

import json
import re
from pathlib import Path

import pandas as pd
import pdfplumber
from loguru import logger
from pdfplumber.page import Page
from pdfplumber.table import Table

from locally.config import DATE_PATTERN, TABLE_SETTINGS


# Utils functions for parsing PDF
def _get_col_boundaries(table: Table) -> dict[str, tuple[str, str]]:
    """
    Détermine les limites des colonnes.

    Args:
            table (Table): Table object from pdfplumber.

    Returns:
            Dict[str, Tuple[str, str]]: Dictionary of column boundaries.
    """
    col_boundaries = {}
    # table.cols donne la liste des colonnes détectées
    # x0 est la limite gauche, x1 est la limite droite de chaque colonne
    auto_boundaries = [col.bbox[0] for col in table.columns] + [
        table.columns[-1].bbox[2]
    ]

    # 2. Reconstruire le dictionnaire de limites automatiquement
    col_names = ["date", "nature", "valeur", "debit", "credit"]

    try:
        for i, name in enumerate(col_names):
            # On prend x0 de la colonne courante et x1 (ou x0 de la suivante)
            col_boundaries[name] = (auto_boundaries[i], auto_boundaries[i + 1])
    except IndexError as e:
        logger.error(f"error on i = {i} : ", e)

    logger.debug(
        f"column boundaries : {json.dumps(col_boundaries, indent=2, ensure_ascii=False)}"
    )

    return col_boundaries


def _split_words_by_totals(
    words: list[dict], y_margin_thresh: float = 2
) -> tuple[list[dict], list[dict]]:
    y_solde_top = None
    y_solde_bottom = None
    y_total = None

    # 1. Détection de y_total d'abord (borne inférieure des transactions)
    for w in words:
        if "TOTAL" in w["text"] and y_total is None:
            y_total = w["top"] - y_margin_thresh
            break

    # 2. Détection du solde initial (doit obligatoirement être au-dessus de y_total s'il y a un total)
    for w in words:
        if "SOLDE" in w["text"]:
            # Si le solde est en dessous du total, c'est le solde final : il ne borne pas le haut des transactions
            if y_total is not None and w["top"] > y_total:
                continue
            if y_solde_top is None:
                y_solde_top = w["top"] - y_margin_thresh
                y_solde_bottom = w["bottom"] + y_margin_thresh
                break

    # Aucun des deux présent sur la page
    if y_solde_top is None and y_total is None:
        logger.info("No transactions nor summary informations detected on this page.")
        return words, []

    # Transactions : sous le solde initial (s'il existe en haut) ET au-dessus du total
    tx_words = [
        w
        for w in words
        if (y_solde_bottom is None or w["top"] >= y_solde_bottom)
        and (y_total is None or w["top"] < y_total)
    ]

    # Résumés : la ligne du solde initial OU tout ce qui est à partir de y_total
    summary_words = [
        w
        for w in words
        if (y_solde_top is not None and y_solde_top <= w["top"] < y_solde_bottom)
        or (y_total is not None and w["top"] >= y_total)
    ]

    return tx_words, summary_words


def _parse_summary_words(
    summary_words: list[dict], col_boundaries: dict[str, tuple[str, str]]
) -> dict[str, str]:
    """
    Extrait :
            - solde_initial (ou credit_initial / debit_initial)
            - total_debit
            - total_credit
            - solde_final

    Args:
            summary_words (List[Dict]): liste des mots de résumé.
            col_boundaries (Dict[str, Tuple[str, str]]): limites des colonnes.

    Returns:
            Dict[str, str]: dictionnaire des résumés.
    """
    summary = {
        "solde_initial": None,
        "total_debit": None,
        "total_credit": None,
        "solde_final": None,
    }

    if not summary_words:
        return summary

    # 1. Regrouper les mots par ligne (selon leur 'top' arrondi à ~2px près)
    lines_dict = {}
    for w in sorted(summary_words, key=lambda x: (x["top"], x["x0"])):
        line_key = round(w["top"] / 3) * 3
        lines_dict.setdefault(line_key, []).append(w)

    for line_words in lines_dict.values():
        line_text = " ".join(w["text"] for w in line_words).upper()

        # Récupérer les morceaux de texte dans chaque colonne
        debit_parts = [
            w["text"]
            for w in line_words
            if col_boundaries["debit"][0] <= w["x0"] < col_boundaries["debit"][1]
        ]
        credit_parts = [
            w["text"]
            for w in line_words
            if col_boundaries["credit"][0] <= w["x0"] < col_boundaries["credit"][1]
        ]

        debit_val = " ".join(debit_parts) if debit_parts else None
        credit_val = " ".join(credit_parts) if credit_parts else None

        # Cas 1 : Ligne de solde initial (en haut de relevé)
        if "SOLDE" in line_text and summary["solde_initial"] is None:
            summary["solde_initial"] = credit_val or debit_val

        # Cas 2 : Ligne de totaux des mouvements
        elif "TOTAL" in line_text:
            if debit_val:
                summary["total_debit"] = debit_val
            if credit_val:
                summary["total_credit"] = credit_val

        # Cas 3 : Ligne de solde final (nouveau solde en fin de relevé)
        elif "SOLDE" in line_text or "NOUVEAU" in line_text:
            summary["solde_final"] = credit_val or debit_val

    return summary


def _get_date_anchors(
    words: list[str],
    DATE_PATTERN: re.Pattern,
    col_boundaries: dict[str, tuple[str, str]],
) -> list[dict[str, str]]:
    """
    Extrait les ancres de date.

    Args:
            words (List[str]): Liste des mots.
            DATE_PATTERN (re.Pattern): Pattern pour les dates.
            col_boundaries (Dict[str, Tuple[str, str]]): Limites des colonnes.

    Returns:
            List[Dict[str, str]]: Liste des ancres de date.
    """
    date_anchors = []
    for w in words:
        if col_boundaries["date"][0] <= w["x0"] < col_boundaries["date"][
            1
        ] and DATE_PATTERN.match(w["text"]):
            date_anchors.append({"date": w["text"], "top": w["top"]})

    # Trier les ancres par position Y
    date_anchors = sorted(date_anchors, key=lambda d: d["top"])
    return date_anchors


## Used for extracting transactions
def _parse_page_by_y_alignment(
    page: Page,
    col_boundaries: dict[str, tuple[str, str]],
    table_bottom: float,
    table_top: float,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """
    Parse une page et extrait les transactions.

    Args:
            page (Page): Page object from pdfplumber.
            col_boundaries (Dict[str, Tuple[str, str]]): Limites des colonnes.
            table_bottom (float): Bottom boundary of the table.
            table_top (float): Top boundary of the table.

    Returns:
            Tuple[List[Dict[str, str]], Dict[str, str]]: Liste des transactions et résumé.
    """
    # 1. Extraire tous les mots avec leurs coordonnées (x0, top, x1, bottom)
    words = [
        w
        for w in page.extract_words(x_tolerance=3, y_tolerance=3)
        if table_top <= w["top"] <= table_bottom
    ]

    # Trie par position verticale (Y) puis horizontale (X)
    words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    # logger.debug(f"Words : {json.dumps(words, indent=2, ensure_ascii=False)}")
    # 2. Séparation des mots de transactions de ceux du résumé de fin de tableau
    words, summary_words = _split_words_by_totals(words, 2)
    logger.debug(f"Words : {json.dumps(words, indent=2, ensure_ascii=False)}")
    logger.debug(
        f"summary_words : {json.dumps(summary_words, indent=2, ensure_ascii=False)}"
    )

    summary = _parse_summary_words(summary_words, col_boundaries)
    # 3. Isoler les mots de la colonne 'Date' pour trouver les Y d'ancrage de chaque transaction
    # Et trier les ancres par position Y
    date_anchors = _get_date_anchors(words, DATE_PATTERN, col_boundaries)

    # 4. Assigner chaque mot de la page à la bonne transaction selon sa position Y
    transactions = []
    for i, anchor in enumerate(date_anchors):
        y_min = anchor["top"] - 2  # Marge haute
        # Le y_max est la date suivante (ou la fin de la page s'il n'y en a plus)
        y_max = (
            date_anchors[i + 1]["top"] - 2 if i + 1 < len(date_anchors) else page.height
        )

        # Récupérer tous les mots compris entre y_min et y_max
        tx_words = [w for w in words if y_min <= w["top"] < y_max]

        # Répartir les mots dans les colonnes selon X
        nature_words = []
        valeur_val = None
        debit_val = None
        credit_val = None

        for w in tx_words:
            x = w["x0"]
            if col_boundaries["nature"][0] <= x < col_boundaries["nature"][1]:  # Nature
                nature_words.append(w["text"])
            elif (
                col_boundaries["valeur"][0] <= x < col_boundaries["valeur"][1]
                and not valeur_val
            ):
                valeur_val = w["text"]
            elif (
                col_boundaries["debit"][0] <= x < col_boundaries["debit"][1]
                and not debit_val
            ):
                debit_val = w["text"]
            elif col_boundaries["credit"][0] <= x and not credit_val:
                credit_val = w["text"]

        if credit_val is None and debit_val is None:
            raise ValueError(
                "Neither of credit_val and debit_val should not be both None."
            )

        transactions.append(
            {
                "date": anchor["date"],
                "nature": " ".join(nature_words),
                "valeur": valeur_val,
                "debit": debit_val,
                "credit": credit_val,
                "page_number": int(page.page_number),
            }
        )

    return transactions, summary


def extract_pdf_to_dataframe(
    file_path: Path | str,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Extract transactions from a BNP Paribas bank statement.

    Args:
            file_path (Path | str): Path to the bank statement PDF file.

    Returns:
            pd.DataFrame: DataFrame of transactions.
            Dict[str, str]: Dictionary of summary data.
    """
    transactions = []
    summary_data = {}

    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            tables = page.find_tables(TABLE_SETTINGS)

            if tables:
                table = tables[0]

                # La bounding box du tableau est (x0, top, x1, bottom)
                table_bottom = table.bbox[3]
                table_top = table.bbox[1]

                col_boundaries = _get_col_boundaries(table)
                # debug : on regarde uniquement ce qui se passe sur la dernière page du relevé.
                # retirer la condition une fois le bug résolu.
                # if i == len(pdf.pages) - 1:
                # logger.debug(f"Last page (n°{i + 1})")
                txs, summary = _parse_page_by_y_alignment(
                    page, col_boundaries, table_bottom, table_top
                )
                transactions.extend(txs)

                if any(summary.values()):
                    summary_data = summary

    return pd.DataFrame(data=transactions), summary_data
