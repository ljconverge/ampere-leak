# Analyst walkthrough

## From raw data to a decision

1. **Establish the grain.** An event is an attempt. A telemetry row is one reported station hour. A support row is one ticket. A rider has one signup date. A battery record is a snapshot with commissioning details. Join these grains explicitly. Adding a ticket or telemetry join directly to every event can duplicate charges.
2. **Reconcile counts.** Open forensic_audit.csv and attempt_outcomes.csv. Raw attempts equal test rows plus any duplicate, out-of-window, or unmatched rows plus analytical attempts. The audit percentages use the count presented to each check. They are not additive.
3. **Separate service and finance.** The failure denominator includes all analytical attempts. Gross receipts count only completed swaps. Every calendar month keeps prorated rent and maintenance for active sites even when those sites had zero completed swaps. The receipt, energy, wear and station-cost ledger reconciles between month, half-year, and station-month outputs.
4. **Diagnose location and timing.** Queue records aggregate by service attributes. Compare observed inventory stockouts by class with observed-hours coverage. Follow large absolute failure counts with demand estimates and station-level operating context.
5. **Study riders and batteries at their own grain.** The returned-pack SoH metric uses the pack returned on a swap. The paired metric compares distance with the preceding issue of that same pack, when observable. A rider can contribute many swaps to the event data and only one response to a signup cohort. The population eligible for the logistic model is restricted to first-week attempters with 30 days of possible observation.
6. **Translate into a decision.** Distinguish observed facts, statistical associations, and simulated interventions. The payback grid converts recovered swaps into contribution using the current observed variable value per completed swap, then subtracts assumed recurring costs and divides investment by the net gain. Report no finite payback when the monthly gain is nonpositive.

## Evidence tables by question

| What you want to inspect | Main files | Important denominator |
| --- | --- | --- |
| Input provenance and audit | manifest.json, forensic_audit.csv, attempt_outcomes.csv, odometer_thresholds.csv, soc_drift.csv | Check-specific populations |
| Network and profitability | monthly.csv, half_year.csv, margin_bridge.csv, cost_diagnostics.csv | Attempts for failures, completed swaps for unit economics |
| Capacity and seasonality | spatial_hourly.csv, station_priority.csv, station_coverage.csv, telemetry_coverage.csv, thermal_hourly.csv, thermal_stratified.csv | Queue readings, observed stockout hours, or active station-months |
| Expansion | expansion_waves.csv, station_month.csv, opening_comparison.csv | Months with station records, nearby openings with complete windows |
| Pack and range | supplier_summary.csv, battery_lots.csv, lot_watchlist.csv, battery_cycle_curves.csv, battery_exposure.csv, matched_pack_range.csv | Pack snapshots, measured returns, or successfully matched pack pairs |
| Rider and support | retention_cohorts.csv, retention_logit.csv, retention_drivers.csv, return_km.csv, csat_strata.csv, csat_tests.csv, ticket_root_causes.csv | Eligibility window, model population, or valid respondents by stratum |
| Pilot and partners | tariff_mix.csv, pricing_parallel_trends.csv, pricing_did.csv, pricing_did_outcomes.csv, fleet_economics.csv, fleet.csv, fleet_terms.csv | City-level changes and completed partner swaps |
| Budget | roi_scenarios.csv and assumptions.json | Monthly normalized 2025 H1 demand and finance |

## How to defend the methodology

- Show the three half-year rows before describing the reversal. Year-over-year growth and sequential reliability deterioration answer different questions.
- Point to the CSV ledger and bridge when challenged on contribution. Explain that observed energy cost per swap can move with usage and network mix. Debit actual discounts, show unresolved price reconciliation separately, and avoid allocating unobserved tariff or contract effects.
- Explain your exposure windows. Pricing treatment is assigned by city and date; peak hours are inferred from tariff codes. First-week rider exposures precede the day 14–30 return outcome. The Kaplan–Meier curve assumes administrative censoring at data cutoff or day 60. The city reassignment exercise is a sensitivity measure under a hypothetical exchangeable-city design.
- Use associations to select a test. An early stockout coefficient, a hot-cabinet difference, or a satellite opening comparison can motivate a controlled trial. Establish causality through assignment, controls and a defined primary outcome.
- Explain why narrowly specified anomaly checks can return zeros. An offline record needs all four identifiers and a matching neighbor in the permitted time gap. Ambiguous app and vehicle complaints need review before a root cause is assigned.
- Use the system as a batch analysis. Measure pipeline execution time and memory in your target environment, configure protected storage, and use a deployment-specific scheduler and service-monitoring policy before recurring publication.

## Release checks

- Run verify.py on the evidence and confirm the manifest exists.
- Verify the dashboard and report agree on the 2025 H1 KPIs. Check the dashboard filters and downside ROI scenario.
- Review the report for current source and scenario assumptions. Retain the prior verified version so a failed refresh can be rolled back.
- For a public demo, check the license or competition terms, review aggregates and small cells, and verify the public URL in a signed-out browser.
