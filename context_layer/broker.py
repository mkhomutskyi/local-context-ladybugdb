"""Host-side fixed-loopback broker. Private queue content never goes to stdout."""
import argparse,json,time,threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import runtime
from .local_model import LocalModel,save_json
from .service import validate_chat
from .ocr import validate_request as validate_ocr

def validate(path,body,settings):
    if path=='/v1/models' and body is None:return None
    if path=='/v1/chat/completions':
        if isinstance(body,dict) and body.get('model')==settings.get('ocr_model','glm-ocr'):return validate_ocr(body,settings)
        return validate_chat(body,settings)
    if path=='/v1/embeddings':
        if not isinstance(body,dict) or body.get('model')!=settings['embedding_model']:raise ValueError('Embedding model refused')
        texts=body.get('input');texts=[texts] if isinstance(texts,str) else texts
        if not isinstance(texts,list) or not 1<=len(texts)<=32 or any(not isinstance(t,str) or len(t)>12000 for t in texts):raise ValueError('Embedding input limit')
        return {'model':settings['embedding_model'],'input':texts}
    raise ValueError('Route refused')

def run(home):
    home=Path(home);model=LocalModel(home);queue=home/'queue';pending=set();lock=threading.Lock()
    def process(path):
        response=path.with_name(path.name.replace('.request.json','.response.json'))
        try:
            if path.stat().st_size>8*1024*1024:raise ValueError('Input limit')
            request=json.loads(path.read_text(encoding='utf-8'));body=validate(request['path'],request.get('body'),model.config)
            result=model.direct(request['path'],body);save_json(response,{'status':200,'body':result})
        except Exception as e:
            save_json(response,{'status':503,'body':{'error':'Local request failed','error_class':type(e).__name__}})
        finally:
            with lock:pending.discard(path.name)
    heartbeat_at=0
    with ThreadPoolExecutor(max_workers=2) as pool:
        while True:
            if time.monotonic()>=heartbeat_at:
                save_json(queue/'broker.heartbeat.json',{'time':time.time(),'pid':__import__('os').getpid()})
                heartbeat_at=time.monotonic()+1
            for path in queue.glob('*.request.json'):
                if not __import__('re').fullmatch(r'[a-f0-9]{32}\.request\.json',path.name):continue
                if path.with_name(path.name.replace('.request.json','.response.json')).exists():continue
                with lock:
                    if path.name in pending:continue
                    pending.add(path.name)
                pool.submit(process,path)
            time.sleep(.1)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',required=True);a=p.parse_args();run(a.home)
