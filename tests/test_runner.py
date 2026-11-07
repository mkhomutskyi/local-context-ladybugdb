import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from context_layer.local_model import LocalModel
from context_layer import runtime
spec=importlib.util.spec_from_file_location('local_runner',runtime.ROOT/'run.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class RunnerTests(unittest.TestCase):
    def test_source_checkout_cannot_be_state_home(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            runner.configure(runtime.ROOT,None,'installed/chat','installed/embedding')
    def test_missing_models_create_no_private_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)/'state'
            with patch.object(LocalModel,'direct',return_value={'data':[]}):
                with self.assertRaisesRegex(ValueError,'unavailable'):
                    runner.configure(home,None,'installed/chat','installed/embedding')
            self.assertFalse(home.exists())
    def test_existing_identity_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);path=home/'settings.json'
            text=json.dumps({'chat_model':'original/model','embedding_model':'original/embedding','model_origin':'http://127.0.0.1:1235'})
            path.write_text(text)
            with self.assertRaisesRegex(ValueError,'will not rewrite'):
                runner.configure(home,None,'replacement/model',None)
            self.assertEqual(path.read_text(),text)
    def test_cloud_model_origin_rejected_before_request(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('urllib.request.build_opener') as opener:
                with self.assertRaisesRegex(ValueError,'Remote model'):
                    runner.configure(Path(folder)/'state','http://example.com','installed/chat','installed/embedding')
                opener.assert_not_called()
    def test_demo_refuses_existing_records(self):
        from unittest.mock import Mock
        lib=Mock();lib.prepared.return_value={'documents':[{'id':'existing'}]}
        with self.assertRaisesRegex(ValueError,'existing data is preserved'):runner.seed_demo(lib)
    def test_first_run_demo_and_second_run_preserve_settings(self):
        from context_layer.library import read
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)/'state'
            inventory={'data':[{'id':'installed/chat'},{'id':'installed/embedding'}]}
            with patch.object(LocalModel,'direct',return_value=inventory),patch.object(LocalModel,'embed',side_effect=lambda texts,query=False:[[1.0]+[0.0]*767 for _ in texts]):
                lib=runner.configure(home,None,'installed/chat','installed/embedding')
                runner.seed_demo(lib)
                before=(home/'settings.json').read_bytes();generation=lib.current()
                again=runner.configure(home,None,None,None)
            self.assertEqual((home/'settings.json').read_bytes(),before)
            self.assertEqual(again.current(),generation)
            data=again.prepared();self.assertEqual(len(data['documents']),2);self.assertEqual(len(data['edges']),1)
            self.assertTrue(all(d['scope']=='synthetic' for d in data['documents']))

if __name__=='__main__':unittest.main()
