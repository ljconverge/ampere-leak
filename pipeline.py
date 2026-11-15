"""Stream the VoltRelay source ZIP into reproducible, aggregate-only evidence."""
import argparse
import calendar
import collections as c
import csv
import datetime as dt
import hashlib
import gzip
import io
import json
import math
import re
import tempfile
import zipfile
from pathlib import Path

PEAK_HOURS = {12, 13, 19, 20, 21, 22}
START, END = "2024-01-01", "2025-06-30"
RULES = {
    "battery": r"battery jaldi|mileage kam|range issue|battery drain|low range|range kam",
    "stockout": r"stock.?out|no charged|battery nahi mil|charged pack unavailable",
    "hardware": r"cabinet lock|jammed|door stuck|hardware fault",
    "billing": r"overcharg|refund|double charg|billing|paise kat|amount galat",
}
FAILURES = {"failed_no_charged_battery", "abandoned_queue", "cancelled_by_rider", "failed_system_error"}
FIELDS = ("attempts completed revenue energy wear wear_covered list_price discount "
          "lost_list_proxy stockout_fail abandoned queue_seconds queue_observed fixed_op_ex").split()


def number(value):
    return float(value) if value else None


def write(path, name, header, rows):
    with (path / (name + ".csv")).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


TABLES = ("swap_events","station_hourly_status","riders","batteries","support_tickets",
          "stations","city_daily_context","fleet_partners")


class Dataset:
    def __init__(self,source):
        self.source=source

    def __enter__(self):
        self.zip = None if self.source.is_dir() else zipfile.ZipFile(self.source)
        return self

    def __exit__(self,*args):
        if self.zip:
            self.zip.close()

    def namelist(self):
        return self.zip.namelist() if self.zip else [
            p.relative_to(self.source).as_posix() for p in self.source.rglob("*") if p.is_file()]

    def open(self,key):
        stream=self.zip.open(key) if self.zip else (self.source/key).open("rb")
        if key.endswith(".gz"):
            stream.close()
            if not self.zip:
                return gzip.open(self.source/key,"rb")
            # GzipFile does not own its file object. Nest the wrappers explicitly.
            return NestedGzip(self.zip.open(key))
        return stream


class NestedGzip(gzip.GzipFile):
    def close(self):
        source = self.fileobj
        try:
            super().close()
        finally:
            if source is not None:
                source.close()


def member_name(archive,name):
    matches=[key for key in archive.namelist() if Path(key).name in {name+".csv",name+".csv.gz"}]
    if len(matches)!=1:
        raise ValueError(f"{name}: expected exactly one CSV or CSV.GZ, found {matches}")
    return matches[0]


def fingerprint(dataset):
    digest=hashlib.sha256()
    for name in sorted(TABLES):
        key=member_name(dataset,name)
        with dataset.open(key) as handle:
            header=handle.readline().decode("utf-8-sig")
            if not header.strip():
                raise ValueError(f"{name}: header is empty")
            digest.update(name.encode()+b":"+
                          hashlib.sha256(header.encode()+hashlib.file_digest(handle,"sha256").digest()).digest())
    return digest.hexdigest()


def table(archive, name, required):
    with archive.open(member_name(archive,name)) as member:
        reader = csv.DictReader(io.TextIOWrapper(member, encoding="utf-8-sig"))
        missing = set(required.split()) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{name}: missing fields {sorted(missing)}")
        yield from reader


def dimension(archive, name, key, required):
    result = {}
    for row in table(archive, name, required + " " + key):
        if not row[key] or row[key] in result:
            raise ValueError(f"{name}: blank or duplicate {key}")
        result[row[key]] = row
    return result


def percentile(counts, q):
    if not counts:
        return None
    position = q * (sum(counts.values()) - 1)
    lower, upper = math.floor(position), math.ceil(position)
    running = 0
    a = None
    for value, count in sorted(counts.items()):
        running += count
        if a is None and lower < running:
            a = value
        if upper < running:
            return a + (value - a) * (position - lower)


def offline_drops(offline):
    drops = set()
    for events in offline.values():
        events.sort()
        winner = previous = None
        for stamp, event, done in events:
            if previous is None or (stamp - previous).total_seconds() > 180:
                winner = (event, done)
            elif done or not winner[1]:
                drops.add(winner[0])
                winner = (event, done)
            else:
                drops.add(event)
            previous = stamp
    return drops


def period(month):
    return "2024H1" if month < "2024-07" else "2024H2" if month < "2025-01" else "2025H1"


def write_cube(path, name, keys, cube):
    rows = []
    for key, values in sorted(cube.items()):
        record = dict(zip(FIELDS, values))
        n = record["completed"]
        attempts = record["attempts"]
        margin = record["revenue"] - record["energy"] - record["wear"] - record["fixed_op_ex"]
        rows.append([*key, *[round(v, 6) for v in values],
                     round((attempts-n)/attempts, 8) if attempts else "",
                     round(margin, 4), round(margin/n, 6) if n else ""])
    write(path, name, [*keys, *FIELDS, "failure_rate", "contribution_inr", "contribution_per_swap"], rows)


def main(source, out):
    if not source.exists():
        raise FileNotFoundError(f"Input does not exist: {source.resolve()}")
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("Use an empty output directory")
    with tempfile.TemporaryDirectory(dir=out.parent) as staging, Dataset(source) as archive:
        digest = fingerprint(archive)
        path = Path(staging)
        print("Validating source tables and indexing forensic checks", flush=True)
        analyze(archive, path)
        (path / "manifest.json").write_text(json.dumps({"source_sha256": digest, "fingerprint_kind": "ordered logical tables v1", "first_day": START,
             "last_day": END, "currency": "INR", "pipeline": "1.0.0"}, indent=2))
        for item in sorted(path.iterdir(), key=lambda p: p.name == "manifest.json"):
            item.replace(out / item.name)
        print(f"Published evidence to {out}", flush=True)


def analyze(z, path):
    stations = dimension(z, "stations", "station_id", "city location_type host_type expansion_wave charger_generation connectivity_tier commissioned_date decommissioned_date monthly_rent_inr monthly_maintenance_inr grid_tariff_inr_kwh competitor_within_1_5km_since")
    riders = dimension(z, "riders", "rider_id", "vehicle_class home_city signup_date signup_channel plan_type kyc_verified partner_id")
    packs = dimension(z, "batteries", "battery_id", "supplier manufacturing_lot pack_type bms_firmware initial_soh_pct current_soh_pct purchase_cost_inr retired_date commission_date")
    from pack_study import PackStudy
    pack_study = PackStudy(packs)
    fleet = dimension(z, "fleet_partners", "partner_id", "partner_name amendment_date discount_pct discount_pct_after_amendment peak_surcharge_billable payment_terms_days")
    context = {(r["city"], r["date"]): r for r in table(z, "city_daily_context", "city date max_temp_c heat_alert competitor_promo_active")}
    audit = c.Counter()
    totals = c.Counter()
    canonical = {re.sub("[^a-z]", "", s["city"].lower()): s["city"] for s in stations.values()}
    canonical.update(dict.fromkeys(["blr", "bangalore"], "Bengaluru"))
    canonical.update(dict.fromkeys(["delhi", "newdelhi", "gurgaon", "ncr"], "Delhi NCR"))
    canonical.update({"hyd":"Hyderabad","pun":"Pune","mum":"Mumbai","bombay":"Mumbai","jai":"Jaipur"})
    for rider in riders.values():
        raw = rider["home_city"]
        rider["canonical"] = canonical.get(re.sub("[^a-z]", "", raw.lower()), "")
        audit["city_unmapped"] += not rider["canonical"]
        audit["city_normalized"] += bool(rider["canonical"]) and raw != rider["canonical"]
        rider["signup"] = dt.date.fromisoformat(rider["signup_date"])
    totals["riders"] = len(riders)
    for s in stations.values():
        s["tariff"] = float(s["grid_tariff_inr_kwh"])
        s["fixed"] = float(s["monthly_rent_inr"]) + float(s["monthly_maintenance_inr"])
    fields = ("event_id rider_id station_id event_ts event_type queue_wait_sec battery_in_id battery_out_id "
              "soc_in_pct soc_out_pct soh_in_pct soh_out_pct km_since_last_swap tariff_code "
              "list_price_inr discount_inr amount_charged_inr energy_to_recharge_kwh station_firmware sync_mode")
    offline = c.defaultdict(list)
    completed_offline = {}
    distances = c.defaultdict(c.Counter)
    shift_start, shift_end = "2025-03-10", "2025-04-15"

    def adjusted(r):
        stamp = r["event_ts"]
        if r["station_firmware"] == "v3.2.0" and shift_start <= stamp[:10] < shift_end:
            return (dt.datetime.fromisoformat(stamp) + dt.timedelta(minutes=330)).isoformat(sep=" ")
        return stamp

    for r in table(z, "swap_events", fields):
        totals["events"] += 1
        if r["station_id"].startswith("STN-TST"):
            audit["event_test"] += 1
            continue
        rider = riders.get(r["rider_id"])
        vehicle = rider["vehicle_class"] if rider else "unknown"
        done = r["event_type"] == "swap_completed"
        km = number(r["km_since_last_swap"]) if done else None
        if r["sync_mode"] == "offline_batch":
            audit["offline_batch_rows"] += 1
            key = tuple(r[k] for k in ("rider_id","station_id","battery_in_id","battery_out_id"))
            if all(key):
                audit["offline_batch_complete_key"] += 1
                event = r["event_id"]
                offline[key].append((dt.datetime.fromisoformat(adjusted(r)), event, done))
                if km is not None and km >= 0:
                    completed_offline[event] = (vehicle, km)
        if km is not None and km >= 0:
            distances[vehicle][km] += 1

    print(f"Indexed {totals['events']:,} source swap events", flush=True)
    drops = offline_drops(offline)
    audit["offline_duplicate"] = len(drops)
    for event in drops:
        if event in completed_offline:
            vehicle, km = completed_offline[event]
            distances[vehicle][km] -= 1
    limits = {vehicle: percentile(+counts, .99) for vehicle, counts in distances.items()}
    del offline, distances, completed_offline
    write(path, "odometer_thresholds", ["vehicle_class","p99_km"], sorted(limits.items()))
    monthly, half, station_month, spatial, partner, pricing = [c.defaultdict(lambda: [0.0]*len(FIELDS)) for _ in range(6)]
    outcomes, tariffs, drift = c.Counter(), c.Counter(), c.Counter()
    pack_totals = c.defaultdict(lambda: [0.0]*6)
    ranges = c.defaultdict(lambda: [0.0, 0.0])
    cohort = c.defaultdict(lambda: [False]*7)
    dates = {}
    first_repeat = {}
    first_seven_attempts = c.Counter()
    amendments = c.defaultdict(float)
    fixed_by_wave = c.defaultdict(float)
    for r in table(z, "swap_events", fields):
        sid = r["station_id"]
        if sid.startswith("STN-TST"):
            continue
        stamp = adjusted(r)
        audit["firmware_shift"] += stamp != r["event_ts"]
        if r["event_id"] in drops:
            continue
        day, month, hour = stamp[:10], stamp[:7], int(stamp[11:13])
        if not START <= day <= END:
            audit["outside_window"] += 1
            continue
        station = stations.get(sid)
        rider = riders.get(r["rider_id"])
        if station is None or rider is None:
            audit["event_unmatched_dimension"] += 1
            continue
        outcome = r["event_type"]
        done = outcome == "swap_completed"
        if not done and outcome not in FAILURES:
            audit["unknown_outcome"] += 1
        outcomes[outcome] += 1
        vehicle = rider["vehicle_class"]
        soh_in, soh_out = number(r["soh_in_pct"]), number(r["soh_out_pct"])
        soc_in, soc_out = number(r["soc_in_pct"]), number(r["soc_out_pct"])
        if (soc_in or 0) > 100 or (soc_out or 0) > 100:
            audit["soc_drift"] += 1
            drift[sid,r["station_firmware"],"affected"] += 1
        drift[sid,r["station_firmware"],"rows"] += 1
        km = number(r["km_since_last_swap"])
        negative = km is not None and km < 0
        high = km is not None and limits.get(vehicle) is not None and km > limits[vehicle]
        audit["odometer_negative"] += negative
        audit["odometer_upper"] += high
        if done:
            hot = context.get((station["city"],day),{}).get("heat_alert") == "True"
            pack_study.add(r["rider_id"],stamp,vehicle,r["battery_in_id"],r["battery_out_id"],soc_in,soh_in,soc_out,soh_out,
                           km if not (negative or high) else None,hot)
        amount = number(r["amount_charged_inr"]) if done else None
        kwh = number(r["energy_to_recharge_kwh"]) if done else None
        listed = number(r["list_price_inr"])
        discount = number(r["discount_inr"]) if done else None
        queue = number(r["queue_wait_sec"])
        pack = packs.get(r["battery_in_id"]) if done else None
        wear, covered = 0.0, False
        if done:
            audit["completed_missing_price"] += amount is None
            audit["completed_missing_energy"] += kwh is None
            tariffs[station["city"], month, r["tariff_code"], "completed"] += 1
        if pack:
            p = pack_totals[r["battery_in_id"]]
            p[0] += 1
            if soh_in is not None:
                p[1] += min(100, soh_in)
                p[2] += 1
            if soc_in is not None and soc_in >= 0:
                # kWh throughput proxy: returned pack deficit, 1500 equivalent full cycles.
                wear = float(pack["purchase_cost_inr"]) * (1 - min(100, soc_in)/100) / 1500
                covered = True
                p[3] += wear
        audit["completed_wear_uncovered"] += done and not covered
        # Delivered distance belongs to the previously issued pack. Track it separately below.
        if done:
            audit["completed_missing_returned_pack"] += pack is None
        if done and km is not None and not negative and not high and soh_in is not None:
            bucket = "<82" if soh_in < 82 else "82–89" if soh_in < 90 else "90+"
            v = ranges[vehicle,bucket]
            v[0] += km
            v[1] += 1
        pid = rider["partner_id"]
        fleet_row = fleet.get(pid)
        bill_period = "post" if fleet_row and fleet_row["amendment_date"] and day >= fleet_row["amendment_date"] else "base"
        if done and bill_period == "post":
            amendments[period(month),pid] += discount or 0
        values = (1, int(done), amount or 0, (kwh or 0)*station["tariff"], wear, int(covered),
                  (listed or 0) if done else 0, discount or 0, (listed or 0) if not done else 0,
                  int(outcome == "failed_no_charged_battery"), int(outcome == "abandoned_queue"),
                  queue or 0, int(queue is not None))
        for target in (monthly[(month,)], half[(period(month),)], station_month[(sid,month)],
                       spatial[(station["city"],station["location_type"],station["charger_generation"],vehicle,hour)],
                       partner[(pid or "Retail",bill_period)], pricing[(station["city"],day,"peak" if hour in PEAK_HOURS else "other")]):
            for i, value in enumerate(values):
                target[i] += value
        signup = rider["signup"]
        if START <= rider["signup_date"] <= END:
            event_date = dates.get(day)
            if event_date is None:
                event_date = dates[day] = dt.date.fromisoformat(day)
            age = (event_date-signup).days
            state = cohort[r["rider_id"]]
            if 0 <= age <= 6:
                first_seven_attempts[r["rider_id"]] += 1
                state[0] |= outcome == "failed_no_charged_battery"
                state[1] |= (queue or 0) > 300
                state[2] |= done and soh_out is not None and soh_out < 82
                state[3] |= True
                state[4] |= bool(station["competitor_within_1_5km_since"] and station["competitor_within_1_5km_since"] <= day)
                state[5] |= context.get((station["city"],day),{}).get("competitor_promo_active") == "True"
            state[6] |= done and 14 <= age <= 30
            if done and age >= 14:
                rid = r["rider_id"]
                first_repeat[rid] = min(age,first_repeat.get(rid,age))
    station_fixed = c.defaultdict(float)
    for sid, station in stations.items():
        if sid.startswith("STN-TST"):
            continue
        for year, month_num in [(2024,m) for m in range(1,13)] + [(2025,m) for m in range(1,7)]:
            month = f"{year}-{month_num:02d}"
            days = calendar.monthrange(year,month_num)[1]
            first, last = month+"-01",f"{month}-{days}"
            begin = max(first,station["commissioned_date"])
            end = min(last,station["decommissioned_date"] or last)
            if begin > end:
                continue
            active = (dt.date.fromisoformat(end)-dt.date.fromisoformat(begin)).days+1
            fixed = station["fixed"] * active/days
            monthly[(month,)][-1] += fixed
            half[(period(month),)][-1] += fixed
            station_month[(sid,month)][-1] += fixed
            station_fixed[sid,month] = fixed
            fixed_by_wave[period(month),station["expansion_wave"]] += fixed
    print(f"Aggregated {sum(outcomes.values()):,} analytical attempts", flush=True)
    # Allocate fixed cost to the fleet using completed swaps at the same station-month.
    partner_fixed(z, fields, drops, adjusted, stations, riders, fleet, station_month, station_fixed, partner)
    write_cube(path,"monthly",["month"],monthly)
    write_cube(path,"half_year",["period"],half)
    write_cube(path,"station_month",["station_id","month"],station_month)
    write_cube(path,"spatial_hourly",["city","location_type","charger_generation","vehicle_class","hour"],spatial)
    write_cube(path,"fleet",["partner_id","contract_period"],partner)
    write_cube(path,"pricing_daily",["city","day","window"],pricing)
    write(path,"tariff_mix",["city","month","tariff_code","state","rows"],[(*k,v) for k,v in sorted(tariffs.items())])
    write(path,"attempt_outcomes",["outcome","attempts"],sorted(outcomes.items()))
    write(path,"soc_drift",["station_id","firmware","affected","denominator"],
          [(sid,fw,drift[sid,fw,"affected"],v) for (sid,fw,kind),v in sorted(drift.items()) if kind=="rows"])
    write(path,"range_proxy",["vehicle","returned_soh_band","total_km","rows"],[(*k,*v) for k,v in sorted(ranges.items())])
    pack_output(path,packs,pack_totals)
    print("Building matched-pack trajectories and support diagnostics", flush=True)
    pack_study.export(path)
    retention_output(path,riders,cohort,first_seven_attempts,first_repeat)
    write(path,"amendment_discount",["period","partner","actual_discount"],[(*k,v) for k,v in sorted(amendments.items())])
    write(path,"fixed_by_wave",["period","wave","station_opex"],[(*k,v) for k,v in sorted(fixed_by_wave.items())])
    telemetry(z,path,stations,context,audit,totals)
    tickets(z,path,audit,totals)
    write(path,"station_dimension",["station_id","city","wave","host","charger","latitude","longitude"],
          [(sid,s["city"],s["expansion_wave"],s["host_type"],s["charger_generation"],s["latitude"],s["longitude"]) for sid,s in stations.items() if not sid.startswith("STN-TST")])
    write(path,"fleet_terms",["partner_id","name","amendment_date","discount_pct","amended_discount_pct","peak_billable","payment_days"],
          [(pid, p["partner_name"],p["amendment_date"],p["discount_pct"],p["discount_pct_after_amendment"],p["peak_surcharge_billable"],p["payment_terms_days"]) for pid,p in fleet.items()])
    audit_output(path,audit,totals,sum(outcomes.values()),outcomes["swap_completed"])

def partner_fixed(z, fields, drops, adjusted, stations, riders, fleet, station_month, station_fixed, partner):
    allocations = c.Counter()
    for r in table(z,"swap_events",fields):
        sid, rid = r["station_id"], r["rider_id"]
        if (r["event_type"] != "swap_completed" or sid.startswith("STN-TST")
                or sid not in stations or rid not in riders or r["event_id"] in drops):
            continue
        day = adjusted(r)[:10]
        if not START <= day <= END:
            continue
        pid = riders[rid]["partner_id"]
        amendment = fleet.get(pid, {}).get("amendment_date")
        allocations[sid,day[:7],pid or "Retail","post" if amendment and day >= amendment else "base"] += 1
    for (sid,month,pid,phase), n in allocations.items():
        partner[pid,phase][-1] += station_fixed[sid,month]*n/station_month[sid,month][1]


def pack_output(path,packs,observed):
    groups = c.defaultdict(lambda: [0.0]*9)
    for bid, pack in packs.items():
        key = tuple(pack[x] for x in ("supplier","pack_type","manufacturing_lot","bms_firmware"))
        v = groups[key]
        n, total, measured, wear, _, _ = observed.get(bid,[0]*6)
        v[0] += 1
        v[1] += n
        v[2] += bool(pack["retired_date"] and pack["retired_date"] <= END)
        v[3] += total
        v[4] += measured
        v[5] += wear
        initial, final = number(pack["initial_soh_pct"]),number(pack["current_soh_pct"])
        if initial is not None and final is not None:
            v[6] += initial-final
            v[7] += 1
            v[8] += initial
    write(path,"battery_lots",["supplier","pack_type","lot","firmware","packs","returns","retired",
        "return_soh_sum","return_soh_n","modeled_wear","snapshot_soh_loss_sum","snapshot_pairs","initial_soh_sum"],
        [(*k,*v) for k,v in sorted(groups.items())])


def retention_output(path,riders,cohort,first_seven,first_repeat):
    aggregate = c.defaultdict(lambda: [0,0,0])
    survival = c.Counter()
    for rid,r in riders.items():
        if not START <= r["signup_date"] <= END:
            continue
        state = cohort.get(rid,[False]*7)
        key = (r["signup_date"][:7],r["canonical"],r["plan_type"],r["signup_channel"],r["kyc_verified"],
               *map(int,state[:6]),min(10,first_seven[rid]))
        v = aggregate[key]
        v[0] += 1
        followup = (dt.date.fromisoformat(END)-r["signup"]).days
        if followup >= 14:
            event = first_repeat.get(rid,math.inf)
            horizon = min(60,followup)
            survival[r["signup_date"][:7],r["canonical"],r["plan_type"],int(min(event,horizon)),int(event<=horizon)] += 1
        if followup >= 30:
            v[1] += 1
            v[2] += state[6]
    write(path,"retention_cells",["signup_month","city","plan","channel","kyc","early_stockout","early_long_queue",
        "early_low_soh","early_attempt","near_competitor","early_competitor_promo","first_week_attempts_cap10","signups","eligible","retained"],
        [(*k,*v) for k,v in sorted(aggregate.items())])
    write(path,"return_survival_cells",["month","city","plan","age","event","riders"],[(*k,v) for k,v in sorted(survival.items())])


def telemetry(z,path,stations,context,audit,totals):
    groups = c.defaultdict(lambda: [0]*10)
    by_station = c.defaultdict(lambda: [0]*5)
    coverage = c.Counter()
    need = "station_id hour_start telemetry_status charged_2w_min charged_3w_min cabinet_temp_c avg_charge_minutes packs_quarantined"
    for r in table(z,"station_hourly_status",need):
        totals["telemetry"] += 1
        sid = r["station_id"]
        if sid.startswith("STN-TST"):
            audit["telemetry_test"] += 1
            continue
        totals["telemetry_production"] += 1
        station = stations.get(sid)
        if station is None:
            audit["telemetry_unmatched"] += 1
            continue
        stamp = r["hour_start"]
        city, generation, tier = (station[k] for k in ("city","charger_generation","connectivity_tier"))
        status = r["telemetry_status"].strip().lower()
        coverage[tier,status] += 1
        valid = status == "ok"
        audit["telemetry_incomplete"] += not valid
        v = by_station[sid]
        v[0] += 1
        ambient = number(context.get((city,stamp[:10]),{}).get("max_temp_c",""))
        cabinet = number(r["cabinet_temp_c"])
        hot = "unknown" if ambient is None else "35C+" if ambient >= 35 else "<35C"
        cabinet_band = "unknown" if cabinet is None else "45C+" if cabinet >= 45 else "<45C"
        q = groups[city,generation,int(stamp[11:13]),hot,cabinet_band]
        q[0] += 1
        for i,vehicle in enumerate(("2w","3w")):
            reading = number(r[f"charged_{vehicle}_min"])
            if valid and reading is not None and reading >= 0:
                q[1+2*i] += 1
                q[2+2*i] += reading == 0
                v[1+2*i] += 1
                v[2+2*i] += reading == 0
            else:
                audit[f"stockout_{vehicle}_unobserved"] += 1
        if valid:
            for index,key in ((5,"avg_charge_minutes"),(7,"packs_quarantined")):
                value = number(r[key])
                if value is not None:
                    q[index] += value
                    q[index+1] += 1
    write(path,"station_coverage",["station_id","hours","observed_2w","stockout_2w","observed_3w","stockout_3w"],
          [(*[k],*v) for k,v in sorted(by_station.items())])
    write(path,"telemetry_coverage",["connectivity","status","hours"],[(*k,v) for k,v in sorted(coverage.items())])
    write(path,"thermal_hourly",["city","generation","hour","ambient_band","cabinet_band","hours","observed_2w",
          "stockout_2w","observed_3w","stockout_3w","charge_minutes_sum","charge_n","quarantine_sum","quarantine_n"],
          [(*k,*v[:9]) for k,v in sorted(groups.items())])


def tickets(z,path,audit,totals):
    strata = c.defaultdict(lambda:[0,0,0.0])
    reasons = c.Counter()
    records = list(table(z,"support_tickets","station_id category rider_comment resolution_status resolution_hours csat_score"))
    eligible_comments = []
    for r in records:
        totals["tickets"] += 1
        if r["station_id"].startswith("STN-TST"):
            audit["ticket_test"] += 1
            continue
        totals["ticket_production"] += 1
        hrs = number(r["resolution_hours"])
        bucket = "unknown" if hrs is None else "0–24" if hrs <= 24 else "24–72" if hrs <= 72 else "72+"
        score = number(r["csat_score"])
        v = strata[r["resolution_status"],bucket]
        v[0] += 1
        v[1] += score is not None
        v[2] += score or 0
        audit["csat_missing"] += score is None
        if r["category"] in {"other","app_issue"}:
            totals["nlp_eligible"] += 1
            comment = r["rider_comment"].lower()
            label = [k for k,expr in RULES.items() if re.search(expr,comment)]
            if len(label) == 1:
                audit["ticket_reclassified"] += 1
                reasons[r["category"], label[0], "rule"] += 1
            else:
                eligible_comments.append((r["category"],comment))
    tokenize = lambda s: re.findall(r"[a-z]{2,}",s)
    prototypes = {k:c.Counter(tokenize(v)) for k,v in RULES.items()}
    vocab = set().union(*(p.keys() for p in prototypes.values()))
    docs = [(kind,c.Counter(t for t in tokenize(comment) if t in vocab)) for kind,comment in eligible_comments]
    df = c.Counter(t for _,doc in docs for t in doc)
    weights = {t: 1+math.log((len(docs)+1)/(df[t]+1)) for t in vocab}
    for kind,doc in docs:
        scores = {}
        for label,p in prototypes.items():
            norm = math.sqrt(sum((n*weights[t])**2 for t,n in p.items()))
            scores[label] = sum(n*p[t]*weights[t]**2 for t,n in doc.items())/norm
        ranked = sorted(scores,key=scores.get,reverse=True)
        label = ranked[0] if scores[ranked[0]] > scores[ranked[1]] else "unresolved"
        reasons[kind,label,"review"] += 1
        audit["ticket_review"] += 1
    write(path,"csat_strata",["status","hours_bucket","tickets","responses","score_sum",
          "response_rate","respondent_mean"],[(*k,n,m,s,m/n,s/m if m else "") for k,(n,m,s) in sorted(strata.items())])
    write(path,"ticket_root_causes",["original","root_cause","method","tickets"],[(*k,v) for k,v in sorted(reasons.items())])


def audit_output(path,audit,totals,attempts,completed):
    checks = {
        "event_test":(totals["events"],"Exclude STN-TST prefix"),
        "firmware_shift":(totals["events"]-audit["event_test"],"Add 330 minutes in raw calendar window"),
        "offline_batch_rows":(totals["events"]-audit["event_test"],"Count configured offline sync mode"),
        "offline_batch_complete_key":(audit["offline_batch_rows"],"Complete four-field identifier key"),
        "offline_duplicate":(totals["events"]-audit["event_test"],"Keep latest success in each adjacent-gap cluster, otherwise latest state"),
        "outside_window":(totals["events"]-audit["event_test"]-audit["offline_duplicate"],"Exclude corrected timestamps outside study window"),
        "event_unmatched_dimension":(totals["events"]-audit["event_test"]-audit["offline_duplicate"]-audit["outside_window"],"Exclude missing rider or station joins"),
        "unknown_outcome":(attempts,"Retain separately as an unknown noncompletion"),
        "city_normalized":(totals["riders"],"Map aliases to network cities"),
        "city_unmapped":(totals["riders"],"Keep unknown category"),
        "soc_drift":(attempts,"Flag and cap upper bound for wear estimates"),
        "odometer_negative":(attempts,"Exclude from range summaries"),
        "odometer_upper":(attempts,"Exclude above completed-swap p99 within vehicle class"),
        "completed_missing_price":(completed,"Track incomplete revenue coverage"),
        "completed_missing_energy":(completed,"Track incomplete energy coverage"),
        "completed_wear_uncovered":(completed,"Track incomplete wear coverage"),
        "completed_missing_returned_pack":(completed,"Exclude from lot-level returns"),
        "noncompleted":(attempts,"Preserve operational demand, zero recognized revenue"),
        "telemetry_test":(totals["telemetry"],"Exclude test stations"),
        "telemetry_unmatched":(totals["telemetry_production"],"Exclude missing station joins"),
        "telemetry_incomplete":(totals["telemetry_production"]-audit["telemetry_unmatched"],"Exclude non-ok telemetry from observed rates"),
        "stockout_2w_unobserved":(totals["telemetry_production"]-audit["telemetry_unmatched"],"Mask unknown 2W status"),
        "stockout_3w_unobserved":(totals["telemetry_production"]-audit["telemetry_unmatched"],"Mask unknown 3W status"),
        "ticket_test":(totals["tickets"],"Exclude test stations"),
        "csat_missing":(totals["ticket_production"],"Report resolution strata and response rates"),
        "ticket_reclassified":(totals["nlp_eligible"],"Unique bilingual phrase match"),
        "ticket_review":(totals["nlp_eligible"],"Unassigned, optional TF-IDF suggestion"),
    }
    audit["noncompleted"] = attempts-completed
    write(path,"forensic_audit",["check","affected","denominator","percent","treatment"],
          [(k,audit[k],n,100*audit[k]/n if n else "",t) for k,(n,t) in checks.items()])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Source ZIP or directory of CSV/CSV.GZ files")
    parser.add_argument("output", type=Path)
    options = parser.parse_args()
    main(options.archive,options.output)
