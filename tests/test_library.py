"""Synthetic-only lifecycle, scope, budget and transport validation."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from context_layer import runtime
from context_layer.library import Library,Retrieval,sha,read,writer
from context_layer.local_model import save_json,LocalModel
from context_layer.service import create_app,validate_chat
from context_layer.broker import validate
from starlette.testclient import TestClient

MODEL='google/gemma-4-12b-qat';EMBED='text-embedding-nomic-embed-text-v1.5'
def seed(lib):
    docs=[];chunks=[];vectors=[]
    for n,scope,text in [('a','synthetic','Orchid current balance is 127 dollars. Reference ORCHID-427.'),('b','synthetic','Orchid payment was received, not overdue.'),('c','other','Other house balance 999 dollars, private cross-scope fixture.')]:
        path=lib.home/'inbox'/f'{n}.txt';path.write_text(text);digest,key=lib.preserve(path)
        docs.append({'id':n,'title':n+'.txt','path':n+'.txt','scope':scope,'version':digest,'sha256':digest,'object_key':key,'format':'.txt','review_state':'text-extracted'})
        chunks.append({'id':'c'+n,'doc_id':n,'text':text,'scope':scope,'location':'line 1','method':'synthetic','offset':0})
        vectors.append([1.0]+[0.0]*767)
    return {'documents':docs,'chunks':chunks,'vectors':vectors,'edges':[{'source':'a','target':'b'},{'source':'b','target':'c'}]}

class Tests(unittest.TestCase):
    def setUp(self):
        root=runtime.ROOT/'private-runs/context-service-tests';root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(prefix='ladybug-fixture-',dir=root);self.lib=Library(self.tmp.name)
        self.settings={'chat_model':MODEL,'ocr_model':'glm-ocr','ocr_quantization':'Q8_0','embedding_model':EMBED,'model_origin':'http://127.0.0.1:1235','api_token':'fixture-token'}
        save_json(self.lib.home/'settings.json',self.settings);self.data=seed(self.lib)
        with writer(self.lib.home):self.lib.publish(self.data,EMBED,'synthetic-test')
    def tearDown(self):self.tmp.cleanup()
    def test_missing_or_stale_broker_fails_before_queueing(self):
        import os,time
        queue=self.lib.home/'queue';model=LocalModel(self.lib.home)
        for heartbeat in (None,{'time':time.time()-60,'pid':1}):
            if heartbeat is not None:save_json(queue/'broker.heartbeat.json',heartbeat)
            with patch.dict(os.environ,{'CONTEXT_FILE_BROKER':'1'}):
                with self.assertRaisesRegex(RuntimeError,'inference broker is not ready'):
                    model.embed(['fictional query'],query=True)
            self.assertEqual(list(queue.glob('*.request.json')),[])
    def test_scoped_search_budget_and_source(self):
        r=Retrieval(self.lib.home)
        try:
            x=r.search('balance',scope='synthetic',token_budget=350,vector=[1.0]+[0.0]*767)
            self.assertTrue(x['evidence']);self.assertLessEqual(x['tokens_approx'],350)
            self.assertTrue(all(v['scope']=='synthetic' for v in x['evidence']))
            self.assertNotIn('c',[v['document_id'] for v in r.related('a','synthetic',2)['documents']])
            with self.assertRaises(ValueError):r.evidence('../settings.json','synthetic')
            with self.assertRaises(ValueError):r.evidence('cc','synthetic')
            self.assertTrue(all(v['scope']!='synthetic' for v in r.search('balance',mode='keyword')['evidence']))
        finally:r.close()
    def test_atomic_failure_and_hash_validation(self):
        before=self.lib.current()
        with patch('context_layer.runtime.connect',side_effect=RuntimeError('fixture failure')):
            with self.assertRaises(RuntimeError):self.lib.publish(self.data,EMBED,'injected-failure')
        self.assertEqual(before,self.lib.current())
        p=self.lib.generation_path(before)/'prepared.json';p.write_text(p.read_text()+' ')
        with self.assertRaises(ValueError):Retrieval(self.lib.home)
    def test_snapshot_restore_withdraw_and_originals(self):
        original=[(self.lib.home/d['object_key'],d['version']) for d in self.data['documents']]
        snap=self.lib.snapshot();self.lib.withdraw('a')
        self.assertEqual(len(self.lib.prepared()['documents']),2)
        self.lib.restore(snap);self.assertEqual(len(self.lib.prepared()['documents']),3)
        self.assertTrue(all(sha(p)==digest for p,digest in original))
        manifest=read(snap/'generation/manifest.json');manifest['files']['../../settings.json']='x'
        save_json(snap/'generation/manifest.json',manifest);meta=read(snap/'snapshot.json');meta['manifest_sha256']=sha(snap/'generation/manifest.json');save_json(snap/'snapshot.json',meta)
        with self.assertRaises(ValueError):self.lib.restore(snap)
    def test_duplicate_ingest_and_replacement(self):
        with patch.object(LocalModel,'embed',return_value=[[1.0]+[0.0]*767]):
            x=self.lib.ingest('synthetic');self.assertEqual(x['duplicates'],3);self.assertEqual(x['added'],0)
            # Clear only synthetic inbox inputs, never originals.
            for p in (self.lib.home/'inbox').iterdir():p.unlink()
            (self.lib.home/'inbox/a.txt').write_text('Orchid revised balance 128 dollars.')
            x=self.lib.ingest('synthetic',replace_document='a');self.assertEqual(x['added'],1)
            self.assertEqual(len(self.lib.prepared()['documents']),3)
            self.assertIn('128',next(c['text'] for c in self.lib.prepared()['chunks'] if c['doc_id']=='a'))
    def test_auth_host_origin_and_mcp_listing(self):
        with TestClient(create_app(self.lib.home),base_url='http://127.0.0.1:8765') as client:
            self.assertEqual(client.get('/health').status_code,200)
            self.assertEqual(client.get('/api/status').status_code,401)
            headers={'Authorization':'Bearer fixture-token'}
            self.assertEqual(client.get('/api/status',headers=headers).status_code,200)
            self.assertEqual(client.get('/api/status',headers={**headers,'Host':'evil.example'}).status_code,421)
            self.assertEqual(client.get('/api/status',headers={**headers,'Origin':'https://evil.example'}).status_code,403)
            reply=client.post('/mcp',headers={**headers,'Accept':'application/json, text/event-stream'},json={'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}})
            self.assertEqual(reply.status_code,200);self.assertEqual(len(reply.json()['result']['tools']),5)
    def test_inference_boundary(self):
        body={'model':MODEL,'messages':[{'role':'user','content':'Synthetic question'}],'reasoning_effort':'none'}
        self.assertEqual(validate_chat(body,self.settings)['reasoning_effort'],'none')
        for change in ({'model':'research/alias'},{'reasoning_effort':'high'},{'tools':[{'type':'function','function':{'name':'web_search'}}]},{'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'https://example.com/private'}}]}]}):
            with self.assertRaises(ValueError):validate_chat({**body,**change},self.settings)
        with self.assertRaises(ValueError):validate('/v1/embeddings',{'model':MODEL,'input':['test']},self.settings)
        for origin in ('http://example.com','http://127.0.0.1:1235@evil.example'):
            save_json(self.lib.home/'settings.json',{**self.settings,'model_origin':origin})
            with self.assertRaises(ValueError):LocalModel(self.lib.home).request('/v1/models')
        # Explicitly assert model endpoint rejection before any socket is opened.
        save_json(self.lib.home/'settings.json',{**self.settings,'model_origin':'https://example.com'})
        with self.assertRaises(ValueError):LocalModel(self.lib.home).request('/v1/models')
    def test_native_pdf_word_csv_and_text_extraction(self):
        import pymupdf
        from docx import Document
        root=self.lib.home/'review'
        p=root/'synthetic.pdf';pdf=pymupdf.open();page=pdf.new_page();page.insert_text((50,50),'Fictional Orchid balance 127 dollars. This synthetic PDF has native selectable text.');pdf.save(p);pdf.close()
        self.assertIn('127',self.lib.extract(p)[0][1])
        p=root/'synthetic.docx';doc=Document();doc.add_paragraph('Fictional Orchid balance 127 dollars.');table=doc.add_table(rows=1,cols=2);table.cell(0,0).text='status';table.cell(0,1).text='received';doc.save(p)
        units=self.lib.extract(p);self.assertTrue(any('127' in t for _,t,_ in units));self.assertTrue(any('received' in t for _,t,_ in units))
        p=root/'synthetic.csv';p.write_text('account,balance\nOrchid,127\n');self.assertIn('127',self.lib.extract(p)[0][1])
        p=root/'synthetic.md';p.write_text('# Orchid\nBalance 127.');self.assertIn('127',self.lib.extract(p)[0][1])
    def test_owner_link_requires_source_evidence(self):
        with self.assertRaises(ValueError):self.lib.link('a','c','cb')
        self.lib.link('a','c','ca');r=Retrieval(self.lib.home)
        try:
            # Cross-scope links may exist, but retrieval must respect its scope.
            self.assertNotIn('c',[x['document_id'] for x in r.related('a','synthetic',2)['documents']])
        finally:r.close()
    def test_ocr_role_is_separate_and_strict(self):
        import base64
        from context_layer.ocr import make_request,validate_request
        image=base64.b64encode(b'\x89PNG\r\n\x1a\nsynthetic-header-only-validator-fixture').decode()
        body=make_request(self.settings,image)
        self.assertEqual(validate('/v1/chat/completions',body,self.settings)['model'],'glm-ocr')
        with self.assertRaises(ValueError):validate_chat(body,self.settings)
        self.assertNotIn('reasoning_effort',body)
        for changed in ({**body,'tools':[]},{**body,'reasoning_effort':'none'},{**body,'model':'research/ocr-alias'},{**body,'max_tokens':9000}):
            with self.assertRaises(ValueError):validate_request(changed,self.settings)
        body['messages'][0]['content'][0]['image_url']['url']='https://example.com/image.png'
        with self.assertRaises(ValueError):validate_request(body,self.settings)
    def test_selective_pdf_ocr_replaces_only_selected_pages(self):
        import pymupdf,base64
        from context_layer import reocr
        p=self.lib.home/'review/fixture.pdf';pdf=pymupdf.open();page=pdf.new_page();page.insert_text((40,60),'Native selectable page text is long enough to preserve unchanged in this synthetic test.');page=pdf.new_page();page.draw_rect(pymupdf.Rect(50,50,200,100),color=(0,0,0),fill=(0.8,0.8,0.8));pdf.save(p);pdf.close();digest,key=self.lib.preserve(p)
        data=self.lib.prepared();data['documents'].append({'id':'pdf','title':'fixture.pdf','path':'fixture.pdf','scope':'synthetic','version':digest,'sha256':digest,'object_key':key,'format':'.pdf','review_state':'ocr-unreviewed'})
        data['chunks'].extend([{'id':'pdf-native','doc_id':'pdf','text':'Native text stays unchanged.','scope':'synthetic','location':'1','method':'pdf-text','offset':0},{'id':'pdf-old','doc_id':'pdf','text':'Old balance 126.','scope':'synthetic','location':'2','method':'old-gemma-ocr-unreviewed','offset':0}]);data['vectors'].extend([[1.0]+[0.0]*767]*2);self.lib.publish(data,EMBED,'synthetic-pdf')
        before=self.lib.current();out=self.lib.home/'review/ocr-test';prepared=reocr.prepare(self.lib.home,out);self.assertEqual(prepared['candidate_pages'],1)
        response={'model':'glm-ocr','choices':[{'message':{'content':'Balance: 127.'},'finish_reason':'stop'}]}
        with patch('context_layer.reocr.transcribe',return_value=('Balance: 127.',response)),patch.object(LocalModel,'embed',side_effect=lambda texts,query=False:[[1.0]+[0.0]*767 for _ in texts]):
            result=reocr.apply(self.lib.home,out)
        self.assertEqual(result['pages_replaced'],1);self.assertEqual(result['previous_chunks_replaced'],1)
        current=self.lib.prepared();self.assertTrue(any(c['id']=='pdf-native' for c in current['chunks']));self.assertFalse(any(c['id']=='pdf-old' for c in current['chunks']))
        self.assertEqual(sha(self.lib.home/key),digest);self.assertTrue(self.lib.generation_path(before).exists())
        r=Retrieval(self.lib.home)
        try:
            c=next(c for c in current['chunks'] if c.get('ocr_model')=='glm-ocr');self.assertEqual(r.evidence(c['id'],'synthetic')['ocr_model'],'glm-ocr')
        finally:r.close()
    def test_truncated_ocr_is_not_accepted(self):
        import base64
        from context_layer.ocr import transcribe
        response={'model':'glm-ocr','choices':[{'message':{'content':'Incomplete'},'finish_reason':'length'}]}
        with patch.object(LocalModel,'request',return_value=response):
            with self.assertRaises(ValueError):transcribe(self.lib.home,base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode())

if __name__=='__main__':unittest.main()
