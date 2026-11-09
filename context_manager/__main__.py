"""Commands share one codebase and one local state directory."""
import argparse,os
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('role',choices=('init','api','worker','reader','broker'));p.add_argument('--home',default=os.environ.get('CONTEXT_MANAGER_HOME','/data'));p.add_argument('--bridge',default=os.environ.get('CONTEXT_MANAGER_BRIDGE'));p.add_argument('--bind',default='127.0.0.1');a=p.parse_args()
    if a.role=='init':
        from .catalog import Catalog
        Catalog(a.home)
    elif a.role=='worker':
        from .engine import run_worker
        run_worker(a.home)
    elif a.role=='broker':
        from .broker import run
        run(a.home,a.bridge)
    else:
        import uvicorn
        if a.role=='api':
            from .web import create_app
            app=create_app(a.home);port=8791
        else:
            from .reader import create_reader
            app=create_reader(a.home);port=8792
        uvicorn.run(app,host=a.bind,port=port,log_level='error',access_log=False)

if __name__=='__main__':main()
