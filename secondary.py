"""Secondary analyses on disclosed aggregates. No event-level exports."""
import collections as c
import math

from decision import read, total, ratio
from pipeline import write


def survival(path):
    curves = c.defaultdict(lambda: c.defaultdict(lambda:[0,0]))
    for r in read(path,"return_survival_cells"):
        for key in (("network","all"),("city",r["city"]),("plan",r["plan"]),("signup_month",r["month"])):
            curves[key][int(r["age"])][int(r["event"])] += int(r["riders"])
    results = []
    for (scope,label),counts in sorted(curves.items()):
        risk = sum(sum(v) for v in counts.values())
        s = 1
        variance = 0
        for age,(censored,events) in sorted(counts.items()):
            s *= 1-events/risk
            if events and risk>events:
                variance += events/(risk*(risk-events))
            se = s*math.sqrt(variance)
            results.append((scope,label,age,risk,events,censored,1-s,max(0,1-s-1.96*se),min(1,1-s+1.96*se)))
            risk -= censored+events
    write(path,"return_km",["scope","group","day","risk","first_returns","censored","return_probability",
          "lower_wald","upper_wald"],results)


def logistic(path):
    import numpy as np

    rows = [r for r in read(path,"retention_cells") if int(r["eligible"]) and int(r["early_attempt"])]
    numeric = ("early_stockout","early_long_queue","early_low_soh","near_competitor","early_competitor_promo",
               "first_week_attempts_cap10")
    categorical = ("signup_month","city","plan","channel","kyc")
    levels = [(key,value) for key in categorical for value in sorted({r[key] for r in rows})[1:]]
    names = ["intercept",*numeric,*[f"{key}={value}" for key,value in levels]]
    x = np.array([[1,*[float(r[n]) for n in numeric],*[float(r[key]==value) for key,value in levels]] for r in rows])
    n = np.array([int(r["eligible"]) for r in rows])
    y = np.array([int(r["retained"]) for r in rows])
    beta = np.zeros(x.shape[1])
    penalty = np.diag([0]+[1]*(x.shape[1]-1))
    for i in range(100):
        prob = 1/(1+np.exp(-np.clip(x@beta,-35,35)))
        information = (x.T*(n*prob*(1-prob)))@x + penalty
        step = np.linalg.solve(information,x.T@(y-n*prob)-penalty@beta)
        beta += step
        if np.max(np.abs(step))<1.e-8:
            break
    else:
        raise RuntimeError("Retention model did not converge")
    se = np.sqrt(np.diag(np.linalg.inv(information)))
    results = zip(names,beta,np.exp(beta),np.exp(beta-1.96*se),np.exp(beta+1.96*se))
    write(path,"retention_logit",["feature","coefficient","adjusted_odds_ratio","approx_lower","approx_upper"],results)


def secondary(path):
    survival(path)
    logistic(path)
    opening_comparison(path)
    thermal = read(path,"thermal_hourly")
    stratified_thermal(path,thermal)
    groups = c.defaultdict(list)
    for row in thermal:
        groups[row["ambient_band"],row["cabinet_band"]].append(row)
    summary = []
    for k, rr in sorted(groups.items()):
        summary.append((*k,int(total(rr,"hours")),ratio(total(rr,"charge_minutes_sum"),total(rr,"charge_n")),
                        ratio(total(rr,"quarantine_sum"),total(rr,"quarantine_n")),
                        ratio(total(rr,"stockout_2w"),total(rr,"observed_2w")),
                        ratio(total(rr,"stockout_3w"),total(rr,"observed_3w"))))
    write(path,"thermal_summary",["ambient_band","cabinet_band","hours","mean_charge_minutes","mean_quarantined",
                                  "2w_stockout_share","3w_stockout_share"],summary)
    lots = read(path,"battery_lots")
    supplier = c.defaultdict(list)
    for r in lots:
        supplier[r["supplier"],r["pack_type"]].append(r)
    summ = []
    for k, rows in sorted(supplier.items()):
        n = total(rows,"packs")
        summ.append((*k,n,total(rows,"returns"),ratio(total(rows,"retired"),n),
                     ratio(total(rows,"return_soh_sum"),total(rows,"return_soh_n")),
                     ratio(total(rows,"snapshot_soh_loss_sum"),total(rows,"snapshot_pairs"))))
    write(path,"supplier_summary",["supplier","pack_type","packs","returns","retired_share",
                                  "mean_return_soh","mean_snapshot_soh_loss"],summ)
    rank = sorted(([r["supplier"],r["pack_type"],r["lot"],r["firmware"],int(float(r["packs"])),
                   ratio(float(r["snapshot_soh_loss_sum"]),float(r["snapshot_pairs"])),
                   ratio(float(r["retired"]),float(r["packs"]))] for r in lots if float(r["packs"])>=20),key=lambda r:r[5],reverse=True)
    write(path,"lot_watchlist",["supplier","pack_type","lot","firmware","packs","mean_snapshot_loss","retired_share"],rank)
    halves = read(path,"half_year")
    amendments = read(path,"amendment_discount")
    fixed = read(path,"fixed_by_wave")
    rows = []
    for r in halves:
        phase = r["period"]
        n = float(r["completed"])
        rows.append((phase, "contract_discount_on_post_amendment_swaps",
                     total([x for x in amendments if x["period"]==phase],"actual_discount")/n))
        for wave in sorted({x["wave"] for x in fixed}):
            rows.append((phase,"fixed_cost_"+wave,total([x for x in fixed if x["period"]==phase and x["wave"]==wave],"station_opex")/n))
        for life in (1000,1500,2200):
            rev, energy,wear,op = (float(r[x]) for x in ("revenue","energy","wear","fixed_op_ex"))
            rows.append((phase,f"modeled_contribution_{life}_equivalent_cycles",(rev-energy-wear*1500/life-op)/n))
    write(path,"cost_diagnostics",["period","metric","inr_per_completed_swap"],rows)

def opening_comparison(path):
    """Compare nearby launch hubs with never-near controls around monthly openings."""
    dimensions = read(path,"station_dimension")
    site_months = {(r["station_id"],r["month"]):r for r in read(path,"station_month")}
    months = sorted({month for _,month in site_months})
    launch = [s for s in dimensions if s["wave"]=="Launch"]
    expansions = [s for s in dimensions if s["wave"]!="Launch"]

    def km(a,b):
        def radians(row,field):
            return math.radians(float(row[field]))
        x,y = radians(a,"latitude"),radians(b,"latitude")
        z = radians(a,"longitude")-radians(b,"longitude")
        h = math.sin((x-y)/2)**2+math.cos(x)*math.cos(y)*math.sin(z/2)**2
        return 12742*math.asin(min(1,math.sqrt(h)))

    near = {}
    for hub in launch:
        sid = hub["station_id"]
        candidates = []
        for site in expansions:
            if hub["city"]!=site["city"]:
                continue
            distance = km(hub,site)
            if distance>1.5:
                continue
            match = [month for month in months if float(site_months.get((site["station_id"],month),{}).get("fixed_op_ex",0))>0]
            if match:
                candidates.append((match[0],distance,site["station_id"],site["wave"]))
        near[sid] = min(candidates) if candidates else None
    results = []
    for hub in launch:
        sid = hub["station_id"]
        opening = near[sid]
        if opening is None:
            continue
        month,distance,expansion,wave = opening
        index = months.index(month)
        if index<2 or index+2>=len(months):
            continue
        pre,post = months[index-2:index],months[index+1:index+3]
        def measure(hub_id,window):
            rr = [site_months[hub_id,m] for m in window if (hub_id,m) in site_months]
            n = total(rr,"attempts")
            return (ratio(total(rr,"stockout_fail"),n),n) if n else None
        before,after = measure(sid,pre),measure(sid,post)
        if before is None or after is None:
            continue
        controls = []
        for other in launch:
            tid = other["station_id"]
            if other["city"]!=hub["city"] or near[tid] is not None:
                continue
            a,b=measure(tid,pre),measure(tid,post)
            if a and b:
                controls.append((abs(math.log(a[1]/before[1])),tid,b[0]-a[0],a[0],b[0]))
        if controls:
            _,control,change,cb,ca = min(controls)
            results.append((sid,hub["city"],expansion,wave,month,distance,control,before[0],after[0],cb,ca,after[0]-before[0]-change))
    write(path,"opening_comparison",["launch_hub","city","expansion_station","wave","opening_month","distance_km",
        "comparison_hub","hub_pre","hub_post","control_pre","control_post","relative_no_pack_failure_rate_change"],
        sorted(results))
    return results


def stratified_thermal(path, thermal):
    cells = c.defaultdict(dict)
    for row in thermal:
        if row["ambient_band"]=="35C+" and row["cabinet_band"] in {"45C+","<45C"}:
            key=tuple(row[x] for x in ("city","generation","hour"))
            cells[key][row["cabinet_band"]]=row
    results=[]
    for measure,num,denom in (("mean_charge_minutes","charge_minutes_sum","charge_n"),
                             ("mean_quarantined","quarantine_sum","quarantine_n"),
                             ("2w_stockout_probability","stockout_2w","observed_2w")):
        effects=[]
        for pair in cells.values():
            if len(pair)!=2:
                continue
            hot,cool = pair["45C+"],pair["<45C"]
            a,b = float(hot[denom]),float(cool[denom])
            if min(a,b)>=30:
                effects.append((float(hot[num])/a-float(cool[num])/b,min(a,b)))
        if effects:
            results.append((measure,len(effects),sum(d*w for d,w in effects)/sum(w for _,w in effects)))
    write(path,"thermal_stratified",["metric","city_generation_hour_strata","weighted_hot_minus_cool"],results)
