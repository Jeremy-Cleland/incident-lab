import asyncio,json
import pytest
from incident_lab import store
from incident_lab.models import Proposal
from incident_lab.simulator import read_tool,propose,approve,cancel
from incident_lab.agent import session,tool,investigate

@pytest.fixture
def db(tmp_path):
 path=str(tmp_path/'test.sqlite');store.init(path);return path

def prepared(db):
 fixture=store.cases()[0];rid=store.create(fixture['id'],path=db);store.transition(rid,'investigating',path=db)
 result=read_tool(rid,'query_logs',{},db)
 with store.transaction(db) as c:store.emit(c,rid,'tool_result',{'name':'query_logs','result':result})
 p={'diagnosis':'bad_deployment','action':'rollback_release','target':'orders-api','summary':'Release change correlates with TypeError','evidence_ids':['log-001'],'uncertainty':'Synthetic test','expected_effect':'API recovery'}
 pid=propose(rid,p,db);return rid,pid,p

def test_approval_single_execution_and_stale(db):
 rid,pid,_=prepared(db)
 with pytest.raises(ValueError):approve(rid,{'proposal_id':pid,'revision':1,'decision':'approve'},db)
 body={'proposal_id':pid,'revision':0,'decision':'approve'};approve(rid,body,db)
 with pytest.raises(ValueError):approve(rid,body,db)
 assert store.get(rid,db)['executions']==1
 assert read_tool(rid,'get_service_health',{},db)['status']=='healthy'

def test_cross_run_and_reject(db):
 first,pid,_=prepared(db);second,_,_=prepared(db)
 with pytest.raises(ValueError):approve(second,{'proposal_id':pid,'revision':0,'decision':'approve'},db)
 approve(first,{'proposal_id':pid,'revision':0,'decision':'reject'},db)
 assert store.get(first,db)['executions']==0

def test_cancel_and_invalid_action(db):
 rid,pid,p=prepared(db);cancel(rid,db)
 with pytest.raises(ValueError):approve(rid,{'proposal_id':pid,'revision':0,'decision':'approve'},db)
 with pytest.raises(ValueError):Proposal.model_validate(p|{'action':'execute_shell'})
 with pytest.raises(ValueError):read_tool(rid,'query_logs',{'run_id':'other'},db)

async def test_actual_mcp_is_scoped_and_read_only(db):
 rid=store.create(store.cases()[0]['id'],path=db)
 async with session(rid,db) as client:
  names={t.name for t in (await client.list_tools()).tools}
  assert names=={'get_service_health','query_logs','query_metrics','list_changes','search_runbooks'}
  result=await tool(client,rid,'query_logs',{},db)
  assert 'supports' not in json.dumps(result)
  assert result['items'][0]['id']=='log-001'
  assert (await client.call_tool('execute_shell',{'command':'whoami'})).isError

async def test_unavailable_provider_fails_explicitly(db):
 class Unavailable:
  async def chat(self,*args,**kwargs):raise ConnectionError('Ollama unavailable')
 rid=store.create(store.cases()[0]['id'],path=db);await investigate(rid,db,Unavailable());assert store.get(rid,db)['state']=='failed'

def test_split_frozen():
 import hashlib
 manifest=json.loads((store.ROOT/'cases/manifest.json').read_text())
 assert hashlib.sha256((store.ROOT/'cases/cases.json').read_bytes()).hexdigest()==manifest['sha256']
 assert sum(c['split']=='development' for c in store.cases())==12
 assert sum(c['split']=='held_out' for c in store.cases())==18
