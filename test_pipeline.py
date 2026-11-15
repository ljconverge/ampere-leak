import datetime as dt
import unittest
import tempfile
from pathlib import Path
from decision import read
from pack_study import PackStudy
from collections import Counter

from decision import chi_survival
from pipeline import offline_drops, percentile


class ForensicRules(unittest.TestCase):
    def test_duplicate_boundary_and_success_priority(self):
        at = lambda seconds: dt.datetime(2025,3,10,12)+dt.timedelta(seconds=seconds)
        candidates = {"key":[(at(361),"isolated",False),(at(0),"success",True),
                             (at(180),"late_failure",False)]}
        self.assertEqual(offline_drops(candidates),{"late_failure"})

    def test_later_completion_wins_within_transitive_cluster(self):
        at = lambda seconds: dt.datetime(2025,3,10,12)+dt.timedelta(seconds=seconds)
        candidates = {"key":[(at(0),"early",True),(at(180),"middle",False),(at(360),"late",True)]}
        self.assertEqual(offline_drops(candidates),{"early","middle"})

    def test_weighted_quantile_and_chi_square(self):
        self.assertAlmostEqual(percentile(Counter({0:1,10:1}),.99),9.9)
        self.assertAlmostEqual(chi_survival(3.841458820694124,1),.05,places=7)
        self.assertAlmostEqual(chi_survival(5.991464547107979,2),.05,places=7)


    def test_range_uses_prior_issued_pack_and_soc(self):
        pack = {"supplier":"A","pack_type":"2W","manufacturing_lot":"x","bms_firmware":"f",
                "commission_date":"2024-01-01","retired_date":"","initial_soh_pct":"100","current_soh_pct":"90"}
        study = PackStudy({"a":pack,"b":dict(pack)})
        study.add("r","2024-01-03 00:00:00","2W","a","b",20,90,90,95,40,False)
        study.add("r","2024-01-02 00:00:00","2W","b","a",12,90,80,89,30,False)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            study.export(path)
            [result] = read(path,"matched_pack_range")
            self.assertEqual(result["issued_soh_band"],"82–89")
            self.assertAlmostEqual(float(result["mean_km_per_soc_pp"]),40/60)


if __name__=="__main__":
    unittest.main()
