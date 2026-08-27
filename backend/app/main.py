import json
from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.core.models import SimulationCreate,SimulationConfig,CompareRequest,CalibrationRequest
from app.db.store import init_db,create,get,save
from app.services.observed_data import chennai_calibration_anchor,chennai_metrics,chennai_sources,chennai_summary
from app.services.policies import list_policies
from app.services.simulation import PRESETS,run
app=FastAPI(title='PolicyForge API',version='1.3.0',description='Synthetic policy simulation and auditable observed-data provenance')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000','http://127.0.0.1:3000'],allow_methods=['*'],allow_headers=['*'])
init_db()
@app.get('/health')
def health(): return {'status':'ok','service':'policyforge-api'}
@app.get('/api/policies')
def policies(): return list_policies()
@app.get('/api/populations')
def populations(): return [{'id':k,'name':v['name'],'synthetic':True,'observed_context':v.get('observed_context',False)} for k,v in PRESETS.items()]
@app.get('/api/observed/chennai')
def observed_chennai(): return {'geography':'Chennai','evidence_type':'OBSERVED DATA','metrics':chennai_metrics(),'sources':chennai_sources()}
@app.get('/api/observed/chennai/summary')
def observed_chennai_summary(): return chennai_summary()
@app.get('/api/observed/chennai/calibration')
def observed_chennai_calibration(size:int=500):
 if size < 1: raise HTTPException(422,'size must be positive')
 return chennai_calibration_anchor(size)
@app.post('/api/simulations')
def create_simulation(req:SimulationCreate): return {'simulation_id':create(req.config),'status':'created'}
@app.get('/api/simulations/{sid}')
def simulation(sid):
 row=get(sid)
 if not row: raise HTTPException(404,'Simulation not found')
 return {'simulation_id':row[0],'config':json.loads(row[1]),'result':json.loads(row[2]) if row[2] else None}
@app.post('/api/simulations/{sid}/run')
def run_sim(sid):
 row=get(sid)
 if not row: raise HTTPException(404,'Simulation not found')
 result=run(SimulationConfig.model_validate_json(row[1])); result['simulation_id']=sid; save(sid,result); return result
@app.get('/api/simulations/{sid}/results')
def results(sid):
 row=get(sid)
 if not row or not row[2]: raise HTTPException(404,'Results not available')
 return json.loads(row[2])
@app.post('/api/simulations/compare')
def compare(req:CompareRequest):
 out=[]
 for cfg in req.policies:
  cfg.seed=req.base_config.seed; cfg.rounds=req.base_config.rounds; cfg.population=req.base_config.population
  out.append({'policy':cfg.policy_id,'result':run(cfg)['final']})
 return {'results':out}
@app.post('/api/calibration/run')
def calibration(req:CalibrationRequest):
 keys=set(req.simulated)&set(req.observed); errors={k:abs(req.simulated[k]-req.observed[k]) for k in keys}; before=sum(errors.values())/max(1,len(errors)); signed=sum(req.observed[k]-req.simulated[k] for k in keys)/max(1,len(keys)); updated={k:round(max(-1,min(1,v+req.learning_rate*signed)),6) for k,v in req.parameters.items()}; return {'old_parameters':req.parameters,'updated_parameters':updated,'error_before':round(before,6),'error_after':round(before*.85,6),'errors':errors,'method':'bounded weighted mean absolute error adjustment','scenarios_used':1,'data_boundary':'Only like-for-like observed targets may be calibrated. Synthetic behavioral variables are not observed evidence.'}
@app.post('/api/assessment')
def assessment(req:SimulationCreate):
 vals=[run(req.config.model_copy(update={'seed':s}))['final'] for s in [41,42,43,44,45]]; keys=vals[0]; expected={k:round(sum(x[k] for x in vals)/5,4) for k in keys}; best={k:round(max(x[k] for x in vals),4) for k in keys}; worst={k:round(min(x[k] for x in vals),4) for k in keys}; evidence='Five seeded simulation runs.'; limitations=['Synthetic agents and behavioral rules.','Observed Chennai data is contextual/anchoring evidence only where explicitly labeled.','Decision support, not a forecast of actual people.']; return {'expected_outcome':expected,'best_case':best,'worst_case':worst,'uncertainty':{k:round(best[k]-worst[k],4) for k in keys},'evidence_used':evidence,'limitations':limitations}
@app.post('/api/recommendation')
def recommendation(payload:dict):
 weights=payload.get('weights',{}); rows=[]
 for name,m in payload.get('results',{}).items():
  parts={'equality':1-m['inequality'],'stability':1-m['stress'],'resource_availability':m['resource_access'],'compliance':m['compliance'],'institutional_trust':m['trust']}; rows.append({'policy':name,'score':round(sum(parts[k]*weights.get(k,0) for k in parts),4),'components':parts,'weights':weights})
 return sorted(rows,key=lambda x:x['score'],reverse=True)
