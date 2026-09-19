"""Read-only verification using the exact installed Codex MCP command, then release GUI."""
import asyncio
import json
import os
from pathlib import Path
import tomllib
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    root=Path(__file__).resolve().parents[1]
    config=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'config.toml'
    entry=tomllib.loads(config.read_text(encoding='utf-8'))['mcp_servers']['marvelous-designer']
    params=StdioServerParameters(command=entry['command'],args=entry['args'],env={**os.environ,**entry.get('env',{})})
    results=[]
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as session:
            await session.initialize()
            for name,args in [('ping',{}),('environment_info',{}),('search_md_docs',{'query':'create sewing between two pattern edges','limit':3}),('get_md_doc',{'name':'pattern_api.AddSeamlinePairGroup'}),('inspect_md_api',{'module':'pattern_api','function':'CreatePatternWithPoints'}),('execute_python',{'code':'import pattern_api\nresult=pattern_api.GetPatternCount()'}),('list_sewings',{}),('shutdown_listener',{})]:
                out=await session.call_tool(name,args)
                results.append({'tool':name,'response':out.model_dump(mode='json')})
                assert not out.isError, results[-1]
                print(name,'OK',flush=True)
    (root/'evidence'/'configured-mcp.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')

if __name__=='__main__': asyncio.run(main())
