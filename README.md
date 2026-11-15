# Ampere Leak

An operations analytics project for VoltRelay Energy, a simulated battery-swapping network across six Indian cities. The analysis connects service reliability, rider retention, and unit economics to a capital allocation decision.

## Findings

Across **3.81 million eligible attempts**, modeled contribution improved year over year, reaching **₹13.59 per completed swap** in 2025 H1. Reliability moved in the opposite direction versus the preceding half. The failure rate rose from **4.33% to 6.49%**, and a shortage of charged packs was the largest recorded failure category.

The recommendation is to test additional charged-pack availability at matched stations before committing capital. Evaluate recovered swaps, incremental contribution, and 30-day rider return against a predefined decision rule.

## Explore the results

- [Interactive scorecard](web/index.html) with monthly performance, a contribution bridge, cohort views, and a battery-pilot payback calculator
- [Executive report](web/analysis_report.html) covering the six core questions, evidence and recommendations
- [Colab notebook](ampere_leak_colab.ipynb) and [methods guide](METHODS.md) for analytical definitions and reproducibility

Open either HTML file in a browser to view it locally.

## Reproduce the analysis

Use Python 3.11 or 3.12. From the repository root in PowerShell, place the eight source tables in dataset/ or pass the original archive with -Dataset.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -Dataset .\dataset
```

The runner generates the audit, evidence, report, and scorecard in a fresh run directory and verifies the aggregate results. For Colab, set the project and data paths in the notebook setup cell.

## Deploy the website

In Vercel, import this repository and set **Root Directory** to **web**. Select **Other** as the framework preset, leave **Build Command** empty, and use **.** if an output directory is requested. The homepage is index.html and the report is available at /analysis_report.html. Review the competition’s sharing terms before deploying the embedded aggregates publicly. Use the event’s submission channel when public sharing is restricted.

## Data and interpretation

The source is the synthetic Gradient Learnings Data Analytics Hackathon dataset. Raw data, local run outputs, and video files are kept outside version control. Contribution includes modeled battery wear, and pilot scenarios depend on documented assumptions. The pricing, equipment, and retention findings are observational.
