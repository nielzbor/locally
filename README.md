# LOCALLY

Laboratoire d'extraction, normalisation, enrichissement et catégorisation sémantique de relevés bancaires (PDF) vers des structures de données tabulaires (Parquet, CSV) et des modèles validés Pydantic.

Le projet propose un pipeline modulaire utilisable en ligne de commande (CLI avec Typer) ainsi qu'une couche de services réutilisable conçue pour être exposée via une API (FastAPI).

---

## 1. Architecture du projet

```text
src/
├── main.py                        # Script d'exécution (délègue à la CLI)
└── locally/
    ├── cli.py                     # Interface CLI Typer (commandes, arguments, flags)
    ├── config.py                  # Chemins, paramètres LLM, logging & télémétrie Phoenix
    ├── models.py                  # Modèles Pydantic (TransactionExtraite, ReleveBancaire)
    ├── parsers/                   # Moteurs d'extraction PDF (pdfplumber)
    │   └── bnp_parser.py          # Parsing BNP (tableaux, soldes, montants)
    ├── processors/                # Post-traitements & intelligence
    │   ├── feature_extraction.py  # Regex (SEPA, dates cartes, types d'opérations)
    │   └── llm_processors.py      # Catégorisation LLM via Instructor / Ollama
    ├── services/                  # Logique métier pure (indépendante de toute UI)
    │   └── pipeline.py            # Orchestration des étapes de traitement
    └── utils/
        └── io_utils.py            # I/O CSV & Parquet
```

### Architecture des données (Data Lake)

```text
data/
├── raw/bnp/                       # BRONZE : PDFs sources non modifiés
├── interim/bnp/                   # SILVER : Relevés extraits et enrichis (Parquet/CSV)
└── processed/bnp/                 # GOLD : Relevés catégorisés par le LLM
```

---

## 2. Installation

Le projet utilise [`uv`](https://docs.astral.sh/uv/) comme gestionnaire de paquets et d'environnements Python.

### Prérequis

- Python $\ge$ 3.14
- `uv` installé sur votre machine
- *(Optionnel pour la catégorisation)* : [Ollama](https://ollama.ai/) actif avec le modèle configuré (par ex. `gemma4:e4b-mlx`).
- *(Optionnel pour la télémétrie)* : [Arize Phoenix](https://phoenix.arize.com/) (`phoenix serve`).

### Cloner et installer les dépendances

```bash
git clone <url-du-repo>
cd locally

# Synchroniser l'environnement virtuel avec uv
uv sync
```

---

## 3. Prise en main rapide

Vous pouvez exécuter l'outil soit via la commande installée `locally`, soit via le script `src/main.py`.

### Afficher l'aide

```bash
uv run locally --help
```

### Traiter un relevé de bout en bout (sans LLM)

Pour vérifier rapidement le parsing et la cohérence comptable d'un relevé bancaire sans attendre l'inférence LLM :

```bash
uv run locally process -f data/raw/bnp/mon_releve_de_compte_2026-05-08.pdf --skip-llm
```

### Lancer la suite de tests

```bash
uv run pytest -v
```

---

## 4. Guide des commandes CLI

La CLI propose 4 commandes principales ainsi que des options globales.

### Options globales (disponibles sur toutes les commandes)

- `--log-level` : Niveau de log Loguru (`DEBUG`, `INFO`, `WARNING`, `ERROR`). *Défaut: `INFO`*.
- `--log-mode` : Mode d'ouverture du fichier de log (`w` pour écraser, `a` pour ajouter). *Défaut: `w`*.
- `--monitoring / --no-monitoring` : Active ou désactive la télémétrie OpenTelemetry vers Arize Phoenix. *Défaut: `no-monitoring`*.

---

### `process` : Pipeline complet

Exécute la chaîne d'un coup : Extraction $\rightarrow$ Enrichissement $\rightarrow$ Validation Pydantic $\rightarrow$ Catégorisation LLM.

#### Syntaxe et options

- `-f, --file PATH` : Chemin vers un fichier PDF unique.
- `-d, --dir PATH` : Répertoire contenant des fichiers PDF à traiter en lot.
- `--skip-llm` : Désactive l'étape de catégorisation LLM (idéal pour le dev rapide ou le debug).

#### Exemples

```bash
# Traiter un relevé unique sans étape LLM
uv run locally process -f data/raw/bnp/mon_releve_de_compte_2026-05-08.pdf --skip-llm

# Traiter un relevé unique avec catégorisation LLM
uv run locally process -f data/raw/bnp/mon_releve_de_compte_2026-05-08.pdf

# Traiter tous les relevés d'un dossier en mode DEBUG
uv run locally --log-level DEBUG process -d data/raw/bnp --skip-llm
```

---

### `extract` : Extraction tabulaire brute

Parse le PDF, convertit les dates et montants au format numérique, calcule les métadonnées de soldes et enregistre les données dans `data/interim/bnp/`.

#### Syntaxe et options

- `-f, --file PATH` : Fichier PDF à extraire.
- `-d, --dir PATH` : Dossier contenant les PDFs à extraire.
- `-o, --output-dir PATH` *(optionnel)* : Répertoire de destination personnalisé.

#### Exemples

```bash
# Extraire un seul fichier
uv run locally extract -f data/raw/bnp/mon_releve_de_compte_2026-05-08.pdf

# Extraire en lot tous les fichiers d'un répertoire
uv run locally extract -d data/raw/bnp
```

---

### `enrich` : Enrichissement et validation

Lit un fichier intermédiaire (`.parquet`), extrait les identifiants SEPA, dates cartes, types d'opérations et effectue le contrôle de cohérence comptable via Pydantic.

#### Syntaxe et options

- `-f, --file PATH` : Chemin du fichier Parquet intermédiaire à enrichir.
- `-o, --output-dir PATH` *(optionnel)* : Répertoire de destination personnalisé.

#### Exemple

```bash
uv run locally enrich -f data/interim/bnp/releve_de_compte_bnp_tmp_dt=2025-08-08.parquet
```

---

### `categorize` : Catégorisation LLM

Prend un fichier enrichi (`.parquet`), interroge le LLM en local pour classifier chaque opération par marchand et catégorie, et sauvegarde le résultat final dans `data/processed/bnp/`.

#### Syntaxe et options

- `-f, --file PATH` : Chemin du fichier Parquet enrichi à catégoriser.
- `-o, --output-dir PATH` *(optionnel)* : Répertoire de destination personnalisé.

#### Exemple

```bash
uv run locally categorize -f data/interim/bnp/releve_de_compte_bnp_enriched_dt=2025-08-08.parquet
```

---

## 5. Observabilité (Arize Phoenix)

Pour inspecter les traces d'appels LLM (tokens, latence, retries Instructor) :

1. Lancer le serveur Phoenix :

   ```bash
   phoenix serve
   ```

2. Exécuter la commande souhaitée avec le flag `--monitoring` :

   ```bash
   uv run locally --monitoring process -f data/raw/bnp/mon_releve_de_compte_2026-05-08.pdf
   ```

3. Consulter l'interface web Phoenix sur `http://localhost:6006`.
