"""MCP stdio end-to-end test. Requires an empty scene or explicit known test scene."""
import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--known-probe-scene',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    folder=root/'evidence'/('live-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    folder.mkdir(parents=True)
    events=[]
    params=StdioServerParameters(command=sys.executable,args=['-m','marvelous_designer_mcp'],cwd=str(root))
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            (folder/'tools.json').write_text(json.dumps([t.model_dump(mode='json') for t in (await session.list_tools()).tools],indent=2),encoding='utf-8')
            async def run(tool_name,**arguments):
                r=await session.call_tool(tool_name,arguments)
                data=r.structuredContent
                if data is None:
                    texts=[c.text for c in r.content if c.type=='text']
                    data=json.loads(texts[0]) if len(texts)==1 else [json.loads(x) for x in texts]
                events.append({'tool':tool_name,'arguments':arguments,'response':data,'isError':r.isError})
                (folder/'results.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
                if r.isError or isinstance(data,dict) and data.get('ok') is False:
                    raise RuntimeError(str(events[-1]))
                print(tool_name,'OK',flush=True)
                return data.get('result',data) if isinstance(data,dict) else data
            await run('ping')
            scene=await run('scene_info')
            avatars=await run('avatar_info')
            pats=await run('list_patterns')
            if pats:
                expected=[['Pattern_1839','Pattern_2099'],['MCP_Test_A','MCP_Test_B']]
                assert args.known_probe_scene and [p['name'] for p in pats] in expected and avatars['count']==0, 'Refusing non-test scene'
                await run('save_project',path=str(folder/'probe-checkpoint.zprj'))
            else:
                assert avatars['count']==0, 'Refusing avatar scene'
            await run('search_md_docs',query='create sewing between two pattern edges')
            await run('get_md_doc',name='pattern_api.AddSeamlinePairGroup')
            await run('get_md_scenario',name='Pattern')
            for module,fn in [('utility_api','NewProject'),('pattern_api','CreatePatternWithPoints'),('pattern_api','AddSeamlinePairGroup'),('export_api','ExportOBJW')]:
                await run('inspect_md_api',module=module,function=fn)
            await run('execute_python',code='import utility_api, pattern_api\nutility_api.NewProject()\nresult=pattern_api.GetPatternCount()',allow_potentially_modal=True)
            a=await run('create_pattern',points=[[0,0,0],[120,0,0],[120,80,0],[0,80,0]],name='MCP_Test_A')
            b=await run('create_pattern',points=[[180,0,0],[300,0,0],[300,80,0],[180,80,0]],name='MCP_Test_B')
            ai,bi=a['pattern']['index'],b['pattern']['index']
            await run('get_pattern_points',pattern_index=ai)
            await run('move_pattern_point',pattern_index=ai,point_index=0,x=-10.,y=0.)
            await run('move_pattern_point',pattern_index=ai,point_index=0,x=0.,y=0.)
            await run('get_pattern_info',pattern_index=bi)
            await run('create_sewing',pattern_a=ai,line_a=1,pattern_b=bi,line_b=3,direction_a=True,direction_b=False)
            await run('inspect_sewing',group_index=0)
            await run('list_fabrics')
            await run('assign_fabric',fabric_index=0,pattern_index=ai,assign_option=1)
            await run('simulate',steps=5)
            await run('simulation_state')
            await run('save_project',path=str(folder/'two-patterns.zprj'))
            opts={'scale':1.0,'axisX':0,'axisY':1,'axisZ':2,'bExportGarment':True,'bExportAvatar':False,'bThin':True,'bSingleObject':False}
            await run('export_obj',path=str(folder/'two-patterns.obj'),options=opts)
            await run('export_fbx',path=str(folder/'two-patterns.fbx'),options=opts)
            await run('environment_info')
            extra=await run('create_pattern',points=[[400,0,0],[450,0,0],[450,50,0],[400,50,0]],name='MCP_Delete_Test')
            await run('delete_pattern',pattern_index=extra['pattern']['index'])
            assert (folder/'two-patterns.obj').stat().st_size>32
            assert (folder/'two-patterns.zprj').stat().st_size>32
            print('Evidence:',folder)

if __name__=='__main__':
    asyncio.run(main())
