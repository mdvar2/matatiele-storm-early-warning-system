# Final master refinement: evidence (1 November 2026)

## Integrity

| Check | Result |
|---|---|
| Model, 29-feature list, threshold file | Identical to `main`; held-out probabilities reproduced (largest difference 1.1 × 10⁻¹⁶); threshold 0.35 ([model_unchanged.json](model_unchanged.json)) |
| Worker behaviour | 21/21 scenarios identical ([equivalence_r3.txt](equivalence_r3.txt)) |
| Model evidence | `25_build_model_evidence.py --check` passes ([evidence_check.txt](evidence_check.txt)) |
| Tests | Run 1: **393 passed** ([test_run1.txt](test_run1.txt)). Run 2 under a network guard: **393 passed**, 0 outbound attempts ([test_run2.txt](test_run2.txt)). |
| SMS | No live SMS sent. Public subscriber delivery is still off (`SUBSCRIBER_ALERTS_ENABLED` and `OUTLOOK_ALERTS_ENABLED` default to `false`). |

**Note on the test runs:** one guarded run that overlapped a browser capture had a single failure (`test_official_reviews_a_warning_with_aggregate_acknowledgements`); that run took 5 min 28 s instead of about 3 min. The test passed alone, and the repeated guarded run passed all 393.

## Real-browser checks ([browser_live_checks.json](browser_live_checks.json))

| Item | Result |
|---|---|
| Supplied valley image in the header | Loaded (139 KB, from `Stormy Valley Overlook.png`, SHA-256 starting `ca5c893e`); header 128 px on desktop and 130 px on phones, which use the 33 KB version; tooltip "Illustrative Matatiele storm landscape artwork — not current weather." |
| Live pulse | Computed animation `ring`; the ring's shadow changes between samples |
| Countdown | "Next refresh in 14:37" became "14:34" after 3 s, ticking on the device |
| Clock | 01:53:53 became 01:53:56 |
| Gauge | No sweep on first load. A sweep only when the genuine score changes (AppTest: 5% → 27% sweeps; a repeat run does not). |
| Reduced motion | Pulse and live dot animations `none` |
| Stale state | Admin connectivity demonstration: "Saved data · last update …" in amber, no pulse, NO DECISION, OUT OF DATE ([screenshot](screenshots/light_desktop_stale_demo.png)); back to "System online" with the pulse afterwards |
| Phone 390 × 800 | Header 130 px; risk score ends at 509 px and the warning decision at 725 px, both on the first screen; no overflow |
| Offline page, network cut | "No connection: showing the last saved information. Saved … SAST", with the decision and emergency numbers |

**Bug found by browser verification and fixed:** a CSS declaration containing `<number>` caused Streamlit's HTML sanitiser to drop the **entire stylesheet**. The automated tests could not see this, because they inspect the HTML before the browser sanitises it. It is now written as a CSS escape (`\3C number>`), and `StylesheetSurvivesTheSanitiser` guards against it. The browser checks also found that reduced motion did not stop the "Live forecast data" dot; that is fixed as well.

## Terminology

- **User interface:** "Storm probability" → "Model risk score" (Risk Analysis gauge, history table and chart); "No severe weather warning issued…" → "No storm warning issued by this research system"; the system-design diagram is updated.
- **Left unchanged:** the console messages of the older pipeline scripts, `12_live_forecast_and_predict.py` and the worker's `sms_alert.py` were deliberately not edited, so the live script and the worker stay verified as unchanged.
