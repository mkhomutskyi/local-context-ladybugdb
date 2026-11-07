"""Local CLI. All document details are saved to private review files, never printed."""
import argparse,html,json,secrets,sys,time
from pathlib import Path
from . import runtime
from .library import Library,Retrieval,read,sha,writer
from .local_model import save_json

def review(home):
    lib=Library(home);data=lib.prepared();parts=['<!doctype html><html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>Private context review</title><style>body{max-width:960px;margin:40px auto;font:18px system-ui;line-height:1.5}pre{white-space:pre-wrap}summary{cursor:pointer}small{color:#555}</style><h1>Private context review</h1><p>Local file only. Extracted text, including OCR, needs owner review. No factual correctness score is implied.</p>']
    answer_file=lib.home/'review/real-grounded-answer.json'
    if answer_file.exists():
        saved=read(answer_file);answer=saved['response']['choices'][0]['message'].get('content') or ''
        parts.append('<h2>Saved local answer for review</h2><p>This is an ungraded model answer. Check the cited source text below.</p><pre>'+html.escape(saved['query'])+'</pre><pre>'+html.escape(answer)+'</pre><details><summary>Evidence supplied to the model</summary><pre>'+html.escape(json.dumps(saved['evidence'],ensure_ascii=False,indent=2))+'</pre></details><h2>Indexed documents</h2>')
    for d in data['documents']:
        parts.append('<details><summary>'+html.escape(d['title'])+'</summary><small>'+html.escape(json.dumps({k:d[k] for k in ('id','scope','version','review_state')}))+'</small>')
        for c in data['chunks']:
            if c['doc_id']==d['id']:parts.append('<p><strong>'+html.escape(c['id']+' Â· '+str(c['location'])+' Â· '+c['method'])+'</strong></p><pre>'+html.escape(c['text'])+'</pre>')
        parts.append('</details>')
    parts.append('</html>');(lib.home/'review/index.html').write_text('\n'.join(parts),encoding='utf-8')
    return {'review_created':True,'documents':len(data['documents']),'chunks':len(data['chunks'])}

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',default=str(runtime.default_home()));sub=p.add_subparsers(dest='command',required=True)
    i=sub.add_parser('init');i.add_argument('--model-origin',default='http://127.0.0.1:1235')
    b=sub.add_parser('bootstrap');b.add_argument('--baseline',required=True);b.add_argument('--source',required=True)
    i=sub.add_parser('ingest');i.add_argument('--scope',default='unassigned');i.add_argument('--ocr',action='store_true');i.add_argument('--replace-document')
    w=sub.add_parser('withdraw');w.add_argument('document_id')
    link=sub.add_parser('link');link.add_argument('--source',required=True);link.add_argument('--target',required=True);link.add_argument('--evidence-chunk',required=True)
    r=sub.add_parser('restore');r.add_argument('snapshot')
    for name in ('status','review','snapshot'):sub.add_parser(name)
    a=p.parse_args();lib=Library(a.home)
    try:
        if a.command=='init':
            config=lib.home/'settings.json'
            if config.exists():raise ValueError('Settings already exist')
            save_json(config,{'schema':1,'chat_model':'google/gemma-4-12b-qat','ocr_model':'glm-ocr','ocr_quantization':'Q8_0','embedding_model':'text-embedding-nomic-embed-text-v1.5','model_origin':a.model_origin,'api_token':secrets.token_urlsafe(36),'webui_secret':secrets.token_urlsafe(48)})
            result={'initialized':True}
        elif a.command=='bootstrap':result=lib.bootstrap(a.baseline,a.source)
        elif a.command=='ingest':result=lib.ingest(a.scope,a.ocr,a.replace_document)
        elif a.command=='withdraw':result=lib.withdraw(a.document_id)
        elif a.command=='link':result=lib.link(a.source,a.target,a.evidence_chunk)
        elif a.command=='restore':result=lib.restore(a.snapshot)
        elif a.command=='review':result=review(a.home)
        elif a.command=='snapshot':
            dest=lib.snapshot();save_json(lib.home/'exports/latest.json',{'snapshot':dest.name});result={'snapshot_created':True}
        else:
            retrieval=Retrieval(a.home)
            try:result=retrieval.status()
            finally:retrieval.close()
        print(json.dumps(result));return 0
    except Exception as e:
        lib.journal('command_failed',command=a.command,error_class=type(e).__name__,reason=str(e)[:200])
        print(json.dumps({'ok':False,'error_class':type(e).__name__,'diagnostics':'private ingestion journal'}));return 1
if __name__=='__main__':sys.exit(main())
