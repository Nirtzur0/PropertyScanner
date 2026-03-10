# Retriever Ablation Report

- Generated: `2026-02-09T12:56:04.951312`
- Listing type: `sale`
- Label source: `auto`
- Targets: `80`

## Mode Metrics

| Mode | Status | Coverage | MAE | MAPE | MedAE |
| --- | --- | --- | --- | --- | --- |
| geo_only | ok | 0.863 | 380073.94 | 68.20% | 199420.20 |
| geo_structure | ok | 0.212 | 85962.62 | 20.78% | 76519.48 |
| geo_structure_semantic | ok | 0.287 | 231918.80 | 24.97% | 79220.23 |

## Decisions

- Semantic retrieval decision: `simplify` (supported)
- Semantic reasons: `semantic_mae_improvement_below_threshold`
- Decomposition diagnostics status: `insufficient_segment_samples` (keep_gap_visible)
- Decomposition reasons: `segment_sample_floor_not_met`
- Embedding drift proxy: `ok`
- Drift reasons: `none`

## Thresholds

- Semantic min MAE improvement: `0.02`
- Semantic max coverage drop: `0.05`
- Decomposition min segment samples: `20`
- Decomposition MAE gap threshold: `0.25`
