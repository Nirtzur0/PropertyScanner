# How-To: Configure Property Scanner

## Configuration Model

Configuration is Hydra-composed from `config/app.yaml` and included files.

Primary files:
- `config/paths.yaml`
- `config/sources.yaml`
- `config/valuation.yaml`
- `config/llm.yaml`
- `config/description_analyst.yaml`
- `config/vlm.yaml`

## Common Tasks

### Change data/model paths

Use environment variable overrides defined in `config/paths.yaml`:

```bash
export PROPERTY_SCANNER_DATA_DIR="$PWD/data"
export PROPERTY_SCANNER_MODELS_DIR="$PWD/models"
export PROPERTY_SCANNER_DB_PATH="$PWD/data/listings.db"
```

### Enable or disable crawler sources

Edit `config/sources.yaml` and change `enabled: true/false` per source.

Important: crawler reliability differs by source due anti-bot protections. Check `docs/crawler_status.md` before enabling new sources.

### Tune valuation retrieval behavior

Edit `config/valuation.yaml`:
- `K_candidates`, `K_model`
- `max_distance_km`, `max_age_months`
- `retriever_model_name`, `retriever_backend`, `retriever_vlm_policy`

### Point the app at ChatMock or another OpenAI-compatible backend

Edit:
- `config/llm.yaml` for shared text-model defaults
- `config/description_analyst.yaml` for listing-description analysis
- `config/vlm.yaml` for image analysis

Common fields:
- `provider`
- `api_base`
- `api_key_env`
- model names (`text_models`, `model_name`, `model`)

Example auth override:

```bash
export CHATMOCK_API_KEY="your-token-if-required"
```

Note:
- the shipped default endpoint is `http://127.0.0.1:8000/v1`
- VLM requests require the configured backend/model to support OpenAI-style image inputs
- if vision is unsupported, the run logs an explicit VLM backend failure instead of silently reverting to Ollama

### Override transactions input path

```bash
export PROPERTY_SCANNER_TRANSACTIONS_PATH="$PWD/data/transactions.csv"
```

## Verify your configuration

```bash
python3 -m src.interfaces.cli preflight --help
python3 -m src.interfaces.cli build-index --listing-type sale
```

Use [Configuration Reference](../reference/configuration.md) for full setting tables.
