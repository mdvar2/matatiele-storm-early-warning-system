"""Build docs/model_evidence.json: the model-evaluation figures shown on the dashboard's Risk Analysis page.

Everything is recomputed from saved artefacts; nothing is retrained and the model and the 35% threshold are
only read. The deployed model re-scores the held-out rows, and the run stops if the result differs from the
probabilities saved when the model was trained, so the figures cannot drift from the model file.

Inputs (all committed, so a clean checkout can reproduce the JSON):
- outputs/model_live/random_forest_live_model.pkl, live_model_features.txt, live_selected_threshold.txt
- docs/evidence/held_out_test_set.csv.gz: the held-out 20% from script 14 (the 29 ERA5 inputs, labels and the
  saved probabilities), copied value-for-value from the git-ignored outputs/model_live/live_model_test_predictions.csv
- evaluation_reports/ml_evaluation_2026-10-29/test_metrics.csv (the chronological evaluation with a validation year)

Run from the repository root:
  python 25_build_model_evidence.py           # rewrite docs/model_evidence.json
  python 25_build_model_evidence.py --check   # recompute and confirm the committed JSON is reproduced; writes nothing
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / 'outputs' / 'model_live'
ML_EVAL = ROOT / 'evaluation_reports' / 'ml_evaluation_2026-10-29'
HELD_OUT = ROOT / 'docs' / 'evidence' / 'held_out_test_set.csv.gz'
OUT = ROOT / 'docs' / 'model_evidence.json'
THRESHOLDS = (0.30, 0.35, 0.40, 0.45, 0.50)

# Readable groups for the 29 inputs (current and previous hour of each variable count in the same group).
GROUPS = {
    'Rainfall (total and convective)': ('tp', 'cp'),
    'Atmospheric instability (CAPE)': ('cape',),
    'Cloud cover': ('tcc',),
    'Temperature and humidity': ('t2m', 'd2m'),
    'Wind and gusts': ('u10', 'v10', 'i10fg', 'wind_speed'),
    'Air pressure': ('msl', 'sp'),
    'Time of day and season': ('hour', 'month', 'day_of_year'),
    'Grid-cell position': ('latitude', 'longitude'),
}
NAMES = {'tp': 'Total precipitation', 'cp': 'Convective precipitation', 'cape': 'CAPE (instability)', 'tcc': 'Total cloud cover',
         't2m': 'Temperature (2 m)', 'd2m': 'Dew point (2 m)', 'u10': 'Wind, east-west (10 m)', 'v10': 'Wind, north-south (10 m)',
         'i10fg': 'Wind gusts (10 m)', 'wind_speed': 'Wind speed (10 m)', 'msl': 'Sea-level pressure', 'sp': 'Surface pressure',
         'hour': 'Hour of day', 'month': 'Month', 'day_of_year': 'Day of year', 'latitude': 'Latitude', 'longitude': 'Longitude'}


def scores(truth, decision):
    tp = int(((decision == 1) & (truth == 1)).sum()); fp = int(((decision == 1) & (truth == 0)).sum())
    fn = int(((decision == 0) & (truth == 1)).sum()); tn = int(((decision == 0) & (truth == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    return {'precision': precision, 'recall': recall, 'f1': f1, 'TP': tp, 'FP': fp, 'FN': fn, 'TN': tn, 'warnings': tp + fp}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    model = joblib.load(MODEL_DIR / 'random_forest_live_model.pkl')
    features = (MODEL_DIR / 'live_model_features.txt').read_text(encoding='utf-8').split()
    threshold = float((MODEL_DIR / 'live_selected_threshold.txt').read_text().strip())
    test = pd.read_csv(HELD_OUT, parse_dates=['valid_time'])
    probability = model.predict_proba(test[features])[:, 1]
    if np.max(np.abs(probability - test['live_model_probability'])) >= 1e-9:
        raise SystemExit('Stopped: the model does not reproduce the saved held-out probabilities.')
    truth = test['target_storm'].astype(int).to_numpy()

    comparison = [{'threshold': t, **scores(truth, (probability >= t).astype(int))} for t in THRESHOLDS]
    # Persistence: "the next hour will be like this hour" (this hour's ERA5 storm label predicts the next hour's).
    persistence = scores(truth, test['storm_label'].astype(int).to_numpy())

    # Reliability (calibration) check: mean estimate against the observed label frequency in probability bins.
    edges = [0, 0.05, 0.1, 0.2, 0.35, 0.5, 0.7, 1.0001]
    bins = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (probability >= low) & (probability < high)
        if mask.sum():
            bins.append({'range': f'{low:.0%}-{min(high, 1):.0%}', 'rows': int(mask.sum()),
                         'mean_estimate': float(probability[mask].mean()), 'observed_storm_fraction': float(truth[mask].mean())})

    importance = dict(zip(features, model.feature_importances_.tolist()))
    groups = [{'group': name, 'importance': sum(v for f, v in importance.items() if f.removeprefix('previous_') in members),
               'inputs': sorted({NAMES[f.removeprefix('previous_')] for f in importance if f.removeprefix('previous_') in members})}
              for name, members in GROUPS.items()]
    top = sorted(importance.items(), key=lambda kv: kv[1], reverse=True)[:10]

    metrics = pd.read_csv(ML_EVAL / 'test_metrics.csv')
    keep = {'M2 deployed RF @ validation-selected primary threshold': 'Deployed model at the threshold chosen on the validation year (0.46)',
            'M1 @ validation-selected primary threshold': 'Same settings retrained on the training years only, threshold chosen on validation (0.46)',
            'B2 persistence baseline': 'Persistence baseline'}
    rows = metrics[(metrics['period'] == 'test') & metrics['classifier'].isin(keep)]
    chronological = [{'model': keep[r.classifier], 'precision': r.precision, 'recall': r.recall, 'f1': r.f1,
                      'FP': int(r.FP), 'FN': int(r.FN), 'warnings': int(r.warnings)} for r in rows.itertuples()]

    return {
        'generated_by': '25_build_model_evidence.py',
        'inputs_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): sha256(p)
                          for p in (MODEL_DIR / 'random_forest_live_model.pkl', HELD_OUT, ML_EVAL / 'test_metrics.csv')},
        'software': {'scikit-learn': sklearn.__version__, 'numpy': np.__version__, 'pandas': pd.__version__},
        'features': features,
        'threshold_in_use': threshold,
        'threshold_rule': 'warning when the estimate is at or above the threshold (the comparison the hourly worker uses)',
        'labels': 'ERA5-derived proxy storm labels (03_create_labels.py), not observed storm reports',
        'held_out': {'rows': int(len(test)), 'storm_hours': int(truth.sum()),
                     'first_utc': f"{test['valid_time'].min():%Y-%m-%d %H:%M}", 'last_utc': f"{test['valid_time'].max():%Y-%m-%d %H:%M}",
                     'note': 'Most recent 20% of the chronological record, held out from training (script 14). The 35% threshold was '
                             'chosen by comparing F1 on this same period (script 15), so figures at 35% are optimistic.'},
        'threshold_comparison': comparison,
        'persistence_baseline': persistence,
        'brier_score': float(np.mean((probability - truth) ** 2)),
        'reliability_bins': bins,
        'feature_importance_groups': sorted(groups, key=lambda g: g['importance'], reverse=True),
        'feature_importance_top10': [{'feature': f, 'importance': v} for f, v in top],
        'chronological_evaluation': {
            'source': 'evaluation_reports/ml_evaluation_2026-10-29 (train Jan 2018-Aug 2024, validation Aug 2024-Aug 2025, '
                      'test Aug 2025-Aug 2026, 7-day gaps; threshold chosen on validation only)',
            'test_rows': 30428, 'rows': chronological},
    }


def differences(committed, rebuilt, tolerance=1e-12):
    """Keys whose values differ; numbers are compared to within floating-point rounding. Software versions are not compared."""
    def same(a, b):
        if isinstance(a, dict) and isinstance(b, dict):
            return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
        if isinstance(a, list) and isinstance(b, list):
            return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
        if isinstance(a, float) or isinstance(b, float):
            return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) <= tolerance
        return a == b
    return sorted(k for k in set(committed) | set(rebuilt) if k != 'software' and not same(committed.get(k), rebuilt.get(k)))


def main(check=False):
    evidence = build()
    if check:
        diff = differences(json.loads(OUT.read_text(encoding='utf-8')), json.loads(json.dumps(evidence)))
        print('CHECK PASSED: docs/model_evidence.json is reproduced from the committed inputs' if not diff
              else 'CHECK FAILED, these entries differ: ' + ', '.join(diff))
        return 1 if diff else 0
    OUT.write_text(json.dumps(evidence, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: evidence[k] for k in ('threshold_in_use', 'held_out', 'threshold_comparison', 'persistence_baseline', 'brier_score')}, indent=1))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build or check docs/model_evidence.json')
    parser.add_argument('--check', action='store_true', help='recompute and compare with the committed JSON; write nothing')
    sys.exit(main(parser.parse_args().check))
