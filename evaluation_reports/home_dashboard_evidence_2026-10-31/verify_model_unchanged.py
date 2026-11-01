"""Verify that the deployed Random Forest and the warning threshold are unchanged.

1. The model file, feature list and threshold file have the same content as on the GitHub `main` branch.
2. Re-running the model on the saved held-out inputs reproduces the saved probabilities and class predictions.
3. The threshold in use is 0.35; the script also reports which threshold reproduces the saved (local) threshold-decision file.
Run from the repository root:  python evaluation_reports/home_dashboard_evidence_2026-10-31/verify_model_unchanged.py
"""
import hashlib
import json
import subprocess
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / 'outputs' / 'model_live'
CRLF, LF = bytes([13, 10]), bytes([10])
result = {}

for name in ('random_forest_live_model.pkl', 'live_model_features.txt', 'live_selected_threshold.txt'):
    local = (MODEL_DIR / name).read_bytes()
    main = subprocess.run(['git', 'show', f'origin/main:outputs/model_live/{name}'], cwd=ROOT, capture_output=True, check=True).stdout
    if name.endswith('.txt'):  # Windows checkouts store text with CRLF; compare the content, not the line endings
        local, main = local.replace(CRLF, LF), main.replace(CRLF, LF)
    result[f'{name} identical to origin/main'] = hashlib.sha256(local).hexdigest() == hashlib.sha256(main).hexdigest()

model = joblib.load(MODEL_DIR / 'random_forest_live_model.pkl')
features = (MODEL_DIR / 'live_model_features.txt').read_text(encoding='utf-8').split()
saved = pd.read_csv(MODEL_DIR / 'live_model_test_predictions.csv')
recomputed = model.predict_proba(saved[features])[:, 1]
result['rows re-scored'] = int(len(saved))
result['max |recomputed - saved probability|'] = float(np.max(np.abs(recomputed - saved['live_model_probability'])))
result['class predictions identical to saved (scikit-learn predict)'] = bool((model.predict(saved[features]) == saved['live_model_prediction']).all())
threshold = float((MODEL_DIR / 'live_selected_threshold.txt').read_text().strip())
result['threshold'] = threshold
thresholded = pd.read_csv(MODEL_DIR / 'live_test_predictions_with_threshold.csv')
# The saved, git-ignored evaluation file of thresholded decisions: report which threshold reproduces it exactly.
scores = model.predict_proba(thresholded[features])[:, 1]
result['saved threshold-decision file reproduced exactly at'] = [t for t in (0.30, 0.35, 0.40, 0.45)
                                                               if ((scores >= t).astype(int) == thresholded['live_threshold_prediction']).all()]
print(json.dumps(result, indent=1))
