"""Standalone operations scorecard with embedded aggregate evidence."""
import json
import base64
from pathlib import Path

from decision import read


def build(evidence,out,summary):
    names = ["monthly","margin_bridge","pricing_parallel_trends","retention_cohorts","retention_drivers",
             "station_priority","supplier_summary","battery_cycle_curves","thermal_summary","roi_scenarios","return_km"]
    data = {name:read(evidence,name) for name in names}
    data["summary"] = summary
    payload = json.dumps(data,ensure_ascii=False).replace("<","\\u003c")
    template = Path(__file__).with_name("scorecard_template.html").read_text(encoding="utf-8-sig")
    logo=base64.b64encode(Path(__file__).with_name("logo.png").read_bytes()).decode("ascii")
    template=template.replace("{{LOGO}}",logo)
    (out/"scorecard.html").write_text(template.replace("<!--EVIDENCE-->",payload),encoding="utf-8")
