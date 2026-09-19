"""Bounded regression on named Agent test scenes only; writes fresh artifacts."""
from datetime import datetime
import json
from pathlib import Path
import shutil
from marvelous_designer_mcp import enhanced as e, operations, recovery
from marvelous_designer_mcp.bridge import call

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence'/('agent-live-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
OUT.mkdir(parents=True)
events=[]


def run(name,fn,*args,**kwargs):
    out=fn(*args,**kwargs)
    events.append(dict(step=name,response=out))
    (OUT/'results.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
    assert out.get('ok'), (name,out)
    print(name,'OK',flush=True)
    return out.get('result')


def raw(name,code):
    return run(name,e.execute_python,code,allow_potentially_modal=True)


def main():
    scene=e.list_patterns()
    assert scene['ok'] and all(p['name'].startswith('Agent_') for p in scene['result']), 'Refusing non-test scene'
    run('preserve_test_scene',e.save_project,str(OUT/'before-test.zprj'))
    raw('new_project','import utility_api as u,pattern_api as p\nu.NewProject()\nresult=p.GetPatternCount()')
    fixture=OUT/'测试人台.obj'
    shutil.copyfile(ROOT/'tests/fixtures/avatar_mm.obj',fixture)
    options=dict(bAdd=False,scale=1.0,axisX=0,axisY=1,axisZ=2,ImportObjectType=0)
    run('avatar_import_unicode',e.import_avatar,str(fixture),options)
    avatar=run('avatar_query',e.avatar_info)
    assert avatar['count']==1 and avatar['avatars'][0]['properties']
    run('avatar_append',e.import_avatar,str(fixture),{**options,'bAdd':True})
    assert e.avatar_info()['result']['count']==2
    raw('avatar_replace_native',f"import import_api as imp,ApiTypes,export_api as ex\nopt=ApiTypes.ImportExportOption()\nopt.bAdd=False\nopt.scale=1.0\nreturned=imp.ImportOBJW({str(fixture)!r},opt)\nassert returned and ex.GetAvatarCount()==1\nresult=dict(returned=returned,count=ex.GetAvatarCount())")
    export_options=dict(scale=1.0,axisX=0,axisY=1,axisZ=2,bExportGarment=False,bExportAvatar=True,bSingleObject=True)
    run('avatar_export_bounds',e.export_obj,str(OUT/'avatar-roundtrip.obj'),export_options)
    vertices,_=recovery.read_obj(OUT/'avatar-roundtrip.obj')
    bounds=[max(v[k] for v in vertices)-min(v[k] for v in vertices) for k in range(3)]
    assert all(abs(a-b)<.01 for a,b in zip(bounds,[200,400,100])),bounds
    checkpoint=run('avatar_checkpoint',e.create_checkpoint,'avatar roundtrip')
    run('avatar_reopen',e.restore_checkpoint,checkpoint['checkpoint_id'])
    assert e.avatar_info()['result']['count']==1
    raw('create_curves_and_internals',"""
import pattern_api as p
a=p.CreatePatternWithPoints([(0.,500.,0),(120.,500.,0),(140.,560.,2),(120.,620.,0),(0.,620.,0)])
p.SetPatternPieceName(a,'Agent_Front')
b=p.CreatePatternWithPoints([(200.,500.,0),(320.,500.,0),(340.,560.,2),(320.,620.,0),(200.,620.,0)])
p.SetPatternPieceName(b,'Agent_Back')
children=[p.CreateInternalShapeWithPoints(a,[(20.,520.,0),(80.,520.,0)],False),p.CreateInternalShapeWithPoints(a,[(20.,540.,0),(50.,560.,2),(80.,540.,0)],False),p.CreateInternalShapeWithPoints(a,[(20.,580.,0),(60.,580.,0),(60.,600.,0),(20.,600.,0)],True)]
result=dict(patterns=[a,b],children=children)
""")
    a=run('topology_front',e.get_pattern_topology,'Agent_Front')
    b=run('topology_back',e.get_pattern_topology,'Agent_Back')
    assert not a['ambiguous'] and not b['ambiguous']
    assert [x['type'] for x in a['internal_lines']]==['internal_line','internal_curve']
    ref=next(p['stable_ref'] for p in a['points'] if p['child_index'] is None and p['runtime_index']==2)
    run('move_curve_endpoint',e.move_pattern_point,point_ref=ref,x=125.,y=625.)
    stale=e.move_pattern_point(point_ref=ref,x=126.,y=625.)
    assert stale['error']['code']=='STALE_REFERENCE',stale
    events.append(dict(step='stale_rejected',response=stale))
    a=run('topology_refresh',e.get_pattern_topology,'Agent_Front')
    run('curve_sewing',e.create_sewing,side_a=a['outer_boundary'][1]['stable_ref'],side_b=b['outer_boundary'][1]['stable_ref'],direction_a=True,direction_b=False)
    run('internal_sewing',e.create_sewing,side_a=b['outer_boundary'][0]['stable_ref'],side_b=a['internal_lines'][0]['edges'][0]['stable_ref'],direction_a=True,direction_b=False)
    partial=e.create_sewing(side_a={'edge_ref':a['outer_boundary'][0]['stable_ref'],'range_start':.2,'range_end':.8},side_b=b['outer_boundary'][0]['stable_ref'],direction_a=True,direction_b=False)
    assert not partial['ok'] and 'Partial/free' in str(partial)
    events.append(dict(step='partial_sewing_unsupported',response=partial))
    run('fabric_assignment',e.assign_fabric,0,0,assign_option=1)
    for face,color in [('FRONT',[1.,0.,0.,1.]),('BACK',[0.,1.,0.,1.]),('SIDE',[0.,0.,1.,1.])]:
        run('material_'+face,e.fabric_material,0,face,color)
    colors=run('material_all_faces',e.fabric_material,0,'FRONT')['all_faces']
    assert colors==dict(FRONT=[1.,0.,0.,1.],BACK=[0.,1.,0.,1.],SIDE=[0.,0.,1.,1.])
    run('arrangement_offsets',e.pattern_arrangement,0,[40,60,30])
    first=run('metrics_before',e.get_simulation_metrics)
    repeated=run('metrics_repeat',e.get_simulation_metrics,first['current_snapshot_id'])
    assert repeated['comparable'] and repeated['max_vertex_displacement']==0
    run('simulate_small_batch',e.simulate,3)
    run('metrics_after',e.get_simulation_metrics,repeated['current_snapshot_id'])
    run('simulation_state',e.simulation_state)
    checkpoint=run('checkpoint',e.create_checkpoint,'before geometry edit')
    before=run('topology_before_edit',e.get_pattern_topology,0)
    pref=next(p['stable_ref'] for p in before['points'] if p['mutable'])
    run('checkpointed_edit',e.move_pattern_point,point_ref=pref,x=-20.,y=500.)
    run('restore',e.restore_checkpoint,checkpoint['checkpoint_id'])
    after=run('topology_restored',e.get_pattern_topology,0)
    def geometry(t):
        return [[(p['PointType'],p['Position']) for p in edge['raw']['PointList']] for edge in t['outer_boundary']] + [[[ (p['PointType'],p['Position']) for p in edge['raw']['PointList']] for edge in child['edges']] for child in t['internal_lines']+t['internal_shapes']]
    assert geometry(after)==geometry(before)
    assert after['session_id']!=before['session_id']
    assert len(e.list_sewings()['result'])==2
    assert e.avatar_info()['result']['count']==1
    raw('cloth_positions_binding_probe','import utility_api as u\npositions=[]\nu.GetClothPositions(positions)\nresult=dict(positions=positions)')
    run('save_final',e.save_project,str(OUT/'agent-final.zprj'))
    garment=dict(scale=1.0,axisX=0,axisY=1,axisZ=2,bExportGarment=True,bExportAvatar=True)
    run('export_obj',e.export_obj,str(OUT/'agent-final.obj'),garment)
    run('export_fbx',e.export_fbx,str(OUT/'agent-final.fbx'),garment)
    unknown=operations.execute('import time\ntime.sleep(.2)\nresult=42','timeout_test',timeout=.05)
    assert unknown['status']=='UNKNOWN',unknown
    call('ping',timeout=3)
    reconciled=run('reconcile_timed_out_python',e.reconcile_operation,unknown['operation_id'])
    assert reconciled==42
    outputs={ext:operations.file_evidence(OUT/('agent-final.'+ext)) for ext in ['zprj','obj','fbx']}
    assert all(v['valid'] for v in outputs.values())
    (OUT/'outputs.json').write_text(json.dumps(dict(outputs=outputs,avatar_bounds_mm=bounds),indent=2),encoding='utf-8')
    print(OUT)


if __name__=='__main__': main()
