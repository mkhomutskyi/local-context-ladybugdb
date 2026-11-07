"""Selective PDF OCR revisions. Source bytes and previous generations stay intact."""
import argparse,base64,hashlib,html,json,re,sys,time,uuid
from pathlib import Path
from . import runtime
from .library import Library,read,sha,writer
from .local_model import LocalModel,save_json
from .ocr import transcribe,GLM_PROMPT

RECIPE={'model':'glm-ocr','quantization':'Q8_0','prompt':GLM_PROMPT,'render_scale':2,'maximum_dimension':2400,'chunk_characters':1200,'chunk_stride':1000,'version':1}
REVISION=hashlib.sha256(json.dumps(RECIPE,sort_keys=True).encode()).hexdigest()

def prepare(home,out):
    import pymupdf
    lib=Library(home);out=Path(out)
    if (out/'plan.json').exists():raise ValueError('OCR plan already exists; preserve it and use a new output directory')
    out.mkdir(parents=True,exist_ok=True);(out/'pages').mkdir(exist_ok=True)
    name=lib.current();data=lib.prepared();pages=[];pdfs=total=0
    for doc in data['documents']:
        if doc.get('format','').lower()!='.pdf':continue
        pdfs+=1;source=lib.home/doc['object_key']
        if sha(source)!=doc['version']:raise ValueError('Original checksum mismatch')
        with pymupdf.open(source) as pdf:
            if pdf.needs_pass:raise ValueError('Encrypted input needs review')
            for n,page in enumerate(pdf,1):
                total+=1;text=page.get_text(sort=True).strip()
                old=[c for c in data['chunks'] if c['doc_id']==doc['id'] and str(c['location'])==str(n)]
                old_ocr=any('ocr' in c['method'] for c in old)
                if len(text)>=50 and not old_ocr:continue
                key=hashlib.sha256((doc['id']+'|'+str(n)).encode()).hexdigest()[:24]
                scale=min(2,2400/max(page.rect.width,page.rect.height));pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False)
                image_path=out/'pages'/(key+'.png');image_path.write_bytes(pix.tobytes('png'))
                pages.append({'id':key,'document_id':doc['id'],'page':str(n),'source_sha256':doc['version'],'object_key':doc['object_key'],'image':'pages/'+key+'.png','image_sha256':sha(image_path),'native_characters':len(text),'previous_ocr':old_ocr,'old_chunk_ids':[c['id'] for c in old]})
    if lib.current()!=name:raise ValueError('Library changed during OCR planning')
    save_json(out/'plan.json',{'generation_before':name,'recipe':RECIPE,'extraction_revision':REVISION,'pdf_documents':pdfs,'pdf_pages':total,'pages':pages})
    return {'pdf_documents':pdfs,'pdf_pages':total,'candidate_pages':len(pages),'candidate_documents':len({p['document_id'] for p in pages})}

def review(out,plan,records,data):
    out=Path(out);parts=['<!doctype html><html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\' data:; style-src \'unsafe-inline\'"><title>Private GLM OCR review</title><style>body{max-width:1100px;margin:35px auto;font:18px/1.5 system-ui}img{width:100%;max-width:900px}pre{white-space:pre-wrap}details{margin:22px 0}.note{background:#fff3bd;padding:12px}</style><h1>Private GLM-OCR review</h1><p class="note">These are model transcriptions, not verified facts. Compare the rendered source with the old and new text, especially amounts, dates, identifiers and status.</p>']
    docs={d['id']:d for d in data['documents']}
    for page,record in zip(plan['pages'],records):
        old='\n'.join(c['text'] for c in data['chunks'] if c['id'] in page['old_chunk_ids'])
        changed=set(re.findall(r'-?\d[\d,.%-]*',old))!=set(re.findall(r'-?\d[\d,.%-]*',record['text']))
        parts.append('<details'+(' open' if changed else '')+'><summary>'+('NUMERIC DIFFERENCE â€” ' if changed else '')+html.escape(docs[page['document_id']]['title']+' Â· page '+page['page'])+'</summary>'+('<p class="note">Numeric text differs from the previous extraction. Check both against the rendered source; neither model output is ground truth.</p>' if changed else '')+'<p>'+html.escape(record['outcome'])+'</p><img src="'+page['image']+'" alt="Local source page for OCR review"><h2>Previous indexed text</h2><pre>'+html.escape(old or '(none)')+'</pre><h2>GLM-OCR transcription</h2><pre>'+html.escape(record['text'])+'</pre></details>')
    parts.append('</html>');(out/'review.html').write_text('\n'.join(parts),encoding='utf-8')

def apply(home,out):
    lib=Library(home);out=Path(out);plan=read(out/'plan.json')
    if (out/'adoption-results.json').exists():raise ValueError('OCR adoption is already recorded; refusing to overwrite')
    if plan['recipe']!=RECIPE or plan['extraction_revision']!=REVISION:raise ValueError('OCR recipe changed; prepare a new plan')
    model=LocalModel(home)
    if model.config.get('ocr_model')!='glm-ocr' or model.config.get('ocr_quantization')!='Q8_0':raise ValueError('Configure the verified original GLM-OCR checkpoint first')
    with writer(lib.home):
        if lib.current()!=plan['generation_before']:raise ValueError('Library changed; prepare a new OCR plan')
        data=lib.prepared();records=[];updates=[];reused=0
        for page in plan['pages']:
            source=lib.home/page['object_key'];image=out/page['image']
            if sha(source)!=page['source_sha256'] or sha(image)!=page['image_sha256']:raise ValueError('OCR input checksum mismatch')
            result_path=out/'pages'/(page['id']+'-result.json')
            if result_path.exists():
                record=read(result_path)
                if record.get('image_sha256')!=page['image_sha256'] or record.get('extraction_revision')!=REVISION:raise ValueError('Saved OCR result identity mismatch')
                reused+=1
            else:
                start=time.perf_counter()
                text,response=transcribe(lib.home,base64.b64encode(image.read_bytes()).decode())
                save_json(out/'pages'/(page['id']+'-response.json'),response)
                save_json(out/'pages'/(page['id']+'-request-provenance.json'),{'recipe':RECIPE,'source_sha256':page['source_sha256'],'image_sha256':page['image_sha256'],'page':page['page']})
                # Empty output is a review item, not authority to erase existing evidence.
                meaningful=any(c.isalnum() for c in text)
                record={'page_id':page['id'],'document_id':page['document_id'],'page':page['page'],'text':text,'seconds':time.perf_counter()-start,'outcome':'text-unreviewed' if meaningful else 'empty-needs-review','image_sha256':page['image_sha256'],'extraction_revision':REVISION,'usage':response.get('usage',{}),'model':response['model']}
                save_json(result_path,record)
            records.append(record)
            if record['outcome']=='text-unreviewed':updates.append((page,record))
            print(json.dumps({'ocr_pages_completed':len(records),'total':len(plan['pages']),'last_outcome':record['outcome']}),flush=True)
        review(out,plan,records,data)
        dropped={cid for page,_ in updates for cid in page['old_chunk_ids']};keep=[i for i,c in enumerate(data['chunks']) if c['id'] not in dropped]
        preserved_chunks=[data['chunks'][i] for i in keep];preserved_vectors=[data['vectors'][i] for i in keep]
        new_chunks=[];touched=set();numeric_differences=0
        for page,record in updates:
            doc=next(d for d in data['documents'] if d['id']==page['document_id']);touched.add(doc['id'])
            old='\n'.join(c['text'] for c in data['chunks'] if c['id'] in page['old_chunk_ids'])
            if set(re.findall(r'-?\d[\d,.%-]*',old))!=set(re.findall(r'-?\d[\d,.%-]*',record['text'])):numeric_differences+=1
            for offset in range(0,len(record['text']),1000):
                text=record['text'][offset:offset+1200].strip()
                if not text:continue
                cid='c'+hashlib.sha256((doc['id']+'|'+doc['version']+'|'+REVISION+'|'+page['page']+'|'+str(offset)).encode()).hexdigest()[:24]
                new_chunks.append({'id':cid,'doc_id':doc['id'],'path':doc['path'],'location':page['page'],'method':'local-glm-ocr-unreviewed','scope':doc['scope'],'text':text,'offset':offset,'ocr_model':'glm-ocr','ocr_quantization':'Q8_0','extraction_revision':REVISION,'source_image_sha256':page['image_sha256']})
        vectors=[]
        for i in range(0,len(new_chunks),12):vectors.extend(model.embed([c['text'] for c in new_chunks[i:i+12]]))
        for doc in data['documents']:
            if doc['id'] in touched:doc.update(review_state='ocr-unreviewed',extraction_revision=REVISION)
        for edge in data['edges']:
            if edge.get('evidence_chunk_id') in dropped:edge.update(evidence_chunk_id=None,review_state='source-extraction-changed-needs-review')
        data['chunks']=preserved_chunks+new_chunks;data['vectors']=preserved_vectors+vectors
        manifest=lib.publish(data,model.config['embedding_model'],'dedicated-glm-ocr-revision') if updates else None
        result={'generation_before':plan['generation_before'],'generation_after':lib.current(),'pdf_documents_audited':plan['pdf_documents'],'pdf_pages_audited':plan['pdf_pages'],'ocr_pages_processed':len(records),'pages_replaced':len(updates),'documents_updated':len(touched),'previous_chunks_replaced':len(dropped),'new_chunks':len(new_chunks),'unchanged_chunks_preserved':len(preserved_chunks),'empty_pages_retained_for_review':sum(r['outcome']!='text-unreviewed' for r in records),'pages_with_changed_numeric_tokens':numeric_differences,'cached_page_results_reused':reused,'human_accuracy_review':'pending','ocr_model':'glm-ocr','ocr_quantization':'Q8_0','total_documents':len(data['documents']),'total_chunks':len(data['chunks'])}
        save_json(out/'adoption-results.json',result);lib.journal('glm_ocr_adopted',**result)
        return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',default=str(runtime.default_home()));p.add_argument('--out',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    try:print(json.dumps(apply(a.home,a.out) if a.apply else prepare(a.home,a.out)))
    except Exception as e:
        import traceback
        out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
        with (out/'error.log').open('a',encoding='utf-8') as f:f.write(traceback.format_exc()+'\n')
        print(json.dumps({'ok':False,'error_class':type(e).__name__,'diagnostics':'private OCR run error.log'}));return 1
    return 0
if __name__=='__main__':sys.exit(main())
