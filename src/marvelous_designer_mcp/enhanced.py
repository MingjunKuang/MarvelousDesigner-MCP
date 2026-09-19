"""Documentation tools and verified operations registered on the upstream FastMCP server."""
from pathlib import Path
import os
from . import bridge, __version__
from .docs import DocsIndex
from .safety import preflight
from . import operations, recovery


def _md_exec(code):
    try:
        resp=bridge.call('execute_python',{'code':'result = None\n'+code})
    except bridge.BridgeError as e:
        return {'ok':False,'error':e.as_dict()}
    if resp.get('error'):
        return {'ok':False,'error':{'code':'md_exception','message':resp['error']},'stdout':resp.get('stdout','')}
    return {'ok':True,'result':resp.get('result'),'stdout':resp.get('stdout','')}


def _op(name,*args):
    source=Path(__file__).with_name('runtime_ops.py').read_text(encoding='utf-8')
    code=f"_ops = {{}}\nexec({source!r}, _ops)\nresult = _ops[{name!r}](*{args!r})"
    if name=='import_asset':
        top=Path(__file__).with_name('topology.py').read_text(encoding='utf-8')
        code=f"_ti={{}}\nexec({top!r},_ti)\n_ti['invalidate']()\n"+code
    if name in {'simulate','export_file','import_asset','create_pattern','move_point','delete_pattern','create_sewing','assign_fabric'}:
        return operations.execute(code,name,target_path=args[0] if name=='export_file' else None,input_path=args[0] if name=='import_asset' else None,expected_effect={'operation':name,'arguments':args})
    out=_md_exec(code)
    if not out['ok'] and out['error']['code']=='md_exception':
        message=out['error']['message']
        if 'ValueError:' in message or 'FileExistsError:' in message:
            out['error']['code']='invalid_parameter'
        elif 'NotImplementedError:' in message:
            out['error']['code']='unsupported_api'
        elif 'RuntimeError:' in message:
            out['error']['code']='api_error'
    return out


def execute_python(code: str, allow_potentially_modal: bool = False) -> dict:
    """Execute reviewed Python; import API modules and assign result. Look up docs/runtime first. Static guard is not a sandbox; modal-risk calls require explicit override."""
    if os.environ.get('MD_MCP_ALLOW_RAW_PYTHON', '1').lower() in {'0', 'false', 'no', 'off'}:
        return {'ok': False, 'error': {'code': 'raw_python_disabled', 'message': 'Raw execution disabled by MD_MCP_ALLOW_RAW_PYTHON; semantic tools remain available.'}}
    return _execute_reviewed(code, allow_potentially_modal)


def _execute_reviewed(code, allow_potentially_modal=False):
    try:
        check=preflight(code)
    except SyntaxError as e:
        return {'ok':False,'error':{'code':'invalid_python','message':str(e)}}
    if check['blocked'] and not allow_potentially_modal:
        return {'ok':False,'error':{'code':'modal_risk','message':'Review modal behavior before explicit override'},'preflight':check}
    top=Path(__file__).with_name('topology.py').read_text(encoding='utf-8')
    code=f"_ti={{}}\nexec({top!r},_ti)\n_ti['invalidate']()\n"+code
    return operations.execute(code,'execute_python',expected_effect='Reviewed user Python; receipt confirms execution, not design quality')


def preflight_python(code: str) -> dict:
    """Classify visible calls as safe, potentially modal, unsafe or unknown without execution."""
    return preflight(code)


def scene_info() -> dict:
    """Project, MD/Python version, pattern and fabric counts."""
    return _md_exec("import utility_api as u, pattern_api as p, fabric_api as f, sys\nresult={'project_name':u.GetProjectName(),'project_path':u.GetProjectFilePath(),'md_version':[u.GetMajorVersion(),u.GetMinorVersion(),u.GetPatchVersion()],'embedded_python':sys.version,'pattern_count':p.GetPatternCount(),'fabric_count':f.GetFabricCount(False),'used_fabric_count':f.GetFabricCount(True),'fabric_styles':f.GetFabricStyleNameList()}")


def environment_info() -> dict:
    """Runtime, MCP commit/version, documentation timestamp and connection health."""
    scene=scene_info()
    try: listener=bridge.call('ping', timeout=3)
    except bridge.BridgeError as e: listener={'error':e.as_dict()}
    try: docs=DocsIndex().metadata()
    except FileNotFoundError as e: docs={'error':str(e)}
    return {'scene':scene,'connection_status':'connected' if scene['ok'] else 'unavailable',
        'mcp_version':__version__,'docs':docs,
        'warning':'Documentation may lag behind the installed Marvelous Designer version; runtime API introspection is authoritative for availability.',
        'listener':listener,
        'gui':'Windows timer listener keeps the GUI responsive between requests. Synchronous API calls occupy the main thread for their duration; modal dialogs still require user attention.'}


def md_api(module: str, contains: str = '') -> dict:
    """List runtime symbols; inspect_md_api reads signatures safely without trial calls."""
    out=_op('inspect_api',module)
    if out['ok']: out['result']=[f['function'] for f in out['result'].get('functions',[]) if contains.lower() in f['function'].lower()]
    return out


def inspect_md_api(module: str, function: str | None = None) -> dict:
    """Runtime availability, callable/type/signature, docstring and pybind overloads without invoking functions."""
    return _op('inspect_api',module,function)


def search_md_docs(query: str, limit: int = 10) -> list[dict]:
    """Search local official MD docs with BM25; return signatures and sources."""
    return DocsIndex().search(query,limit)


def get_md_doc(name: str) -> dict:
    """Exact API/type documentation, overloads, parameter meanings, returns and source."""
    return DocsIndex().get(name)


def search_md_scenarios(query: str, limit: int = 10) -> list[dict]:
    """Search official Pattern, Simulation, Animation and Substance scenarios."""
    return DocsIndex().search(query,limit,'scenario')


def get_md_scenario(name: str) -> dict:
    """Read one official scenario; adapt paths and review mutations before execution."""
    return DocsIndex().get(name,'scenario')


def list_patterns() -> dict:
    """Structured patterns with runtime indices, geometry, fabrics, placement and sewing groups."""
    out=_op('snapshot')
    if out['ok']: out['result']=out['result']['patterns']
    return out


def get_pattern_info(pattern_index: int) -> dict:
    """Inspect geometry and line indices before edits; ambiguous mappings are flagged."""
    return _op('pattern_info',pattern_index)


def get_pattern_points(pattern_index: int) -> dict:
    """Point coordinates in mm and IDs; curve point mutation mapping is unverified."""
    return _op('points',pattern_index)


def create_pattern(points: list[list[float | int]], name: str | None = None) -> dict:
    """Create [x_mm,y_mm,type] vertices: 0=straight,2=spline,3=Bezier. Verify resulting pattern."""
    return _op('create_pattern',points,name)


def move_pattern_point(pattern_index: int | None = None, point_index: int | None = None, x: float = 0, y: float = 0, point_ref: str | None = None) -> dict:
    """Prefer point_ref for verified outer endpoints, including curved boundaries. Legacy numeric form supports straight polygons. Re-read after STALE_REFERENCE."""
    if point_ref is not None:
        return _agent_op('topology','move_reference',point_ref,x,y,mutation=True)
    return _op('move_point',pattern_index,point_index,x,y)


def delete_pattern(pattern_index: int) -> dict:
    """Inspect, delete and verify count change. Remaining indices may shift."""
    return _op('delete_pattern',pattern_index)


def list_sewings() -> dict:
    """Sewing groups, pattern/edge references, directions and raw properties."""
    out=_op('snapshot')
    if out['ok']: out['result']=out['result']['sewings']
    return out


def inspect_sewing(group_index: int) -> dict:
    """Read a sewing group; partial-edge/internal-shape line indices may be unresolved."""
    out=list_sewings()
    if out['ok']:
        if not 0<=group_index<len(out['result']):
            return {'ok':False,'error':{'code':'invalid_index','message':'Sewing group out of range'}}
        out['result']=out['result'][group_index]
    return out


def create_sewing(pattern_a: int | None = None, line_a: int | None = None, pattern_b: int | None = None, line_b: int | None = None, direction_a: bool | None = None, direction_b: bool | None = None, side_a: str | dict | None = None, side_b: str | dict | None = None) -> dict:
    """Prefer side_a/side_b edge refs for whole straight/curved/internal edges; optional ranges must be 0..1. Explicit boolean directions required. Legacy indices support straight outer edges."""
    if side_a is not None or side_b is not None:
        return _agent_op('topology','sew_references',side_a,side_b,direction_a,direction_b,mutation=True)
    return _op('create_sewing',pattern_a,line_a,pattern_b,line_b,direction_a,direction_b)


def list_fabrics() -> dict:
    """All object-browser fabrics plus current-colorway used count."""
    return _md_exec("import fabric_api as f\nresult={'fabrics':[{'index':i,'name':f.GetFabricName(i)} for i in range(f.GetFabricCount(False))],'used_count':f.GetFabricCount(True),'styles':f.GetFabricStyleNameList()}")


def assign_fabric(fabric_index: int, pattern_index: int, face: int = 2, assign_option: int | None = None) -> dict:
    """Assign and verify. Legacy face is colorway option, NOT surface face: 1=current,2=all unlinked,3=all linked. Prefer assign_option."""
    return _op('assign_fabric',fabric_index,pattern_index,face if assign_option is None else assign_option)


def get_pattern_fabric(pattern_index: int) -> dict:
    """Read actual pattern fabric assignment."""
    out=get_pattern_info(pattern_index)
    if out['ok']: out['result']={k:out['result'][k] for k in ['index','fabric_index','name']}
    return out


def avatar_info() -> dict:
    """Read avatar count, names and runtime properties."""
    return _op('avatar_info')


def project_info() -> dict:
    """Read active project and runtime state."""
    return scene_info()


def simulate(steps: int = 1) -> dict:
    """Simulate steps (=frames) and verify synchronous success; does not claim convergence."""
    return _op('simulate',steps)


def simulation_state() -> dict:
    """Native quality, pattern and mesh counts; physical convergence/collision judgments are not exposed."""
    return _md_exec("import utility_api as u, pattern_api as p\nresult={'quality':u.GetSimulationQuality(),'pattern_count':p.GetPatternCount(),'meshes':[p.GetMeshCountByType(i) for i in range(p.GetPatternCount())],'unavailable':['completed_step_counter','collision_contacts','convergence'],'positions_binding':'GetClothPositions output list remains empty on tested Python binding; request get_simulation_metrics for explicit OBJ sampling'}")


def save_project(path: str) -> dict:
    """Save a new ZPRJ checkpoint and verify file. Existing outputs are protected."""
    return _op('export_file',path,'zprj')


def export_project(path: str) -> dict:
    """Save ZPRJ with explicit path; API bool controls thumbnail creation."""
    return save_project(path)


def export_obj(path: str, options: dict) -> dict:
    """Export OBJ with explicit options, scale, axes and object selection; verify output."""
    return _op('export_file',path,'obj',options)


def export_fbx(path: str, options: dict) -> dict:
    """Export FBX with explicit runtime options; verify output."""
    return _op('export_file',path,'fbx',options)


def import_project(path: str, allow_potentially_modal: bool = False, options: dict | None = None) -> dict:
    """Prefer .zprj plus explicit ImportZPRJOption (including bAppend). Legacy generic import requires modal-risk acknowledgement."""
    if options is not None:
        return _op('import_asset',path,'project',options)
    p=Path(path)
    if not p.is_absolute() or not p.is_file():
        return {'ok':False,'error':{'code':'invalid_path','message':'Existing absolute input path required'}}
    if not allow_potentially_modal:
        return {'ok':False,'error':{'code':'modal_risk','message':'ImportFile may display dialogs. Save and review before opting in.'}}
    out=_execute_reviewed(f"import import_api\nresult=import_api.ImportFile({str(p)!r})",allow_potentially_modal=True)
    if out['ok'] and not out['result']:
        return {'ok':False,'error':{'code':'api_error','message':'ImportFile returned false'}}
    if out['ok']: out['verification']=scene_info()
    return out


def import_garment(path: str, options: dict) -> dict:
    """Import .zpac using explicit ImportExportOption including bAdd; verify count."""
    return _op('import_asset',path,'garment',options)


def import_avatar(path: str, options: dict, acknowledge_modal_risk: bool = False) -> dict:
    """Import verified OBJ avatar using explicit scale/axes/type=0; AVT still needs modal acknowledgement."""
    if Path(path).suffix.lower()!='.obj' and not acknowledge_modal_risk:
        return {'ok':False,'error':{'code':'modal_risk','message':'ImportAvatar dialog behavior is not live verified in this environment'}}
    return _op('import_asset',path,'avatar',options)


def _agent_op(module,name,*args,mutation=False):
    source=Path(__file__).with_name(module+'.py').read_text(encoding='utf-8')
    code=f"_agent={{}}\nexec({source!r},_agent)\nresult=_agent[{name!r}](*{args!r})"
    out=operations.execute(code,name) if mutation else _md_exec(code)
    if not out.get('ok') and 'STALE_REFERENCE' in str(out.get('error')):
        out['error']['code']='STALE_REFERENCE'
    return out


def get_pattern_topology(pattern: int | str) -> dict:
    """UUID + native point/line enumeration + geometry snapshot refs. Read again after STALE_REFERENCE; ambiguous mappings are never guessed."""
    return _agent_op('topology','read_topology',pattern)


def reconcile_operation(operation_id: str) -> dict:
    """Read durable MD completion receipt and output evidence; returns SUCCEEDED/FAILED/UNKNOWN and never retries."""
    return operations.reconcile(operation_id)


def create_checkpoint(label: str) -> dict:
    """Save a unique ZPRJ checkpoint. Retain latest 20; older than 7 days are cleaned on creation."""
    return recovery.create_checkpoint(label,save_project,lambda:_agent_op('agent_runtime','checkpoint_scene'))


def restore_checkpoint(checkpoint_id: str) -> dict:
    """Replace active scene with a verified checkpoint and invalidate all topology refs."""
    return recovery.restore_checkpoint(checkpoint_id,Path(__file__).with_name('topology.py').read_text(encoding='utf-8'))


def get_simulation_metrics(previous_snapshot_id: str | None = None) -> dict:
    """On-demand garment OBJ positions and index-based displacement if connectivity/UUIDs match; never judges convergence."""
    return recovery.measure(previous_snapshot_id,lambda path: export_obj(path,dict(scale=1.0,axisX=0,axisY=1,axisZ=2,bExportGarment=True,bExportAvatar=False,bThin=True,bSingleObject=True)))


def pattern_arrangement(pattern_index: int, arrangement_offsets: list[int] | None = None) -> dict:
    """Read/set verified arrangement X/Y/offset parameters. Not absolute world translation or Euler rotation."""
    return _agent_op('agent_runtime','placement',pattern_index,arrangement_offsets,mutation=arrangement_offsets is not None)


def fabric_material(fabric_index: int, face: str, rgba: list[float] | None = None) -> dict:
    """Read/set FRONT/BACK/SIDE RGBA (0..1). Setting BACK/SIDE unlinks material/color from FRONT. Verified MD 2026.0.315."""
    return _agent_op('agent_runtime','material',fabric_index,face,rgba,mutation=rgba is not None)


def register(mcp):
    replacements={'execute_python','scene_info','md_api','list_patterns','list_fabrics','assign_fabric','simulate','export_project','import_project'}
    for name in replacements:
        mcp.remove_tool(name)
    for name,fn in list(globals().items()):
        if name.startswith('_') or name=='register' or not callable(fn) or getattr(fn,'__module__',None)!=__name__:
            continue
        from .tool_help import description
        mcp.add_tool(fn, description=description(name, fn.__doc__))
