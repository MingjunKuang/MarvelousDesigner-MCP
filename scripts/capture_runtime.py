"""Capture signatures without invoking API functions."""
import json
from pathlib import Path
from marvelous_designer_mcp.bridge import call

code = '''
import importlib, inspect, sys
result = {'python': sys.version, 'modules': {}}
for name in ['pattern_api', 'fabric_api', 'utility_api', 'import_api', 'export_api', 'ApiTypes', 'rest_api']:
    try:
        mod = importlib.import_module(name)
        entries = {}
        for attr in dir(mod):
            if attr.startswith('_'): continue
            obj = getattr(mod, attr)
            try: signature = str(inspect.signature(obj))
            except (TypeError, ValueError): signature = None
            entries[attr] = {'callable': callable(obj), 'type': str(type(obj)), 'signature': signature, 'doc': getattr(obj, '__doc__', None)}
        result['modules'][name] = entries
    except Exception as e:
        result['modules'][name] = {'error': str(e)}
result['qt_modules'] = [n for n in sys.modules if any(x in n.lower() for x in ('pyside','pyqt','qtcore'))]
'''
r = call('execute_python', {'code': code})
p = Path(__file__).resolve().parents[1] / 'evidence' / 'runtime.json'
p.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding='utf-8')
print(p, r.get('error'))
