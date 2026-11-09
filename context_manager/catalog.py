"""Local operational catalog. Source text and credentials never go to stdout."""
import contextlib,hashlib,hmac,json,os,re,secrets,sqlite3,time,uuid
from pathlib import Path

PROJECT=re.compile(r'p[0-9a-f]{24}')
FOLDERS=('Agreements','Receipts','Statements','Notes','Other')
DEFAULT_PROFILE={'chat_model':'google/gemma-4-12b-qat','embedding_model':'text-embedding-nomic-embed-text-v1.5','ocr_model':'glm-ocr','ocr_quantization':'Q8_0','model_origin':'http://127.0.0.1:1235'}
def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def uid(prefix=''):return prefix+uuid.uuid4().hex
def now():return time.time()
def safe_name(value):
    if not isinstance(value,str) or not 1<=len(value)<=180 or any(ord(c)<32 for c in value) or '/' in value or '\\' in value or value in ('.','..'):
        raise ValueError('Choose a plain filename without folder paths.')
    return value
def project_id(value):
    if not PROJECT.fullmatch(value or ''):raise ValueError('Unknown project.')
    return value

SCHEMA='''
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,created REAL NOT NULL,token_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,csrf TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,name TEXT NOT NULL,extension TEXT NOT NULL,sha256 TEXT NOT NULL,object_key TEXT NOT NULL,size INTEGER NOT NULL,status TEXT NOT NULL,category TEXT NOT NULL DEFAULT 'Other',document_id TEXT NOT NULL,review_json TEXT,error TEXT,created REAL NOT NULL,updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS receipts_project ON receipts(project_id,created);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,receipt_id TEXT,kind TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,stage TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,lease_until REAL NOT NULL DEFAULT 0,worker TEXT,cancel_requested INTEGER NOT NULL DEFAULT 0,error TEXT,artifact TEXT,generation TEXT,created REAL NOT NULL,updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS jobs_project ON jobs(project_id,created);
CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,source TEXT NOT NULL,target TEXT NOT NULL,chunk_id TEXT NOT NULL,source_version TEXT NOT NULL,target_version TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',created REAL NOT NULL,UNIQUE(project_id,source,target,source_version,target_version));
CREATE TABLE IF NOT EXISTS workers(id TEXT PRIMARY KEY,last_seen REAL NOT NULL);
'''

class Catalog:
    def __init__(self,home,readonly=False):
        self.home=Path(home).resolve();self.readonly=readonly;self.path=self.home/'control/catalog.sqlite'
        if not readonly:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            for name in ('projects','uploads','exports'):(self.home/name).mkdir(exist_ok=True)
            with contextlib.closing(self.connect()) as c:c.executescript(SCHEMA)
            profile=self.home/'control/profile.json'
            if not profile.exists():self.save(profile,DEFAULT_PROFILE)
            code=self.home/'control/owner-code.txt'
            if not code.exists():
                code.write_text(secrets.token_urlsafe(28),encoding='utf-8')
                if os.name!='nt':code.chmod(0o600)
    def connect(self):
        c=sqlite3.connect('file:'+self.path.as_posix()+'?mode=ro' if self.readonly else str(self.path),uri=self.readonly,timeout=15)
        c.row_factory=sqlite3.Row;c.execute('PRAGMA busy_timeout=15000')
        # Small operational catalog; DELETE mode lets the reader mount it truly
        # read-only without needing to create SQLite WAL shared-memory files.
        if not self.readonly:c.execute('PRAGMA journal_mode=DELETE');c.execute('PRAGMA synchronous=FULL')
        return c
    @contextlib.contextmanager
    def transaction(self):
        c=self.connect()
        try:c.execute('BEGIN IMMEDIATE');yield c;c.commit()
        except Exception:c.rollback();raise
        finally:c.close()
    def rows(self,sql,args=()):
        with contextlib.closing(self.connect()) as c:return [dict(r) for r in c.execute(sql,args).fetchall()]
    def one(self,sql,args=()):
        r=self.rows(sql,args);return r[0] if r else None
    def write(self,sql,args=()):
        with contextlib.closing(self.connect()) as c:
            with c:c.execute(sql,args)
    def save(self,path,value):
        from context_layer.local_model import save_json
        save_json(path,value)
    @property
    def profile(self):return json.loads((self.home/'control/profile.json').read_text(encoding='utf-8-sig'))
    def project_home(self,pid):return self.home/'projects'/project_id(pid)
    def project(self,pid):
        p=self.one('SELECT id,name,description,created FROM projects WHERE id=?',(project_id(pid),))
        if not p:raise ValueError('Unknown project.')
        return p
    def projects(self):return self.rows('SELECT id,name,description,created FROM projects ORDER BY created')
    def create_project(self,name,description=''):
        if not isinstance(name,str) or not name.strip() or len(name)>100 or len(description)>500:raise ValueError('Enter a project name, up to 100 characters.')
        from context_layer.library import Library
        pid='p'+uuid.uuid4().hex[:24];home=self.project_home(pid);Library(home)
        token=secrets.token_urlsafe(36)
        self.save(home/'settings.json',{**self.profile,'api_token':secrets.token_urlsafe(36)})
        (home/'mcp-token.txt').write_text(token,encoding='utf-8')
        if os.name!='nt':(home/'mcp-token.txt').chmod(0o600)
        self.write('INSERT INTO projects VALUES(?,?,?,?,?)',(pid,name.strip(),description.strip(),now(),digest(token)))
        return self.project(pid)
    def verify_project_token(self,pid,token):
        p=self.one('SELECT token_hash FROM projects WHERE id=?',(project_id(pid),))
        return bool(p and hmac.compare_digest(p['token_hash'],digest(token)))
    def login(self,code):
        if not isinstance(code,str) or not hmac.compare_digest(code,(self.home/'control/owner-code.txt').read_text().strip()):raise PermissionError('Invalid access code.')
        token=secrets.token_urlsafe(36);csrf=secrets.token_urlsafe(24)
        self.write('INSERT INTO sessions VALUES(?,?,?)',(digest(token),csrf,now()+8*3600))
        return token,csrf
    def session(self,token):return self.one('SELECT csrf FROM sessions WHERE token_hash=? AND expires>?',(digest(token or ''),now()))
    def enqueue(self,pid,kind,receipt=None,payload=None):
        self.project(pid);jid=uid('j');t=now()
        self.write('INSERT INTO jobs(id,project_id,receipt_id,kind,payload,status,stage,created,updated) VALUES(?,?,?,?,?,?,?,?,?)',(jid,pid,receipt,kind,json.dumps(payload or {}),'queued','Queued',t,t))
        return jid
    def receipt(self,rid):
        r=self.one('SELECT * FROM receipts WHERE id=?',(rid,))
        if not r:raise ValueError('Unknown upload.')
        return r
    def claim(self,worker):
        with self.transaction() as c:
            t=now()
            c.execute("UPDATE jobs SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'queued' END,stage='Recovered after worker restart',worker=NULL WHERE status='running' AND lease_until<?",(t,))
            r=c.execute("SELECT * FROM jobs j WHERE status='queued' AND cancel_requested=0 AND NOT EXISTS(SELECT 1 FROM jobs x WHERE x.project_id=j.project_id AND x.status='running' AND x.lease_until>?) ORDER BY created LIMIT 1",(t,)).fetchone()
            if not r:return None
            c.execute("UPDATE jobs SET status='running',stage='Starting',attempts=attempts+1,worker=?,lease_until=?,updated=? WHERE id=?",(worker,t+30,t,r['id']))
            c.execute('INSERT OR REPLACE INTO workers VALUES(?,?)',(worker,t))
            return dict(c.execute('SELECT * FROM jobs WHERE id=?',(r['id'],)).fetchone())
    def heartbeat(self,worker):
        t=now()
        with self.transaction() as c:
            c.execute('INSERT OR REPLACE INTO workers VALUES(?,?)',(worker,t))
            c.execute("UPDATE jobs SET lease_until=? WHERE worker=? AND status='running'",(t+30,worker))
    def stage(self,job,label):self.write('UPDATE jobs SET stage=?,updated=? WHERE id=?',(label,now(),job['id']))
    def cancelled(self,jid):return bool(self.one('SELECT cancel_requested FROM jobs WHERE id=?',(jid,))['cancel_requested'])
    def finish(self,job,status,stage,error=None,artifact=None,generation=None):
        self.write('UPDATE jobs SET status=?,stage=?,error=?,artifact=?,generation=?,lease_until=0,updated=? WHERE id=?',(status,stage,error,artifact,generation,now(),job['id']))
    def cancel(self,jid):
        with self.transaction() as c:
            r=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
            if not r:raise ValueError('Unknown job.')
            if r['status'] in ('complete','duplicate'):raise ValueError('This job has already completed.')
            c.execute("UPDATE jobs SET cancel_requested=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END,updated=? WHERE id=?",(now(),jid))
    def retry(self,jid):
        with self.transaction() as c:
            r=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
            if not r or r['status'] not in ('failed','cancelled'):raise ValueError('Only a failed or cancelled job can be retried.')
            c.execute("UPDATE jobs SET status='queued',stage='Queued for retry',cancel_requested=0,error=NULL,lease_until=0,updated=? WHERE id=?",(now(),jid))
