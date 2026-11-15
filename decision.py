"""Build decision tables, an executive report, and a standalone HTML scorecard."""
import argparse
import collections as c
import csv
import datetime as dt
import html
import itertools
import json
import math
import statistics as stats
from pathlib import Path

from pipeline import write
from datetime import date, timedelta


def read(path,name):
    with (path/(name+".csv")).open(encoding="utf-8",newline="") as handle:
        return list(csv.DictReader(handle))


def total(rows,key):
    return math.fsum(float(r[key] or 0) for r in rows)


def ratio(a,b):
    return a/b if b else 0.0


def chi_survival(x, df):
    half = x/2
    if x == 0:
        return 1.0
    a = 0.5 if df%2 else 1
    tail = math.erfc(math.sqrt(half)) if df%2 else math.exp(-half)
    while a < df/2:
        tail += math.exp(a*math.log(half)-half-math.lgamma(a+1))
        a += 1
    return min(tail,1.0)


def csat_tests(rows,path):
    results = []
    for field in ("status","hours_bucket"):
        levels = c.defaultdict(lambda:[0,0])
        for r in rows:
            levels[r[field]][0] += int(r["responses"])
            levels[r[field]][1] += int(r["tickets"])-int(r["responses"])
        counts = [sum(t) for t in zip(*levels.values())]
        score = 0
        minimum = math.inf
        if min(counts) and len(levels)>1:
            for actual in levels.values():
                for observed,total_count in zip(actual,counts):
                    expected = sum(actual)*total_count/sum(counts)
                    score += (observed-expected)**2/expected
                    minimum = min(minimum,expected)
            results.append((field,score,len(levels)-1,chi_survival(score,len(levels)-1),minimum))
    write(path,"csat_tests",["feature","chi_square","df","p_value","min_expected"],results)
    return results


def price_study(rows,path,treatment,cutoff):
    by_city = c.defaultdict(lambda: [0]*4)
    monthly = c.defaultdict(lambda: [0,0])
    for r in rows:
        city, day, window = r["city"],r["day"],r["window"]
        attempts = int(float(r["attempts"]))
        index = 2*int(day >= cutoff)
        by_city[city][index] += attempts
        by_city[city][index+1] += attempts*(window=="peak")
        m = monthly[city,day[:7]]
        m[0] += attempts
        m[1] += attempts*(window=="peak")
    cities = sorted(by_city)
    changes = {k:ratio(post_peak,post)-ratio(pre_peak,pre)
               for k,(pre,pre_peak,post,post_peak) in by_city.items()}
    def estimate(treated):
        return stats.mean(changes[k] for k in treated)-stats.mean(changes[k] for k in cities if k not in treated)
    if not set(treatment)<set(cities):
        raise ValueError("Pilot cities require both treated and control observations")
    effect = estimate(treatment)
    placebo = [estimate(pair) for pair in itertools.combinations(cities,len(treatment))]
    p = sum(abs(v)>=abs(effect)-1.e-12 for v in placebo)/len(placebo)
    write(path,"pricing_did",["treated","post_from","effect_peak_share","permutation_tail_fraction","placebo_assignments"],
          [("|".join(treatment),cutoff,effect,p,len(placebo))])
    write(path,"pricing_parallel_trends",["city","month","pilot","attempts","peak_attempts","peak_share"],
          [(city,month,city in treatment,n,peak,ratio(peak,n)) for (city,month),(n,peak) in sorted(monthly.items())])
    diagnostics = []
    full = [r for r in rows if r["window"]=="peak"]
    cutoff_day = date.fromisoformat(cutoff)
    for scope in ("full","56_day_window"):
        grouped = c.defaultdict(list)
        for r in full:
            day = date.fromisoformat(r["day"])
            if scope=="56_day_window" and not cutoff_day-timedelta(days=56)<=day<cutoff_day+timedelta(days=56):
                continue
            grouped[r["city"],int(day>=cutoff_day)].append(r)
        for metric in ("peak_failure_rate","peak_abandonment_rate","log_peak_attempts_per_day"):
            changes = {}
            for city in cities:
                measures = []
                for phase in (0,1):
                    rr = grouped[city,phase]
                    attempts = total(rr,"attempts")
                    if metric=="peak_failure_rate":
                        v = ratio(attempts-total(rr,"completed"),attempts)
                    elif metric=="peak_abandonment_rate":
                        v = ratio(total(rr,"abandoned"),attempts)
                    else:
                        v = math.log(attempts/len(rr))
                    measures.append(v)
                changes[city] = measures[1]-measures[0]
            result = estimate(treatment)
            permutations = [estimate(pair) for pair in itertools.combinations(cities,len(treatment))]
            tail = sum(abs(v)>=abs(result)-1.e-12 for v in permutations)/len(permutations)
            diagnostics.append((scope,metric,result,tail))
    write(path,"pricing_did_outcomes",["period","metric","effect","city_reassignment_tail"],diagnostics)
    return effect,p


def retention_study(rows,path):
    monthly = c.defaultdict(lambda:[0,0,0])
    for r in rows:
        for key in ((r["signup_month"],r["city"]),(r["signup_month"],"Network")):
            v = monthly[key]
            for i,name in enumerate(("signups","eligible","retained")):
                v[i] += int(r[name])
    write(path,"retention_cohorts",["signup_month","city","signups","eligible","retained","retained_share"],
          [(*k,*v,v[2]/v[1] if v[1] else "") for k,v in sorted(monthly.items())])
    # Mantel-Haenszel common odds ratios adjusted by signup quarter, city and plan.
    drivers = []
    for feature in ("early_stockout","early_long_queue","early_low_soh","near_competitor","early_competitor_promo","early_attempt"):
        cells = c.defaultdict(lambda:[0]*4)
        for r in rows:
            if feature!="early_attempt" and not int(r["early_attempt"]):
                continue
            year,month = r["signup_month"].split("-")
            key = (year,(int(month)-1)//3,r["city"],r["plan"])
            offset = 2*(1-int(r[feature]))
            kept,eligible = int(r["retained"]),int(r["eligible"])
            cells[key][offset] += kept
            cells[key][offset+1] += eligible-kept
        nd,dd = 0,0
        for a,b,cc,d in cells.values():
            n = a+b+cc+d
            if n:
                nd += a*d/n
                dd += b*cc/n
        counts = [sum(group[i] for group in cells.values()) for i in range(4)]
        drivers.append((feature,*counts,nd/dd if dd else ""))
    write(path,"retention_drivers",["feature","exposed_retained","exposed_not_retained","unexposed_retained",
          "unexposed_not_retained","stratified_retention_odds_ratio"],drivers)
    eligible, retained = total(rows,"eligible"),total(rows,"retained")
    return int(eligible),ratio(retained,eligible),drivers


def fleet_study(rows,terms,path,capital_rate):
    summary = []
    for term in terms:
        records = [r for r in rows if r["partner_id"] == term["partner_id"]]
        rev, margin, n = (total(records,k) for k in ("revenue","contribution_inr","completed"))
        carry = rev*capital_rate*int(term["payment_days"])/365
        summary.append((term["partner_id"],term["name"],rev,n,margin,carry,margin-carry,
                        ratio(margin-carry,n),term["peak_billable"],term["payment_days"]))
    summary.sort(key=lambda r:r[2],reverse=True)
    write(path,"fleet_economics",["partner_id","name","revenue","completed","modeled_contribution",
          "working_capital_cost","adjusted_contribution","adjusted_per_swap","peak_billable","payment_days"],summary)
    return summary


def station_study(rows,dimensions,coverage,path):
    out = []
    for station in dimensions:
        sid = station["station_id"]
        records = [r for r in rows if r["station_id"] == sid and r["month"] >= "2025-01"]
        cov = coverage.get(sid,{})
        obs,zero = [float(cov.get(k,0)) for k in ("observed_2w","stockout_2w")]
        out.append((sid,station["city"],station["wave"],station["host"],len(records),total(records,"completed"),
                    total(records,"attempts"),total(records,"stockout_fail"),total(records,"contribution_inr"),obs,
                    zero/obs if obs else ""))
    out.sort(key=lambda r:r[7],reverse=True)
    write(path,"station_priority",["station_id","city","wave","host","months_in_2025H1","completed_h1","attempts_h1",
          "no_pack_failures_h1","contribution_h1","observed_2w_hours_full_period","observed_2w_stockout_rate_full_period"],out)
    waves = []
    for wave in sorted({r[2] for r in out}):
        rr = [r for r in out if r[2]==wave and r[4]]
        months, completed, failures, margin = (sum(r[i] for r in rr) for i in (4,5,7,8))
        waves.append((wave,len(rr),months,completed,ratio(completed,months),failures,margin))
    write(path,"expansion_waves",["wave","stations","station_months","completed","completed_per_station_month",
          "no_pack_failures","contribution"],waves)
    return out,waves


def scenarios(path,config,stations,margin,whale,half):
    top = stations[:math.ceil(len(stations)*.2)]
    recoverable = sum(r[7] for r in top)/6
    all_recoverable = sum(r[7] for r in stations)/6
    rows = []
    for case,scale in config["recovery_multipliers"].items():
        for option in config["options"]:
            basis = option["basis"]
            recovery = 0
            if basis in {"top_stockouts","all_stockouts"}:
                opportunity = recoverable if basis=="top_stockouts" else all_recoverable
                recovery = opportunity*min(1,option["recovery_share"]*scale)
                gross = recovery*margin
            elif basis == "pricing":
                gross = half["completed"] / 6 * option["increment_per_swap"] * scale
            else:
                gross = whale[2] / 18 * option["incremental_revenue_share"] * scale
            net = gross-option["monthly_opex"]
            capex = option["capex"]
            rows.append((case,option["option"],capex,recovery,gross,net,
                         capex/net if net>0 else "",(12*net-capex)/capex if capex else "",
                         recovery/(half["attempts"]/6)*100))
    write(path,"roi_scenarios",["case","option","capex","recovered_swaps_month","gross_gain_month","net_gain_month",
          "payback_months","year1_roi","failure_rate_pp_improvement_at_fixed_demand"],rows)
    return rows


def analyze(path,config):
    monthly = read(path,"monthly")
    halves = {r["period"]:{k:float(v) for k,v in r.items() if k!="period" and v}
              for r in read(path,"half_year")}
    old,new = [halves[p] for p in ("2024H1","2025H1")]
    for r in (old,new):
        n = r["completed"]
        r["pricing_residual"] = r["revenue"]-r["list_price"]+r["discount"]
    bridge = []
    for metric,sign in (("list_price",1),("discount",-1),("pricing_residual",1),
                        ("energy",-1),("wear",-1),("fixed_op_ex",-1)):
        start = sign*old[metric]/old["completed"]
        end = sign*new[metric]/new["completed"]
        bridge.append((metric,start,end,end-start))
    residual = new["contribution_per_swap"]-old["contribution_per_swap"]-sum(r[3] for r in bridge)
    assert abs(residual)<0.00002, f"Margin bridge reconciliation failed: {residual}"
    write(path,"margin_bridge",["component","2024H1_inr_per_swap","2025H1_inr_per_swap","delta_inr_per_swap"],bridge)

    effect,p = price_study(read(path,"pricing_daily"),path,config["pilot_cities"],config["pilot_start"])
    n,retention,drivers = retention_study(read(path,"retention_cells"),path)
    cs = csat_tests(read(path,"csat_strata"),path)
    fleet = fleet_study(read(path,"fleet"),read(path,"fleet_terms"),path,config["annual_capital_rate"])
    stations,waves = station_study(read(path,"station_month"),read(path,"station_dimension"),
                                 {r["station_id"]:r for r in read(path,"station_coverage")},path)
    unit_variable_margin = (new["revenue"]-new["energy"]-new["wear"])/new["completed"]
    roi = scenarios(path,config,stations,unit_variable_margin,max(fleet,key=lambda row:row[3]),new)
    half = read(path,"half_year")
    audits = {r["check"]:int(r["affected"]) for r in read(path,"forensic_audit")}
    assert audits["noncompleted"]==sum(int(r["attempts"]) for r in read(path,"attempt_outcomes") if r["outcome"]!="swap_completed")
    assert abs(total(monthly,"revenue")-total(half,"revenue"))<.1
    validate = {"monthly_revenue_ties_to_half_year":True,"audit_failures_tie_to_outcomes":True,
                "margin_bridge_ties":True,"months":len(monthly)}
    (path/"validation.json").write_text(json.dumps(validate,indent=2),encoding="utf-8")
    return old,new,bridge,effect,p,n,retention,drivers,cs,fleet,stations,waves,roi,audits,monthly


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence",type=Path)
    parser.add_argument("--config",type=Path,default=Path(__file__).with_name("assumptions.json"))
    args = parser.parse_args()
    analyze(args.evidence,json.loads(args.config.read_text(encoding="utf-8-sig")))
