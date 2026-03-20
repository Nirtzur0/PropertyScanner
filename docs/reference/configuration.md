# Configuration Reference

## Config Composition

Hydra defaults are declared in `config/app.yaml`.

Included config groups:
- `paths`
- `sources`
- `registry`
- `agents`
- `scoring`
- `valuation`
- `pipeline`
- `hedonic`
- `quality_gate`
- `description_analyst`
- `vlm`
- `image_selector`
- `tft`
- `dataframe`
- `llm`

## Environment Variable Overrides

From `config/paths.yaml`:

| Variable | Default |
| --- | --- |
| `PROPERTY_SCANNER_DATA_DIR` | `${cwd}/data` |
| `PROPERTY_SCANNER_MODELS_DIR` | `${cwd}/models` |
| `PROPERTY_SCANNER_CONFIG_DIR` | `${cwd}/config` |
| `PROPERTY_SCANNER_SNAPSHOTS_DIR` | `${data_dir}/snapshots` |
| `PROPERTY_SCANNER_DB_PATH` | `${data_dir}/listings.db` |
| `PROPERTY_SCANNER_DB_URL` | `sqlite:///${default_db_path}` |
| `PROPERTY_SCANNER_VECTOR_INDEX_PATH` | `${data_dir}/vector_index.lancedb` |
| `PROPERTY_SCANNER_VECTOR_METADATA_PATH` | `${data_dir}/vector_metadata.json` |
| `PROPERTY_SCANNER_LANCEDB_PATH` | `${data_dir}/vector_index.lancedb` |
| `PROPERTY_SCANNER_FUSION_MODEL_PATH` | `${models_dir}/fusion_model.pt` |
| `PROPERTY_SCANNER_FUSION_CONFIG_PATH` | `${models_dir}/fusion_config.json` |
| `PROPERTY_SCANNER_CALIBRATION_PATH` | `${models_dir}/calibration_registry.json` |
| `PROPERTY_SCANNER_TFT_MODEL_PATH` | `${models_dir}/tft_forecaster.pt` |
| `PROPERTY_SCANNER_TRANSACTIONS_PATH` | `${data_dir}/transactions.csv` |

## Proxy-backed Crawl Overrides

The first-wave proxy-backed sources are `realtor_us`, `redfin_us`, `seloger_fr`, and `immowelt_de`.

Global provider-agnostic overrides:

| Variable | Meaning |
| --- | --- |
| `PROPERTY_SCANNER_PROXY_URL` | Browser context proxy URL (`http://`, `https://`, or provider-compatible proxy endpoint) |
| `PROPERTY_SCANNER_PROXY_BYPASS` | Optional bypass list forwarded to the browser context |
| `PROPERTY_SCANNER_REMOTE_BROWSER_WS` | Optional remote browser WebSocket endpoint instead of a local browser session |

Source-specific overrides take precedence over the global values:

| Source | Proxy URL | Proxy Bypass | Remote Browser |
| --- | --- | --- | --- |
| `realtor_us` | `PROPERTY_SCANNER_REALTOR_US_PROXY_URL` | `PROPERTY_SCANNER_REALTOR_US_PROXY_BYPASS` | `PROPERTY_SCANNER_REALTOR_US_REMOTE_BROWSER_WS` |
| `redfin_us` | `PROPERTY_SCANNER_REDFIN_US_PROXY_URL` | `PROPERTY_SCANNER_REDFIN_US_PROXY_BYPASS` | `PROPERTY_SCANNER_REDFIN_US_REMOTE_BROWSER_WS` |
| `seloger_fr` | `PROPERTY_SCANNER_SELOGER_FR_PROXY_URL` | `PROPERTY_SCANNER_SELOGER_FR_PROXY_BYPASS` | `PROPERTY_SCANNER_SELOGER_FR_REMOTE_BROWSER_WS` |
| `immowelt_de` | `PROPERTY_SCANNER_IMMOWELT_DE_PROXY_URL` | `PROPERTY_SCANNER_IMMOWELT_DE_PROXY_BYPASS` | `PROPERTY_SCANNER_IMMOWELT_DE_REMOTE_BROWSER_WS` |

Runtime behavior:

- direct/no-proxy mode remains the default local path
- sources marked with `browser_config.proxy_required: true` do not attempt a direct crawl without a resolved proxy or remote-browser setting
- missing proxy config surfaces as explicit `proxy_required` runtime evidence rather than a fake successful crawl

## Key Valuation Settings (`config/valuation.yaml`)

| Key | Default | Meaning |
| --- | --- | --- |
| `K_candidates` | `100` | Retriever candidate set size |
| `K_model` | `10` | Comps fed into model |
| `max_distance_km` | `10.0` | Geo distance cap for comps |
| `max_age_months` | `24` | Time horizon for comps |
| `retriever_model_name` | `all-MiniLM-L6-v2` | Embedding model |
| `retriever_backend` | `lancedb` | Retrieval backend |
| `retriever_vlm_policy` | `gated` | VLM text usage policy |
| `horizons_months` | `[12, 36, 60]` | Projection horizons |
| `conformal_alpha` | `0.1` | Conformal uncertainty alpha |

## Model Backend Settings

### Shared Text LLMs (`config/llm.yaml`)

| Key | Default | Meaning |
| --- | --- | --- |
| `provider` | `chatmock` | Default text-model backend identifier |
| `api_base` | `http://127.0.0.1:8000/v1` | OpenAI-compatible endpoint used by LiteLLM |
| `api_key_env` | `CHATMOCK_API_KEY` | Optional env var name for backend auth |
| `text_models` | `["gpt-4o-mini", "gpt-4.1-mini"]` | Ordered fallback list for text completions |
| `vision_model` | `gpt-4o-mini` | Default vision-capable model name used by vision consumers |

Backwards-compatibility note:
- legacy `models` config values are still accepted and normalized into `text_models`.

### Description Analyst (`config/description_analyst.yaml`)

| Key | Default | Meaning |
| --- | --- | --- |
| `provider` | `chatmock` | Backend used for description analysis |
| `api_base` | `http://127.0.0.1:8000/v1` | OpenAI-compatible endpoint |
| `api_key_env` | `CHATMOCK_API_KEY` | Optional env var name for auth |
| `model_name` | `gpt-4o-mini` | Model used for strict-JSON text analysis |
| `timeout_seconds` | `60` | Request timeout |
| `min_description_length` | `50` | Skip analysis for shorter descriptions |

### Vision LLM (`config/vlm.yaml`)

| Key | Default | Meaning |
| --- | --- | --- |
| `provider` | `chatmock` | Backend used for image analysis |
| `api_base` | `http://127.0.0.1:8000/v1` | OpenAI-compatible endpoint |
| `api_key_env` | `CHATMOCK_API_KEY` | Optional env var name for auth |
| `model` | `gpt-4o-mini` | Vision-capable model name |
| `supports_vision` | `true` | Whether the configured backend/model is expected to accept images |
| `max_images` | `2` | Images included per listing description request |
| `debug_max_images` | `4` | Debug capture limit |
| `timeout_seconds` | `60` | Request timeout |

If the configured backend rejects image inputs, the VLM path fails explicitly and stays disabled for that run; it does not silently fall back to Ollama.

## Source Controls (`config/sources.yaml`)

Each source contains:
- `id`, `name`, `base_url`, `type`, `enabled`
- optional browser runtime settings such as `browser_max_concurrency` and `browser_config`
- rate limit policy
- compliance section (`robots_txt_url`, allowed/disallowed paths)

Source reliability varies by portal and anti-bot posture.
