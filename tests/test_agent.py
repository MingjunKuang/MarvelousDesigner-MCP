import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid
import zipfile
from marvelous_designer_mcp import topology as t, operations as op, recovery as r, enhanced as e
from marvelous_designer_mcp.agent_runtime import MaterialFace


class TopologyTests(unittest.TestCase):
    def setUp(self):
        data=json.loads((Path(__file__).parent/'fixtures/topology.json').read_text())
        self.raw=data['raw']; self.native=data['native']
        self.session=dict(epoch='test',refs={})
    def build(self): return t.build_topology(self.raw,self.native,0,self.session)
    def test_straight_and_curved_edges(self):
        out=self.build()
        self.assertFalse(out['ambiguous'])
        self.assertEqual([v['type'] for v in out['outer_boundary']],['straight','curve','straight','straight'])
    def test_internal_line_curve_and_shape(self):
        out=self.build()
        self.assertEqual([v['type'] for v in out['internal_lines']],['internal_line','internal_curve'])
        self.assertEqual(out['internal_shapes'][0]['child_index'],2)
    def test_curve_control_is_not_runtime_endpoint(self):
        controls=[p for p in self.build()['points'] if p['is_control_point']]
        self.assertTrue(controls)
        self.assertTrue(all(p['stable_ref'] is None and not p['mutable'] for p in controls))
    def test_refresh_preserves_refs_when_geometry_unchanged(self):
        self.assertEqual(self.build()['outer_boundary'],self.build()['outer_boundary'])
    def test_runtime_index_change_does_not_change_reference(self):
        first=self.build()
        second=t.build_topology(self.raw,self.native,5,self.session)
        self.assertEqual(first['outer_boundary'][0]['stable_ref'],second['outer_boundary'][0]['stable_ref'])
    def test_geometry_change_invalidates(self):
        before=self.build()
        self.raw['ShapeInfo']['LineList'][0]['PointList'][0]['Position']['x']=-5
        after=self.build()
        with patch.object(t,'state',return_value=self.session),patch.object(t,'read_topology',return_value=after):
            with self.assertRaisesRegex(t.ReferenceError,'STALE_REFERENCE'):t.resolve(before['outer_boundary'][0]['stable_ref'],'edge')
    def test_foreign_session_reference_rejected(self):
        before=self.build()
        with patch.object(t,'state',return_value={'refs':{}}):
            with self.assertRaises(t.ReferenceError):t.resolve(before['outer_boundary'][0]['stable_ref'],'edge')
    def test_duplicate_internal_geometry_is_ambiguous(self):
        self.raw['InternalLineList'].append(copy.deepcopy(self.raw['InternalLineList'][0]))
        out=self.build()
        self.assertTrue(out['ambiguous'])
        self.assertTrue(out['internal_lines'][0]['ambiguous'])
    def test_duplicate_endpoint_is_ambiguous(self):
        self.native['PointList'][2]['Point positionX']=0
        self.native['PointList'][2]['Point positionY']=0
        self.assertTrue(self.build()['ambiguous'])
    def test_unknown_native_line_order_rejected(self):
        self.native['LineList'][1]['Line index']='3'
        self.assertTrue(self.build()['ambiguous'])
    def test_sewing_stale_rejected_before_api(self):
        import types,sys
        native=types.SimpleNamespace()
        with patch.dict(sys.modules,{'pattern_api':native}):
            with self.assertRaises(t.ReferenceError):t.sew_references('missing','missing',True,False)
    def test_partial_range_rejected(self):
        import types,sys
        with patch.dict(sys.modules,{'pattern_api':types.SimpleNamespace()}):
            with self.assertRaises(NotImplementedError):t.sew_references({'edge_ref':'x','range_start':.2},'y',True,False)


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Path(self.tmp.name)
        self.patcher=patch.object(op,'STORE',self.store);self.patcher.start();self.addCleanup(self.patcher.stop)
    def record(self,receipt=None,target=None,existing=False):
        ident=uuid.uuid4().hex
        op.write_json(self.store/(ident+'.json'),dict(operation_id=ident,target_path=str(target) if target else None,target_before={'exists':existing}))
        if receipt:op.write_json(self.store/(ident+'.receipt.json'),dict(operation_id=ident,**receipt))
        return ident
    def test_no_receipt_unknown(self):
        out=op.reconcile(self.record())
        self.assertEqual(out['status'],'UNKNOWN');self.assertFalse(out['retry_safe'])
    def test_running_simulation_unknown(self):
        self.assertEqual(op.reconcile(self.record(dict(status='RUNNING')))['status'],'UNKNOWN')
    def test_success_receipt(self):
        out=op.reconcile(self.record(dict(status='SUCCEEDED',result=42)))
        self.assertEqual(out['status'],'SUCCEEDED');self.assertEqual(out['result'],42)
    def test_exception_not_automatically_retried(self):
        out=op.reconcile(self.record(dict(status='FAILED',error='error')))
        self.assertEqual(out['status'],'FAILED');self.assertFalse(out['retry_safe'])
    def test_unverified_effect_remains_unknown(self):
        out=op.reconcile(self.record(dict(status='SUCCEEDED',result={'verified':False})))
        self.assertEqual(out['status'],'UNKNOWN');self.assertEqual(out['metadata']['status'],'UNKNOWN')
    def test_existing_output_does_not_prove_success(self):
        target=self.store/'existing.obj';target.write_text('v 0 0 0\nf 1 1 1\n')
        self.assertEqual(op.reconcile(self.record(dict(status='SUCCEEDED'),target,True))['status'],'UNKNOWN')
    def test_new_valid_output_and_receipt_reconcile(self):
        target=self.store/'new.zprj'
        with zipfile.ZipFile(target,'w') as z:z.writestr('project.xml','test')
        self.assertEqual(op.reconcile(self.record(dict(status='SUCCEEDED',output_sha256=op.file_evidence(target)['sha256']),target))['status'],'SUCCEEDED')
    def test_valid_output_replaced_after_completion_is_unknown(self):
        target=self.store/'new.obj';target.write_text('v 0 0 0\nf 1 1 1\n')
        ident=self.record(dict(status='SUCCEEDED',output_sha256=op.file_evidence(target)['sha256']),target)
        target.write_text('v 1 0 0\nf 1 1 1\n')
        self.assertEqual(op.reconcile(ident)['status'],'UNKNOWN')
    def test_corrupt_zip_unknown(self):
        target=self.store/'bad.zprj';target.write_bytes(b'PK invalid')
        self.assertEqual(op.reconcile(self.record(dict(status='SUCCEEDED'),target))['status'],'UNKNOWN')
    def test_timeout_operation_id_is_durable(self):
        from marvelous_designer_mcp.bridge import BridgeError
        with patch.object(op.bridge,'call',side_effect=BridgeError('timeout','bridge_timeout')) as call:
            out=op.execute('result=1','simulate')
        self.assertEqual(out['status'],'UNKNOWN');self.assertTrue((self.store/(out['operation_id']+'.json')).is_file());self.assertEqual(call.call_count,1)
    def test_id_traversal_rejected(self):
        self.assertFalse(op.reconcile('../../secret')['ok'])


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
    def test_obj_geometry_ignores_localized_material_encoding(self):
        path=self.folder/'mesh.obj';path.write_bytes(b'mtllib \xff.mtl\nv 0 0 0\nv 1 2 3\nf 1 2 1\n')
        vertices,h=r.read_obj(path);self.assertEqual(vertices,[(0.,0.,0.),(1.,2.,3.)]);self.assertEqual(len(h),64)
    def test_cleanup_preserves_recent_and_foreign_files(self):
        ident=uuid.uuid4().hex
        for ext in ['.json','.zprj']:
            path=self.folder/(ident+ext);path.write_text('{}');os.utime(path,(0,0))
        (self.folder/'user-file.zprj').write_text('keep')
        recent=self.folder/(uuid.uuid4().hex+'.json');recent.write_text('{}')
        self.assertEqual(r.cleanup(self.folder,keep=0),[ident]);self.assertTrue(recent.exists());self.assertTrue((self.folder/'user-file.zprj').exists())
    def test_checkpoint_id_traversal_rejected(self):
        with self.assertRaises(ValueError):r.restore_checkpoint('../x','')
    def test_checkpoint_corruption_rejected_before_import(self):
        ident=uuid.uuid4().hex
        (self.folder/(ident+'.json')).write_text(json.dumps({'file':{'sha256':'expected'}}))
        (self.folder/(ident+'.zprj')).write_bytes(b'broken')
        with patch.object(r,'CHECKPOINTS',self.folder),patch.object(op,'execute') as execute:
            with self.assertRaises(ValueError):r.restore_checkpoint(ident,'')
        execute.assert_not_called()
    def test_material_enum(self):
        self.assertEqual({v.name:int(v) for v in MaterialFace},dict(FRONT=0,BACK=1,SIDE=2))
    def test_metrics_never_claim_convergence(self):
        def export(path):
            Path(path).write_text('v 0 0 0\nv 1 1 1\nv 1 0 0\nf 1 2 3\n')
            return dict(ok=True,metadata={'receipt':{'scene_snapshot_before':{'patterns':['a'],'topology_epoch':'one'}}})
        with patch.object(r,'SAMPLES',self.folder):
            first=r.measure(None,export)['result'];second=r.measure(first['current_snapshot_id'],export)['result']
        self.assertEqual(second['max_vertex_displacement'],0);self.assertNotIn('converged',second)


if __name__=='__main__':unittest.main()
