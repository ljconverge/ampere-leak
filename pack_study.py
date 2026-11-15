"""Pack trajectory estimates and prior-issue matching from the cleaned stream."""
import collections as c
import datetime as dt
import math
import struct

from pipeline import write

ISSUE = struct.Struct("<IIffffffH")
EPOCH = dt.datetime(2024,1,1)


class PackStudy:
    def __init__(self,packs):
        self.packs = packs
        self.index = {key:i for i,key in enumerate(packs,1)}
        self.records = c.defaultdict(bytearray)
        self.exposure = c.defaultdict(lambda:[0,0])
        self.snapshots = c.defaultdict(lambda:[0,0.0])
        self.lagged = c.Counter()

    def add(self,rider,stamp,vehicle,in_id,out_id,soc_in,soh_in,soc_out,soh_out,km,hot):
        t = int((dt.datetime.fromisoformat(stamp)-EPOCH).total_seconds())
        if in_id in self.index:
            v = self.exposure[in_id]
            v[0] += 1
            v[1] += hot
            if soh_in is not None and 0<soh_in<=105:
                phase = stamp[:7]
                key = (in_id,phase)
                q = self.snapshots[key]
                q[0] += 1
                q[1] += min(soh_in,100)
        if vehicle not in ("2W","3W"):
            return
        fields = [soc_in,soc_out,soh_out,km]
        self.records[rider].extend(ISSUE.pack(t,self.index.get(in_id,0),
            *[math.nan if v is None else v for v in fields],float(self.index.get(out_id,0)),0.,int(vehicle=="3W")))

    def export(self,path):
        results = c.defaultdict(lambda:[0,0.0,0.0,0.0])
        per_pack = c.Counter()
        curves = c.defaultdict(lambda:[0,0.0])
        exposures = []
        for (bid,month),(n,soh) in sorted(self.snapshots.items()):
            pack = self.packs[bid]
            per_pack[bid] += n
            band = (per_pack[bid]//100)*100
            key = (pack["supplier"],pack["pack_type"],band)
            v = curves[key]
            v[0] += n
            v[1] += soh
        for bid,pack in self.packs.items():
            returns,hot = self.exposure.get(bid,(0,0))
            if returns==0 or not pack["commission_date"] or not pack["current_soh_pct"]:
                continue
            end = min(pack["retired_date"] or "2025-06-30","2025-06-30")
            age = (dt.date.fromisoformat(end)-dt.date.fromisoformat(pack["commission_date"])).days
            if age < 1:
                continue
            soh_loss = float(pack["initial_soh_pct"])-float(pack["current_soh_pct"])
            exposures.append((pack["supplier"],pack["pack_type"],pack["manufacturing_lot"],
                pack["bms_firmware"], age,returns,hot,soh_loss))
        for records in self.records.values():
            previous = None
            for row in sorted(ISSUE.iter_unpack(records)):
                stamp, returned, charge_in, charge_out, soh_out, km, issued, _, is3w = row
                self.lagged["completed_records"] += 1
                if previous:
                    old_t, old_id, old_charge,old_soh = previous
                    if 0<stamp-old_t<=30*86400 and returned and returned==old_id:
                        self.lagged["matched_pack_return"] += 1
                        used = min(100,old_charge)-min(100,charge_in)
                        if all(map(math.isfinite,(old_charge,charge_in,old_soh,km))) and 5 <= used <= 100 and 0<=charge_in<=100 and 0<old_charge<=105:
                            self.lagged["valid_discharge_and_distance"] += 1
                            band = "<82" if old_soh<82 else "82–89" if old_soh<90 else "90+"
                            v = results["3W" if is3w else "2W",band]
                            v[0] += 1
                            v[1] += km
                            v[2] += used
                            v[3] += km/used
                previous = (stamp,int(issued),charge_out,soh_out)
        write(path,"matched_pack_range",["vehicle","issued_soh_band","pairs","total_km","total_soc_used_pp","mean_km_per_soc_pp"],
              [(*key,n,km,soc,value/n) for key,(n,km,soc,value) in sorted(results.items())])
        write(path,"matched_pack_coverage",["check","rows"],sorted(self.lagged.items()))
        write(path,"battery_cycle_curves",["supplier","pack_type","cumulative_measured_returns_bin","soh_measurements","mean_return_soh"],
              [(*key,n,soh/n) for key,(n,soh) in sorted(curves.items())])
        for_pack = c.defaultdict(lambda:[0,0,0,0,0.])
        for supplier,pack_type,lot,firmware,age,n,hot,loss in exposures:
            key = (supplier,pack_type,lot,firmware,(age//90)*90,(n//100)*100)
            v=for_pack[key]
            v[0]+=1
            v[1]+=age
            v[2]+=n
            v[3]+=hot
            v[4]+=loss
        write(path,"battery_exposure",["supplier","pack_type","lot","firmware","age_bin_days","return_count_bin",
              "packs","age_days_sum","return_count","hot_city_day_returns","snapshot_loss_sum"],
              [(*key,*v) for key,v in sorted(for_pack.items())])
