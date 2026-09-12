import re
from pathlib import Path

APP_NAME = "locally"

# Data directories
DATA_DIR = Path(__file__).parent.parent.parent / "data"

RAW_DIR = DATA_DIR / "raw/bnp"
INTERIM_DIR = DATA_DIR / "interim/bnp"
PROCESSED_DIR = DATA_DIR / "processed/bnp"

# PDF EXTRACTION SETTINGS
TABLE_SETTINGS = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}

## Regex patterns
DATE_PATTERN = re.compile(r"^\d{2}\.\d{2}$")

# LLM Settings
MODEL_NAME = "gemma4:e4b-mlx"
BASE_URL = "http://localhost:11434/v1"
BATCH_SIZE = 10

## Prompts
system_prompt = """
Tu es un moteur d'extraction JSON comptable.
Ta mission est d'analyser les libellés de transactions bancaires pour extraire le nom du marchand et assigner une catégorie.

RÈGLES :
    1. Réponds uniquement avec le schéma JSON attendu. Aucun texte avant ou après.
    2. Pour 'categorie', utilise STRICTEMENT l'une des valeurs exactes de l'Enum fournie. N'invente aucun libellé.
"""

# Open Telemetry / Phoenix Settings
PHOENIX_ENDPOINT = "http://127.0.0.1:6006/v1/traces"


def setup_monitoring(enabled: bool = False, endpoint: str = PHOENIX_ENDPOINT) -> None:
    """Configure l'instrumentation OpenTelemetry et Phoenix si activé.

    Args:
        enabled: Booléen indiquant si le monitoring doit être activé.
        endpoint: URL de l'endpoint OTLP Phoenix.

    Returns:
        None.
    """
    if not enabled:
        return

    from openinference.instrumentation.instructor import InstructorInstrumentor
    from openinference.instrumentation.openai import OpenAIInstrumentor
    from phoenix.otel import register

    tracer_provider = register(project_name=APP_NAME, endpoint=endpoint)
    InstructorInstrumentor().instrument(tracer_provider=tracer_provider)
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)


def configure_logging(
    level: str = "INFO", mode: str = "w", log_file: str | Path = "logs/all.log"
) -> None:
    """Configure le système de journalisation via Loguru.

    Args:
        level: Niveau de log ('DEBUG', 'INFO', 'WARNING', 'ERROR').
        mode: Mode d'ouverture du fichier de log ('w' pour écraser, 'a' pour concaténer).
        log_file: Chemin vers le fichier de destination des logs.

    Returns:
        None.
    """
    from loguru import logger

    logger.remove()
    logger.add(log_file, level=level.upper(), mode=mode)
