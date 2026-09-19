"""Small verified primitives executed on MD's existing main-thread listener."""
import math
from enum import IntEnum


class MaterialFace(IntEnum):
    FRONT=0
    BACK=1
    SIDE=2


def checkpoint_scene():
    import pattern_api as p, fabric_api as f, export_api as e, utility_api as u
    import tempfile,os,json
    fd,path=tempfile.mkstemp(suffix='.json')
    os.close(fd)
    try:
        if not p.ExportPatternJSON(path): raise RuntimeError('Checkpoint geometry query failed')
        with open(path,encoding='utf-8-sig') as stream: raw=json.load(stream)
    finally:
        os.unlink(path)
    def clean(value):
        if isinstance(value,dict): return {k:clean(v) for k,v in value.items() if k!='ID'}
        if isinstance(value,list): return [clean(v) for v in value]
        return value
    shapes={}
    patterns=[]
    for pat in raw['PatternList']:
        shapes[pat['ID']]=[pat['Name'],'outer']
        for ci,child in enumerate(pat.get('InternalLineList',[])):
            shapes[child['ID']]=[pat['Name'],'internal',ci]
        patterns.append(dict(name=pat['Name'],outer=clean(pat['ShapeInfo']),internal=clean(pat.get('InternalLineList',[]))))
    sewings=[]
    for group in raw.get('SeamLinePairGroupList',[]):
        pairs=[]
        for pair in group['PairList']:
            ends=[]
            for key in ['First','Second']:
                end=pair[key]
                ends.append(dict(shape=shapes.get(end['ShapeID']),direction=end['Direction'],range=end['LengthParam']))
            pairs.append(ends)
        sewings.append(pairs)
    return dict(patterns=patterns,sewings=sewings,avatars=e.GetAvatarNameListW(),
        avatar_properties=[u.GetAvatarProperties(i) for i in range(e.GetAvatarCount())],
        fabrics=[dict(name=f.GetFabricName(i),colors=[f.GetFabricPBRMaterialBaseColor(i,j) for j in [0,1,2]]) for i in range(f.GetFabricCount(False))])


def material(fabric_index, face, rgba=None):
    import fabric_api as f, utility_api as u
    if type(fabric_index) is not int or not 0<=fabric_index<f.GetFabricCount(False):
        raise ValueError('Invalid fabric index')
    if (u.GetMajorVersion(),u.GetMinorVersion(),u.GetPatchVersion()) != (2026,0,315):
        raise NotImplementedError('Material face mapping only verified on 2026.0.315')
    face=MaterialFace[face.upper()]
    if rgba is not None:
        if len(rgba)!=4 or any(type(v) not in (float,int) or not math.isfinite(v) or not 0<=v<=1 for v in rgba):
            raise ValueError('RGBA requires four finite values in 0..1')
        if face!=MaterialFace.FRONT:
            f.SetUseSameMaterialAsFront(fabric_index,int(face),False)
            f.SetUseSameColorAsFront(fabric_index,int(face),False)
        if not f.SetFabricPBRMaterialBaseColor(fabric_index,int(face),*rgba):
            raise RuntimeError('Material color API returned false')
    actual=f.GetFabricPBRMaterialBaseColor(fabric_index,int(face))
    if rgba is not None and any(not math.isclose(a,b,abs_tol=1e-5) for a,b in zip(actual,rgba)):
        raise RuntimeError('Material color postcondition failed')
    return dict(verified=True,face=face.name,enum_value=int(face),rgba=actual,
        all_faces={v.name:f.GetFabricPBRMaterialBaseColor(fabric_index,int(v)) for v in MaterialFace},
        linkage={v.name:dict(material=f.GetUseSameMaterialAsFront(fabric_index,int(v)),color=f.GetUseSameColorAsFront(fabric_index,int(v))) for v in [MaterialFace.BACK,MaterialFace.SIDE]})


def placement(pattern_index, offsets=None):
    import pattern_api as p
    if type(pattern_index) is not int or not 0<=pattern_index<p.GetPatternCount():
        raise ValueError('Invalid pattern index')
    before=p.GetArrangementOfPattern(pattern_index)
    if offsets is not None:
        if len(offsets)!=3 or any(type(v) is not int for v in offsets):
            raise ValueError('Three integer arrangement offsets required')
        p.SetArrangementPosition(pattern_index,*offsets)
    after=p.GetArrangementOfPattern(pattern_index)
    if offsets is not None and [float(after['ArrangementOffset'+axis]) for axis in 'XYZ'] != offsets:
        raise RuntimeError('Arrangement offset readback failed')
    return dict(verified=True,before=before,arrangement=after,world_transform=None,
        limitation='Arrangement parameters only; absolute 3D position/rotation API and units are not established')
