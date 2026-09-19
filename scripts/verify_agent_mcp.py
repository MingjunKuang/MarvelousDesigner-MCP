"""Read-only stdio MCP validation; keeps the Windows listener running."""
import asyncio,json,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    root=Path(__file__).resolve().parents[1]
    results=[]
    async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','marvelous_designer_mcp'],cwd=str(root))) as (r,w):
        async with ClientSession(r,w) as session:
            await session.initialize()
            tools=(await session.list_tools()).tools
            for name,args in [('ping',{}),('environment_info',{}),('get_pattern_topology',{'pattern':'Agent_Front'}),('avatar_info',{}),('pattern_arrangement',{'pattern_index':0}),('fabric_material',{'fabric_index':0,'face':'FRONT'}),('simulation_state',{})]:
                response=await session.call_tool(name,args)
                assert not response.isError,response
                data=response.structuredContent
                if data is None:data=json.loads(response.content[0].text)
                assert data.get('ok',True),data
                results.append(dict(tool=name,result=data))
            (root/'evidence/agent-mcp.json').write_text(json.dumps(dict(tools=[t.model_dump(mode='json') for t in tools],results=results),indent=2,ensure_ascii=False),encoding='utf-8')
            print('MCP tools:',len(tools))
            print([t.name for t in tools])


if __name__=='__main__':asyncio.run(main())
