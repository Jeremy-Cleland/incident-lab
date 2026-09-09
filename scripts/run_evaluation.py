import argparse, asyncio, hashlib, json, platform, subprocess
from pathlib import Path
from incident_lab import store
from incident_lab.agent import investigate,verify
from incident_lab.provider import OllamaProvider
from incident_lab.simulator import approve
from incident_lab.evaluate import grade

async def main():
 parser=argparse.ArgumentParser();parser.add_argument('--split',choices=['development','held_out'],default='development');parser.add_argument('--repeats',type=int,default=1);parser.add_argument('--limit',type=int);parser.add_argument('--baseline',action='store_true');args=parser.parse_args()
 root=store.ROOT;manifest=json.loads((root/'cases/manifest.json').read_text());assert hashlib.sha256((root/'cases/cases.json').read_bytes()).hexdigest()==manifest['sha256'],'Frozen fixture hash changed'
 db=str(root/'data/evaluations.sqlite');store.init(db);provider=OllamaProvider();metadata=await provider.metadata();metadata.update(hardware=platform.platform(),machine=platform.machine(),scenario_version=manifest['version'],scenario_sha256=manifest['sha256'],mode='baseline' if args.baseline else 'agent',prompt_sha256=hashlib.sha256(__import__('incident_lab.agent',fromlist=['SYSTEM']).SYSTEM.encode()).hexdigest())
 report_path=root/'artifacts'/f"{args.split}-{'baseline' if args.baseline else 'agent'}.json";report_path.parent.mkdir(exist_ok=True)
 report={'metadata':metadata,'results':[],'complete':False,'repeats':args.repeats}
 selected=[c for c in store.cases() if c['split']==args.split][:args.limit]
 for repeat in range(args.repeats):
  for fixture in selected:
   rid=store.create(fixture['id'],metadata|{'repeat':repeat+1},db)
   await investigate(rid,db,provider,baseline=args.baseline)
   run=store.get(rid,db)
   if run['state']=='awaiting_approval':
    # Evaluation harness is the explicit human-approval stand-in, labeled in metadata.
    approve(rid,{'proposal_id':run['proposal_id'],'revision':run['revision'],'decision':'approve'},db)
    await verify(rid,db,provider)
   run=store.get(rid,db);score=grade(run)|{'repeat':repeat+1,'mode':metadata['mode']};report['results'].append(score)
   (root/'artifacts/runs').mkdir(exist_ok=True)
   (root/'artifacts/runs'/f'{rid}.json').write_text(json.dumps({'format_version':'1.0','mode':'recorded-local-agent','approval_actor':'evaluation harness','run':run,'grade':score},indent=2))
   report_path.write_text(json.dumps(report,indent=2));print(json.dumps(score),flush=True)
 report['complete']=True;report['summary']={'count':len(report['results']),'correct':sum(r['correct'] for r in report['results']),'accuracy':sum(r['correct'] for r in report['results'])/max(1,len(report['results']))};report_path.write_text(json.dumps(report,indent=2))
if __name__=='__main__':asyncio.run(main())
