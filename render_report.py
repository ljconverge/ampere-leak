import base64,csv,html,re,sys
from pathlib import Path
p=Path(__file__).resolve().parent
evidence,out=map(Path,sys.argv[1:3])
raw=(out/"executive_report.md").read_text(encoding="utf-8-sig")
escape=html.escape
def inline(s):
    s=escape(s)
    return re.sub(r"\*\*(.+?)\*\*",r"<strong>\1</strong>",s)
parts=[]
table=False
for line in raw.splitlines()+[""]:
    if line.startswith("|"):
        values=[v.strip() for v in line.strip("|").split("|")]
        if all(v and set(v)<={"-",":"} for v in values): continue
        tag="td" if table else "th"
        if not table: parts.append("<table>")
        table=True
        parts.append("<tr>"+"".join(f"<{tag}>{inline(v)}</{tag}>" for v in values)+"</tr>")
        continue
    if table:
        parts.append("</table>")
        table=False
    if line.startswith("#"):
        rank=len(line)-len(line.lstrip("#"))
        parts.append(f"<h{rank}>{inline(line[rank:].strip())}</h{rank}>")
    elif line:
        parts.append(f"<p>{inline(line)}</p>")
bars=[]
with (evidence/"half_year.csv").open() as f:
    for r in csv.DictReader(f):
        val=float(r["failure_rate"])*100
        bars.append(f'<div>{r["period"]} <strong>{val:.2f}%</strong><div class="track"><i style="width:{val*10:.2f}%"></i></div></div>')
logo=base64.b64encode((p/"logo.png").read_bytes()).decode()
style='''body{background:#f6f2ea;color:#212832;max-width:1000px;margin:3rem auto;padding:0 1.2rem;font:16px/1.6 "Segoe UI",sans-serif}h1{font-size:3.5rem;margin:0}h2,h3{color:#874626}table{width:100%;border-collapse:collapse;font-size:.9rem}td,th{padding:.5rem;border-bottom:1px solid #d8cabb;text-align:left}th{background:#ebe0d2}a{color:#874626}section{background:#fffdf8;padding:1rem 1.5rem;margin:1.5rem 0;border:1px solid #dccdbc}.track{background:#e7ddd0;height:11px;margin:.25rem 0 .65rem}.track i{background:#a45a36;height:100%;display:block}@media print{body{margin:0}tr{break-inside:avoid}h3{break-after:avoid}}'''
intro=f'<img width="160" alt="Ampere Leak logo" src="data:image/png;base64,{logo}"><section><h2>Service failure rate by half year</h2>{"".join(bars)}<p><a href="scorecard.html">Explore the interactive scorecard</a></p></section>'
(out/"analysis_report.html").write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Ampere Leak | Analysis Report</title><style>{style}</style><main>{intro}{"".join(parts)}</main></html>',encoding="utf8")
