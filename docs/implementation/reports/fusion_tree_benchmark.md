# Fusion vs Tree Baseline Benchmark

- Generated: `2026-03-10T14:33:33.755134`
- Split: `time+geo` (`geo_key=city`, `seed=42`)
- Dataset rows: train `3102`, val `486`, test `896`

## Model Metrics

| Model | Status | MAE | MAPE | MedAE |
| --- | --- | --- | --- | --- |
| random_forest | ok | 515841116649.21 | 285242118.75% | 303910318110.00 |
| xgboost | ok | 711946899522.30 | 473930289.07% | 356854013652.00 |
| fusion_service | failed | n/a | n/a | n/a |

## Fusion Coverage

- Attempted: `80`
- Success: `0`
- Coverage ratio: `0.000`

## Gate Result

- Pass: `False`
- Reasons: `fusion_coverage_below_threshold, fusion_metrics_missing`
