from pathlib import Path

import pandas as pd
from loguru import logger


def save_df_to_csv(
    df: pd.DataFrame, save_dir: Path | str, filename: str, sep=";"
) -> None:
    """
    Save a dataframe to a csv file.

    Args:
        df (pd.DataFrame): DataFrame to save
        save_dir (Path | str): Directory to save the file
        filename (str): Name of the file without .csv extension
        sep (str): Separator to use in the csv file

    Returns:
        None
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / f"{filename}.csv"
    df.to_csv(file_path, sep=sep)

    logger.info(f"DataFrame saved to {file_path}")


def save_df_to_parquet(df: pd.DataFrame, save_dir: Path | str, filename: str) -> None:
    """
    Save a dataframe to a parquet file.

    Args:
        df (pd.DataFrame): DataFrame to save
        save_dir (Path | str): Directory to save the file
        filename (str): Name of the file without .parquet extension

    Returns:
        None
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / f"{filename}.parquet"
    df.to_parquet(file_path)

    logger.info(f"DataFrame saved to {file_path}")


def read_df_from_parquet(file_path: Path | str) -> pd.DataFrame:
    """Lit un fichier Parquet et le retourne sous forme de DataFrame Pandas.

    Args:
        file_path: Chemin vers le fichier Parquet à lire.

    Returns:
        pd.DataFrame: Les données lues depuis le fichier.

    Raises:
        FileNotFoundError: Si le fichier spécifié n'existe pas.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier Parquet introuvable : {path}")

    df = pd.read_parquet(path)
    logger.info(f"DataFrame chargé depuis {path} ({len(df)} lignes)")
    return df


def read_df_from_csv(file_path: Path | str, sep: str = ";") -> pd.DataFrame:
    """Lit un fichier CSV et le retourne sous forme de DataFrame Pandas.

    Args:
        file_path: Chemin vers le fichier CSV à lire.
        sep: Séparateur de colonnes (par défaut ';').

    Returns:
        pd.DataFrame: Les données lues depuis le fichier.

    Raises:
        FileNotFoundError: Si le fichier spécifié n'existe pas.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier CSV introuvable : {path}")

    df = pd.read_csv(path, sep=sep)
    logger.info(f"DataFrame chargé depuis {path} ({len(df)} lignes)")
    return df
