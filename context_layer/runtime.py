"""Native runtime: use installed packages and local extension files only."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def default_home():
    return Path(os.environ.get('LOCAL_CONTEXT_HOME',str(Path.home()/'.local/share/local-context'))).expanduser().resolve()

def extension_dir():
    value=os.environ.get('CONTEXT_EXTENSION_DIR')
    if not value:raise RuntimeError('Set CONTEXT_EXTENSION_DIR to the installed native Ladybug extension directory. No download is attempted.')
    return Path(value).expanduser().resolve()

def connect(path,read_only=False):
    import ladybug
    if ladybug.__version__!='0.22.1':raise RuntimeError('This library requires Ladybug 0.22.1')
    db=ladybug.Database(str(path),read_only=read_only,buffer_pool_size=268435456,max_num_threads=2)
    c=ladybug.Connection(db)
    try:
        for name in ('vector','fts'):
            base=extension_dir();p=base/f'lib{name}.lbug_extension'
            if not p.is_file():p=base/name/f'lib{name}.lbug_extension'
            if not p.is_file():raise RuntimeError('Offline Ladybug extension missing; no automatic download')
            c.execute("LOAD '"+p.as_posix().replace("'","''")+"'")
        return db,c
    except Exception:
        c.close();db.close();raise

def rows(result):return [dict(zip(result.get_column_names(),r)) for r in result.get_all()]
