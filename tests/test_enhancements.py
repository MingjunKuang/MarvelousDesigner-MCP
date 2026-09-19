import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, MagicMock
from marvelous_designer_mcp import bridge, runtime_ops
from marvelous_designer_mcp.docs import DocsIndex, build_index, parse_page
from marvelous_designer_mcp.safety import classify, preflight
from marvelous_designer_mcp.enhanced import execute_python


ROOT = Path(__file__).resolve().parents[1]

class DocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.path=Path(cls.tmp.name)/'docs.sqlite3'
        build_index(ROOT/'tests/fixtures/docs',cls.path)
        cls.docs=DocsIndex(cls.path)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_overloads_and_parameter_meaning(self):
        r=self.docs.get('pattern_api.AddSeamlinePairGroup')['result']
        self.assertEqual(len(r['overloads']),3)
        self.assertIn('true : forward',r['text'])
        self.assertTrue(r['source_url'].startswith('https://developer.marvelousdesigner.com/'))

    def test_name_resolution(self):
        self.assertTrue(self.docs.get('pattern_api::MovePatternPoint()')['ok'])
        self.assertFalse(self.docs.get('DefinitelyMissing')['ok'])
        self.assertTrue(self.docs.get('ImportExportOption')['ok'])

    def test_natural_language_search(self):
        hits=self.docs.search('create sewing between two pattern edges')
        self.assertEqual(hits[0]['id'],'pattern_api.AddSeamlinePairGroup')
        self.assertEqual(self.docs.search('" OR *'),[])
        with self.assertRaises(ValueError): self.docs.search('pattern',0)

    def test_scenarios(self):
        for name in ['Pattern','Simulation','Animation','Substance']:
            r=self.docs.get(name,'scenario')
            self.assertTrue(r['ok'])
            self.assertTrue(r['result']['examples'])

    def test_navigation_excluded(self):
        r=self.docs.get('CreatePatternWithPoints')['result']
        self.assertNotIn('Read the Docs',r['text'])
        self.assertIn('Straight Point',r['text'])

    def test_parser_entities(self):
        s='<section id="pattern-api"><pre>def Test(x : int) -&gt; bool\n"""\n@brief x &amp; y\n"""</pre></section>'
        r=parse_page(s,'list.html','now')
        self.assertEqual(r[0]['description'],'x & y')

    def test_rebuild_releases_windows_handles(self):
        self.docs.metadata()
        build_index(ROOT/'tests/fixtures/docs',self.path)
        self.assertGreater(self.docs.metadata()['entry_count'],8)


class SafetyTests(unittest.TestCase):
    def test_modal_classification(self):
        self.assertEqual(classify('import_api.ImportFile',1),'potentially_modal')
        self.assertEqual(classify('ExportOBJ',1),'potentially_modal')
        self.assertEqual(classify('ExportOBJ',2),'safe_with_explicit_options')
        self.assertEqual(classify('ShowMessageBox'),'unsafe')
        self.assertEqual(classify('UnknownAPI'),'unknown')
        self.assertTrue(preflight('import_api.ImportFile("x")')['blocked'])

    def test_guard_does_not_execute(self):
        with patch.object(bridge,'call') as call:
            r=execute_python('utility_api.NewProject()')
            self.assertEqual(r['error']['code'],'modal_risk')
            call.assert_not_called()


class BridgeTests(unittest.TestCase):
    def test_connection_refused(self):
        with patch('socket.create_connection',side_effect=ConnectionRefusedError('closed')):
            with self.assertRaises(bridge.BridgeError) as cm: bridge.call('ping')
        self.assertEqual(cm.exception.as_dict()['code'],'listener_unavailable')

    def test_timeout_is_not_cancellation(self):
        sock=MagicMock()
        sock.__enter__.return_value=sock
        sock.recv.side_effect=socket.timeout()
        with patch('socket.create_connection',return_value=sock):
            with self.assertRaises(bridge.BridgeError) as cm: bridge.call('execute_python',timeout=.01)
        d=cm.exception.as_dict()
        self.assertEqual(d['code'],'bridge_timeout')
        self.assertEqual(d['outcome'],'unknown')
        self.assertFalse(d['retry_safe'])

    def test_connection_lost(self):
        sock=MagicMock()
        sock.recv.return_value=b''
        with self.assertRaises(bridge.BridgeError) as cm: bridge._recv_line(sock)
        self.assertEqual(cm.exception.as_dict()['code'],'connection_lost')

    def test_bad_id(self):
        sock=MagicMock()
        sock.__enter__.return_value=sock
        sock.recv.return_value=b'{"id":"wrong","result":true}\n'
        with patch('socket.create_connection',return_value=sock):
            with self.assertRaises(bridge.BridgeError) as cm: bridge.call('ping')
        self.assertEqual(cm.exception.as_dict()['code'],'protocol_error')


class ValidationTests(unittest.TestCase):
    def test_indices(self):
        for val in [-1,True,3,1.2]:
            with self.assertRaises(ValueError): runtime_ops.index(val,3,'pattern')

    def test_invalid_vertices_never_mutate(self):
        module=types.SimpleNamespace(CreatePatternWithPoints=MagicMock())
        with patch.dict(sys.modules,{'pattern_api':module}):
            for points in [[],[[0,0,0]]*3,[[0,0,0],[1,0,0],[0,float('nan'),0]],[[0,0,0],[1,0,0],[0,1,9]]]:
                with self.assertRaises(ValueError): runtime_ops.create_pattern(points)
        module.CreatePatternWithPoints.assert_not_called()

    def test_false_simulation_is_failure(self):
        module=types.SimpleNamespace(Simulate=lambda steps:False)
        with patch.dict(sys.modules,{'utility_api':module,'pattern_api':types.SimpleNamespace()}):
            with self.assertRaises(RuntimeError): runtime_ops.simulate(1)
            with self.assertRaises(ValueError): runtime_ops.simulate(-1)

    def test_stale_listener_result_cleared(self):
        spec=importlib.util.spec_from_file_location('listener',ROOT/'md_addon'/'md_listener.py')
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod._handle_execute_python({'code':'result=42'})['result'],42)
        self.assertIsNone(mod._handle_execute_python({'code':'x=1'})['result'])

if __name__=='__main__': unittest.main()
