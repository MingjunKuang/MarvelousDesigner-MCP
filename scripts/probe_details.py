import json
from pathlib import Path
from marvelous_designer_mcp.bridge import call
root=Path(__file__).resolve().parents[1]
code='''
import importlib.util, utility_api, pattern_api, ApiTypes
result = {'qt_available': {n: importlib.util.find_spec(n) is not None for n in ['PySide2','PySide6','PyQt5','PyQt6','sip']},
 'hooks': [n for n in dir(utility_api) if any(s in n.lower() for s in ['timer','event','callback','thread','dispatch','idle'])],
 'options': {n: str(getattr(ApiTypes.ImportExportOption(),n)) for n in dir(ApiTypes.ImportExportOption()) if not n.startswith('_')}}
'''
r=call('execute_python',{'code':code})
(root/'evidence'/'environment-probe.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
print(json.dumps(r,indent=2))
path=str(root/'evidence'/'patterns.json')
print(call('execute_python',{'code':f'import pattern_api\nresult = pattern_api.ExportPatternJSON({path!r})'}))
