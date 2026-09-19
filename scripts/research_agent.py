"""Small auditable research steps on the dedicated agent test project."""
import json
from pathlib import Path
import sys
from marvelous_designer_mcp.bridge import call

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence' / 'agent-research'
OUT.mkdir(parents=True, exist_ok=True)

def run(name, code):
    result = call('execute_python', {'code': code}, timeout=30)
    (OUT / (name + '.json')).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))
    if result.get('error'):
        raise RuntimeError(result['error'])
    return result['result']

if __name__ == '__main__':
    step = sys.argv[1]
    if step == 'geometry':
        run(step, f'''
import utility_api as u, export_api as e, pattern_api as p, json, os
assert u.GetProjectName() == 'two-patterns' and e.GetAvatarCount() == 0
checkpoint = {str(OUT / 'before-research.zprj')!r}
assert not os.path.exists(checkpoint)
assert e.ExportZPrjW(checkpoint, False)
u.NewProject()
a=p.CreatePatternWithPoints([(0.,0.,0),(120.,0.,0),(140.,60.,2),(120.,120.,0),(0.,120.,0)])
p.SetPatternPieceName(a,'Agent_Curve_A')
b=p.CreatePatternWithPoints([(200.,0.,0),(320.,0.,0),(340.,60.,2),(320.,120.,0),(200.,120.,0)])
p.SetPatternPieceName(b,'Agent_Curve_B')
children=[]
children.append(p.CreateInternalShapeWithPoints(a,[(20.,20.,0),(80.,20.,0)],False))
children.append(p.CreateInternalShapeWithPoints(a,[(20.,40.,0),(50.,60.,2),(80.,40.,0)],False))
children.append(p.CreateInternalShapeWithPoints(a,[(20.,80.,0),(60.,80.,0),(60.,100.,0),(20.,100.,0)],True))
path={str(OUT / 'geometry-raw.json')!r}
assert p.ExportPatternJSON(path)
result=dict(children=children,raw=json.load(open(path,encoding='utf-8-sig')),input=p.GetPatternInputInformation(a),information=p.GetPatternInformation(a),arrangement=p.GetArrangementOfPattern(a))
''')
    elif step == 'options':
        run(step, '''
import ApiTypes
result={}
for name,obj in [('io',ApiTypes.ImportExportOption()),('project',ApiTypes.ImportZPRJOption())]:
    result[name]={}
    for key in dir(obj):
        if key.startswith('_'): continue
        try:
            val=getattr(obj,key)
            if isinstance(val,(bool,int,float,str)): result[name][key]=val
        except Exception as exc: result[name][key]=str(exc)
''')
