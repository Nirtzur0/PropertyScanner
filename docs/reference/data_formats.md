# Data Formats Reference

## Domain Models

Source: `src/platform/domain/schema.py`.

### `RawListing`

| Field | Type | Meaning |
| --- | --- | --- |
| `source_id` | `str` | Source identifier |
| `external_id` | `str` | Source-native listing ID |
| `url` | `str` | Listing URL |
| `raw_data` | `dict` | Raw extracted payload |
| `fetched_at` | `datetime` | Fetch timestamp |
| `html_snapshot_path` | `str?` | Optional snapshot path |

### `CanonicalListing`

Key fields:
- identity: `id`, `source_id`, `external_id`, `url`
- value: `price`, `currency`, `listing_type`
- attributes: bedrooms/bathrooms/surface/floor/location
- enrichment: `vlm_description`, sentiment fields, tags
- status: `listed_at`, `updated_at`, `status`, `sold_at`

### `DealAnalysis` and Evidence

Key outputs:
- `fair_value_estimate`
- `fair_value_uncertainty_pct`
- `deal_score`
- `flags`
- `evidence` (`EvidencePack`)

`EvidencePack` includes:
- `model_used`
- anchor values (`anchor_price`, `anchor_std`)
- top comparable evidence (`top_comps`)
- calibration and fallback indicators

## Persistence Tables

Source: `src/platform/domain/models.py`.

### `listings`

Primary listing storage with normalized listing fields and enrichment metadata.

### `valuations`

Valuation snapshots keyed by `listing_id` with `fair_value`, quantile range, confidence, and JSON evidence.

### `agent_runs`

Agent run memory and summary records (`query`, `target_areas`, plan/status, counts, UI blocks).

## Runtime Artifacts

| Artifact | Path |
| --- | --- |
| Operational DB | `data/listings.db` |
| Vector index | `data/vector_index.lancedb` |
| Vector metadata | `data/vector_metadata.json` |
| Model artifacts | `models/` |

### Segmented Calibration Coverage Report (`calibration_coverage.json`)

Produced by:

```bash
python3 -m src.interfaces.cli calibrators --input <samples.jsonl> --coverage-report-output data/calibration_coverage.json
```

Top-level fields:
- `alpha`
- `target_coverage`
- `coverage_floor`
- `min_samples`
- `segment_count`
- `summary` (`evaluated_segments`, `passing_segments`, `failing_segments`, `insufficient_segments`)
- `segments` (array)

Per-segment fields:
- `region_id`
- `listing_type`
- `price_band`
- `horizon_months`
- `n_samples`
- `coverage_rate`
- `target_coverage`
- `coverage_floor`
- `status` (`pass`, `fail`, `insufficient_samples`)

### Spatial Residual Diagnostics Report (`spatial_residual_diagnostics.json`)

Produced by:

```bash
python3 -m src.interfaces.cli calibrators --input <samples.jsonl> --spatial-diagnostics-output data/spatial_residual_diagnostics.json
```

Top-level fields:
- `method` (`spatial_residual_diagnostics_moran_lisa_proxy`)
- `notes`
- `thresholds` (`min_samples`, `drift_threshold_pct`, `outlier_rate_threshold`, `outlier_zscore`)
- `global` (`sample_count`, `mean_residual`, `residual_std`)
- `summary` (`segment_count`, `pass_segments`, `warn_segments`, `insufficient_segments`)
- `segments` (array)

Per-segment fields:
- `region_id`
- `listing_type`
- `price_band`
- `horizon_months`
- `n_samples`
- `mean_residual`
- `median_residual`
- `residual_std`
- `mae`
- `rmse`
- `mean_pct_error`
- `outlier_rate`
- `drift_flag`
- `outlier_flag`
- `lisa_like_hotspot`
- `status` (`pass`, `warn_drift`, `warn_outlier`, `warn_drift_outlier`, `insufficient_samples`)

## Format/Compatibility Notes

- Schema evolution is currently migration-driven; formal compatibility policy is in [Versioning Policy](./versioning_policy.md).
- Release-impacting format changes must include migration notes in `docs/how_to/upgrade_notes_template.md`.
