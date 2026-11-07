"""Fixed-loopback inference and an internal-container file bridge. No redirects/proxies."""
import hashlib,ipaddress,json,os,time,urllib.request,uuid
from pathlib import Path

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**kw):raise ValueError('Redirect refused')

def save_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.pending')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def require_broker(queue,max_age=15):
    """Fail promptly when the host queue consumer is absent; no network probe."""
    try:
        heartbeat=json.loads((Path(queue)/'broker.heartbeat.json').read_text(encoding='utf-8'))
        age=time.time()-float(heartbeat['time'])
        if not -5<=age<=max_age:raise ValueError('Stale broker heartbeat')
    except (OSError,ValueError,KeyError,TypeError):
        raise RuntimeError('Local inference broker is not ready. Run scripts/restart-context.ps1 before retrying.') from None

class LocalModel:
    def __init__(self,home):
        self.home=Path(home);self.config=json.loads((self.home/'settings.json').read_text(encoding='utf-8'))
    def request(self,path,body=None):
        if path not in ('/v1/models','/v1/embeddings','/v1/chat/completions'):raise ValueError('Inference route refused')
        if os.environ.get('CONTEXT_FILE_BROKER')=='1':
            queue=self.home/'queue';key=uuid.uuid4().hex
            require_broker(queue)
            save_json(queue/(key+'.request.json'),{'path':path,'body':body})
            response=queue/(key+'.response.json');end=time.monotonic()+300;next_check=time.monotonic()+1
            while not response.exists():
                if time.monotonic()>end:raise TimeoutError('Local model broker unavailable')
                if time.monotonic()>=next_check:
                    require_broker(queue);next_check=time.monotonic()+1
                time.sleep(.05)
            r=json.loads(response.read_text(encoding='utf-8'))
            # Queue payloads can contain private text. Retention is local only;
            # keep them out of service logs and public support bundles.
            if r['status']!=200:raise RuntimeError('Local inference failed; diagnostics stay local')
            return r['body']
        return self.direct(path,body)
    def direct(self,path,body=None):
        from urllib.parse import urlsplit
        origin=self.config['model_origin'];u=urlsplit(origin)
        if u.scheme!='http' or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
            raise ValueError('Only a fixed local HTTP origin is allowed')
        if u.hostname not in ('127.0.0.1','::1') or not ipaddress.ip_address(u.hostname).is_loopback:
            raise ValueError('Remote model endpoint refused')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        data=None if body is None else json.dumps(body).encode('utf-8')
        req=urllib.request.Request(origin.rstrip('/')+path,data=data,headers={'Content-Type':'application/json'})
        with opener.open(req,timeout=300) as r:return json.load(r)
    def embed(self,texts,query=False):
        prefix='search_query: ' if query else 'search_document: '
        r=self.request('/v1/embeddings',{'model':self.config['embedding_model'],'input':[prefix+t for t in texts]})
        vectors=[x['embedding'] for x in sorted(r['data'],key=lambda x:x['index'])]
        if len(vectors)!=len(texts) or any(len(v)!=768 for v in vectors):raise ValueError('Embedding identity/dimension mismatch')
        return vectors
