"""RO3 chronological train / validation / test evaluation of the Random Forest storm model.

Implements the approved pre-registered design:
    evaluation_reports/RO3_ml_evaluation_design_2026-10-29.md

Read-only with respect to the project: it reads existing datasets and the deployed
model's parameters, never refits or saves a production model, and writes only to
the directory given by --out (default: this script's directory).

Usage (from the project root):
    python evaluation_reports/ml_evaluation_2026-10-29/ro3_chronological_evaluation.py
    python evaluation_reports/ml_evaluation_2026-10-29/ro3_chronological_evaluation.py --smoke --out <tmp>

--smoke uses a tiny forest and few bootstrap resamples to check the code runs; it
prints no metrics and must not be used for reporting.
"""
import argparse
import hashlib
import json
import math
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODEL_READY = ROOT / "outputs" / "model_ready.csv"
FEATURES = ROOT / "outputs" / "model_live" / "live_model_features.txt"
DEPLOYED_MODEL = ROOT / "outputs" / "model_live" / "random_forest_live_model.pkl"
DEPLOYED_TEST = ROOT / "outputs" / "model_live" / "live_model_test_predictions.csv"

# ---------------------------------------------------------------- pre-registered design
PERIODS = {  # UTC, [start, end)
    "train": ("2018-01-01 00:00", "2024-08-12 00:00"),
    "validation": ("2024-08-19 00:00", "2025-08-19 00:00"),
    "test": ("2025-08-26 00:00", "2026-08-08 00:00"),
}
EXPECTED_ROWS = {"train": 85460, "validation": 35040, "test": 30428}
GRID = np.round(np.arange(1, 100) / 100, 2)
PRIMARY_SEED = 42
EXTRA_SEEDS = [1, 2, 3, 4]
BOOT_B = 2000
BOOT_SEED = 20261029
BLOCK_DAYS = 7
MIN_RECALL = 0.70
MEANINGFUL_F1_MARGIN = 0.05
DEPLOYED_THRESHOLD = 0.35
DEFAULT_THRESHOLD = 0.50
SINGLE_CELL = (-30.25, 28.75)
RF_PARAM_KEYS = ["n_estimators", "max_depth", "min_samples_split", "min_samples_leaf",
                 "max_features", "class_weight", "bootstrap", "criterion"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def counts(y, p):
    y = np.asarray(y, dtype=int); p = np.asarray(p, dtype=int)
    tp = int(((p == 1) & (y == 1)).sum()); fp = int(((p == 1) & (y == 0)).sum())
    fn = int(((p == 0) & (y == 1)).sum()); tn = int(((p == 0) & (y == 0)).sum())
    return tp, fp, fn, tn


def scores_from_counts(tp, fp, fn, tn):
    """Vectorised-safe threshold metrics; undefined ratios become NaN."""
    tp, fp, fn, tn = (np.asarray(v, dtype=float) for v in (tp, fp, fn, tn))
    with np.errstate(divide="ignore", invalid="ignore"):
        n = tp + fp + fn + tn
        precision = np.where(tp + fp > 0, tp / (tp + fp), np.nan)
        recall = np.where(tp + fn > 0, tp / (tp + fn), np.nan)
        specificity = np.where(tn + fp > 0, tn / (tn + fp), np.nan)
        f1 = np.where(2 * tp + fp + fn > 0, 2 * tp / (2 * tp + fp + fn), np.nan)
        csi = np.where(tp + fp + fn > 0, tp / (tp + fp + fn), np.nan)
        far = np.where(tp + fp > 0, fp / (tp + fp), np.nan)
        return {"accuracy": (tp + tn) / n, "balanced_accuracy": (recall + specificity) / 2,
                "precision": precision, "recall": recall, "f1": f1,
                "false_alarm_ratio": far, "csi": csi}


def threshold_metrics(y, p):
    tp, fp, fn, tn = counts(y, p)
    out = {k: float(v) for k, v in scores_from_counts(tp, fp, fn, tn).items()}
    out.update(TP=tp, FP=fp, FN=fn, TN=tn, warnings=tp + fp)
    return out


def probability_metrics(y, prob, climatology):
    y = np.asarray(y, dtype=int)
    bs = brier_score_loss(y, prob); bs_ref = brier_score_loss(y, np.full(len(y), climatology))
    return {"roc_auc": roc_auc_score(y, prob), "pr_auc": average_precision_score(y, prob),
            "brier": bs, "brier_skill_vs_train_climatology": 1 - bs / bs_ref,
            "pr_auc_no_skill_reference": float(y.mean())}


def threshold_table(y, prob):
    rows = []
    for t in GRID:
        m = threshold_metrics(y, (prob >= t).astype(int)); m["threshold"] = float(t); rows.append(m)
    return pd.DataFrame(rows)


def select_primary(table):
    best = table["f1"].max()
    return float(table.loc[np.isclose(table["f1"], best, rtol=0, atol=1e-12), "threshold"].max())


def select_recall_constrained(table):
    ok = table[table["recall"] >= MIN_RECALL]
    if ok.empty:
        return None
    best = ok["f1"].max()
    return float(ok.loc[np.isclose(ok["f1"], best, rtol=0, atol=1e-12), "threshold"].max())


def make_rf(params, seed):
    return RandomForestClassifier(**params, random_state=seed, n_jobs=-1)


def block_bootstrap_days(n_days, rng):
    """Moving-block bootstrap over contiguous 7-day blocks; returns day indices."""
    n_blocks = math.ceil(n_days / BLOCK_DAYS)
    starts = rng.integers(0, n_days - BLOCK_DAYS + 1, size=n_blocks)
    days = (starts[:, None] + np.arange(BLOCK_DAYS)[None, :]).ravel()[:n_days]
    return days


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=HERE)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    smoke = args.smoke
    boot_b = 20 if smoke else BOOT_B
    started = time.time()
    log_lines = []

    def log(msg, metric=False):
        if smoke and metric:
            return
        line = f"[{time.time() - started:7.1f}s] {msg}"; print(line, flush=True); log_lines.append(line)

    inputs = {p.name: str(p.relative_to(ROOT)) for p in (MODEL_READY, FEATURES, DEPLOYED_MODEL, DEPLOYED_TEST)}
    hashes_before = {str(p.relative_to(ROOT)): sha256(p) for p in (MODEL_READY, FEATURES, DEPLOYED_MODEL, DEPLOYED_TEST)}

    # ------------------------------------------------------------ data and periods
    features = [f for f in FEATURES.read_text(encoding="utf-8").split() if f]
    deployed = joblib.load(DEPLOYED_MODEL)
    if list(deployed.feature_names_in_) != features:
        raise SystemExit("Feature list does not match the deployed model.")
    rf_params = {k: deployed.get_params()[k] for k in RF_PARAM_KEYS}
    if smoke:
        rf_params["n_estimators"] = 5

    df = pd.read_csv(MODEL_READY)
    df["valid_time"] = pd.to_datetime(df["valid_time"])
    df = df.dropna(subset=features + ["target_storm", "storm_label"]).copy()
    df["target_storm"] = df["target_storm"].astype(int)
    df["storm_label"] = df["storm_label"].astype(int)
    df = df.sort_values(["valid_time", "latitude", "longitude"], kind="mergesort").reset_index(drop=True)

    parts = {}
    for name, (a, b) in PERIODS.items():
        parts[name] = df[(df.valid_time >= a) & (df.valid_time < b)].reset_index(drop=True)
        if len(parts[name]) != EXPECTED_ROWS[name]:
            raise SystemExit(f"{name}: {len(parts[name])} rows, design expects {EXPECTED_ROWS[name]}")
    for a, b in [("train", "validation"), ("validation", "test"), ("train", "test")]:
        if set(parts[a].valid_time) & set(parts[b].valid_time):
            raise SystemExit(f"Timestamp shared between {a} and {b}")
    gap_ab = parts["validation"].valid_time.min() - parts["train"].valid_time.max()
    gap_bc = parts["test"].valid_time.min() - parts["validation"].valid_time.max()
    if gap_ab < pd.Timedelta(days=7) or gap_bc < pd.Timedelta(days=7):
        raise SystemExit("Embargo shorter than 7 days")

    summary = []
    for name, x in parts.items():
        ts = x.groupby("valid_time").size()
        summary.append({"period": name, "first_timestamp_utc": str(x.valid_time.min()), "last_timestamp_utc": str(x.valid_time.max()),
                        "rows": len(x), "timestamps": len(ts), "four_cell_timestamps": int((ts == 4).sum()),
                        "one_cell_timestamps": int((ts == 1).sum()), "positives": int(x.target_storm.sum()),
                        "positive_rate": float(x.target_storm.mean()),
                        "storm_hours": int(x.loc[x.target_storm == 1, "valid_time"].nunique()),
                        "storm_days_utc": int(x.loc[x.target_storm == 1, "valid_time"].dt.normalize().nunique()),
                        "days_utc": int(x.valid_time.dt.normalize().nunique()),
                        "cells": json.dumps({f"{la},{lo}": int(n) for (la, lo), n in x.groupby(["latitude", "longitude"]).size().items()})})
    pd.DataFrame(summary).to_csv(out / "period_summary.csv", index=False)
    log("Periods verified: row counts match design, no shared timestamps, embargoes >= 7 days")
    train, val, test = parts["train"], parts["validation"], parts["test"]
    climatology = float(train.target_storm.mean())

    # ------------------------------------------------------------ M1: train-only RF
    log(f"Fitting M1 (seed {PRIMARY_SEED}) on {len(train)} training rows")
    m1 = make_rf(rf_params, PRIMARY_SEED).fit(train[features], train.target_storm)
    p_val = m1.predict_proba(val[features])[:, 1]
    p_test = m1.predict_proba(test[features])[:, 1]

    vtab = threshold_table(val.target_storm.values, p_val)
    vtab.to_csv(out / "validation_threshold_table.csv", index=False)
    thr_primary = select_primary(vtab)
    thr_recall = select_recall_constrained(vtab)
    log(f"Validation-selected thresholds: primary(max F1)={thr_primary}, recall>={MIN_RECALL}: {thr_recall}", metric=True)

    # ------------------------------------------------------------ M2: deployed model test probabilities
    dep = pd.read_csv(DEPLOYED_TEST, usecols=["valid_time", "latitude", "longitude", "target_storm", "live_model_probability"])
    dep["valid_time"] = pd.to_datetime(dep["valid_time"])
    merged = test.merge(dep, on=["valid_time", "latitude", "longitude"], how="left", suffixes=("", "_dep"), validate="one_to_one")
    if merged.live_model_probability.isna().any() or not (merged.target_storm == merged.target_storm_dep.astype(int)).all():
        raise SystemExit("Deployed test predictions do not align with the test period")
    p_dep = merged.live_model_probability.values

    pred = pd.concat([
        val[["valid_time", "latitude", "longitude", "target_storm", "storm_label"]].assign(period="validation", m1_probability=p_val, deployed_probability=np.nan),
        test[["valid_time", "latitude", "longitude", "target_storm", "storm_label"]].assign(period="test", m1_probability=p_test, deployed_probability=p_dep)])
    pred.to_csv(out / "predictions_validation_test.csv.gz", index=False, compression="gzip")

    # ------------------------------------------------------------ evaluation table
    y_test = test.target_storm.values
    classifiers = {  # name -> (binary predictions on test, probability or None, role)
        "M1 @ validation-selected primary threshold": ((p_test >= thr_primary).astype(int), p_test, "PRIMARY"),
        "M1 @ validation-selected recall>=0.70 threshold": (((p_test >= thr_recall).astype(int) if thr_recall is not None else None), p_test, "SENSITIVITY"),
        "M1 @ 0.35 (deployed threshold; reference)": ((p_test >= DEPLOYED_THRESHOLD).astype(int), p_test, "REFERENCE"),
        "M1 @ 0.50 (default; reference)": ((p_test >= DEFAULT_THRESHOLD).astype(int), p_test, "REFERENCE"),
        "M2 deployed RF @ validation-selected primary threshold": ((p_dep >= thr_primary).astype(int), p_dep, "SECONDARY"),
        "M2 deployed RF @ 0.35 (test-tuned; optimistic reference)": ((p_dep >= DEPLOYED_THRESHOLD).astype(int), p_dep, "REFERENCE"),
        "M2 deployed RF @ 0.50 (default; reference)": ((p_dep >= DEFAULT_THRESHOLD).astype(int), p_dep, "REFERENCE"),
        "B1 always-negative baseline": (np.zeros(len(test), dtype=int), None, "BASELINE"),
        "B2 persistence baseline": (test.storm_label.values, None, "BASELINE"),
    }
    rows = []
    for name, (yhat, prob, role) in classifiers.items():
        if yhat is None:
            continue
        r = {"classifier": name, "role": role, "period": "test"}
        r.update(threshold_metrics(y_test, yhat))
        if prob is not None:
            r.update(probability_metrics(y_test, prob, climatology))
        rows.append(r)
    # validation-period rows for transparency (M1 is in-sample for threshold choice there)
    for name, yhat in {"M1 @ validation-selected primary threshold": (p_val >= thr_primary).astype(int),
                       "B2 persistence baseline": val.storm_label.values,
                       "B1 always-negative baseline": np.zeros(len(val), dtype=int)}.items():
        r = {"classifier": name, "role": "VALIDATION (threshold chosen here)", "period": "validation"}
        r.update(threshold_metrics(val.target_storm.values, yhat))
        if name.startswith("M1"):
            r.update(probability_metrics(val.target_storm.values, p_val, climatology))
        rows.append(r)
    metrics = pd.DataFrame(rows)
    metrics.to_csv(out / "test_metrics.csv", index=False)
    metrics[["classifier", "period", "TN", "FP", "FN", "TP"]].to_csv(out / "confusion_matrices.csv", index=False)
    log("Point metrics written", metric=False)

    # ------------------------------------------------------------ moving-block bootstrap over test days
    days = test.valid_time.dt.normalize()
    day_index = pd.factorize(days, sort=True)[0]
    n_days = day_index.max() + 1
    rng = np.random.default_rng(BOOT_SEED)
    boot_days = [block_bootstrap_days(n_days, rng) for _ in range(boot_b)]
    # per-day confusion counts for each binary classifier
    def per_day_counts(yhat):
        frame = pd.DataFrame({"d": day_index, "tp": (yhat == 1) & (y_test == 1), "fp": (yhat == 1) & (y_test == 0),
                              "fn": (yhat == 0) & (y_test == 1), "tn": (yhat == 0) & (y_test == 0)})
        return frame.groupby("d")[["tp", "fp", "fn", "tn"]].sum().reindex(range(n_days), fill_value=0).values
    boot_cls = {k: v for k, v in classifiers.items() if v[0] is not None}
    daily = {k: per_day_counts(v[0]) for k, v in boot_cls.items()}
    boot_scores = {}
    for name, arr in daily.items():
        sums = np.stack([arr[d].sum(axis=0) for d in boot_days])
        boot_scores[name] = scores_from_counts(*sums.T)
    # threshold-free bootstrap for M1 and M2 (row-level)
    rows_by_day = [np.flatnonzero(day_index == d) for d in range(n_days)]
    prob_boot = {"M1": {"roc_auc": [], "pr_auc": []}, "M2": {"roc_auc": [], "pr_auc": []}}
    for dsel in boot_days:
        idx = np.concatenate([rows_by_day[d] for d in dsel]); yb = y_test[idx]
        for key, prob in (("M1", p_test), ("M2", p_dep)):
            if yb.min() == yb.max():
                prob_boot[key]["roc_auc"].append(np.nan); prob_boot[key]["pr_auc"].append(np.nan); continue
            prob_boot[key]["roc_auc"].append(roc_auc_score(yb, prob[idx]))
            prob_boot[key]["pr_auc"].append(average_precision_score(yb, prob[idx]))

    def ci(values):
        v = np.asarray(values, dtype=float); v = v[np.isfinite(v)]
        return (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)), int(len(v))) if len(v) else (np.nan, np.nan, 0)

    ci_rows = []
    point = metrics[metrics.period == "test"].set_index("classifier")
    for name, sc in boot_scores.items():
        for metric in ["accuracy", "balanced_accuracy", "precision", "recall", "f1", "false_alarm_ratio", "csi"]:
            lo, hi, n = ci(sc[metric])
            ci_rows.append({"comparison": name, "metric": metric, "point": float(point.loc[name, metric]), "ci_low": lo, "ci_high": hi, "valid_resamples": n})
    for key, cname in (("M1", "M1 @ validation-selected primary threshold"), ("M2", "M2 deployed RF @ validation-selected primary threshold")):
        for metric in ["roc_auc", "pr_auc"]:
            lo, hi, n = ci(prob_boot[key][metric])
            ci_rows.append({"comparison": f"{key} (threshold-free)", "metric": metric, "point": float(point.loc[cname, metric]), "ci_low": lo, "ci_high": hi, "valid_resamples": n})
    # paired differences vs persistence
    pers = "B2 persistence baseline"
    diffs = {"M1 primary - persistence": "M1 @ validation-selected primary threshold",
             "M1 recall>=0.70 - persistence": "M1 @ validation-selected recall>=0.70 threshold",
             "M2 deployed @ primary - persistence": "M2 deployed RF @ validation-selected primary threshold",
             "M2 deployed @ 0.35 (test-tuned) - persistence": "M2 deployed RF @ 0.35 (test-tuned; optimistic reference)"}
    for label, cname in diffs.items():
        if cname not in boot_scores:
            continue
        for metric in ["f1", "recall", "precision", "csi"]:
            d = np.asarray(boot_scores[cname][metric]) - np.asarray(boot_scores[pers][metric])
            lo, hi, n = ci(d)
            ci_rows.append({"comparison": label, "metric": f"diff_{metric}", "point": float(point.loc[cname, metric] - point.loc[pers, metric]),
                            "ci_low": lo, "ci_high": hi, "valid_resamples": n})
    boot = pd.DataFrame(ci_rows)
    boot.to_csv(out / "bootstrap_ci.csv", index=False)
    log(f"Bootstrap complete ({boot_b} resamples of {math.ceil(n_days / BLOCK_DAYS)} x {BLOCK_DAYS}-day blocks over {n_days} test days)")

    # pre-registered criterion
    f1d = boot[(boot.comparison == "M1 primary - persistence") & (boot.metric == "diff_f1")].iloc[0]
    criterion = {"point_diff_f1": f1d.point, "ci_low": f1d.ci_low, "ci_high": f1d.ci_high,
                 "margin_met": bool(f1d.point >= MEANINGFUL_F1_MARGIN), "ci_excludes_zero": bool(f1d.ci_low > 0 or f1d.ci_high < 0),
                 }
    criterion["meaningful_improvement"] = bool(criterion["margin_met"] and f1d.ci_low > 0)

    # ------------------------------------------------------------ sensitivity analyses
    sens = []
    cell = (test.latitude == SINGLE_CELL[0]) & (test.longitude == SINGLE_CELL[1])
    yc = y_test[cell.values]
    for name, yhat, prob in [("single cell: M1 @ primary", (p_test[cell.values] >= thr_primary).astype(int), p_test[cell.values]),
                             ("single cell: M2 deployed @ primary", (p_dep[cell.values] >= thr_primary).astype(int), p_dep[cell.values]),
                             ("single cell: B2 persistence", test.storm_label.values[cell.values], None),
                             ("single cell: B1 always-negative", np.zeros(int(cell.sum()), dtype=int), None)]:
        r = {"analysis": "single grid cell (-30.25, 28.75), test", "classifier": name, "rows": int(cell.sum()), "positives": int(yc.sum())}
        r.update(threshold_metrics(yc, yhat))
        if prob is not None:
            r.update(probability_metrics(yc, prob, climatology))
        sens.append(r)
    seed_rows = [{"analysis": "seed stability", "seed": PRIMARY_SEED, "selected_threshold": thr_primary,
                  "test_f1": float(point.loc["M1 @ validation-selected primary threshold", "f1"]),
                  "test_pr_auc": float(point.loc["M1 @ validation-selected primary threshold", "pr_auc"]),
                  "test_roc_auc": float(point.loc["M1 @ validation-selected primary threshold", "roc_auc"])}]
    for seed in EXTRA_SEEDS:
        log(f"Fitting seed-stability model (seed {seed})")
        mdl = make_rf(rf_params, seed).fit(train[features], train.target_storm)
        pv = mdl.predict_proba(val[features])[:, 1]; pt = mdl.predict_proba(test[features])[:, 1]
        t = select_primary(threshold_table(val.target_storm.values, pv))
        seed_rows.append({"analysis": "seed stability", "seed": seed, "selected_threshold": t,
                          "test_f1": threshold_metrics(y_test, (pt >= t).astype(int))["f1"],
                          "test_pr_auc": average_precision_score(y_test, pt), "test_roc_auc": roc_auc_score(y_test, pt)})
        del mdl
    pd.DataFrame(sens).to_csv(out / "sensitivity_single_cell.csv", index=False)
    pd.DataFrame(seed_rows).to_csv(out / "sensitivity_seed_stability.csv", index=False)

    # ------------------------------------------------------------ provenance record
    hashes_after = {k: sha256(ROOT / k) for k in hashes_before}
    config = {
        "design_document": "evaluation_reports/RO3_ml_evaluation_design_2026-10-29.md",
        "run_utc": datetime.now(timezone.utc).isoformat(), "smoke_test": smoke,
        "periods_utc_start_inclusive_end_exclusive": PERIODS, "embargo_days": 7,
        "features": features, "rf_params_from_deployed_model": {k: (v if not isinstance(v, np.generic) else v.item()) for k, v in rf_params.items()},
        "primary_seed": PRIMARY_SEED, "extra_seeds": EXTRA_SEEDS, "n_jobs": -1,
        "threshold_grid": [float(GRID[0]), float(GRID[-1]), 0.01], "decision_rule": "probability >= threshold",
        "primary_rule": "max validation F1; ties -> higher threshold",
        "secondary_rule": f"among validation recall >= {MIN_RECALL}, max F1; ties -> higher threshold",
        "selected_thresholds": {"primary": thr_primary, "recall_constrained": thr_recall},
        "bootstrap": {"type": "moving block", "block_days": BLOCK_DAYS, "resamples": boot_b, "seed": BOOT_SEED, "ci": "percentile 95%"},
        "meaningful_improvement_criterion": {"margin_f1": MEANINGFUL_F1_MARGIN, "requires_ci_lower_bound_above_zero": True, "result": criterion},
        "train_climatology_for_brier": climatology,
        "inputs": inputs, "input_sha256_before": hashes_before, "input_sha256_after": hashes_after,
        "inputs_unchanged": hashes_before == hashes_after,
        "versions": {"python": sys.version.split()[0], "platform": platform.platform(), "numpy": np.__version__,
                     "pandas": pd.__version__, "scikit_learn": sklearn.__version__, "joblib": joblib.__version__},
        "runtime_seconds": round(time.time() - started, 1),
    }
    (out / "config.json").write_text(json.dumps(config, indent=2, default=str), encoding="utf-8")
    (out / "run_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    if not config["inputs_unchanged"]:
        raise SystemExit("Input files changed during the run")
    if smoke:
        print("SMOKE TEST OK: all stages executed; no metrics displayed.")
    else:
        log(f"Done. Meaningful-improvement criterion met: {criterion['meaningful_improvement']}", metric=True)


if __name__ == "__main__":
    main()
