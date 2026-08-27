import json,sqlite3,uuid
from pathlib import Path
DB=Path(__file__).resolve().parents[3]/'policyripple.db'
def init_db():
 c=sqlite3.connect(DB); c.execute('CREATE TABLE IF NOT EXISTS simulations(id TEXT PRIMARY KEY,config TEXT,result TEXT)'); c.commit(); c.close()
def create(cfg):
 sid=str(uuid.uuid4()); c=sqlite3.connect(DB); c.execute('INSERT INTO simulations VALUES(?,?,?)',(sid,cfg.model_dump_json(),None)); c.commit(); c.close(); return sid
def get(sid):
 c=sqlite3.connect(DB); row=c.execute('SELECT id,config,result FROM simulations WHERE id=?',(sid,)).fetchone(); c.close(); return row
def save(sid,result):
 c=sqlite3.connect(DB); c.execute('UPDATE simulations SET result=? WHERE id=?',(json.dumps(result),sid)); c.commit(); c.close()
