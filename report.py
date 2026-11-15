"""Generate executive artifacts from verified evidence."""
import argparse
import collections as c
import html
import json
import subprocess
import sys
from pathlib import Path

import decision as d
from secondary import secondary


def format_pct(r):
    return f"{100*r:.2f}%"


def money(amount):
    return f"â‚¹{amount:,.2f}" if amount>=0 else f"âˆ’â‚¹{abs(amount):,.2f}"


def table(headers,rows):
    return "\n".join(["| "+" | ".join(headers)+" |","| "+" | ".join(["---"]*len(headers))+" |",
                      *["| "+" | ".join(map(str,row))+" |" for row in rows]])


def report(path,out,config,analysis):
    old,new,bridge,effect,p,n,retention,drivers,cs,fleet,stations,waves,roi,audits,monthly = analysis
    look = lambda name: d.read(path,name)
    half = {r["period"]:r for r in look("half_year")}
    py = float(half["2024H2"]["failure_rate"])
    rank = look("lot_watchlist")
    hot = look("thermal_summary")
    comparison = [r for r in hot if r["ambient_band"]=="35C+" and r["cabinet_band"] in {"45C+","<45C"}]
    opening_pairs = look("opening_comparison")
    opening_effect = d.ratio(d.total(opening_pairs,"relative_no_pack_failure_rate_change"),len(opening_pairs))
    opening_result = (f"Among matched sites, the mean relative change in no-pack failure rates was **{opening_effect*100:+.2f} pp**."
                      if opening_pairs else "The available windows produced no matched estimate.")
    contrasted_heat = look("thermal_stratified")
    retention_model = {r["feature"]:r for r in look("retention_logit")}
    eligible = sum(int(r["eligible"]) for r in look("retention_cohorts") if r["city"]=="Network")
    stockout_or = float(retention_model["early_stockout"]["adjusted_odds_ratio"])
    net = [r for r in roi if r[0]=="base"]
    zipdrop = next(r for r in fleet if r[0]=="FP-03")
    partner_rows = [r for r in look("fleet") if r["partner_id"]=="FP-03"]
    battery_case = next(r for r in net if "battery" in r[1].lower())
    payback = f"{battery_case[6]:.1f} months" if battery_case[6]!="" else "no finite payback"
    lot = rank[0]
    matched = look("matched_pack_range")
    matched_coverage = {r["check"]:int(r["rows"]) for r in look("matched_pack_coverage")}
    total_fail = sum(int(r["attempts"]) for r in look("attempt_outcomes") if r["outcome"]!="swap_completed")
    no_pack = next(int(r["attempts"]) for r in look("attempt_outcomes") if r["outcome"]=="failed_no_charged_battery")
    cov = look("telemetry_coverage")
    coverage = {tier:d.ratio(sum(int(r["hours"]) for r in cov if r["connectivity"]==tier and r["status"]=="ok"),
                            sum(int(r["hours"]) for r in cov if r["connectivity"]==tier)) for tier in ("good","fair","poor")}
    text = f"""# Ampere Leak
## Executive analysis of VoltRelay Energy Â· January 2024 to June 2025

### Decision

Defer broad station expansion, system-wide pricing, and an exclusive fleet deal at current terms. Evaluate a small matched-station battery float pilot, with scale contingent on measured net uplift and an approved payback threshold. The base case for the illustrative float budget has **{payback}** under fixed-demand assumptions and loses money in the downside case. Prioritize launch hubs by absolute no-pack failures, then qualify sites with telemetry coverage and comparable control stations.

### 1 Â· Volume, failures and unit economics

{table(["Metric","2024 H1","2024 H2","2025 H1"],[(label,*values) for label,values in [
("Completed swaps",[f'{float(r["completed"]):,.0f}' for r in half.values()]),
("Gross receipts (â‚¹ million)",[f'{float(r["revenue"])/1e6:.2f}' for r in half.values()]),
("Failure rate",[format_pct(float(r["failure_rate"])) for r in half.values()]),
("Modeled contribution per completed swap",[money(float(r["contribution_per_swap"])) for r in half.values()]),
("Failed-attempt list value (â‚¹ million)",[f'{float(r["lost_list_proxy"])/1e6:.2f}' for r in half.values()])]])}

2025 H1 completed swaps were **{new['completed']/old['completed']:.2f}Ã—** 2024 H1 volume. Failure rate rose **{(new['failure_rate']-py)*100:.2f} percentage points** from 2024 H2 and remained below 2024 H1. The failure count still grew with volume. The sum of listed prices on failed attempts is an opportunity bound before accounting for retry overlap, recovery rate and willingness to pay.

{table(["2024 H1 to 2025 H1 bridge","Change per completed swap"],[(label,money(delta)) for (key,_,_,delta),label in zip(bridge,["Listed price and mix","Booked discounts","Billing and price reconciliation residual","Energy per swap","Modeled battery wear","Station fixed OpEx per swap"])])}

The bridge reconciles to **{money(new['contribution_per_swap']-old['contribution_per_swap'])}**. Listed price and mix combine base prices, vehicle mix, plan mix and tariff mix. The billing residual is the gap between recognized revenue and list less discount and needs invoice reconciliation. Energy uses recharge kWh times the stationâ€™s supplied tariff. Wear uses replacement cost times the returned packâ€™s state-of-charge deficit divided by 1,500 equivalent full cycles. Fixed cost is rent and maintenance prorated to station operating days, including station-months with no swaps. Review cycle-life sensitivity and cost by wave in `cost_diagnostics.csv`. Contribution excludes corporate overhead, tax, financing and other unprovided costs. Fleet economics include a separate working-capital charge.

### Forensic audit

{table(["Check","Affected","Denominator","Share"],[(r["check"],f'{int(r["affected"]):,}',f'{int(r["denominator"]):,}',f'{float(r["percent"]):.2f}%' if r["percent"] else "â€”") for r in look("forensic_audit")])}

Firmware corrections use the raw date window and add 330 minutes. The offline rule uses corrected timestamps and complete four-ID keys, retaining a successful event when the cluster includes one. No qualifying duplicate clusters survived the rule on this archive. City normalization matched all rider records. The odometer masks use a class-specific p99 and separately identify negatives. Observed telemetry coverage was {format_pct(coverage['good'])} for good connectivity and {format_pct(coverage['poor'])} for poor connectivity. The 3W denominator consists of hours with valid readings, so its observed stockout rate only describes measured coverage.

CSAT is missing on **{audits['csat_missing']:,}** production tickets. Response missingness varies with resolution status and duration (Pearson Ï‡Â² **{cs[0][1]:,.0f}** and **{cs[1][1]:,.0f}**, both p < 0.001). Compare respondent means within resolution strata and show response rates. Evidence on recorded resolution factors alone cannot identify MNAR. The eligible app and other comments mostly describe generic vehicle or app problems. Zero uniquely supported target labels is an audit finding. Review suggestions require human validation before use.

### 2â€“3 Â· Network bottlenecks, heat and expansion

No charged pack accounts for **{no_pack:,} of {total_fail:,}** non-completions across the study. `station_priority.csv` ranks hubs by no-pack failures, with volume, stockout coverage and contribution beside the ranking. `spatial_hourly.csv` gives queue sums and counts by city, site type, charger generation, class and hour. Convert queue seconds to means using observed queues.

{table(["Wave","Stations with activity","Completed per station-month","No-pack failures"],[(r[0],r[1],f'{r[4]:,.0f}',f'{r[5]:,.0f}') for r in waves])}

Lower throughput at expansion sites can reflect newer age, location mix, and ramp-up. The geographic screen identified **{len(opening_pairs)} matched launch hubs** within 1.5 km of an expansion opening with two full months on each side. {opening_result} Controls are launch hubs in the same city with similar pre-opening attempts and no nearby expansion. Reused controls, site selection, availability of matches, demand displacement, and co-occurring changes limit attribution.

{table(["Cabinet band on 35Â°C+ days","Hours","Mean charge minutes","Mean quarantined","2W observed stockout"],[(r["cabinet_band"],f'{int(r["hours"]):,}',f'{float(r["mean_charge_minutes"]):.1f}',f'{float(r["mean_quarantined"]):.2f}',format_pct(float(r["2w_stockout_share"]))) for r in comparison])}

{table(["Hot-minus-cool comparison within city, charger generation and hour","Strata","Weighted difference"],[(r["metric"],r["city_generation_hour_strata"],f'{float(r["weighted_hot_minus_cool"]):+.3f}') for r in contrasted_heat])}

Heat bands are descriptive. Afternoon demand, generation, site type, maintenance, and missing telemetry can move with temperature. Verify a cabinet threshold and matched within-station lag before attributing a stockout cascade to thermal derating.

### 4 Â· Pack and lot forensics

`supplier_summary.csv` compares pack types within each supplier. `lot_watchlist.csv` ranks lots and firmware cells with at least 20 packs. The leading watchlist cell is **{lot['supplier']} {lot['lot']} ({lot['pack_type']})**, with **{float(lot['mean_snapshot_loss']):.1f} points** of average initial-to-current SoH loss across **{lot['packs']}** packs. Inspect commissioning age, use intensity, thermal history and retirement reasons before attributing quality failure to the supplier. Pack snapshots and event-return SoH are distinct measures. `battery_cycle_curves.csv` groups return SoH by cumulative measured returns within the study. These are usage proxies with left-truncated histories. `battery_exposure.csv` adds age bins and returns on heat-alert days. A return on a heat-alert day measures ambient exposure rather than pack or cabinet temperature.

The prior-issue linkage identified **{matched_coverage.get('matched_pack_return',0):,}** same-pack returns within 30 days, of which **{matched_coverage.get('valid_discharge_and_distance',0):,}** had usable distance, SoC discharge, and issued SoH. The aggregation uses the immediately preceding completed event for that rider and an explicit minimum five-point discharge. It conditions on successful linkage and may not represent the full rider base.

{table(["Class","Issued SoH band","Matched pairs","Mean km/SoC point"],[(r["vehicle"],r["issued_soh_band"],f'{int(r["pairs"]):,}',f'{float(r["mean_km_per_soc_pp"]):.3f}') for r in matched])}

### 5 Â· Pricing pilot and fleet contract

Indexed to the earliest pilot tariff month, the two-city DiD estimates **{effect*100:+.2f} percentage points** for the share of attempts in the tariff-derived peak hours. The comparison uses Bengaluru and Pune versus four cities, city-weighted. The city reassignment tail fraction is **{p:.3f}** across only 15 assignments. The plot is a pretrend diagnostic. See the secondary failure, abandonment, and daily peak volume estimates at full and 56-day bandwidths. Neither city selection nor price exposure by billing class was randomized, and the estimate measures peak share rather than a demand elasticity. Partner exemptions, seasonality and firmware correction can affect interpretation.

**{fleet[0][1]}** ranked first on revenue and had **{money(fleet[0][6])}** after modeled costs and working capital. **ZipDrop** had more completed swaps, and its modeled gap was **{money(zipdrop[6])}** after working capital. Its recorded discount rose from 12% to 28% on November 1, 2024, peak surcharge billing is exempt, and terms are 45 days.

{table(["ZipDrop contract period","Revenue","Modeled contribution / swap"],[(r["contract_period"],money(float(r["revenue"])),money(float(r["contribution_per_swap"]))) for r in partner_rows])}

Require a contribution floor, peak pass-through and volume floors before considering an exclusive. Verify invoice treatment and working-capital terms against contracts. Observed pre/post contribution also reflects changing volume, station mix and pack utilization.

### 6 Â· New-rider returns

**{format_pct(retention)}** of **{eligible:,}** riders eligible for 30 full days completed a swap between signup days 14 and 30. Late signups remain visible in cohort sizes and are censored in the time-to-return view. The Kaplanâ€“Meier output estimates time to first completed return on or after day 14, with up to day 60 observation. It measures return timing rather than an irreversible churn event.

Among first-week attempters, the adjusted odds ratio for early stockout and retention was **{stockout_or:.2f}**. The model adjusts for first-week attempt frequency, signup month, city, plan, channel, KYC, and observed first-week exposures. `retention_logit.csv` includes approximate model intervals. Observational coefficients can reflect unmeasured experience, rider activity and selection. Use controlled station interventions to estimate retention lift.

### Budget alternatives and 30â€“60â€“90 days

{table(["Base case","Monthly net impact","Recovered swaps/month","Failure reduction","Payback"],[(r[1],money(r[5]),f'{r[3]:,.0f}',f'{r[8]:.2f} pp',f'{r[6]:.1f} months' if r[6]!="" else "â€”") for r in net])}

All capital, operating, recovery, and commercial scenario inputs are editable assumptions. The pricing rollout uses zero incremental unit uplift until economics are demonstrated. The exclusive case applies an illustrative additional concession to the highest-volume partner. Payback uses net recurring contribution at constant demand. No retention benefit is credited in the ROI.

- **Day 30.** Reconcile the billing residual and confirm tariff windows. Baseline top no-pack hubs and assign matched controls. Inspect the leading lot before making a quarantine or supplier decision.
- **Day 60.** Trial a small float reallocation and targeted quality checks. The full modeled interventionâ€™s base-case reference is **{battery_case[3]:,.0f} recoveries/month**, **{battery_case[8]:.2f} pp** lower network failure at fixed attempts, and **{money(battery_case[5])}/month** net. Scale pilot targets by the share of baseline stockouts it covers. Track the day-14â€“30 return metric and set a **+1 pp** evaluation target as a planning threshold.
- **Day 90.** Review pilot contribution and out-of-sample service impact, assess effects on 30-day return with completed follow-up, and roll forward only the intervention that clears the agreed operating and payback thresholds. Bring revised ZipDrop terms to committee.

### Scope and verification

The archive-backed results include three reconciliations for outcomes, monthly receipts, and the margin bridge. They are a decision-analysis release with illustrative costs and pilot identification assumptions. Remaining evidence gaps include verified price-change dates and peak billing records, pack-level cabinet exposure, lifetime usage before the study, and a spatial causal test for new openings. See the method notes for operational controls and known limitations.
"""
    (out/"executive_report.md").write_text(text,encoding="utf-8")
    return {"headline": f"{new['completed']:,.0f} completed Â· {format_pct(new['failure_rate'])} failure rate Â· {money(new['contribution_per_swap'])} modeled contribution per swap in 2025 H1",
            "old_yield":old["contribution_per_swap"], "new_yield":new["contribution_per_swap"],
            "pilot_pp":100*effect,"no_pack":no_pack,"float_payback":battery_case[6] if battery_case[6]!="" else None,"top_lot":lot["lot"],
            "retention_or":stockout_or,"roi_net":battery_case[5]}


def main(evidence,out,config):
    out.mkdir(parents=True,exist_ok=True)
    result = d.analyze(evidence,config)
    secondary(evidence)
    summary = report(evidence,out,config,result)
    from scorecard import build
    build(evidence,out,summary)
    from media import build as build_media
    build_media(out,summary)
    subprocess.run([sys.executable,"-B",str(Path(__file__).with_name("render_report.py")),str(evidence),str(out)],check=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence",type=Path)
    parser.add_argument("out",type=Path)
    parser.add_argument("--config",type=Path,default=Path(__file__).with_name("assumptions.json"))
    args=parser.parse_args()
    main(args.evidence,args.out,json.loads(args.config.read_text(encoding="utf-8-sig")))
