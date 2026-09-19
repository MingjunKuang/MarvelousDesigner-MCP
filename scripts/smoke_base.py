"""Read-only baseline MCP stdio test; simulation only on an empty scene."""
import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    root = Path(__file__).resolve().parents[1]
    evidence = {}
    params = StdioServerParameters(command=sys.executable, args=['-m', 'marvelous_designer_mcp'], cwd=str(root))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            evidence['initialize'] = (await session.initialize()).model_dump(mode='json')
            evidence['tools'] = [t.name for t in (await session.list_tools()).tools]
            for name, args in [('ping', {}), ('scene_info', {}), ('list_patterns', {}), ('list_fabrics', {}), ('md_api', {'module':'pattern_api'}), ('execute_python', {'code':'import sys\nresult = {"python": sys.version, "test": 2+2}'})]:
                r = await session.call_tool(name, args)
                evidence[name] = r.model_dump(mode='json')
                print(name, r.structuredContent or [c.text for c in r.content if c.type=='text'], flush=True)
            scene = evidence['scene_info'].get('structuredContent') or json.loads(evidence['scene_info']['content'][0]['text'])
            if scene.get('result', {}).get('pattern_count') == 0:
                evidence['simulate'] = (await session.call_tool('simulate', {'steps':1})).model_dump(mode='json')
                print('simulate', evidence['simulate'], flush=True)
    out = root / 'evidence'
    out.mkdir(exist_ok=True)
    (out / 'baseline.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')

if __name__ == '__main__':
    asyncio.run(main())
