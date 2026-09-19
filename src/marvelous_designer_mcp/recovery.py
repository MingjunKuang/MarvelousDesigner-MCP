"""Filesystem checkpoints and explicitly requested mesh measurements."""
import hashlib
import json
import math
from pathlib import Path
import time
import uuid
from .paths import DATA_DIR
from . import operations

CHECKPOINTS=DATA_DIR/'checkpoints'
SAMPLES=DATA_DIR/'cache'/'simulation-samples'


def cleanup(directory, days=7, keep=20):
    directory.mkdir(parents=True,exist_ok=True)
    manifests=sorted(directory.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    removed=[]
    for path in manifests[keep:]:
        if time.time()-path.stat().st_mtime < days*86400:
            continue
        ident=path.stem
        if len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident):
            continue
        for sibling in directory.glob(ident+'.*'):
            if sibling.is_file() and sibling.resolve().parent==directory.resolve():
                sibling.unlink()
        removed.append(ident)
    return removed


def create_checkpoint(label, execute, inspect_scene):
    cleanup(CHECKPOINTS)
    ident=uuid.uuid4().hex
    path=CHECKPOINTS/(ident+'.zprj')
    before=inspect_scene()
    if not before.get('ok'): return before
    result=execute(str(path))
    if not result.get('ok'):
        return result
    meta=dict(checkpoint_id=ident,label=label,path=str(path),created=time.time(),
        file=operations.file_evidence(path),operation_id=result['operation_id'],
        scene_metadata=result['metadata']['receipt']['scene_snapshot_before'],verification_snapshot=before['result'])
    operations.write_json(CHECKPOINTS/(ident+'.json'),meta)
    return dict(ok=True,result=meta)


def restore_checkpoint(ident, topology_source):
    if not isinstance(ident,str) or len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident):
        raise ValueError('Invalid checkpoint ID')
    meta=json.loads((CHECKPOINTS/(ident+'.json')).read_text(encoding='utf-8'))
    path=CHECKPOINTS/(ident+'.zprj')
    evidence=operations.file_evidence(path)
    if not evidence['valid'] or evidence['sha256']!=meta['file']['sha256']:
        raise ValueError('Checkpoint is missing, corrupt or changed')
    # ImportZprjW explicitly supports dialog-free load options. No NewProject
    # call is required; this avoids an unsaved-changes prompt.
    scene_source=Path(__file__).with_name('agent_runtime.py').read_text(encoding='utf-8')
    code=f'''
import import_api as _ci, ApiTypes as _ct, pattern_api as _cp, export_api as _ce, json as _cj
_ns={{}}
exec({topology_source!r},_ns)
_ns['invalidate']()
_options=_ct.ImportZPRJOption()
_options.bAppend=False
_options.bLoadGarment=True
_options.bLoadAvatar=True
_returned=_ci.ImportZprjW({str(path)!r},_options)
_after=dict(patterns=[_cj.loads(_cp.GetPatternInformation(i)).get('uuid') for i in range(_cp.GetPatternCount())],avatars=_ce.GetAvatarNameListW())
_expected={meta['scene_metadata']!r}
if not _returned or _after['patterns']!=_expected['patterns'] or _after['avatars']!=_expected['avatars']:
    raise RuntimeError('Checkpoint restore identity/count postcondition failed')
_verify={{}}
exec({scene_source!r},_verify)
_actual=_verify['checkpoint_scene']()
_expected_geometry={meta.get('verification_snapshot')!r}
if _expected_geometry is not None and _cj.dumps(_actual,sort_keys=True)!=_cj.dumps(_expected_geometry,sort_keys=True):
    raise RuntimeError('Checkpoint geometry/sewing/material/avatar readback differs; inspect before further edits')
result=dict(verified=True,checkpoint_id={ident!r},scene=_after,verification_scope='Geometry, sewing ranges/directions, material colors, avatar names/properties')
'''
    return operations.execute(code,'restore_checkpoint',expected_effect=meta['scene_metadata'])


def read_obj(path):
    vertices=[]
    faces=[]
    for line in Path(path).read_bytes().splitlines():
        if line.startswith(b'v '):
            values=tuple(float(v) for v in line.split()[1:4])
            if len(values)!=3 or not all(math.isfinite(v) for v in values):
                raise ValueError('Invalid vertex')
            vertices.append(values)
        elif line.startswith((b'f ',b'g ',b'o ')):
            faces.append(line)
    return vertices,hashlib.sha256(b'\n'.join(faces)).hexdigest()


def measure(previous_id, export):
    cleanup(SAMPLES)
    ident=uuid.uuid4().hex
    path=SAMPLES/(ident+'.obj')
    started=time.monotonic()
    result=export(str(path))
    if not result.get('ok'):
        return result
    vertices,topology_hash=read_obj(path)
    scene=result['metadata']['receipt']['scene_snapshot_before']
    snapshot=dict(snapshot_id=ident,vertices=vertices,topology_hash=topology_hash,scene=scene,created=time.time())
    operations.write_json(SAMPLES/(ident+'.json'),snapshot)
    out=dict(current_snapshot_id=ident,previous_snapshot_id=previous_id,sampled_vertices=len(vertices),
        source='Explicit garment-only OBJ export',unit='mm',mean_vertex_displacement=None,max_vertex_displacement=None,
        comparable=False,elapsed_seconds=time.monotonic()-started)
    if previous_id:
        if len(previous_id)!=32 or any(c not in '0123456789abcdef' for c in previous_id):
            raise ValueError('Invalid snapshot ID')
        prev=json.loads((SAMPLES/(previous_id+'.json')).read_text(encoding='utf-8'))
        # OBJ has no persistent vertex IDs. Only claim index-based measurements
        # when the exact connectivity and pattern UUID sequence stay identical.
        if prev['topology_hash']==topology_hash and len(prev['vertices'])==len(vertices) and prev['scene']['patterns']==scene['patterns'] and prev['scene'].get('topology_epoch')==scene.get('topology_epoch'):
            distances=[math.dist(a,b) for a,b in zip(prev['vertices'],vertices)]
            out.update(comparable=True,mean_vertex_displacement=sum(distances)/len(distances) if distances else None,
                max_vertex_displacement=max(distances,default=None),correspondence='Identical OBJ connectivity/order and pattern UUIDs; no persistent mesh vertex IDs exposed')
        else:
            out['reason']='Mesh connectivity/count or pattern identity changed'
    return dict(ok=True,result=out)
