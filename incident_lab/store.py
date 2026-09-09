import json, os, sqlite3, uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
TERMINAL={"completed","rejected","failed","cancelled","inconclusive"}
def now(): return datetime.now(timezone.utc).isoformat()
def connect(path=None):
 p=Path(path or os.environ.get("INCIDENT_DB",str(ROOT/"data/runs.sqlite")));p.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(p,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA journal_mode=WAL');return c
@contextmanager
def transaction(path=None):
 c=connect(path)
 try:
  c.execute('BEGIN IMMEDIATE');yield c;c.commit()
 except BaseException:c.rollback();raise
 finally:c.close()
def init(path=None):
 with connect(path) as c:
  c.executescript("""CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,case_id TEXT NOT NULL,state TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0,proposal_id TEXT,proposal TEXT,outcome TEXT,executions INTEGER DEFAULT 0,created_at TEXT,metadata TEXT);
  CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,type TEXT NOT NULL,payload TEXT NOT NULL,at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS approvals(run_id TEXT,proposal_id TEXT,revision INTEGER,decision TEXT,at TEXT,UNIQUE(run_id,proposal_id));
  CREATE TABLE IF NOT EXISTS attempts(run_id TEXT,tool TEXT,count INTEGER,PRIMARY KEY(run_id,tool));
  CREATE VIRTUAL TABLE IF NOT EXISTS runbooks USING fts5(id UNINDEXED,body);""")
  if not c.execute('SELECT count(*) FROM runbooks').fetchone()[0]:
   c.executemany('INSERT INTO runbooks VALUES (?,?)',[
    ('runbook-rollback','Current v2: bad deployment. Correlate API errors with a release and a matching stack trace or deployment timeline. rollback_release targets orders-api and restores 2026.09.1. Verify error rate below 1 percent and latency below 500ms.'),
    ('runbook-pool','Current v2: connection exhaustion. Inspect db pool utilization and worker concurrency changes. restore_worker_concurrency targets orders-worker and restores concurrency 8. Verify utilization below capacity and errors below 1 percent.'),
    ('runbook-upstream','Current v2: upstream outage. Confirm provider failures and healthy local resources. enable_degraded_mode targets upstream-client and queues shipping work. Local API may recover but the provider stays down. Report degraded, not healthy.'),
   ])
def cases():return json.loads((ROOT/'cases/cases.json').read_text())
def case(case_id):
 return next(c for c in cases() if c['id']==case_id)
def emit(c,run_id,kind,payload):c.execute('INSERT INTO events(run_id,type,payload,at) VALUES(?,?,?,?)',(run_id,kind,json.dumps(payload),now()))
def create(case_id,metadata=None,path=None):
 case(case_id);rid=str(uuid.uuid4())
 with transaction(path) as c:
  c.execute('INSERT INTO runs(id,case_id,state,created_at,metadata) VALUES(?,?,?,?,?)',(rid,case_id,'created',now(),json.dumps(metadata or {})));emit(c,rid,'created',{'brief':case(case_id)['brief'],'synthetic':True})
 return rid
def get(rid,path=None):
 with connect(path) as c:
  row=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
  if row is None:raise KeyError(rid)
  d=dict(row);d['proposal']=json.loads(d['proposal']) if d['proposal'] else None;d['metadata']=json.loads(d['metadata']);d['events']=[dict(e)|{'payload':json.loads(e['payload'])} for e in c.execute('SELECT * FROM events WHERE run_id=? ORDER BY seq',(rid,))];return d
def transition(rid,state,payload=None,path=None,allowed=None):
 with transaction(path) as c:
  row=c.execute('SELECT state FROM runs WHERE id=?',(rid,)).fetchone()
  if row is None:raise KeyError(rid)
  if row['state'] in TERMINAL or (allowed and row['state'] not in allowed):return False
  c.execute('UPDATE runs SET state=? WHERE id=?',(state,rid));emit(c,rid,state,payload or {});return True
