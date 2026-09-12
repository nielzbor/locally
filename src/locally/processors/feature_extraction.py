import re

import pandas as pd


# Utils functions
def _get_tx_type(text):
    text_upper = str(text).upper()

    if text_upper.startswith("PRLV") or "PRLV SEPA" in text_upper:
        return "PRELEVEMENT"
    elif text_upper.startswith(("DU", "FACTURE(S) CARTE ")):
        return "CARTE"
    elif text_upper.startswith("VIR") or "VIREMENT" in text_upper:
        return "VIREMENT"
    elif text_upper.startswith("*COMMISSIONS"):
        return "COMMISSION"
    elif text_upper.startswith("RETROCESSION"):
        return "RETROCESSION"
    elif "RETRAIT DAB" in text_upper:
        return "RETRAIT_DAB"
    return "AUTRE"


def _extract_carte_date(row: pd.Series) -> pd.Timestamp | None:
    # On n'applique la logique que si la transaction est de type CARTE
    if row.get("tx_type") != "CARTE":
        return None

    nature_text = str(row.get("nature", ""))

    # Regex cherchant 'DU' suivi de 6 chiffres (ddmmyy)
    match = re.search(r"\bDU\s+(\d{2})(\d{2})(\d{2})\b", nature_text, re.IGNORECASE)

    if match:
        day, month, year_short = match.groups()
        # Reconstruction au format YYYY-MM-DD (2000 + yy)
        year_full = f"20{year_short}"
        date_str = f"{year_full}-{month}-{day}"
        return pd.to_datetime(date_str, format="%Y-%m-%d")

    return None


def convert_to_timestamp(date_str: str | None, year: str | int) -> pd.Timestamp | None:
    """Convertit '05.06' et '2025' en pd.Timestamp('2025-06-05')."""
    if not date_str or not isinstance(date_str, str):
        return None

    date_clean = date_str.strip()

    # S'assure que le format est bien DD.MM
    if not re.match(r"^\d{2}\.\d{2}$", date_clean):
        return None

    day, month = date_clean.split(".")

    # Reconstruction au format YYYY-MM-DD
    formatted_date = f"{year}-{month}-{day}"

    return pd.to_datetime(formatted_date, format="%Y-%m-%d")


def parse_french_amount(val: str | float | None) -> float | None:
    """Convertit '4 474,68' ou '1 999,29' en float Python.

    Gère les chaînes, les float déjà convertis et les NaN.
    """
    # 1. Si la valeur est déjà absente / NaN / None
    if pd.isna(val) or val is None:
        return None

    # 2. Si la valeur est DÉJÀ un nombre (int ou float)
    if isinstance(val, (int, float)):
        return float(val)

    # 3. Si c'est une chaîne de caractères
    if isinstance(val, str):
        clean_val = val.replace(" ", "").replace("\xa0", "").strip()
        if not clean_val:
            return None
        clean_val = clean_val.replace(",", ".")
        try:
            return float(clean_val)
        except ValueError:
            return None

    return None


def extract_nature_features(df: pd.DataFrame) -> pd.DataFrame:
    # Travailler sur une copie
    df_enriched = df.copy()

    # 1. Type de transaction (Premier mot ou motif connu)
    df_enriched["tx_type"] = df_enriched["nature"].apply(_get_tx_type)

    # 2. Date réelle d'opération pour les Cartes (ex: DU 050625)
    df_enriched["carte_date_reelle"] = df_enriched.apply(
        lambda row: _extract_carte_date(row), axis=1
    )

    # 3. Métadonnées SEPA (Identifiants techniques)
    df_enriched["sepa_emetteur"] = df_enriched["nature"].str.extract(
        r"(?:EMETTEUR/|/DE)\s?([A-Z0-9\s]+)/"
    )
    df_enriched["sepa_mandat"] = df_enriched["nature"].str.extract(r"MDT/([A-Z0-9]+)")
    df_enriched["sepa_reference"] = df_enriched["nature"].str.extract(
        r"REF/([A-Z0-9]+)"
    )

    # 4. Extraction de la partie 'LIB/' ou 'REF/' qui contient le texte utile
    # Exemple : LIB/1042735252803/PAYPAL -> PAYPAL
    df_enriched["raw_merchant_text"] = df_enriched["nature"].str.extract(
        r"(?:LIB|REF)/[0-9]+/(.+)$", flags=re.IGNORECASE
    )[0]

    # # Si pas de motif LIB/REF, on garde le texte brut pour le LLM
    df_enriched["raw_merchant_text"] = df_enriched["raw_merchant_text"].fillna(
        df_enriched["nature"]
    )

    # 5. Extraction du motif suivant le pattern '/MOTIF'
    df_enriched["motif"] = df_enriched["nature"].str.extract(
        r"\s?/MOTIF\s([A-z\s0-9-]+)"
    )

    return df_enriched
