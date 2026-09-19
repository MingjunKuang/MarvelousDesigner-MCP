"""Additional avatar scale/axis and UNKNOWN export/simulation regression."""
from datetime import datetime
import json
from pathlib import Path
from marvelous_designer_mcp import enhanced as e,operations,recovery
from marvelous_designer_mcp.bridge import call

root=Path(__file__).resolve().parents[1]
out=root/'evidence'/('agent-edges-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True)
results=[]
def record(name,value):
    results.append(dict(step=name,result=value))
    (out/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf8')
    return value
assert all(p['name'].startswith('Agent_') for p in e.list_patterns()['result'])
checkpoint=e.create_checkpoint('scale axis regression')['result']
created=e.execute_python("import pattern_api as p\nresult=p.CreateInternalShapeWithPoints(1,[(220.,540.,0),(250.,560.,2),(280.,540.,0)],False)")
assert created['ok']
a=e.get_pattern_topology('Agent_Front')['result'];b=e.get_pattern_topology('Agent_Back')['result']
outer_curve=record('outer_to_internal_curve',e.create_sewing(side_a=b['outer_boundary'][1]['stable_ref'],side_b=a['internal_lines'][1]['edges'][0]['stable_ref'],direction_a=True,direction_b=False))
assert outer_curve['ok']
inner_curve=record('internal_curve_to_internal_curve',e.create_sewing(side_a=a['internal_lines'][1]['edges'][0]['stable_ref'],side_b=b['internal_lines'][0]['edges'][0]['stable_ref'],direction_a=True,direction_b=False))
assert inner_curve['ok']
assert record('restore_after_internal_sewing',e.restore_checkpoint(checkpoint['checkpoint_id']))['ok']
fixture=str(root/'tests/fixtures/avatar_mm.obj')
for label,scale,axes,expected in [('scale2',2.,[0,1,2],[400,800,200]),('axis_yz',1.,[0,2,1],[200,100,400])]:
    code=f"import import_api as imp,ApiTypes,export_api as ex\no=ApiTypes.ImportExportOption()\no.bAdd=False\no.scale={scale!r}\no.axisX,o.axisY,o.axisZ={axes!r}\nassert imp.ImportOBJW({fixture!r},o)\nresult=ex.GetAvatarCount()"
    result=record(label,e.execute_python(code,True));assert result['ok']
    path=out/(label+'.obj')
    result=e.export_obj(str(path),dict(scale=1.,axisX=0,axisY=1,axisZ=2,bExportGarment=False,bExportAvatar=True));assert result['ok']
    vertices,_=recovery.read_obj(path)
    bounds=[max(v[k] for v in vertices)-min(v[k] for v in vertices) for k in range(3)]
    record(label+'_bounds_mm',bounds);assert all(abs(a-b)<.01 for a,b in zip(bounds,expected))
record('restore_after_avatar_tests',e.restore_checkpoint(checkpoint['checkpoint_id']))
source=(root/'src/marvelous_designer_mcp/runtime_ops.py').read_text(encoding='utf8')
for kind,code,target in [
    ('export_timeout',f"import time\ntime.sleep(.15)\n_ops={{}}\nexec({source!r},_ops)\nresult=_ops['export_file']({str(out/'timeout.zprj')!r},'zprj')",str(out/'timeout.zprj')),
    ('simulation_timeout',"import time,utility_api as u\ntime.sleep(.15)\nreturned=u.Simulate(1)\nassert returned\nresult={'verified':True,'steps':1,'scope':'API completed; convergence not inferred'}",None)]:
    unknown=record(kind,operations.execute(code,kind,target_path=target,timeout=.03))
    assert unknown['status']=='UNKNOWN'
    call('ping',timeout=5)
    reconciled=record(kind+'_reconciled',e.reconcile_operation(unknown['operation_id']))
    assert reconciled['status']=='SUCCEEDED'
restore=record('restore_final',e.restore_checkpoint(checkpoint['checkpoint_id']));assert restore['ok']
print(out)
