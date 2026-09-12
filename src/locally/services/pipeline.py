"""Services de pipeline métier pour le traitement de relevés bancaires."""

from pathlib import Path
from typing import Any

import instructor
import numpy as np
import pandas as pd
from loguru import logger
from openai import OpenAI

from locally.config import (
    BASE_URL,
    INTERIM_DIR,
    PROCESSED_DIR,
)
from locally.models import (
    ReleveBancaire,
    TransactionExtraite,
)
from locally.parsers.bnp_parser import extract_pdf_to_dataframe
from locally.processors.feature_extraction import (
    convert_to_timestamp,
    extract_nature_features,
    parse_french_amount,
)
from locally.processors.llm_processors import assign_txs_labels_with_llm
from locally.utils.io_utils import save_df_to_csv, save_df_to_parquet


def extract_statement_service(
    pdf_path: Path,
    output_dir: Path | None = None,
    save_interim: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any], Path | None]:
    """Extrait un relevé bancaire PDF en DataFrame Pandas et extrait les métadonnées.

    Args:
        pdf_path: Chemin du fichier PDF à extraire.
        output_dir: Dossier de sauvegarde intermédiaire (par défaut: INTERIM_DIR).
        save_interim: Indique si les fichiers CSV et Parquet intermédiaires doivent être sauvegardés.

    Returns:
        Un tuple contenant :
            - df: Le DataFrame contenant les opérations avec types normalisés.
            - summary: Dictionnaire contenant les soldes et totaux extraits.
            - output_path: Le chemin de base où les fichiers ont été enregistrés (sans extension), ou None.

    Raises:
        FileNotFoundError: Si le fichier PDF spécifié n'existe pas.
        ValueError: Si la date ne peut être extraite du nom du fichier ou du contenu.
    """
    if not pdf_path.exists() or not pdf_path.is_file():
        raise FileNotFoundError(f"Le fichier PDF spécifié n'existe pas : {pdf_path}")

    target_dir = output_dir or INTERIM_DIR
    logger.info(f"Début de l'extraction pour le fichier : {pdf_path.name}")

    # Récupération de la date depuis le nom de fichier (ex: *_YYYY-MM-DD.pdf)
    date_part = pdf_path.stem.split("_")[-1].strip()
    try:
        statement_date = pd.to_datetime(date_part)
        year = statement_date.year
    except Exception as err:
        raise ValueError(
            f"Impossible d'extraire une date valide depuis le nom {pdf_path.name}: {err}"
        ) from err

    metadata: dict[str, Any] = {
        "filename": pdf_path.name,
        "statement_date": statement_date,
    }

    # 1. Extraction tabulaire
    df, summary = extract_pdf_to_dataframe(pdf_path)
    logger.info("Extraction tabulaire PDF terminée")

    # 2. Conversion des types
    df["date"] = df["date"].apply(lambda x: convert_to_timestamp(x, year))
    df["valeur"] = df["valeur"].apply(lambda x: convert_to_timestamp(x, year))
    df["debit"] = df["debit"].apply(parse_french_amount)
    df["credit"] = df["credit"].apply(parse_french_amount)
    logger.info("Conversion des types des colonnes terminée")

    # 3. Attribution des métadonnées
    date_str = metadata["statement_date"].strftime("%Y-%m-%d")
    df.attrs = {
        "original_filename": metadata["filename"],
        "statement_date": date_str,
        "solde_initial": parse_french_amount(summary.get("solde_initial")),
        "total_debit": parse_french_amount(summary.get("total_debit")),
        "total_credit": parse_french_amount(summary.get("total_credit")),
        "solde_final": parse_french_amount(summary.get("solde_final")),
    }

    saved_base_path: Path | None = None
    if save_interim:
        filename_interim = f"releve_de_compte_bnp_tmp_dt={date_str}"
        save_df_to_csv(df, target_dir, filename_interim, ";")
        save_df_to_parquet(df, target_dir, filename_interim)
        saved_base_path = target_dir / filename_interim
        logger.info(f"Sauvegarde intermédiaire effectuée sous : {saved_base_path}")

    return df, summary, saved_base_path


def enrich_statement_service(
    df: pd.DataFrame,
    output_dir: Path | None = None,
    save_interim: bool = True,
) -> tuple[pd.DataFrame, ReleveBancaire, Path | None]:
    """Enrichit les données de transactions par extraction de features (regex) et valide le modèle Pydantic.

    Args:
        df: DataFrame issu de l'étape d'extraction (portant les attributs df.attrs).
        output_dir: Dossier de sauvegarde (par défaut: INTERIM_DIR).
        save_interim: Indique si les fichiers enrichis doivent être sauvegardés sur disque.

    Returns:
        Un tuple contenant :
            - df_clean: DataFrame enrichi avec NaN remplacés par None.
            - releve: Instance Pydantic validée de ReleveBancaire.
            - saved_base_path: Chemin du fichier sauvegardé ou None.

    Raises:
        KeyError: Si les attributs requis dans df.attrs sont absents.
        pydantic.ValidationError: Si les contrôles de cohérence comptable échouent.
    """
    target_dir = output_dir or INTERIM_DIR
    logger.info("Enrichissement des features (natures, cartes, SEPA)...")

    df_enriched = extract_nature_features(df)
    df_clean = df_enriched.replace({np.nan: None})

    statement_date = df_clean.attrs.get("statement_date", "unknown")
    original_filename = df_clean.attrs.get("original_filename", "unknown")

    saved_base_path: Path | None = None
    if save_interim:
        filename_enriched = f"releve_de_compte_bnp_enriched_dt={statement_date}"
        save_df_to_csv(df_clean, target_dir, filename_enriched, ";")
        save_df_to_parquet(df_clean, target_dir, filename_enriched)
        saved_base_path = target_dir / filename_enriched
        logger.info(f"Sauvegarde du relevé enrichi terminée : {saved_base_path}")

    tx_records = df_clean.to_dict(orient="records")
    transactions_objects = [TransactionExtraite(**row) for row in tx_records]

    releve = ReleveBancaire(
        filename=original_filename,
        statement_date=statement_date,
        solde_initial=df_clean.attrs.get("solde_initial"),
        total_debit=df_clean.attrs.get("total_debit"),
        total_credit=df_clean.attrs.get("total_credit"),
        solde_final=df_clean.attrs.get("solde_final"),
        transactions=transactions_objects,
    )
    logger.info(
        f"Validation Pydantic du ReleveBancaire réussie ({len(transactions_objects)} transactions)"
    )

    return df_clean, releve, saved_base_path


def categorize_statement_service(
    df_clean: pd.DataFrame,
    releve: ReleveBancaire,
    output_dir: Path | None = None,
    client: Any | None = None,
    save_processed: bool = True,
) -> tuple[pd.DataFrame, Path | None]:
    """Catégorise les transactions du relevé à l'aide d'un LLM et sauvegarde les résultats.

    Args:
        df_clean: DataFrame enrichi contenant les transactions à classifier.
        releve: Modèle ReleveBancaire correspondant.
        output_dir: Dossier de sauvegarde final (par défaut: PROCESSED_DIR).
        client: Client Instructor/OpenAI pré-instancié (si None, un client Ollama par défaut est créé).
        save_processed: Indique si les fichiers catégorisés doivent être sauvegardés sur disque.

    Returns:
        Un tuple contenant :
            - df_categorized: DataFrame contenant les colonnes 'marchand' et 'categorie' renseignées.
            - saved_base_path: Chemin du fichier sauvegardé ou None.
    """
    target_dir = output_dir or PROCESSED_DIR
    logger.info("Début de la catégorisation par LLM...")

    if client is None:
        client = instructor.from_openai(
            OpenAI(
                base_url=BASE_URL,
                api_key="ollama",
            ),
            mode=instructor.Mode.MD_JSON,
        )

    df_categorized = assign_txs_labels_with_llm(df_clean, releve, client)
    logger.info("Catégorisation LLM terminée")

    saved_base_path: Path | None = None
    statement_date = releve.statement_date
    if save_processed:
        filename_to_save = f"releve_de_compte_bnp_cat_dt={statement_date}"
        save_df_to_csv(df_categorized, target_dir, filename_to_save, ";")
        save_df_to_parquet(df_categorized, target_dir, filename_to_save)
        saved_base_path = target_dir / filename_to_save
        logger.info(
            f"Sauvegarde finale des transactions catégorisées : {saved_base_path}"
        )

    return df_categorized, saved_base_path


def process_statement_service(
    pdf_path: Path,
    skip_llm: bool = False,
    output_interim_dir: Path | None = None,
    output_processed_dir: Path | None = None,
) -> tuple[pd.DataFrame, ReleveBancaire]:
    """Exécute l'ensemble du pipeline pour un fichier PDF donné.

    Args:
        pdf_path: Chemin vers le fichier PDF à traiter.
        skip_llm: Indique s'il faut sauter l'étape de catégorisation LLM.
        output_interim_dir: Dossier pour les fichiers intermédiaires.
        output_processed_dir: Dossier pour les fichiers finaux catégorisés.

    Returns:
        Un tuple contenant :
            - Le DataFrame final (catégorisé ou enrichi selon skip_llm).
            - Le modèle Pydantic ReleveBancaire validé.
    """
    logger.info(f"--- Début du pipeline complet pour : {pdf_path.name} ---")

    # 1. Extraction
    df_raw, _, _ = extract_statement_service(
        pdf_path, output_dir=output_interim_dir, save_interim=True
    )

    # 2. Enrichissement
    df_clean, releve, _ = enrich_statement_service(
        df_raw, output_dir=output_interim_dir, save_interim=True
    )

    # 3. Catégorisation LLM (optionnelle)
    if not skip_llm:
        df_final, _ = categorize_statement_service(
            df_clean,
            releve,
            output_dir=output_processed_dir,
            save_processed=True,
        )
        return df_final, releve

    logger.info("Étape LLM ignorée (--skip-llm actif)")
    return df_clean, releve


def process_directory_service(
    dir_path: Path,
    skip_llm: bool = False,
    pattern: str = "*.pdf",
) -> list[tuple[Path, pd.DataFrame, ReleveBancaire]]:
    """Traite tous les fichiers PDF correspondants dans un répertoire donné.

    Args:
        dir_path: Répertoire contenant les fichiers PDF à traiter.
        skip_llm: Indique s'il faut sauter l'étape de catégorisation LLM.
        pattern: Motif glob de recherche des fichiers (défaut: '*.pdf').

    Returns:
        Une liste de tuples (chemin_pdf, df_resultat, releve_valide) pour chaque fichier traité.

    Raises:
        NotADirectoryError: Si dir_path n'est pas un répertoire valide.
    """
    if not dir_path.is_dir():
        raise NotADirectoryError(
            f"Le chemin spécifié n'est pas un répertoire : {dir_path}"
        )

    pdf_files = sorted(dir_path.glob(pattern))
    logger.info(
        f"Fichiers trouvés dans {dir_path} ({len(pdf_files)} fichiers) : {[f.name for f in pdf_files]}"
    )

    results: list[tuple[Path, pd.DataFrame, ReleveBancaire]] = []
    for pdf_file in pdf_files:
        df_res, releve = process_statement_service(pdf_file, skip_llm=skip_llm)
        results.append((pdf_file, df_res, releve))

    return results
