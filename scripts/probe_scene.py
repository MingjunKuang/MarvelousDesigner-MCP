"""Create two disposable patterns only when the scene is empty, inspect raw schema."""
import json
from pathlib import Path
from marvelous_designer_mcp.bridge import call

code = '''
import utility_api, pattern_api, export_api, json, ApiTypes
assert pattern_api.GetPatternCount() == 0 and export_api.GetAvatarCount() == 0, 'Requires empty test scene'
utility_api.NewProject()
a = pattern_api.CreatePatternWithPoints([(0.,0.,0),(100.,0.,0),(100.,100.,0),(0.,100.,0)])
b = pattern_api.CreatePatternWithPoints([(150.,0.,0),(250.,0.,0),(250.,100.,0),(150.,100.,0)])
result = {'created':[a,b], 'patterns':[json.loads(pattern_api.GetPatternInformation(i)) for i in [a,b]], 'options':{n:getattr(ApiTypes.ImportExportOption(),n) for n in dir(ApiTypes.ImportExportOption()) if not n.startswith('_')}, 'sewings':pattern_api.GetSeamlinePairGroupCount()}
'''
r=call('execute_python',{'code':code})
p=Path(__file__).resolve().parents[1]/'evidence'/'scene-schema.json'
p.write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(r,ensure_ascii=False,indent=2))
