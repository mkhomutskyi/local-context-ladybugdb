import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from context_layer import runtime
from context_layer.local_model import LocalModel
from context_manager.launcher import configure

class ManagerLauncherTests(unittest.TestCase):
    def test_source_cannot_be_state(self):
        with self.assertRaises(ValueError):configure(runtime.ROOT,{})
    def test_missing_ids_does_not_create_state(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'private'
            with self.assertRaises(ValueError):configure(p,{})
            self.assertFalse(p.exists())
    def test_unavailable_model_does_not_create_state(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'private'
            with patch.object(LocalModel,'direct',return_value={'data':[]}):
                with self.assertRaises(ValueError):configure(p,{'chat_model':'installed/chat','embedding_model':'installed/embed'})
            self.assertFalse(p.exists())
    def test_cloud_origin_never_requested(self):
        with tempfile.TemporaryDirectory() as t,patch('urllib.request.build_opener') as opener:
            with self.assertRaises(ValueError):configure(Path(t)/'private',{'chat_model':'installed/chat','embedding_model':'installed/embed','model_origin':'https://remote.example'})
            opener.assert_not_called()
    def test_restart_preserves_profile_and_token(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'private';inventory={'data':[{'id':'installed/chat'},{'id':'installed/embed'}]}
            with patch.object(LocalModel,'direct',return_value=inventory):
                a=configure(p,{'chat_model':'installed/chat','embedding_model':'installed/embed'});before=(p/'control/profile.json').read_bytes();token=(p/'control/owner-code.txt').read_bytes();b=configure(p,{})
            self.assertEqual(before,(p/'control/profile.json').read_bytes());self.assertEqual(token,(p/'control/owner-code.txt').read_bytes())
            self.assertEqual(a.profile,b.profile)
    def test_existing_identity_cannot_be_rewritten_by_restart(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'private';inventory={'data':[{'id':'installed/chat'},{'id':'installed/embed'}]}
            with patch.object(LocalModel,'direct',return_value=inventory):configure(p,{'chat_model':'installed/chat','embedding_model':'installed/embed'})
            before=(p/'control/profile.json').read_bytes()
            with self.assertRaises(ValueError):configure(p,{'chat_model':'new/model'})
            self.assertEqual(before,(p/'control/profile.json').read_bytes())

if __name__=='__main__':unittest.main()
