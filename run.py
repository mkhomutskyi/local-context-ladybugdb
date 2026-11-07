"""One entry point for repeatable native local MCP startup. No downloads."""
import argparse,json,os,secrets,sys
from pathlib import Path

def configure(home,origin,chat,embedding):
    from context_layer.library import read
    from context_layer.local_model import LocalModel,save_json
    from context_layer import runtime
    home=Path(home).expanduser().resolve()
    if home==runtime.ROOT or runtime.ROOT in home.parents:
        raise ValueError('Keep runtime state outside the source checkout; choose --home outside this directory.')
    path=home/'settings.json'
    if path.exists():
        settings=read(path)
        for key,value in (('chat_model',chat),('embedding_model',embedding),('model_origin',origin)):
            if value and value!=settings[key]:raise ValueError('Existing settings differ; this command will not rewrite model identity or endpoint.')
    else:
        if not chat or not embedding:raise ValueError('First run requires --chat-model and --embedding-model using exact installed API IDs.')
        settings={'schema':1,'chat_model':chat,'embedding_model':embedding,'model_origin':origin or 'http://127.0.0.1:1235','ocr_model':'glm-ocr','ocr_quantization':'Q8_0','api_token':secrets.token_urlsafe(36),'webui_secret':secrets.token_urlsafe(48)}
    # Resolve and validate local inference before creating a library or settings.
    model=object.__new__(LocalModel);model.home=home;model.config=settings
    inventory=model.direct('/v1/models')
    available={item['id'] for item in inventory.get('data',[])}
    if any(settings[k] not in available for k in ('chat_model','embedding_model')):
        raise ValueError('Configured canonical model ID is unavailable. Inspect LM Studio inventory; no model is downloaded or renamed.')
    from context_layer.library import Library,token_count
    runtime.extension_dir();token_count('readiness')
    if not path.exists():
        home.mkdir(parents=True,exist_ok=True)
        if os.name!='nt':home.chmod(0o700)
        save_json(path,settings)
        if os.name!='nt':path.chmod(0o600)
    lib=Library(home)
    if not lib.current():
        from context_layer.library import writer
        with writer(home):lib.publish({'documents':[],'chunks':[],'edges':[],'vectors':[]},settings['embedding_model'],'empty-initialization')
    return lib

def seed_demo(lib):
    """Copy only repository-authored fictional inputs to an empty library."""
    import shutil
    from context_layer import runtime
    if lib.prepared()['documents']:raise ValueError('--demo requires an empty library; existing data is preserved. Omit --demo on restart.')
    if any(p.is_file() for p in (lib.home/'inbox').rglob('*')):raise ValueError('Demo requires an empty inbox.')
    for name in ('orchid-statement.txt','orchid-receipt.txt'):
        shutil.copyfile(runtime.ROOT/'examples'/name,lib.home/'inbox'/name)
    result=lib.ingest('synthetic')
    if result['needs_review'] or result['added']!=2:raise RuntimeError('Demo ingestion incomplete; inspect private journal.')
    data=lib.prepared();statement=next(d for d in data['documents'] if d['title']=='orchid-statement.txt');receipt=next(d for d in data['documents'] if d['title']=='orchid-receipt.txt')
    chunk=next(c for c in data['chunks'] if c['doc_id']==statement['id'])
    lib.link(statement['id'],receipt['id'],chunk['id'])

def main():
    from context_layer import runtime
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',default=str(runtime.default_home()))
    p.add_argument('--model-origin');p.add_argument('--chat-model');p.add_argument('--embedding-model')
    p.add_argument('--extensions',help='Local native vector/fts extension directory')
    p.add_argument('--token-cache',help='Local tiktoken cache directory')
    p.add_argument('--transport',choices=('stdio','http'),default='stdio')
    p.add_argument('--demo',action='store_true',help='First run only: populate an empty library with two fictional records')
    p.add_argument('--check',action='store_true',help='Initialize if needed, verify local dependencies and report aggregate status, then exit')
    a=p.parse_args()
    if sys.version_info<(3,11):raise RuntimeError('Python 3.11 or newer required')
    if a.extensions:os.environ['CONTEXT_EXTENSION_DIR']=str(Path(a.extensions).expanduser().resolve())
    if a.token_cache:os.environ['TIKTOKEN_CACHE_DIR']=str(Path(a.token_cache).expanduser().resolve())
    lib=configure(a.home,a.model_origin,a.chat_model,a.embedding_model)
    if a.demo:seed_demo(lib)
    from context_layer.library import Retrieval
    if a.check:
        retrieval=Retrieval(lib.home)
        try:print(json.dumps(retrieval.status()))
        finally:retrieval.close()
        return
    from context_layer.service import make_mcp,create_app
    if a.transport=='stdio':make_mcp(Retrieval(lib.home)).run(transport='stdio')
    else:
        import uvicorn
        print('MCP: http://127.0.0.1:8765/mcp; bearer token remains in private settings.json',file=sys.stderr)
        uvicorn.run(create_app(lib.home),host='127.0.0.1',port=8765,access_log=False,log_level='error')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # No private exception payloads, credentials or source text on stdout.
        print('Local context startup failed ('+type(exc).__name__+'). Check local prerequisites and private configuration.',file=sys.stderr)
        sys.exit(1)
