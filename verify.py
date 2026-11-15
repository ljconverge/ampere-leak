"""Validate cross-table identities using only the aggregate evidence."""
import argparse
import json
import math
from pathlib import Path

from decision import read, total


def require(condition, description):
    if not condition:
        raise ValueError(description)


def verify(path):
    manifest = json.loads((path/"manifest.json").read_text())
    require(len(manifest["source_sha256"])==64,"Source digest is absent")
    totals = read(path,"half_year")
    monthly = read(path,"monthly")
    sites = read(path,"station_month")
    outcomes = read(path,"attempt_outcomes")
    audit = {r["check"]:r for r in read(path,"forensic_audit")}
    require(len(monthly)==18,"Expected 18 months")
    require(total(monthly,"attempts")==total(outcomes,"attempts"),"Event count mismatch")
    require(total(monthly,"completed")==sum(int(x["attempts"]) for x in outcomes if x["outcome"]=="swap_completed"),"Completion count mismatch")
    require(int(audit["event_test"]["denominator"])==total(outcomes,"attempts")+sum(int(audit[k]["affected"])
        for k in ("event_test","offline_duplicate","outside_window","event_unmatched_dimension")),"Raw swap partition mismatch")
    for field in ("attempts","completed","revenue","energy","wear","fixed_op_ex"):
        for cube in (totals,sites):
            require(math.isclose(total(monthly,field),total(cube,field),abs_tol=.02),"Cube mismatch for "+field)
    for key,row in audit.items():
        require(0<=int(row["affected"])<=int(row["denominator"]),"Invalid audit denominator for "+key)
    for r in read(path,"retention_cohorts"):
        require(0<=int(r["retained"])<=int(r["eligible"])<=int(r["signups"]),"Invalid retention partition")
    for r in read(path,"station_coverage"):
        for vw in ("2w","3w"):
            require(0<=int(r["stockout_"+vw])<=int(r["observed_"+vw])<=int(r["hours"]),"Invalid telemetry partition")
    bridge = total(read(path,"margin_bridge"),"delta_inr_per_swap")
    old,new = [next(float(r["contribution_per_swap"]) for r in totals if r["period"]==p) for p in ("2024H1","2025H1")]
    require(math.isclose(new-old,bridge,abs_tol=2e-5),"Bridge mismatch")
    matched = {r["check"]:int(r["rows"]) for r in read(path,"matched_pack_coverage")}
    require(matched["completed_records"] == total(monthly,"completed"),"Pack study completion mismatch")
    require(matched.get("valid_discharge_and_distance",0)==total(read(path,"matched_pack_range"),"pairs"),"Pack matches mismatch")
    print("Passed: source manifest and aggregate checks for outcomes, finance, audit, coverage, retention, and pack matches")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence",type=Path)
    verify(parser.parse_args().evidence)
