"""Runtime guidance delivered to every MCP client."""
INSTRUCTIONS = '''Control local Marvelous Designer through its embedded Python API.
Inspect the scene before geometry changes. Use stable pattern/point/edge references;
never guess runtime indices. Look up unfamiliar APIs with documentation tools and
verify availability against the running MD version. Verify state after mutations.
Timeout does not cancel execution: mutations are UNKNOWN until reconcile_operation
establishes their outcome. Never blindly retry. Prefer create_checkpoint before
destructive edits; it may affect the current project path depending on MD API
behavior. Do not assume that path is preserved. Restore invalidates topology refs.
Orchestrate complex workflows incrementally with these deterministic operations.
Raw execute_python is not a security sandbox; connect only trusted clients.
Documentation is downloaded separately with md-mcp update-docs.'''

MUTATIONS = {'execute_python', 'create_pattern', 'move_pattern_point', 'delete_pattern',
             'create_sewing', 'assign_fabric', 'simulate', 'save_project', 'export_project',
             'export_obj', 'export_fbx', 'import_project', 'import_garment', 'import_avatar',
             'create_checkpoint', 'restore_checkpoint', 'get_simulation_metrics',
             'pattern_arrangement', 'fabric_material'}
EXTRA = {
    'execute_python': 'Raw code can change the scene and access embedded Python filesystem/process capabilities. Not a sandbox. MD_MCP_ALLOW_RAW_PYTHON=0 refuses this tool.',
    'get_pattern_topology': 'Select by UUID, unique name or freshly inspected index. Prefer returned stable refs for edits; curve controls are not movable native endpoints.',
    'move_pattern_point': 'x/y are 2D millimetres; obtain point_ref from get_pattern_topology. Geometry changes invalidate the old refs.',
    'create_sewing': 'Only full-edge ranges [0,1] are supported; partial/free sewing is unverified. Obtain both refs from fresh topology.',
    'create_checkpoint': 'May affect the current project path depending on MD API behavior. Keep durable project saves outside this auto-cleaned cache.',
    'save_project': 'Requires a new absolute output path. ZPRJ save may change the active project path.',
    'export_project': 'Requires a new absolute output path. ZPRJ save may change the active project path.',
    'export_obj': 'Requires a new absolute path; inspect runtime ExportOBJOption fields before choosing options.',
    'export_fbx': 'Requires a new absolute path; inspect runtime ExportFBXOption fields before choosing options.',
    'import_avatar': 'Use an existing absolute path and explicit scale/axis options. OBJ ImportObjectType=0 is verified; FBX/AVT avatar imports are unverified.',
    'pattern_arrangement': 'Controls Marvelous Designer arrangement parameters, NOT a verified world-space transform. Omit arrangement_offsets to read; otherwise supply three integers.',
    'fabric_material': 'Omit rgba to read. This face enum is distinct from fabric assignment colorway options.',
    'get_simulation_metrics': 'Writes an OBJ measurement in user cache. Compare to previous_snapshot_id only if topology matches; no persistent vertex IDs or collision/convergence guarantee.',
    'reconcile_operation': 'Pass the operation_id from the original call. FAILED can include partial effects; UNKNOWN needs scene/output inspection.',
}


def description(name, original):
    parts = [(original or '').strip(), EXTRA.get(name, '')]
    if name in MUTATIONS:
        parts.append('May change scene or write files. Verify resulting state. A timed-out operation is UNKNOWN: reconcile_operation before any retry.')
    else:
        parts.append('Does not mutate the MD scene.')
    if name in {'search_md_docs', 'get_md_doc', 'search_md_scenarios', 'get_md_scenario'}:
        parts.append('Requires local index: md-mcp update-docs. Documentation can lag the runtime.')
    return ' '.join(p for p in parts if p)
