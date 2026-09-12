"""Point d'entrée de l'interface en ligne de commande (CLI) du projet via Typer."""

from pathlib import Path
from typing import Annotated

import typer

from locally.config import (
    configure_logging,
    setup_monitoring,
)
from locally.services.pipeline import (
    categorize_statement_service,
    enrich_statement_service,
    extract_statement_service,
    process_directory_service,
    process_statement_service,
)
from locally.utils.io_utils import read_df_from_parquet

app = typer.Typer(
    name="locally",
    help="Outil CLI d'extraction, enrichissement et catégorisation de relevés bancaires.",
    add_completion=False,
    rich_markup_mode="rich",
)


@app.callback()
def main_callback(
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            help="Niveau de journalisation (DEBUG, INFO, WARNING, ERROR).",
            case_sensitive=False,
        ),
    ] = "INFO",
    log_mode: Annotated[
        str,
        typer.Option(
            "--log-mode",
            help="Mode d'écriture du fichier de log ('w' écraser, 'a' ajouter).",
        ),
    ] = "w",
    monitoring: Annotated[
        bool,
        typer.Option(
            "--monitoring/--no-monitoring",
            help="Active ou désactive la télémétrie OpenTelemetry / Phoenix.",
        ),
    ] = False,
) -> None:
    """Callback global initialisant le logging et l'observabilité avant chaque commande."""
    configure_logging(level=log_level, mode=log_mode)
    setup_monitoring(enabled=monitoring)


@app.command(name="extract")
def extract_command(
    file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            "-f",
            help="Chemin vers un fichier PDF unique à extraire.",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ] = None,
    directory: Annotated[
        Path | None,
        typer.Option(
            "--dir",
            "-d",
            help="Répertoire contenant les fichiers PDF à extraire en lot.",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-o",
            help="Dossier de destination pour les fichiers intermédiaires.",
        ),
    ] = None,
) -> None:
    """Extrait un relevé PDF (ou un dossier) en données tabulaires intermédiaires."""
    if file is None and directory is None:
        typer.secho(
            "Veuillez spécifier un fichier (--file / -f) ou un répertoire (--dir / -d).",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    targets: list[Path] = [file] if file else sorted(directory.glob("*.pdf"))  # type: ignore
    if not targets:
        typer.secho("Aucun fichier PDF trouvé à extraire.", fg=typer.colors.YELLOW)
        return

    for target in targets:
        typer.echo(f"Extraction de : {target.name}...")
        df, _summary, saved_path = extract_statement_service(
            target, output_dir=output_dir, save_interim=True
        )
        typer.secho(
            f"Extraction réussie pour {target.name} ({len(df)} lignes). Fichier: {saved_path}",
            fg=typer.colors.GREEN,
        )


@app.command(name="enrich")
def enrich_command(
    file: Annotated[
        Path,
        typer.Option(
            "--file",
            "-f",
            help="Chemin vers le fichier intermédiaire (.parquet) à enrichir.",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-o",
            help="Dossier de destination pour les fichiers enrichis.",
        ),
    ] = None,
) -> None:
    """Enrichit un fichier intermédiaire avec les features regex et valide la cohérence comptable."""
    typer.echo(f"Lecture du fichier intermédiaire : {file}...")
    df = read_df_from_parquet(file)
    df_clean, _releve, saved_path = enrich_statement_service(
        df, output_dir=output_dir, save_interim=True
    )
    typer.secho(
        f"Enrichissement réussi ({len(df_clean)} transactions). Enregistré sous : {saved_path}",
        fg=typer.colors.GREEN,
    )


@app.command(name="categorize")
def categorize_command(
    file: Annotated[
        Path,
        typer.Option(
            "--file",
            "-f",
            help="Chemin vers le fichier enrichi (.parquet) à catégoriser.",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-o",
            help="Dossier de destination pour les fichiers catégorisés.",
        ),
    ] = None,
) -> None:
    """Catégorise les transactions d'un fichier enrichi à l'aide d'un LLM."""
    typer.echo(f"Lecture du fichier enrichi : {file}...")
    df_clean = read_df_from_parquet(file)
    # Reconstitution du ReleveBancaire à partir de df_clean
    _, releve, _ = enrich_statement_service(df_clean, save_interim=False)
    df_cat, saved_path = categorize_statement_service(
        df_clean,
        releve,
        output_dir=output_dir,
        save_processed=True,
    )
    typer.secho(
        f"Catégorisation réussie ({len(df_cat)} transactions). Enregistré sous : {saved_path}",
        fg=typer.colors.GREEN,
    )


@app.command(name="process")
def process_command(
    file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            "-f",
            help="Chemin vers un fichier PDF unique à traiter.",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ] = None,
    directory: Annotated[
        Path | None,
        typer.Option(
            "--dir",
            "-d",
            help="Répertoire de fichiers PDF à traiter.",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ] = None,
    skip_llm: Annotated[
        bool,
        typer.Option(
            "--skip-llm",
            help="Saute l'étape de catégorisation LLM (utile pour tester rapidement le parsing).",
        ),
    ] = False,
) -> None:
    """Exécute la chaîne complète (extraction -> enrichissement -> catégorisation)."""
    if file is None and directory is None:
        typer.secho(
            "Veuillez spécifier un fichier (--file / -f) ou un répertoire (--dir / -d).",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    if file:
        typer.echo(
            f"Traitement complet du fichier : {file.name} (skip_llm={skip_llm})..."
        )
        df_res, _releve = process_statement_service(file, skip_llm=skip_llm)
        typer.secho(
            f"Traitement terminé avec succès pour {file.name} ! ({len(df_res)} transactions)",
            fg=typer.colors.GREEN,
        )
    elif directory:
        typer.echo(
            f"Traitement par lot du répertoire : {directory} (skip_llm={skip_llm})..."
        )
        results = process_directory_service(directory, skip_llm=skip_llm)
        typer.secho(
            f"Traitement par lot terminé : {len(results)} relevés traités avec succès !",
            fg=typer.colors.GREEN,
        )
