"""Executed inside MD's Python. All MD API calls remain on the listener thread."""
import importlib
import inspect
import json
import math
import os
import tempfile
import sys


def index(value, count, label):
    if type(value) is not int or not 0 <= value < count:
        raise ValueError('%s must be an integer in [0, %s)' % (label, count))
    return value


def api(module, name):
    obj=getattr(importlib.import_module(module), name, None)
    if not callable(obj):
        raise NotImplementedError(module+'.'+name+' is unavailable in this runtime')
    return obj


def inspect_api(module, function=None):
    allowed={'pattern_api','fabric_api','utility_api','import_api','export_api','ApiTypes','rest_api'}
    if module not in allowed:
        raise ValueError('Choose an MD API module')
    import utility_api
    out={'module':module,'module_exists':False,'md_version':[utility_api.GetMajorVersion(),utility_api.GetMinorVersion(),utility_api.GetPatchVersion()], 'embedded_python':sys.version}
    try:
        mod=importlib.import_module(module)
    except ImportError:
        return out
    out['module_exists']=True
    names=[function] if function else [n for n in dir(mod) if not n.startswith('_')]
    entries=[]
    for name in names:
        obj=getattr(mod,name,None)
        doc=getattr(obj,'__doc__',None)
        try:
            signature=str(inspect.signature(obj))
        except (ValueError,TypeError):
            signature=None
        entries.append({'function':name,'exists':hasattr(mod,name),'callable':callable(obj),
            'runtime_type':str(type(obj)),'signature':signature,'docstring':doc,
            'overloads':doc if doc and 'Overloaded function' in doc else None})
    out['functions']=entries
    return out


def snapshot():
    import pattern_api as p
    fd,path=tempfile.mkstemp(suffix='.json',prefix='md-mcp-snapshot-')
    os.close(fd)
    try:
        if not p.ExportPatternJSON(path):
            raise RuntimeError('ExportPatternJSON returned false')
        with open(path,encoding='utf-8-sig') as f:
            data=json.load(f)
    finally:
        os.unlink(path)
    patterns=[]
    raw=data.get('PatternList',[])
    # Names, not assumed JSON list order, establish the runtime index mapping.
    for i in range(p.GetPatternCount()):
        name=p.GetPatternPieceName(i)
        matches=[r for r in raw if r.get('Name')==name]
        r=matches[0] if len(matches)==1 else None
        item={'index':i,'name':name,'fabric_index':p.GetPatternPieceFabricIndex(i),
            'world_position_xy':p.GetPatternPiecePos(i),'sewing_groups':p.GetSeamlinePairGroupListInPattern(i),
            'information':json.loads(p.GetPatternInformation(i)), 'geometry_mapping_verified':r is not None}
        if r is not None:
            lines=[]
            for j,line in enumerate(r.get('ShapeInfo',{}).get('LineList',[])):
                lines.append({'line_index':j,'id':line.get('ID'),'points':line.get('PointList',[]),
                    'length_mm':p.GetLineLength(i,j)})
            item.update({'id':r.get('ID'),'lines':lines,'internal_shapes':r.get('InternalLineList',[]),
                'arrangement':r.get('ArrangementPointDataMap'), 'fabric_uuid':r.get('CurrentFabricUUID'),
                'index_basis':'Unique runtime name + ExportPatternJSON line order; validated on straight polygons in MD 2026.0.315'})
        else:
            item['warning']='Duplicate or unmatched names: geometry indices are not mapped'
        patterns.append(item)
    sewings=[]
    for i in range(p.GetSeamlinePairGroupCount()):
        name=p.GetSeamlinePairGroupName(i)
        matches=[s for s in data.get('SeamLinePairGroupList',[]) if s.get('Name')==name]
        r=matches[0] if len(matches)==1 else {}
        pairs=[]
        for pair in r.get('PairList',[]):
            ends=[]
            for key in ['First','Second']:
                end=pair[key]
                owner=next((v for v in patterns if v.get('id')==end.get('ShapeID')),None)
                resolved={'shape_id':end.get('ShapeID'),'direction':end.get('Direction'),
                    'length_parameters':end.get('LengthParam'),'pattern_index':owner['index'] if owner else None,
                    'line_index':None}
                if owner:
                    total=sum(l['length_mm'] for l in owner['lines'])
                    low,high=sorted([end['LengthParam']['fStart'],end['LengthParam']['fEnd']])
                    start=0.0
                    for line in owner['lines']:
                        stop=start+line['length_mm']
                        if total and abs(start/total-low)<1e-5 and abs(stop/total-high)<1e-5:
                            resolved['line_index']=line['line_index']
                        start=stop
                ends.append(resolved)
            pairs.append({'a':ends[0],'b':ends[1]})
        sewings.append({'group_index':i,'name':name,'pairs':pairs,'properties':r,
            'warning':None if r else 'No unique JSON group match'})
    return {'patterns':patterns,'sewings':sewings,'unit':data.get('Unit'),
        'generator':data.get('generator'),'fabrics':data.get('FabricList',[])}


def pattern_info(pattern_index):
    s=snapshot()
    return s['patterns'][index(pattern_index,len(s['patterns']),'pattern_index')]


def points(pattern_index):
    info=pattern_info(pattern_index)
    if not info['geometry_mapping_verified']:
        raise ValueError('Cannot map ambiguous pattern geometry')
    seen=set()
    result=[]
    for line in info['lines']:
        for point in line['points']:
            if point['ID'] not in seen:
                seen.add(point['ID'])
                result.append({'point_index':len(result),**point})
    return {'pattern_index':pattern_index,'points':result,'unit':'mm',
        'index_basis':'ExportPatternJSON traversal; point mutation restricted to straight polygons'}


def create_pattern(vertices, name=None):
    import pattern_api as p
    if not isinstance(vertices,list) or not 3 <= len(vertices) <= 10000:
        raise ValueError('3..10000 points required')
    for v in vertices:
        if len(v)!=3 or type(v[2]) is not int or v[2] not in {0,2,3} or any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) for x in v[:2]):
            raise ValueError('Each point is [finite x_mm, finite y_mm, vertex_type 0/2/3]')
    if len({(v[0],v[1]) for v in vertices})<3:
        raise ValueError('At least three distinct vertices required')
    before=p.GetPatternCount()
    created=p.CreatePatternWithPoints([tuple(v) for v in vertices])
    if p.GetPatternCount()!=before+1 or not 0<=created<p.GetPatternCount():
        raise RuntimeError('Pattern creation verification failed')
    if name is not None:
        p.SetPatternPieceName(created,name)
    return {'verified':True,'pattern':pattern_info(created)}


def move_point(pattern_index, point_index, x, y):
    import pattern_api as p
    before=points(pattern_index)['points']
    index(point_index,len(before),'point_index')
    if any(v['PointType']!='Straight' for v in before):
        raise NotImplementedError('Curve point index mapping is not verified')
    if any(not isinstance(v,(float,int)) or isinstance(v,bool) or not math.isfinite(v) for v in [x,y]):
        raise ValueError('finite x/y required')
    p.MovePatternPoint(pattern_index,point_index,x,y)
    after=points(pattern_index)
    pos=after['points'][point_index]['Position']
    verified=math.isclose(pos['x'],x,abs_tol=1e-4) and math.isclose(pos['y'],y,abs_tol=1e-4)
    if not verified:
        raise RuntimeError('MovePatternPoint result does not match requested coordinates')
    return {'verified':True,**after}


def delete_pattern(pattern_index):
    import pattern_api as p
    before=pattern_info(pattern_index)
    count=p.GetPatternCount()
    p.DeletePatternPiece(pattern_index)
    if p.GetPatternCount()!=count-1:
        raise RuntimeError('Pattern deletion verification failed')
    return {'verified':True,'deleted':before,'pattern_count':p.GetPatternCount()}


def create_sewing(pattern_a, line_a, pattern_b, line_b, direction_a, direction_b):
    import pattern_api as p
    if type(direction_a) is not bool or type(direction_b) is not bool:
        raise ValueError('Explicit boolean directions required')
    for pi,li in [(pattern_a,line_a),(pattern_b,line_b)]:
        info=pattern_info(pi)
        if not info['geometry_mapping_verified']:
            raise ValueError('Ambiguous pattern geometry')
        index(li,len(info['lines']),'line_index')
        if any(v['PointType']!='Straight' for line in info['lines'] for v in line['points']):
            raise NotImplementedError('Dedicated sewing currently requires straight outer edges')
    before=p.GetSeamlinePairGroupCount()
    returned=p.AddSeamlinePairGroup(pattern_a,line_a,pattern_b,line_b,direction_a,direction_b)
    s=snapshot()
    matched=[g for g in s['sewings'] if any(
        pair['a']['pattern_index']==pattern_a and pair['a']['line_index']==line_a and
        pair['b']['pattern_index']==pattern_b and pair['b']['line_index']==line_b and
        pair['a']['direction']==direction_a and pair['b']['direction']==direction_b for pair in g['pairs'])]
    if not returned or len(s['sewings'])!=before+1 or not matched:
        raise RuntimeError('Sewing postcondition failed; inspect scene before retrying')
    return {'verified':True,'sewings':matched}


def assign_fabric(fabric_index, pattern_index, assign_option):
    import fabric_api as f, pattern_api as p
    index(pattern_index,p.GetPatternCount(),'pattern_index')
    index(fabric_index,f.GetFabricCount(False),'fabric_index')
    if assign_option not in {1,2,3}:
        raise ValueError('assign_option: 1=current colorway, 2=all unlinked, 3=all linked')
    returned=f.AssignFabricToPattern(fabric_index,pattern_index,assign_option)
    actual=p.GetPatternPieceFabricIndex(pattern_index)
    if not returned or actual!=fabric_index:
        raise RuntimeError('Fabric assignment verification failed')
    return {'verified':True,'pattern_index':pattern_index,'fabric_index':actual,'assign_option':assign_option}


def simulate(steps):
    import utility_api as u, pattern_api as p
    if type(steps) is not int or not 1<=steps<=100000:
        raise ValueError('steps must be 1..100000')
    returned=u.Simulate(steps)
    if not returned:
        raise RuntimeError('Simulate returned false')
    return {'verified':True,'returned':returned,'steps':steps,'pattern_count':p.GetPatternCount(),
        'quality':u.GetSimulationQuality(), 'verification_scope':'Synchronous API success and post-scene query; physical convergence is not exposed'}


def export_file(path, format, options=None):
    import export_api as e, ApiTypes
    if not os.path.isabs(path) or not os.path.isdir(os.path.dirname(path)):
        raise ValueError('Absolute path with existing parent directory required')
    if os.path.splitext(path)[1].lower() != '.'+format:
        raise ValueError('File extension does not match requested format')
    if os.path.exists(path):
        raise FileExistsError('Choose a new checkpoint filename; existing files are not overwritten')
    if format=='zprj':
        returned=e.ExportZPrjW(path,False)
    else:
        opt=ApiTypes.ImportExportOption()
        if options is None or not {'scale','axisX','axisY','axisZ','bExportGarment','bExportAvatar'} <= set(options):
            raise ValueError('Explicit scale, axisX/Y/Z and garment/avatar selection required')
        for key,value in options.items():
            if key.startswith('_') or not hasattr(opt,key):
                raise ValueError('Unknown runtime ImportExportOption field: '+key)
            current=getattr(opt,key)
            if type(current) not in {bool,int,float,str} or type(value) is not type(current):
                if not (type(current) is float and type(value) in {int,float}):
                    raise ValueError('Wrong option type: '+key)
            if isinstance(value,float) and not math.isfinite(value):
                raise ValueError('Non-finite option: '+key)
            setattr(opt,key,value)
        if opt.scale<=0 or sorted([opt.axisX,opt.axisY,opt.axisZ])!=[0,1,2] or opt.bSaveInZip:
            raise ValueError('Positive scale, a permutation of axes 0/1/2, and unzipped export required')
        returned=getattr(e,'Export'+format.upper()+'W')(path,opt)
    if not returned or not os.path.isfile(path) or os.path.getsize(path)<32:
        raise RuntimeError('Export did not create a nonempty output file')
    return {'verified':True,'path':path,'bytes':os.path.getsize(path),'returned':returned}


def avatar_info():
    import export_api as e, utility_api as u
    return {'count':e.GetAvatarCount(),'names':e.GetAvatarNameListW(),
        'avatars':[{'index':i,'properties':u.GetAvatarProperties(i)} for i in range(e.GetAvatarCount())]}


def import_asset(path, kind, options):
    import import_api as imp, ApiTypes, pattern_api as p, export_api as e
    if not os.path.isabs(path) or not os.path.isfile(path):
        raise ValueError('Existing absolute input path required')
    extensions={'project':{'.zprj'},'garment':{'.zpac'},'avatar':{'.avt','.obj'}}[kind]
    extension=os.path.splitext(path)[1].lower()
    if extension not in extensions:
        raise ValueError('Supported extensions: '+str(sorted(extensions)))
    opt=ApiTypes.ImportZPRJOption() if kind=='project' else ApiTypes.ImportExportOption()
    append_key='bAppend' if kind=='project' else 'bAdd'
    if append_key not in options or type(options[append_key]) is not bool:
        raise ValueError('Explicit '+append_key+' required')
    if not options[append_key] and (p.GetPatternCount() or e.GetAvatarCount()):
        raise ValueError('Replacement import requires an empty scene; checkpoint and clear it separately')
    for key,value in options.items():
        if key.startswith('_') or not hasattr(opt,key):
            raise ValueError('Unknown runtime option: '+key)
        old=getattr(opt,key)
        if type(value) is not type(old) and not (type(old) is float and type(value) in {float,int}):
            raise ValueError('Invalid option type: '+key)
        if type(value) is float and not math.isfinite(value):
            raise ValueError('Nonfinite option')
        setattr(opt,key,value)
    before={'patterns':p.GetPatternCount(),'avatars':e.GetAvatarCount()}
    if kind=='avatar' and extension=='.obj':
        import utility_api as u
        if (u.GetMajorVersion(),u.GetMinorVersion(),u.GetPatchVersion())!=(2026,0,315):
            raise NotImplementedError('OBJ avatar object type mapping requires verification on this MD version')
        if not {'scale','axisX','axisY','axisZ','ImportObjectType'} <= set(options):
            raise ValueError('OBJ avatar requires explicit scale, axes and ImportObjectType=0 (verified on 2026.0.315)')
        if opt.ImportObjectType!=0 or opt.scale<=0 or sorted([opt.axisX,opt.axisY,opt.axisZ])!=[0,1,2]:
            raise ValueError('Invalid OBJ avatar options')
        fn=imp.ImportOBJW
    else:
        fn={'project':imp.ImportZprjW,'garment':imp.ImportZpac,'avatar':imp.ImportAvatar}[kind]
    returned=fn(path,opt)
    after={'patterns':p.GetPatternCount(),'avatars':e.GetAvatarCount()}
    if not returned:
        raise RuntimeError('Import API returned false')
    expected='avatars' if kind=='avatar' else 'patterns'
    verified=after[expected]>before[expected] if options[append_key] else after[expected]>0
    return {'verified':verified,'returned':returned,'before':before,'after':after,
        'verification_scope':'API return and object count; full asset equivalence is not established'}
