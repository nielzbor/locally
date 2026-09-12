import pandas as pd
from instructor.core import Instructor
from loguru import logger
from tqdm import tqdm

from locally.config import BATCH_SIZE, system_prompt
from locally.models import BatchCategorisation, ReleveBancaire, TransactionExtraite


def assign_txs_labels_with_llm(
    df: pd.DataFrame,
    releve_complet: ReleveBancaire,
    client: Instructor,
    model: str = "gemma4:e4b-mlx",
    system_prompt: str = system_prompt,
    batch_size: int = BATCH_SIZE,
) -> pd.DataFrame:

    # 1. Copie du DataFrame source et initialisation des nouvelles colonnes
    df_txs_categorized = df.copy()
    df_txs_categorized["categorie"] = None
    df_txs_categorized["marchand_clean"] = None

    transactions_objects: list[TransactionExtraite] = releve_complet.transactions
    nb_total_objects = len(transactions_objects)

    # 2. Boucle par découpage (chunking)
    for i in tqdm(
        range(0, nb_total_objects, batch_size), desc="Catégorisation par le LLM"
    ):
        # Extraction de la tranche d'objets Pydantic sources
        batch_sources = transactions_objects[i : i + batch_size]

        # Construction du payload léger
        # Note: idx reste l'index global pour faire correspondre exactement l'ID du batch au DataFrame
        payload_for_llm = [
            {
                "id": i + idx,
                "tx_type": tx.tx_type,
                "raw_merchant_text": tx.raw_merchant_text,
            }
            for idx, tx in enumerate(batch_sources)
        ]

        try:
            # Appel LLM avec Instructor
            txs_response: BatchCategorisation = client.chat.completions.create(
                model=model,
                response_model=BatchCategorisation,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Voici les transactions à traiter :\n{payload_for_llm}",
                    },
                ],
                max_retries=3,
                temperature=0,
            )

            # 3. Insertion continue dans le DataFrame à chaque batch réussi
            for tx in txs_response.transactions:
                df_txs_categorized.loc[tx.id, "categorie"] = tx.categorie.value
                df_txs_categorized.loc[tx.id, "marchand_clean"] = tx.marchand_clean

        except Exception as e:  # noqa: BLE001
            logger.error(f"\n[Erreur sur le batch {i}-{i + batch_size}] : {e}")
        # Le reste du DataFrame est préservé malgré l'erreur

    return df_txs_categorized
