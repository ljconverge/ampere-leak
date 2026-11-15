"""Generate submission copy with claims tied to the evidence snapshot."""


def build(out,s):
    payback = f"{s['float_payback']:.0f} months" if s["float_payback"] is not None else "no finite payback"
    pilot = f"{s['pilot_pp']:+.1f}"
    old, new = f"{s['old_yield']:,.2f}",f"{s['new_yield']:,.2f}"
    video = f"""# Ampere Leak · Three-minute executive script

| Time | Visual | Spoken narrative |
| --- | --- | --- |
| 0:00–0:15 | Open on monthly failure rate | “VoltRelay has two stories to tell. More riders completed swaps, and unit economics improved. Yet service got worse compared with the previous half. We went through 3.88 million source records to understand how both could be true.” |
| 0:15–0:30 | Split volume and failure cards | “In the first half of 2025, the network completed 1.70 million swaps. The failure rate rose from 4.33% to 6.49% versus the previous half. The earlier 2024 comparison gives a different baseline, so we show all three periods.” |
| 0:30–0:45 | Forensic audit | “We isolated test stations, corrected 139,490 firmware timestamps, and checked whether missing station readings might bias stockout rates. The report shows exactly which rows enter each denominator.” |
| 0:45–1:00 | Margin waterfall | “The modeled contribution goes from ₹{old} to ₹{new} per completed swap year over year. Fixed cost per swap and lower energy cost help explain that change. Booked discounts offset part of the improvement.” |
| 1:00–1:15 | Station priority table | “Across the study, no charged pack accounts for {s['no_pack']:,} failed attempts. That gives us a starting point for action. We rank hubs by failure counts and check inventory telemetry before selecting sites.” |
| 1:15–1:30 | Thermal and battery views | “Hot cabinet hours and battery lots deserve inspection. We compare observed performance and flag lot {s['top_lot']} for review. An unusual cohort can also reflect age, usage or firmware, so a lot ranking is a screening tool.” |
| 1:30–1:45 | Pilot trends | “Bengaluru and Pune shifted relative to comparison cities by {pilot} percentage points on peak attempt share. With six cities and nonrandom selection, the pilot leaves uncertainty about how a rollout would affect demand and revenue.” |
| 1:45–2:00 | FeastFly and ZipDrop economics | “FeastFly led on receipts and remained positive after modeled costs. ZipDrop completed more swaps and was negative after a working-capital charge. The commercial terms matter as much as the volume ranking.” |
| 2:00–2:15 | Cohorts and retention odds ratio | “We follow new riders through days 14 to 30 and account for incomplete follow-up. Early stockout exposure has an adjusted odds ratio of {s['retention_or']:.2f}. A controlled test can establish whether better availability improves returns.” |
| 2:15–2:30 | Budget matrix | “The targeted float scenario has base-case payback of {payback} and a downside loss. A small pilot can test recovery rates and operating costs before leadership commits the full capital.” |
| 2:30–2:45 | Trial design | “For day 30, reconcile the numbers and pair stations. By day 60, measure recovered swaps, incremental contribution and inventory health. Keep the retention tracking window open long enough for the last cohort.” |
| 2:45–3:00 | Dashboard and closing recommendation | “By day 90, fund only the interventions that clear the payback gate. Renegotiate fleet terms using fully loaded economics. That gives VoltRelay a way to protect service and verify that every expansion rupee earns its place.” |

Allow a short pause after each percentage and currency figure. Keep the dashboard visible during the closing.
"""
    linkedin = f"""# Ampere Leak · LinkedIn launch copy

## Post

A battery-swapping network completed 2.43× as many swaps year over year. Its failure rate still rose from **4.33% to 6.49%** against the previous half.

Both comparisons are true. Putting them side by side changed the budget conversation.

For the Gradient Learnings hackathon, I analyzed VoltRelay Energy’s six-city operation using 3.88 million source swap records. I built an audit trail for test stations, firmware shifts and missing telemetry, then followed the evidence into unit economics, rider retention and fleet contracts.

Three findings stood out.

- Across the study, **{s['no_pack']:,} failed attempts** recorded no charged pack.
- The revenue leader stayed positive after modeled costs. The highest-volume partner turned negative after working capital.
- A targeted battery float had **{payback}** of base-case payback and lost money in the downside scenario. I’d test it at matched hubs before funding it at scale.

What would you require from a 60-day trial before approving more batteries or another station?

#DataAnalytics #OperationsAnalytics #EVInfrastructure #UnitEconomics

## Carousel copy

1. **Volumes rose. Service slipped.** Show the three half-year baselines.
2. **The forensic audit** — test stations, timestamp correction and why 3W telemetry coverage matters.
3. **₹{old} to ₹{new} per completed swap** — present the modeled margin bridge.
4. **Where demand went unserved** — show the ranked hub chart and no-pack failure count.
5. **The fleet ranking changes after cost** — compare FeastFly and ZipDrop on revenue, completed swaps and working-capital-adjusted margin.
6. **What the pricing pilot tells us** — annotate the {pilot} pp estimate and six-city limitation.
7. **A capital decision with a downside case** — show the scenarios and matched-station trial gate.
8. **The question for operators** — what payback and service evidence should the board require?

Share only the aggregate figures and visuals from the scorecard, subject to the competition’s dataset sharing terms.
"""
    (out/"video_script.md").write_text(video,encoding="utf-8")
    (out/"linkedin_launch.md").write_text(linkedin,encoding="utf-8")
