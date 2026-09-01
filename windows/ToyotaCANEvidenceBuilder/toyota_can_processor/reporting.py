from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


def _csv(path: Path, limit: int = 1000) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) <= limit:
        return rows
    step = max(1, len(rows) // limit)
    return rows[::step][:limit]


def _table(rows: list[dict[str, str]], columns: list[str], limit: int = 100) -> str:
    if not rows:
        return "<p class='muted'>No rows available.</p>"
    head = "".join(f"<th>{html.escape(name)}</th>" for name in columns)
    body = "".join("<tr>" + "".join(
        f"<td>{html.escape(str(row.get(name, '')))}</td>" for name in columns) + "</tr>"
        for row in rows[:limit])
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def write_offline_report(path: Path, summary: dict[str, Any], session_dir: Path,
                         output_root: Path) -> None:
    profile = summary.get("profile_evidence", {})
    external = summary.get("external_diagnostics", {})
    alignment = summary.get("alignment") or {}
    grading = summary.get("local_evidence_grading", {})
    blocks = _csv(session_dir / "BATTERY_BLOCKS_ALIGNED.csv", 300)
    decoded = _csv(session_dir / "DECODED_FIELDS_ALIGNED.csv", 1200)
    actions = _csv(session_dir / "DIAGNOSTIC_ACTIONS_ALIGNED.csv", 200)
    events = _csv(session_dir / "EVENTS_ALIGNED.csv", 200)
    grades = _csv(session_dir / "EVIDENCE_GRADING.csv", 500)
    transcript = _csv(output_root / "VOICE_TRANSCRIPT.csv", 300)
    keyframes = sorted((output_root / "OCR_KEYFRAMES").glob("*.jpg")) \
        if (output_root / "OCR_KEYFRAMES").exists() else []
    screenshots = "".join(
        f"<figure><img loading='lazy' src='../OCR_KEYFRAMES/{html.escape(item.name)}'>"
        f"<figcaption>{html.escape(item.stem)}</figcaption></figure>" for item in keyframes[:30])
    block_data = [{key: value for key, value in row.items()
                   if key in {"Video_s", "Profile", *[f"B{index:02d}_V" for index in range(1, 18)]}}
                  for row in blocks]
    decoded_data = [{key: row.get(key, "") for key in
                     ("Video_s", "DecoderKey", "Field", "ArrayIndex", "Value", "Unit")}
                    for row in decoded]
    data = json.dumps({"blocks": block_data, "decoded": decoded_data}, separators=(",", ":")).replace("</", "<\\/")
    warnings = "".join(f"<li>{html.escape(str(item))}</li>" for item in summary.get("warnings", [])) or "<li>None</li>"
    conflict = "<div class='alert'>Logger profile corrected from <b>{}</b> to <b>{}</b> using {}.</div>".format(
        html.escape(str(profile.get("manifest_profile", ""))),
        html.escape(str(profile.get("selected_profile", ""))),
        html.escape(str(profile.get("decision", "")))) if profile.get("profile_conflict") else ""
    document = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>Toyota CAN offline evidence</title>
<style>
:root{{--navy:#11263d;--blue:#1f6aa5;--pale:#eef6fb;--line:#c8d8e5;--warn:#fff3cd;--good:#e8f5e9}}
body{{font:14px Segoe UI,Arial,sans-serif;margin:0;color:#162433;background:#f5f8fa}}
header{{background:linear-gradient(120deg,var(--navy),var(--blue));color:white;padding:28px 5vw}}
main{{max-width:1250px;margin:auto;padding:22px}}h1{{margin:0 0 8px}}h2{{color:var(--navy);margin-top:30px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0}}
.card{{background:white;border:1px solid var(--line);border-radius:10px;padding:15px;box-shadow:0 2px 6px #1231}}
.value{{font-size:22px;font-weight:700;color:var(--blue)}}.alert{{background:var(--warn);border-left:5px solid #d39e00;padding:12px;margin:16px 0}}
.panel{{background:white;border:1px solid var(--line);border-radius:10px;padding:16px;margin:14px 0}}
.scroll{{overflow:auto;max-height:430px}}table{{border-collapse:collapse;width:100%;font-size:12px}}th{{position:sticky;top:0;background:var(--navy);color:white}}
th,td{{padding:6px 8px;border-bottom:1px solid #dce5ec;text-align:left;white-space:nowrap}}.muted{{color:#667}}
canvas{{width:100%;height:310px;border:1px solid var(--line);background:white}}select{{padding:6px}}
.gallery{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}}figure{{margin:0}}img{{max-width:100%;border:1px solid var(--line)}}
</style></head><body><header><h1>Toyota Hybrid CAN Offline Evidence</h1>
<div>Session {html.escape(str(summary.get('session', '')))} · Evidence Builder 1.0.3 · Database {html.escape(str(summary.get('decoder_database', {}).get('version', '')))}</div></header>
<main>{conflict}<div class='cards'>
<div class='card'><div>Selected profile</div><div class='value'>{html.escape(str(profile.get('selected_profile', 'UNKNOWN')))}</div></div>
<div class='card'><div>Profile confidence</div><div class='value'>{profile.get('confidence_pct', 0)}%</div></div>
<div class='card'><div>Diagnostic transactions</div><div class='value'>{external.get('transactions', 0)}</div></div>
<div class='card'><div>Decoded field rows</div><div class='value'>{external.get('decoded_field_rows', 0)}</div></div>
<div class='card'><div>CAN/OCR pairs</div><div class='value'>{grading.get('can_ocr_pairs', 0)}</div></div>
<div class='card'><div>BLE RMS</div><div class='value'>{alignment.get('residual_rms_ms', '—')} ms</div></div></div>
<section class='panel'><h2>Warnings and release boundaries</h2><ul>{warnings}</ul>
<p>This is an offline evidence report, not a live vehicle dashboard. It never authorizes CAN transmission, control, reset, or clear-code operations.</p></section>
<section class='panel'><h2>Interactive decoded timeline</h2><label>Signal <select id='signal'></select></label><canvas id='timeline' width='1100' height='310'></canvas></section>
<section class='panel'><h2>Interactive battery-block snapshots</h2><label>Sample <input id='blockSlider' type='range' min='0' max='{max(0, len(blocks)-1)}' value='0'></label>
<span id='blockTime'></span><canvas id='blocks' width='1100' height='310'></canvas></section>
<section class='panel'><h2>Local evidence grading</h2>{_table(grades, ['DecoderKey','Field','ArrayIndex','DecodedSamples','OCRPairs','AgreementRate','RMSE','MedianLag_s','BoundsFailures','IndependentSessions','PreliminaryLocalGrade'], 500)}</section>
<section class='panel'><h2>Diagnostic actions</h2>{_table(actions, ['StartVideo_s','EndVideo_s','ECU','Operation','AttemptCount','SuccessfulResponses','Result','SafetyClass','DecoderKeys'], 200)}</section>
<section class='panel'><h2>Markers and events</h2>{_table(events, ['Video_s','Time_us','Event','Detail','Value'], 200)}</section>
<section class='panel'><h2>Narration</h2>{_table(transcript, ['Start_s','End_s','Text'], 300)}</section>
<section class='panel'><h2>OCR evidence keyframes</h2><div class='gallery'>{screenshots or "<p class='muted'>No OCR keyframes were requested or detected.</p>"}</div></section>
<script>const DATA={data};
function drawLine(rows,canvas){{const c=canvas.getContext('2d'),w=canvas.width,h=canvas.height;c.clearRect(0,0,w,h);if(!rows.length)return;
const pts=rows.map(r=>[+r.Video_s,+r.Value]).filter(p=>Number.isFinite(p[0])&&Number.isFinite(p[1]));if(!pts.length)return;const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);
let xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys);if(xmax===xmin)xmax++;if(ymax===ymin){{ymin--;ymax++;}}c.strokeStyle='#1f6aa5';c.lineWidth=2;c.beginPath();pts.forEach((p,i)=>{{let x=45+(p[0]-xmin)/(xmax-xmin)*(w-65),y=15+(ymax-p[1])/(ymax-ymin)*(h-45);i?c.lineTo(x,y):c.moveTo(x,y)}});c.stroke();c.fillStyle='#243';c.fillText(ymax.toFixed(2),4,18);c.fillText(ymin.toFixed(2),4,h-18);c.fillText(xmin.toFixed(1)+'s',45,h-5);c.fillText(xmax.toFixed(1)+'s',w-65,h-5)}}
const select=document.getElementById('signal'),keys=[...new Set(DATA.decoded.filter(r=>r.Value!==''&&r.ArrayIndex==='').map(r=>r.DecoderKey+' · '+r.Field))].sort();keys.forEach(k=>select.add(new Option(k,k));
function updateLine(){{let k=select.value;drawLine(DATA.decoded.filter(r=>r.DecoderKey+' · '+r.Field===k),document.getElementById('timeline'))}}select.onchange=updateLine;updateLine();
function drawBlocks(){{let i=+document.getElementById('blockSlider').value,r=DATA.blocks[i],c=document.getElementById('blocks'),x=c.getContext('2d');x.clearRect(0,0,c.width,c.height);if(!r)return;let v=[];for(let n=1;n<=17;n++){{let q=+r['B'+String(n).padStart(2,'0')+'_V'];if(Number.isFinite(q)&&q>0)v.push(q)}};let lo=Math.min(...v)-.05,hi=Math.max(...v)+.05,bw=(c.width-70)/v.length;v.forEach((q,n)=>{{let bh=(q-lo)/(hi-lo)*(c.height-60);x.fillStyle='#2d83b5';x.fillRect(45+n*bw,c.height-35-bh,bw-5,bh);x.fillStyle='#123';x.fillText((n+1),50+n*bw,c.height-15);x.fillText(q.toFixed(2),45+n*bw,c.height-40-bh)}});document.getElementById('blockTime').textContent=' '+r.Video_s+' s · '+r.Profile}}document.getElementById('blockSlider').oninput=drawBlocks;drawBlocks();</script>
</main></body></html>"""
    path.write_text(document, encoding="utf-8")
