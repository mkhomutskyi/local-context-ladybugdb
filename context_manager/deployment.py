"""Docker startup from public sources; private data is outside the build context."""
import hashlib,json,os,socket,subprocess,sys,time
from pathlib import Path
from context_layer import runtime

def serve_docker(catalog,build=False):
    root=runtime.ROOT;home=catalog.home;bridge=home/'bridge';bridge.mkdir(exist_ok=True)
    prefix='lc-manager-'+hashlib.sha256(str(home).encode()).hexdigest()[:10]
    env={**os.environ,'COMPOSE_PROJECT_NAME':prefix,'MANAGER_VOLUME':prefix+'-data','MANAGER_BRIDGE':bridge.as_posix(),'MANAGER_SOURCE':(root/'docker').as_posix(),'CONTEXT_EXTENSIONS':runtime.extension_dir().as_posix(),'TOKEN_CACHE':os.environ['TIKTOKEN_CACHE_DIR']}
    compose=['docker','compose','-f',str(root/'docker/compose.yaml')]
    def run(args):return subprocess.run(args,cwd=root,env=env,check=True,capture_output=True,text=True).stdout
    # Never stop another deployment or silently occupy its ports.
    for port in (8791,8792):
        with socket.socket() as s:s.bind(('127.0.0.1',port))
    image='local-context-manager:0.2.0'
    if build:run(['docker','build','--pull=false','-f','docker/Dockerfile','-t',image,'.'])
    else:run(['docker','image','inspect',image])
    volumes=run(['docker','volume','ls','--filter','name=^'+prefix+'-data$','--format','{{.Name}}']).strip()
    if not volumes:
        run(['docker','volume','create','--label','local-context-manager.owner=local-manager',prefix+'-data'])
        run(['docker','run','--rm','--network','none','--user','0:0','--mount','type=volume,source='+prefix+'-data,target=/data','--entrypoint','python',image,'-c','import os; os.chown("/data",1000,1000); os.chmod("/data",0o700)'])
    label=run(['docker','volume','inspect',prefix+'-data','--format','{{index .Labels "local-context-manager.owner"}}']).strip()
    if label!='local-manager':raise ValueError('The selected data volume is not owned by this manager.')
    run(['docker','run','--rm','--network','none','--mount','type=volume,source='+prefix+'-data,target=/data',image,'init'])
    run(['docker','run','--rm','--network','none','--mount','type=volume,source='+prefix+'-data,target=/data','--mount','type=bind,source='+str(home/'control/profile.json')+',target=/profile.json,readonly','--entrypoint','python',image,'-c','import shutil; shutil.copyfile("/profile.json","/data/control/profile.json")'])
    log=(home/'control/broker.log').open('ab');broker=None;started=False
    try:
        broker=subprocess.Popen([sys.executable,'-m','context_manager','broker','--home',str(home),'--bridge',str(bridge)],cwd=root,env=env,stdout=log,stderr=log)
        started=True;run(compose+['up','-d','--pull','never']);run(compose+['restart','proxy'])
        api=json.loads(run(compose+['ps','--format','json','api']).strip().splitlines()[0])
        run(['docker','cp',api['Name']+':/data/control/owner-code.txt',str(home/'control/owner-code.txt')])
        import httpx
        with httpx.Client(trust_env=False,timeout=2) as client:
            for attempt in range(30):
                try:
                    if client.get('http://127.0.0.1:8791/health').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(1)
            else:raise RuntimeError('Manager health check did not become ready.')
        print('Local Context: http://127.0.0.1:8791',flush=True);print('Access code: '+str(home/'control/owner-code.txt'),flush=True);print('Docker data volume: '+prefix+'-data',flush=True)
        while broker.poll() is None:time.sleep(.5)
        raise RuntimeError('Local inference bridge stopped; check its private log.')
    except KeyboardInterrupt:pass
    finally:
        if started:
            try:run(compose+['stop'])
            except Exception:pass
        if broker and broker.poll() is None:broker.terminate();broker.wait(timeout=6)
        log.close()
