"""Extract the LangGraph execution trace (spans -> layered node/edge graph) from recorded
live runs into frontend/_graph.js.

Reads each <runs>/collect_<SYM>/trace.jsonl and enriches scientist nodes from
frontend/_collect.js (so run extract_collect.py FIRST). Runs dir defaults to ../data/runs
relative to this script; override with argv[1].

    python frontend/tools/extract_collect.py   # first
    python frontend/tools/extract_graph.py      # then
"""
import json, sys, glob, os
_HERE=os.path.dirname(os.path.abspath(__file__))
_FRONTEND=os.path.dirname(_HERE)
SS=sys.argv[1] if len(sys.argv)>1 else os.path.join(_FRONTEND,"data","runs")
DIVLBL={"right_target":"Target","right_tissue":"Tissue","right_safety":"Safety",
  "right_patient":"Patient","right_commercial":"Commercial","tractability":"Tractability"}

def stage_of(name, kind):
    if kind=='run': return 'run'
    if name=='chief_of_staff': return 'cso'
    if name=='planner': return 'planner'
    if name.startswith('scientist:'): return 'scientist'
    if name in ('execute','divisions'): return None  # structural, skip as node
    if name=='review_loop': return None
    if name=='review_panel': return 'review'
    if name.startswith('reviewer:'): return 'reviewer'
    if name=='prometheux_gaps': return 'gaps'
    if name.startswith('reroute:'): return 'reroute'
    if name=='prometheux_decision': return 'decision'
    if name=='cso_synthesis': return 'synthesis'
    return 'other'

# fixed lane order (x position) for the layered flow
LANE={'run':0,'cso':1,'planner':2,'scientist':3,'reroute':4,'review':5,'reviewer':6,'gaps':6,'decision':7,'synthesis':8}

out={}
for path in sorted(glob.glob(f"{SS}/collect_*/trace.jsonl")):
    sym=path.split("collect_")[1].split("/")[0]
    rows=[json.loads(l) for l in open(path)]
    # collection step data (already extracted) to attach to scientist nodes
    coll=json.loads(open(os.path.join(_FRONTEND,"_collect.js")).read().split('=',1)[1].rstrip(';\n')).get(sym,{})
    step_by_div={}
    for s in coll.get('steps',[]):
        step_by_div.setdefault(s['division'],s)  # first (primary) step per division

    nodes=[]; seen=set()
    review_iter=0
    for r in rows:
        name=r['name']; kind=r['kind']; st=stage_of(name,kind)
        if st is None: continue
        # dedupe review_panel iterations into distinct nodes (the loop!)
        if name=='review_panel':
            review_iter+=1
            nid=f"review#{review_iter}"
            label=f"Review pass {review_iter}"
        else:
            nid=name
            if nid in seen:
                # reviewer lens repeats each pass; keep the LAST verdict only, skip dup node
                continue
            label=name
        seen.add(nid)
        a=r.get('attrs',{})
        node={
          "id":nid,"stage":st,"lane":LANE.get(st,8),
          "label":label,"kind":kind,
          "duration_ms":round(r.get('duration_ms') or 0),
          "tokens":(r.get('usage') or {}).get('total_tokens'),
          "status":r.get('status'),
          "attrs":{k:a[k] for k in ('grade','n_steps','n_skills','decision','reviewer_verdict','verdict','model','backend','source') if k in a},
        }
        # attach division scientist detail
        if st=='scientist':
            div=name.split(':',1)[1]
            node['div_label']=DIVLBL.get(div,div)
            s=step_by_div.get(div)
            if s:
                node['question']=s['question']; node['tool']=s['tool']; node['args']=s['args']
                node['result_summary']=s['result_summary']; node['skill']=s['skill']
                node['interpretation']=s['interpretation']; node['grade']=s['grade']
        if st=='reviewer':
            node['lens']=name.split(':',1)[1]
        out.setdefault(sym,{"nodes":[],"edges":[]})
        nodes.append(node)

    # ordering within lane (y) by first-seen
    lane_count={}
    for n in nodes:
        n['row']=lane_count.get(n['lane'],0); lane_count[n['lane']]=n['row']+1

    # edges: clean layered flow + review loop back-edges
    ids={n['id'] for n in nodes}
    E=[]
    def add(a,b,kind='flow'):
        if a in ids and b in ids: E.append({"from":a,"to":b,"kind":kind})
    run_id=[n['id'] for n in nodes if n['stage']=='run'][0]
    add(run_id,'chief_of_staff'); add('chief_of_staff','planner')
    scis=[n['id'] for n in nodes if n['stage']=='scientist']
    for s in scis: add('planner',s)
    reviews=sorted([n['id'] for n in nodes if n['stage']=='review'], key=lambda x:int(x.split('#')[1]))
    for s in scis:
        if reviews: add(s,reviews[0])
    revlenses=[n['id'] for n in nodes if n['stage']=='reviewer']
    gaps=[n['id'] for n in nodes if n['stage']=='gaps']
    for rv in reviews:
        for l in revlenses: add(rv,l,'panel')
        for g in gaps: add(rv,g,'panel')
    # review loop: pass1 -reroute-> pass2 -> ...
    reroutes=[n['id'] for n in nodes if n['stage']=='reroute']
    for i in range(len(reviews)-1):
        # back-edge: this pass routed back, went through reroute, to next pass
        if reroutes: add(reviews[i],reroutes[0],'reroute'); add(reroutes[0],reviews[i+1],'reroute')
        else: add(reviews[i],reviews[i+1],'reroute')
    # final review -> decision -> synthesis
    dec=[n['id'] for n in nodes if n['stage']=='decision']
    syn=[n['id'] for n in nodes if n['stage']=='synthesis']
    last_rev=reviews[-1] if reviews else None
    if last_rev and dec: add(last_rev,dec[0])
    if dec and syn: add(dec[0],syn[0])
    elif last_rev and syn: add(last_rev,syn[0])

    out[sym]={"nodes":nodes,"edges":E,
      "meta":{"n_review_passes":len(reviews),"decision":coll.get('decision'),
              "reviewer_verdict":coll.get('reviewer_verdict'),"query":coll.get('query')}}
    print(f"{sym}: {len(nodes)} nodes, {len(E)} edges, {len(reviews)} review passes", file=sys.stderr)

_OUT=os.path.join(_FRONTEND,"_graph.js")
open(_OUT,'w').write("window.TRACE_GRAPHS = "+json.dumps(out)+";")
print("wrote", _OUT, len(json.dumps(out)),"bytes", file=sys.stderr)
