"""Risk Analysis evidence: what the model learned, why a Random Forest, how it performed, and what its score means.

Every figure comes from docs/model_evidence.json, written by 25_build_model_evidence.py from the saved model and
evaluation artefacts. Pure functions: no Streamlit, no network. Nothing here retrains or re-thresholds the model.
"""
import json
from pathlib import Path

import pandas as pd

EVIDENCE = Path(__file__).resolve().parent / 'docs' / 'model_evidence.json'


def load(path=EVIDENCE):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def importance_frame(evidence):
    rows = [{'Input group': g['group'], 'Share (%)': round(100 * g['importance'], 1), 'Inputs': ', '.join(g['inputs'])}
            for g in evidence['feature_importance_groups']]
    return pd.DataFrame(rows)


IMPORTANCE_NOTE = ('Share of the Random Forest\'s split decisions attributed to each group of inputs (impurity-based '
                   'importance, current and previous hour together; the groups add up to 100%). It shows what the model '
                   'relies on, not what causes storms. Rainfall dominates partly because the storm label itself requires '
                   'at least 1 mm of rain, and impurity-based importance can favour some inputs over others.')

WHY_RF = [
    ('Suited to the data.', 'Hourly weather variables in a table, with non-linear interactions (for example rain together '
                            'with instability), are a common use of Random Forests.'),
    ('Rare events.', 'Storm hours are only about 2 to 3% of the record; balanced class weights stop the model ignoring them.'),
    ('A score, not just yes or no.', 'It gives a score between 0 and 1 that a warning threshold can be applied to.'),
    ('Inspectable.', 'Its input importances can be reported, as above.'),
    ('What was shown.', 'In this project the model was compared with a persistence baseline ("the next hour will be like '
                        'this one"), not with other machine-learning algorithms. No claim is made that a Random Forest '
                        'is better than other methods.'),
]


def _pct(value):
    return '' if value is None else f'{100 * value:.1f}'


def threshold_frame(evidence):
    rows = [{'Threshold': f'{row["threshold"]:.0%}' + (' (in use)' if abs(row['threshold'] - evidence['threshold_in_use']) < 1e-9 else ''),
             'Precision (%)': _pct(row['precision']), 'Recall (%)': _pct(row['recall']), 'F1': f'{row["f1"]:.3f}',
             'False alarms': row['FP'], 'Missed storm hours': row['FN'], 'Warnings issued': row['warnings']}
            for row in evidence['threshold_comparison']]
    base = evidence['persistence_baseline']
    rows.append({'Threshold': 'Persistence baseline', 'Precision (%)': _pct(base['precision']), 'Recall (%)': _pct(base['recall']),
                 'F1': f'{base["f1"]:.3f}', 'False alarms': base['FP'], 'Missed storm hours': base['FN'], 'Warnings issued': base['warnings']})
    return pd.DataFrame(rows)


def chronological_frame(evidence):
    rows = (evidence.get('chronological_evaluation') or {}).get('rows') or []
    return pd.DataFrame([{'Model': r['model'], 'Precision (%)': _pct(r['precision']), 'Recall (%)': _pct(r['recall']),
                          'F1': f'{r["f1"]:.3f}', 'False alarms': r['FP'], 'Missed storm hours': r['FN'], 'Warnings issued': r['warnings']}
                         for r in rows])


def confusion_frame(evidence):
    row = next(r for r in evidence['threshold_comparison'] if abs(r['threshold'] - evidence['threshold_in_use']) < 1e-9)
    return pd.DataFrame([{'': 'Labelled storm hour', 'Warning (35% or more)': row['TP'], 'No warning': row['FN']},
                         {'': 'Labelled non-storm hour', 'Warning (35% or more)': row['FP'], 'No warning': row['TN']}])


def performance_caption(evidence):
    held = evidence['held_out']
    return (f'Held-out test period {held["first_utc"][:10]} to {held["last_utc"][:10]} (UTC): {held["rows"]:,} grid-cell hours, '
            f'{held["storm_hours"]} labelled storm hours. Labels are ERA5-derived proxy storm labels, not observed storm reports, '
            'and the inputs are ERA5 reanalysis, not live forecasts. Precision: share of warnings that matched a labelled storm hour. '
            'Recall: share of labelled storm hours that were warned. The 35% threshold was chosen by comparing F1 on this same '
            'period, so its row is optimistic (selection bias); the thresholds from 30% to 40% are almost equal.')


CHRONOLOGICAL_NOTE = ('A stricter check (evaluation report of 29 October 2026): training years 2018 to August 2024, a separate '
                      'validation year to choose the threshold (46%), then a later test year that was not used for any choice. '
                      'On that test year the model and the persistence baseline scored almost the same F1; the difference was '
                      'not meaningful. The model warned of more storm hours only at lower thresholds, at the cost of more false alarms.')


def reliability_frame(evidence):
    return pd.DataFrame([{'Model score range': b['range'], 'Hours': b['rows'], 'Average score (%)': _pct(b['mean_estimate']),
                          'Labelled storm hours (%)': _pct(b['observed_storm_fraction'])} for b in evidence['reliability_bins']])


CONFIDENCE_POINTS = [
    ('Model score.', 'The percentage on this page is the Random Forest\'s score for the next hour. It is a model output, '
                     'not a guaranteed chance of a storm.'),
    ('Model performance.', 'The table above describes how often past warnings matched the labels. It is about the model '
                           'overall, not about this hour\'s estimate.'),
    ('Calibration.', 'A calibrated score of 40% would mean storms in about 40 of 100 such hours. The model was not calibrated '
                     'after training. The check below shows its scores run higher than the labelled storm frequency, so they '
                     'should be read as relative risk levels.'),
    ('Confidence interval.', 'No confidence interval is calculated for a single hour\'s estimate. A higher score means a higher '
                             'estimated risk, not that the estimate is more certain.'),
]


def reliability_caption(evidence):
    return (f'Calibration check (an assessment only; the model was not changed): held-out hours grouped by model score. '
            f'Brier score {evidence["brier_score"]:.4f} (lower is better; it is dominated by the many dry hours).')
