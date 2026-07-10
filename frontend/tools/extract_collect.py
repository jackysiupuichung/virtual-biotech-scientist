"""Extract the CSO collection steps (per-division tool calls + grades) from recorded
live runs into frontend/_collect.js.

Reads each <runs>/collect_<SYM>/result.json (produced by
skills/virtual-biotech-cso/harness.py --live). Runs dir defaults to ../data/runs
relative to this script; override with argv[1]. Run from anywhere:

    python frontend/tools/extract_collect.py [runs_dir]
"""
import json, sys, glob, os
_HERE=os.path.dirname(os.path.abspath(__file__))
_FRONTEND=os.path.dirname(_HERE)
SS=sys.argv[1] if len(sys.argv)>1 else os.path.join(_FRONTEND,"data","runs")
DIVLBL={"right_target":"Target","right_tissue":"Tissue","right_safety":"Safety",
  "right_patient":"Patient","right_commercial":"Commercial","tractability":"Tractability"}
def summ(res):
    # compact one-line result summary from the tool result
    if not isinstance(res,dict): return str(res)[:160]
    s=res.get("summary")
    if isinstance(s,dict): return " · ".join(f"{k}={v}" for k,v in list(s.items())[:4])
    return str(s)[:160] if s else res.get("via","")[:160]
out={}
for path in sorted(glob.glob(f"{SS}/collect_*/result.json")):
    sym=path.split("collect_")[1].split("/")[0]
    d=json.load(open(path)); data=d['data']; su=d['summary']
    # Iterate the EVIDENCE trail (execution order — includes reviewer re-route steps
    # that never appear in the original plan). Enrich from the plan where a step matches.
    findings_by_div={f['division']:f for f in data['division_findings'] if f.get('division')}
    plan_by_step={p['step']:p for p in data['plan']}
    steps=[]
    for e in data['evidence']:
        sid=e['step']; p=plan_by_step.get(sid,{})
        res=e.get('result',{})
        tc=(res or {}).get('tool_call',{}) if isinstance(res,dict) else {}
        div=e.get('division') or p.get('division')
        fin=findings_by_div.get(div,{})
        steps.append({
          "id":sid, "division":div, "div_label":DIVLBL.get(div,div),
          "question":e.get('question') or p.get('question') or '',
          "skill":e.get('skill') or p.get('skill') or '',
          "depends_on":p.get('depends_on',[]),
          "reroute": "reroute" in sid,
          "tool": tc.get('tool_name'), "args": tc.get('arguments'),
          "result_summary": summ(res), "backend": (res or {}).get('backend') if isinstance(res,dict) else None,
          "grade": fin.get('evidence_grade'), "confidence": fin.get('confidence'),
          "interpretation": (fin.get('interpretation') or '')[:600],
        })
    rev=data.get('review',{})
    gaps=[{"missing":g.get('missing'),"route_to":g.get('route_to'),"why":(g.get('why') or '')[:400],
           "lenses":g.get('lenses',[])} for g in rev.get('gaps',[])][:6]
    out[sym]={
      "symbol":sym, "query":su.get('query'), "backend":su.get('backend'), "model":su.get('model'),
      "n_steps":su.get('n_steps'), "n_executed":su.get('n_executed'),
      "decision":su.get('decision'), "confidence":su.get('confidence'),
      "reviewer_verdict":su.get('reviewer_verdict'),
      "briefing":{k:(data['briefing'].get(k) if not isinstance(data['briefing'].get(k),str) else data['briefing'][k][:400]) for k in ['context','feasibility_flags']},
      "steps":steps,
      "review":{"verdict":rev.get('verdict'),"scores":rev.get('scores'),"gaps":gaps},
    }
    print(f"{sym}: {len(steps)} steps, verdict={rev.get('verdict')}, {len(gaps)} gaps shown", file=sys.stderr)
_OUT=os.path.join(_FRONTEND,"_collect.js")
open(_OUT,'w').write("window.COLLECT_RUNS = "+json.dumps(out)+";")
print("wrote", _OUT+":", len(out), "targets,", len(json.dumps(out)), "bytes", file=sys.stderr)
