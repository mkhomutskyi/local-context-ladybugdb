"""Host-only bridge with a fixed inference profile, no proxy or redirects."""
import json,os,re,threading,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from context_layer.broker import validate
from context_layer.local_model import LocalModel,save_json

def run(home,bridge):
    home=Path(home);queue=Path(bridge);queue.mkdir(parents=True,exist_ok=True)
    profile=home/'control/profile.json'
    if not profile.exists():profile=home/'profile.json'
    model=object.__new__(LocalModel);model.home=home;model.config=json.loads(profile.read_text(encoding='utf-8-sig'))
    pending=set();lock=threading.Lock()
    def process(path):
        response=path.with_name(path.name.replace('.request.json','.response.json'))
        try:
            if path.stat().st_size>8*1024*1024:raise ValueError('Input limit')
            request=json.loads(path.read_text(encoding='utf-8'));body=validate(request['path'],request.get('body'),model.config)
            result=model.direct(request['path'],body);save_json(response,{'status':200,'body':result})
        except Exception as exc:save_json(response,{'status':503,'body':{'error_class':type(exc).__name__}})
        finally:
            # A processed request is no longer needed. Responses remain until collected.
            path.unlink(missing_ok=True)
            with lock:pending.discard(path.name)
    with ThreadPoolExecutor(max_workers=2) as pool:
        beat=0
        while True:
            if time.monotonic()>beat:
                save_json(queue/'broker.heartbeat.json',{'time':time.time(),'pid':os.getpid()});beat=time.monotonic()+1
            for path in queue.glob('*.request.json'):
                if not re.fullmatch(r'[a-f0-9]{32}\.request\.json',path.name):continue
                with lock:
                    if path.name in pending:continue
                    pending.add(path.name)
                pool.submit(process,path)
            time.sleep(.1)
