"""Manual installed-package test on an inspected disposable Agent_* scene.

Run with the NEW environment's python, passing its md-mcp executable and an
absolute output directory. Server cwd is that output directory, not the clone.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def verify(executable, output, shutdown=False):
    output.mkdir(parents=True, exist_ok=True)
    events = []
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    async with stdio_client(StdioServerParameters(command=str(executable), args=['serve'], cwd=str(output), env=env)) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            assert 'UNKNOWN' in initialized.instructions
            tools = (await session.list_tools()).tools
            assert len(tools) == 42
            names = {t.name for t in tools}
            assert 'pattern_arrangement' in names and 'pattern_placement' not in names

            async def call(tool_name, **args):
                response = await session.call_tool(tool_name, args)
                assert not response.isError, response
                data = response.structuredContent
                if data is None:
                    data = json.loads(response.content[0].text)
                events.append({'tool': tool_name, 'result': data})
                (output / 'results.json').write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding='utf-8')
                assert data.get('ok', True), data
                print(tool_name, 'OK', flush=True)
                return data.get('result', data)

            await call('ping')
            await call('environment_info')
            await call('scene_info')
            patterns = await call('list_patterns')
            assert patterns and all(p['name'].startswith('Agent_') for p in patterns), 'Disposable Agent scene required'
            await call('get_pattern_topology', pattern=patterns[0]['index'])
            cp = await call('create_checkpoint', label='installed-wheel-validation')
            await call('create_pattern', points=[[500, 500, 0], [550, 500, 0], [500, 550, 0]], name='Agent_Release')
            after = await call('list_patterns')
            assert len(after) == len(patterns) + 1 and any(p['name'] == 'Agent_Release' for p in after)
            await call('save_project', path=str(output / 'verified.zprj'))
            await call('export_obj', path=str(output / 'verified.obj'), options=dict(scale=1.0, axisX=0, axisY=1, axisZ=2, bExportGarment=True, bExportAvatar=False, bThin=True, bSingleObject=True))
            await call('restore_checkpoint', checkpoint_id=cp['checkpoint_id'])
            restored = await call('list_patterns')
            assert len(restored) == len(patterns)
            if shutdown:
                await call('shutdown_listener')
            (output / 'schema.json').write_text(json.dumps({'instructions': initialized.instructions, 'tools': [t.model_dump(mode='json') for t in tools]}, indent=2), encoding='utf-8')
            print('Installed stdio tools:', len(tools))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--shutdown', action='store_true')
    args = parser.parse_args()
    asyncio.run(verify(args.executable, args.output.resolve(), args.shutdown))
