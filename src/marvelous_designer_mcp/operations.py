"""Small durable operation journal. Unknown mutations are never retried."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid
import zipfile
from . import bridge
from .paths import DATA_DIR

STORE = DATA_DIR / 'operations'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=True), encoding='utf-8')
    os.replace(temp, path)


def file_evidence(path):
    p = Path(path)
    if not p.is_file():
        return {'exists':False, 'valid':False}
    sha=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):sha.update(chunk)
    out = dict(exists=True, bytes=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns,
               sha256=sha.hexdigest(), valid=False)
    try:
        if p.suffix.lower()=='.zprj':
            with zipfile.ZipFile(p) as z:
                out['valid']=bool(z.namelist()) and z.testzip() is None
        elif p.suffix.lower()=='.obj':
            out['vertices']=out['faces']=0
            with p.open('rb') as stream:
                for line in stream:
                    out['vertices']+=line.startswith(b'v ')
                    out['faces']+=line.startswith(b'f ')
            out['valid']=out['vertices']>0 and out['faces']>0
        elif p.suffix.lower()=='.fbx':
            with p.open('rb') as stream:head=stream.read(100)
            out['valid']=head.startswith(b'Kaydara FBX Binary  \x00') or b'FBX' in head
    except (OSError,zipfile.BadZipFile):
        pass
    return out


def execute(code, operation_type, target_path=None, expected_effect=None, timeout=None, input_path=None):
    operation_id=uuid.uuid4().hex
    record_path=STORE/(operation_id+'.json')
    receipt_path=STORE/(operation_id+'.receipt.json')
    metadata=dict(operation_id=operation_id, operation_type=operation_type,
        start_time=datetime.now(timezone.utc).isoformat(), target_path=target_path,
        expected_effect=expected_effect, status='UNKNOWN', retry_safe=False,
        input_path=input_path,
        target_before=file_evidence(target_path) if target_path else None)
    write_json(record_path, metadata)
    # Execute in persistent listener globals to preserve execute_python semantics.
    # Metadata is written inside MD before and after execution, on the same thread.
    wrapped=f'''
import json as _oj, os as _oo, traceback as _ot, time as _oti, sys as _osys, hashlib as _oh
import pattern_api as _op, export_api as _oe, utility_api as _ou
_receipt_path={str(receipt_path)!r}
def _operation_scene():
    return dict(patterns=[_oj.loads(_op.GetPatternInformation(i)).get('uuid') for i in range(_op.GetPatternCount())], avatars=_oe.GetAvatarNameListW(), project=_ou.GetProjectFilePath(), topology_epoch=getattr(_osys,'_md_agent_topology',{{}}).get('epoch'))
def _operation_write(value):
    with open(_receipt_path+'.tmp','w',encoding='utf-8') as f: _oj.dump(value,f,default=repr)
    _oo.replace(_receipt_path+'.tmp',_receipt_path)
_receipt=dict(operation_id={operation_id!r},status='RUNNING',scene_snapshot_before=_operation_scene(),start_time=_oti.time())
_operation_write(_receipt)
try:
    result=None
    exec({code!r},globals())
except BaseException:
    _receipt.update(status='FAILED',error=_ot.format_exc(),end_time=_oti.time())
else:
    _receipt.update(result=result,end_time=_oti.time())
    try:
        _receipt.update(scene_snapshot_after=_operation_scene(),status='SUCCEEDED')
        _target={target_path!r}
        if _target and _oo.path.isfile(_target):
            _hash=_oh.sha256()
            with open(_target,'rb') as _stream:
                for _chunk in iter(lambda:_stream.read(1048576),b''): _hash.update(_chunk)
            _receipt['output_sha256']=_hash.hexdigest()
    except Exception:
        _receipt.update(status='UNKNOWN',error=_ot.format_exc())
_operation_write(_receipt)
result=_receipt
'''
    try:
        response=bridge.call('execute_python',{'code':wrapped},timeout=timeout)
    except bridge.BridgeError as exc:
        metadata['transport_error']=exc.as_dict()
        write_json(record_path,metadata)
        return dict(ok=False,operation_id=operation_id,status='UNKNOWN',retry_safe=False,error=exc.as_dict())
    if response.get('error'):
        metadata['runtime_error']=response['error']
        write_json(record_path,metadata)
        return dict(ok=False,operation_id=operation_id,status='UNKNOWN',retry_safe=False,error={'code':'md_exception','message':response['error']})
    return reconcile(operation_id)


def reconcile(operation_id):
    if not isinstance(operation_id,str) or len(operation_id)!=32 or any(c not in '0123456789abcdef' for c in operation_id):
        return dict(ok=False,status='UNKNOWN',error={'code':'invalid_operation_id'},retry_safe=False)
    path=STORE/(operation_id+'.json')
    if not path.is_file():
        return dict(ok=False,status='UNKNOWN',operation_id=operation_id,retry_safe=False,error={'code':'unknown_operation'})
    meta=json.loads(path.read_text(encoding='utf-8'))
    receipt_path=STORE/(operation_id+'.receipt.json')
    receipt=json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.is_file() else None
    status='UNKNOWN'
    evidence=file_evidence(meta['target_path']) if meta.get('target_path') else None
    if receipt and receipt.get('operation_id')==operation_id:
        if receipt['status']=='FAILED':
            status='FAILED'
        elif receipt['status']=='SUCCEEDED':
            status='SUCCEEDED'
            if evidence is not None:
                if not evidence['valid'] or meta['target_before'].get('exists') or receipt.get('output_sha256')!=evidence.get('sha256'):
                    status='UNKNOWN'
    result=receipt.get('result') if receipt else None
    if isinstance(result,dict) and result.get('verified') is False:
        status='UNKNOWN'
    meta.update(status=status,receipt=receipt,file_evidence=evidence)
    write_json(path,meta)
    out=dict(ok=status=='SUCCEEDED',operation_id=operation_id,status=status,retry_safe=False,
             result=result,metadata=meta)
    if status!='SUCCEEDED':
        out['error']=dict(code='operation_'+status.lower(),message=receipt.get('error','Outcome unproven; inspect before retrying') if receipt else 'No completion receipt')
    return out
