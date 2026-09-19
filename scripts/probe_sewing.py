import json
from pathlib import Path
from marvelous_designer_mcp.bridge import call
root=Path(__file__).resolve().parents[1]
code='''
import pattern_api
assert pattern_api.GetPatternCount()==2 and pattern_api.GetSeamlinePairGroupCount()==0
result = {'lengths':[pattern_api.GetLineLength(0,1),pattern_api.GetLineLength(1,3)],
 'created':pattern_api.AddSeamlinePairGroup(0,1,1,3,True,False),
 'count':pattern_api.GetSeamlinePairGroupCount(),
 'name':pattern_api.GetSeamlinePairGroupName(0)}
'''
r=call('execute_python',{'code':code})
(root/'evidence'/'sewing-probe.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
print(r)
path=str(root/'evidence'/'patterns-sewn.json')
print(call('execute_python',{'code':f'import pattern_api\nresult=pattern_api.ExportPatternJSON({path!r})'}))
