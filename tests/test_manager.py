"""Fictional integration cases. No personal library is opened."""
import io,json,os,sys,tempfile,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from context_manager.catalog import Catalog,now
from context_manager.engine import Processor,Inference,ManagedLibrary,Readers,Library,read
from context_manager.web import create_app
from context_manager.reader import create_reader
from starlette.testclient import TestClient

def vectors(self,texts,query=False):return [[1.0]+[0.0]*767 for _ in texts]
STATEMENT=b'Fictional House Orchid account statement. Balance 127 dollars as of 6 November 2026. Reference: ORCHID-427. No bank account number is provided.'
RECEIPT=b'Fictional House Orchid payment received 5 November 2026. Not overdue. Reference: ORCHID-427.'

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name);self.app=create_app(self.home);self.c=self.app.state.catalog
        self.client=TestClient(self.app,base_url='http://127.0.0.1:8791',raise_server_exceptions=False);self.client.__enter__()
        self.client.headers['origin']='http://127.0.0.1:8791';code=(self.home/'control/owner-code.txt').read_text()
        r=self.client.post('/api/login',json={'code':code});self.assertEqual(r.status_code,200);self.client.headers['x-csrf-token']=r.json()['csrf']
        self.p=self.c.create_project('Fictional House Orchid');self.pid=self.p['id'];self.prefix='/api/projects/'+self.pid
        self.mock=patch.object(Inference,'embed',vectors);self.mock.start();self.processor=Processor(self.c)
    def tearDown(self):
        self.mock.stop();self.client.__exit__(None,None,None);self.temp.cleanup()
    def drain(self):
        while (job:=self.c.claim('test-worker')):self.processor.process(job)
    def upload(self,body=STATEMENT,name='statement.txt',replace=None):
        r=self.client.post(self.prefix+'/uploads',params={'name':name,**({'replace_document':replace} if replace else {})},content=body)
        self.assertEqual(r.status_code,202,r.text);self.drain();return self.c.receipt(r.json()['receipt_id'])
    def indexed(self):return Library(self.c.project_home(self.pid)).prepared()
    def test_auth_origin_csrf_and_host(self):
        with TestClient(self.app,base_url='http://127.0.0.1:8791',raise_server_exceptions=False) as anonymous:self.assertEqual(anonymous.get('/api/projects').status_code,401)
        self.assertEqual(self.client.post('/api/projects',json={'name':'bad'},headers={'origin':'http://evil.test'}).status_code,403)
        self.assertEqual(self.client.post('/api/projects',json={'name':'bad'},headers={'x-csrf-token':'wrong'}).status_code,401)
        self.assertEqual(self.client.get('/api/projects',headers={'host':'evil.test'}).status_code,421)
    def test_upload_preserve_dedup_and_locations(self):
        r=self.upload();self.assertEqual(r['status'],'ready');self.assertEqual((self.c.project_home(self.pid)/r['object_key']).read_bytes(),STATEMENT)
        d=self.indexed();self.assertEqual(len(d['chunks']),1);self.assertTrue(d['chunks'][0]['location']);self.assertEqual(self.upload()['status'],'duplicate');self.assertEqual(len(self.indexed()['documents']),1)
    def test_path_rejected_and_partial_preserved(self):
        self.assertEqual(self.client.post(self.prefix+'/uploads?name=../bad.txt',content=b'text').status_code,400)
        self.assertEqual(self.client.post(self.prefix+'/uploads?name=empty.txt',content=b'').status_code,400)
        self.assertEqual(self.c.one('SELECT status FROM receipts')['status'],'failed')
    def test_ocr_review_is_required_and_editable(self):
        with patch.object(ManagedLibrary,'extract',return_value=[('page 1','Balance 12 dollars.','glm-ocr')]):r=self.upload(b'fake-png','scan.png')
        self.assertEqual(r['status'],'review');self.assertEqual(len(self.indexed()['documents']),0)
        result=self.client.post(self.prefix+'/receipts/'+r['id']+'/approve',json={'category':'Statements','units':[{'location':'page 1','method':'glm-ocr','text':'Balance 127 dollars.'}]})
        self.assertEqual(result.status_code,202);self.drain();self.assertIn('127',self.indexed()['chunks'][0]['text']);self.assertEqual(self.indexed()['documents'][0]['review_state'],'owner-reviewed')
    def test_uncertain_classification_not_live(self):
        with patch.object(Inference,'request',side_effect=RuntimeError('Unavailable')):r=self.upload(b'Uncertain miscellaneous details.','unknown.txt')
        self.assertEqual(r['status'],'review');self.assertFalse(self.indexed()['documents'])
    def test_lease_recovery_cancel_retry(self):
        jid=self.c.enqueue(self.pid,'folders');job=self.c.claim('interrupted');self.assertEqual(job['id'],jid);self.assertIsNone(self.c.claim('other'))
        self.c.write('UPDATE jobs SET lease_until=0 WHERE id=?',(jid,));self.assertEqual(self.c.claim('replacement')['attempts'],2)
        self.c.cancel(jid);self.processor.process(self.c.one('SELECT * FROM jobs WHERE id=?',(jid,)));self.assertEqual(self.c.one('SELECT status FROM jobs WHERE id=?',(jid,))['status'],'cancelled');self.c.retry(jid);self.assertEqual(self.c.one('SELECT status FROM jobs WHERE id=?',(jid,))['status'],'queued')
    def test_lost_lease_cannot_publish(self):
        jid=self.c.enqueue(self.pid,'folders');old=self.c.claim('old');self.c.write('UPDATE jobs SET lease_until=0 WHERE id=?',(jid,));new=self.c.claim('new');self.processor.process(old)
        self.assertEqual(self.c.one('SELECT worker,status FROM jobs WHERE id=?',(jid,)),{'worker':'new','status':'running'})
    def test_folder_change_keeps_original_and_vectors(self):
        r=self.upload();before=self.indexed();self.c.enqueue(self.pid,'categorize',payload={'document_id':r['document_id'],'category':'Agreements'});self.drain();after=self.indexed()
        self.assertEqual(after['documents'][0]['category'],'Agreements');self.assertEqual(before['chunks'],after['chunks']);self.assertEqual(before['vectors'],after['vectors']);self.assertEqual(before['documents'][0]['object_key'],after['documents'][0]['object_key'])
    def test_failed_model_leaves_active_generation(self):
        self.upload();before=Library(self.c.project_home(self.pid)).current()
        with patch.object(Inference,'embed',side_effect=RuntimeError('Test failure')):r=self.upload(b'Another account statement. Balance 2 dollars.','second.txt')
        self.assertEqual(r['status'],'failed');self.assertEqual(Library(self.c.project_home(self.pid)).current(),before);self.assertTrue((self.c.project_home(self.pid)/r['object_key']).exists())
    def test_replacement_and_generation_pinning(self):
        r=self.upload();old=Library(self.c.project_home(self.pid)).current();cid=self.indexed()['chunks'][0]['id'];self.app.state.readers.evidence(self.pid,cid,old)
        self.upload(STATEMENT.replace(b'127',b'250'),'statement-v2.txt',r['document_id']);new=Library(self.c.project_home(self.pid)).current();self.assertNotEqual(old,new)
        self.assertIn('127',self.app.state.readers.evidence(self.pid,cid,old)['text'])
        with self.assertRaises(ValueError):self.app.state.readers.evidence(self.pid,cid,new)
    def test_project_boundaries(self):
        self.upload();other=self.c.create_project('Another fictional project');cid=self.indexed()['chunks'][0]['id']
        with self.assertRaises(ValueError):self.app.state.readers.evidence(other['id'],cid)
        token=(self.c.project_home(self.pid)/'mcp-token.txt').read_text();self.assertFalse(self.c.verify_project_token(other['id'],token))
    def test_approved_graph_link(self):
        self.upload();self.upload(RECEIPT,'receipt.txt');p=self.c.one('SELECT * FROM proposals');self.assertIsNotNone(p);self.assertFalse(self.indexed()['edges'])
        self.c.enqueue(self.pid,'link',payload={'proposal':p['id']});self.drain();self.assertEqual(len(self.indexed()['edges']),1)
        r=self.app.state.readers.related(self.pid,p['source']);self.assertEqual(r['documents'][0]['document_id'],p['target'])
    def test_snapshot_restore_and_no_credentials(self):
        self.upload();jid=self.c.enqueue(self.pid,'snapshot');self.drain();j=self.c.one('SELECT * FROM jobs WHERE id=?',(jid,));self.assertEqual(j['status'],'complete')
        archive=self.home/'exports'/j['artifact']
        with zipfile.ZipFile(archive) as z:
            self.assertFalse(any('token' in n or 'settings' in n or 'catalog' in n for n in z.namelist()))
            self.assertEqual(json.loads(z.read('project.json'))['format'],'local-context-project/v1')
        dest=self.c.create_project('Travel copy');upload='r'+'a'*32;(self.home/'uploads'/(upload+'.zip')).write_bytes(archive.read_bytes());jid=self.c.enqueue(dest['id'],'restore',payload={'upload':upload});self.drain()
        self.assertEqual(self.c.one('SELECT status FROM jobs WHERE id=?',(jid,))['status'],'complete');self.assertEqual(len(Library(self.c.project_home(dest['id'])).prepared()['documents']),1)
    def test_organized_export_and_withdraw(self):
        r=self.upload();jid=self.c.enqueue(self.pid,'folders');self.drain();j=self.c.one('SELECT * FROM jobs WHERE id=?',(jid,))
        with zipfile.ZipFile(self.home/'exports'/j['artifact']) as z:self.assertTrue(any(n.startswith('Documents/Statements/') for n in z.namelist()))
        self.c.enqueue(self.pid,'withdraw',payload={'document_id':r['document_id']});self.drain();self.assertFalse(self.indexed()['documents']);self.assertTrue((self.c.project_home(self.pid)/r['object_key']).exists())
    def test_zip_traversal_rejected(self):
        upload='r'+'b'*32
        with zipfile.ZipFile(self.home/'uploads'/(upload+'.zip'),'w') as z:z.writestr('../escaped.txt','x')
        jid=self.c.enqueue(self.pid,'restore',payload={'upload':upload});self.drain();self.assertEqual(self.c.one('SELECT status FROM jobs WHERE id=?',(jid,))['status'],'failed');self.assertFalse((self.home/'escaped.txt').exists())
    def test_mcp_real_protocol_project_auth(self):
        self.upload();mcp=create_reader(self.home);token=(self.c.project_home(self.pid)/'mcp-token.txt').read_text();url='/projects/'+self.pid+'/mcp'
        with TestClient(mcp,base_url='http://127.0.0.1:8792',raise_server_exceptions=False) as client:
            headers={'Authorization':'Bearer '+token,'Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-03-26'}
            self.assertEqual(client.post(url,json={'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code,401)
            result=client.post(url,headers=headers,json={'jsonrpc':'2.0','id':2,'method':'tools/list'})
            self.assertEqual(result.status_code,200,result.text);self.assertEqual(len(result.json()['result']['tools']),5)
            result=client.post(url,headers=headers,json={'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'search_context','arguments':{'query':'balance','mode':'keyword'}}})
            self.assertEqual(result.status_code,200,result.text);result=result.json()['result'];self.assertFalse(result.get('isError'),result);self.assertIn('127',json.dumps(result))
            other=self.c.create_project('Other');self.assertEqual(client.post('/projects/'+other['id']+'/mcp',headers=headers,json={'jsonrpc':'2.0','id':4,'method':'tools/list'}).status_code,401)

if __name__=='__main__':unittest.main(verbosity=2)
