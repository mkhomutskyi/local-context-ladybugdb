"""Portable native manager startup. Reuses installed models and local assets."""
import argparse,json,os,socket,subprocess,sys,time
from pathlib import Path
from context_layer import runtime
from context_layer.local_model import LocalModel,save_json
from .catalog import Catalog,DEFAULT_PROFILE

def configure(home,values):
    home=Path(home).expanduser().resolve();checkout=runtime.ROOT.resolve()
    if home==checkout or checkout in home.parents or home==Path.home().resolve() or home==Path(home.anchor):
        raise ValueError('Choose a private state directory outside the source checkout, not your home directory or drive root.')
    profile_path=home/'control/profile.json'
    if profile_path.exists():
        profile=json.loads(profile_path.read_text(encoding='utf-8-sig'))
        if any(value is not None and value!=profile.get(key) for key,value in values.items()):raise ValueError('Existing profile differs; startup will not rewrite model identities or endpoint.')
    else:
        if not values.get('chat_model') or not values.get('embedding_model'):raise ValueError('First run requires the exact installed --chat-model and --embedding-model IDs.')
        profile={**DEFAULT_PROFILE,**{k:v for k,v in values.items() if v is not None}}
    model=object.__new__(LocalModel);model.home=home;model.config=profile
    inventory=model.direct('/v1/models');available={m['id'] for m in inventory.get('data',[])}
    if any(profile[k] not in available for k in ('chat_model','embedding_model')):raise ValueError('Configured canonical models are unavailable; inspect the installed inventory. No download or alias is created.')
    from context_layer.library import token_count
    token_count('local readiness')
    base=runtime.extension_dir()
    for name in ('vector','fts'):
        if not any(p.is_file() for p in (base/f'lib{name}.lbug_extension',base/name/f'lib{name}.lbug_extension')):raise ValueError('Prepare the native vector and fts extensions for this host first.')
    if not home.exists():
        home.mkdir(parents=True)
        if os.name!='nt':home.chmod(0o700)
    catalog=Catalog(home)
    if not profile_path.exists() or catalog.profile!=profile:save_json(profile_path,profile)
    return catalog

def serve(catalog):
    # Check both ports before starting any child. Never stop an existing service.
    probes=[]
    try:
        for port in (8791,8792):
            s=socket.socket();probes.append(s);s.bind(('127.0.0.1',port))
    finally:
        for s in probes:s.close()
    from context_layer.library import writer
    with writer(catalog.home/'control'):
        processes=[];handles=[];env=os.environ.copy();env.pop('CONTEXT_MANAGER_BRIDGE',None);env.pop('CONTEXT_FILE_BROKER',None)
        try:
            for role in ('api','reader','worker'):
                log=catalog.home/'control'/(role+'.log');f=log.open('ab');handles.append(f)
                processes.append(subprocess.Popen([sys.executable,'-m','context_manager',role,'--home',str(catalog.home)],cwd=runtime.ROOT,env=env,stdout=f,stderr=f))
            print('Local Context: http://127.0.0.1:8791',flush=True)
            print('Read the access code locally: '+str(catalog.home/'control/owner-code.txt'),flush=True)
            print('Ctrl+C stops this manager and retains its documents.',flush=True)
            while all(p.poll() is None for p in processes):time.sleep(.5)
            raise RuntimeError('A manager process stopped; inspect the private role logs.')
        except KeyboardInterrupt:pass
        finally:
            for p in processes:
                if p.poll() is None:p.terminate()
            for p in processes:
                try:p.wait(timeout=6)
                except subprocess.TimeoutExpired:p.kill();p.wait()
            for f in handles:f.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--home',default=str(Path.home()/'.local/share/local-context-manager'))
    p.add_argument('--chat-model');p.add_argument('--embedding-model');p.add_argument('--ocr-model');p.add_argument('--ocr-quantization');p.add_argument('--model-origin');p.add_argument('--extensions');p.add_argument('--token-cache');p.add_argument('--check',action='store_true');p.add_argument('--deployment',choices=('native','docker'),default='native');p.add_argument('--build',action='store_true',help='Build the public Docker image; dependency preparation needs network access')
    a=p.parse_args()
    if a.extensions:os.environ['CONTEXT_EXTENSION_DIR']=str(Path(a.extensions).expanduser().resolve())
    if a.token_cache:os.environ['TIKTOKEN_CACHE_DIR']=str(Path(a.token_cache).expanduser().resolve())
    values={k:getattr(a,k) for k in ('chat_model','embedding_model','ocr_model','ocr_quantization','model_origin')}
    c=configure(a.home,values)
    if a.check:print(json.dumps({'ready':True,'projects':len(c.projects()),'downloads':False,'profile_preserved':True}));return
    if a.deployment=='docker':
        from .deployment import serve_docker
        serve_docker(c,a.build)
    else:serve(c)
