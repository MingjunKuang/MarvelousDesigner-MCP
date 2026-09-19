"""Conservative topology mapping; executed in MD alongside runtime_ops."""
import hashlib
import json
import math
import sys
import uuid


class ReferenceError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def state():
    if not hasattr(sys, '_md_agent_topology'):
        sys._md_agent_topology = {'epoch': uuid.uuid4().hex, 'refs': {}}
    return sys._md_agent_topology


def invalidate():
    sys._md_agent_topology = {'epoch': uuid.uuid4().hex, 'refs': {}}


def same_xy(a, b):
    return all(math.isclose(float(a[k]), float(b[k]), abs_tol=1e-4, rel_tol=0) for k in ('x', 'y'))


def runtime_points(info):
    return [dict(runtime_index=int(p['Point index']), position={'x': p['Point positionX'], 'y': p['Point positionY']})
            for p in info.get('PointList', []) if 'Point index' in p]


def map_shape(raw, info):
    """Validate ordered endpoints against native point and line enumerations.

    Curved control points are deliberately excluded from native point indexing.
    Unknown shape types or repeated endpoint coordinates are not guessed.
    """
    lines = raw.get('LineList', [])
    points = runtime_points(info)
    native_lines = [v for v in info.get('LineList', []) if 'Line index' in v]
    if len({line.get('ID') for line in lines})!=len(lines):
        return None
    endpoints = []
    for line in lines:
        if len(line.get('PointList', [])) < 2:
            return None
        for p in (line['PointList'][0], line['PointList'][-1]):
            if not any(q['ID'] == p['ID'] for q in endpoints):
                endpoints.append(p)
    if len(endpoints) != len(points) or len(lines) != len(native_lines):
        return None
    mapping = {}
    for p in endpoints:
        matches = [q for q in points if same_xy(p['Position'], q['position'])]
        if len(matches) != 1:
            return None
        mapping[p['ID']] = matches[0]['runtime_index']
    if len(set(mapping.values())) != len(mapping):
        return None
    for i, line in enumerate(lines):
        if int(native_lines[i]['Line index']) != i:
            return None
        a, b = line['PointList'][0], line['PointList'][-1]
        if mapping[a['ID']] != i or mapping[b['ID']] != ((i + 1) % len(points)):
            return None
        straight = len(line['PointList']) == 2 and all(v['PointType'] == 'Straight' for v in line['PointList'])
        if straight:
            length = math.dist(tuple(a['Position'].values()), tuple(b['Position'].values()))
            if not math.isclose(length, native_lines[i]['Line length'], abs_tol=.01, rel_tol=1e-5):
                return None
    return mapping, native_lines


def build_topology(raw, info, runtime_index, session):
    version = digest({'outer': raw.get('ShapeInfo'), 'internal': raw.get('InternalLineList'), 'closed': raw.get('IsClosed')})
    pid = raw['ID']
    output = dict(pattern_id=pid, pattern_name=raw['Name'], runtime_index=runtime_index,
                  topology_version=version, session_id=session['epoch'], ambiguous=False,
                  outer_boundary=[], internal_lines=[], internal_shapes=[], points=[],
                  raw_runtime_data=info, raw_pattern_data=raw, unit='mm')

    def ref(kind, item_id, child_id=None):
        key = 'mdref:' + digest([session['epoch'], pid, version, kind, child_id, item_id])
        session['refs'][key] = dict(pattern_id=pid, version=version, kind=kind, item_id=item_id, child_id=child_id)
        return key

    def shape(raw_shape, native, child_id=None, child_index=None, closed=True):
        mapped = map_shape(raw_shape, native) if native else None
        edges, points = [], []
        if mapped is None:
            output['ambiguous'] = True
        point_map, native_lines = mapped or ({}, [])
        lines = raw_shape.get('LineList', [])
        for i, line in enumerate(lines):
            controls = line['PointList']
            is_curve = len(controls) > 2 or any(p['PointType'] != 'Straight' for p in controls)
            edge = dict(stable_ref=ref('edge', line['ID'], child_id) if mapped else None,
                        id=line['ID'], runtime_index=i if mapped else None, child_index=child_index,
                        type='curve' if is_curve else 'straight', start_point=controls[0], end_point=controls[-1],
                        length_mm=native_lines[i]['Line length'] if mapped else None,
                        curve_data=controls if is_curve else [], raw=line, ambiguous=mapped is None,
                        adjacency={'previous_id': lines[i-1]['ID'] if i or closed else None,
                                   'next_id': lines[(i+1) % len(lines)]['ID'] if i+1 < len(lines) or closed else None})
            edges.append(edge)
            for p in controls:
                if any(v['id'] == p['ID'] for v in points):
                    continue
                pi = point_map.get(p['ID'])
                points.append(dict(id=p['ID'], position=p['Position'], type=p['PointType'],
                    runtime_index=pi, child_index=child_index, is_control_point=pi is None,
                    stable_ref=ref('point', p['ID'], child_id) if mapped and pi is not None else None,
                    mutable=mapped is not None and pi is not None and child_id is None, raw=p))
        output['points'].extend(points)
        return edges

    output['outer_boundary'] = shape(raw['ShapeInfo'], info, closed=raw.get('IsClosed', True))
    native_children = [x for x in info.get('Children Information', []) if 'Shape index' in x]
    children = raw.get('InternalLineList', [])
    matches = [[n for n in native_children if n.get('Shape type') == 'InnerShape' and map_shape(c, n)] for c in children]
    for c, candidates in zip(children, matches):
        native = candidates[0] if len(candidates) == 1 else None
        if native and sum(any(n['Shape index'] == native['Shape index'] for n in group) for group in matches) != 1:
            native = None
        ci = int(native['Shape index']) if native else None
        edges = shape(c, native, c['ID'], ci, c.get('IsClosed', False))
        obj = dict(id=c['ID'], child_index=ci, closed=c.get('IsClosed'), edges=edges,
                   ambiguous=native is None, raw=c,
                   type='internal_shape' if c.get('IsClosed') else ('internal_curve' if any(e['type']=='curve' for e in edges) else 'internal_line'))
        output['internal_shapes' if c.get('IsClosed') else 'internal_lines'].append(obj)
    return output


def read_topology(pattern):
    import pattern_api as p
    from tempfile import NamedTemporaryFile
    import os
    with NamedTemporaryFile(suffix='.json', delete=False) as f:
        path = f.name
    try:
        if not p.ExportPatternJSON(path):
            raise RuntimeError('Pattern export failed')
        with open(path, encoding='utf-8-sig') as f:
            raw = json.load(f)
    finally:
        os.unlink(path)
    identities = [json.loads(p.GetPatternInformation(i)) for i in range(p.GetPatternCount())]
    if type(pattern) is int:
        candidates = [pattern] if 0 <= pattern < len(identities) else []
    else:
        candidates = [i for i, v in enumerate(identities) if v.get('uuid') == pattern or v.get('name') == pattern]
    if len(candidates) != 1:
        return dict(ambiguous=True, reason='Pattern not uniquely identified', matches=candidates)
    pi = candidates[0]
    matches = [x for x in raw['PatternList'] if x['ID'] == identities[pi].get('uuid')]
    if len(matches) != 1:
        return dict(ambiguous=True, reason='Runtime UUID has no unique JSON match')
    native = json.loads(p.GetPatternInputInformation(pi))['Pattern InputInformation']
    # 2026.0.315 reports local index 0 even when querying runtime pattern 1.
    # The queried UUID plus name and endpoint checks establish identity instead.
    if len(native) != 1 or native[0].get('Pattern name') != identities[pi].get('name'):
        return dict(ambiguous=True, reason='Native pattern enumeration mismatch')
    return build_topology(matches[0], native[0], pi, state())


def resolve(reference, kind):
    record = state()['refs'].get(reference)
    if not record or record['kind'] != kind:
        raise ReferenceError('STALE_REFERENCE: read get_pattern_topology again')
    current = read_topology(record['pattern_id'])
    if current.get('topology_version') != record['version']:
        raise ReferenceError('STALE_REFERENCE: geometry changed; read get_pattern_topology again')
    items = current['points'] if kind == 'point' else current['outer_boundary'] + [e for c in current['internal_lines'] + current['internal_shapes'] for e in c['edges']]
    matches = [v for v in items if v['stable_ref'] == reference]
    if len(matches) != 1 or matches[0]['runtime_index'] is None:
        raise ReferenceError('STALE_REFERENCE: mapping is ambiguous; read get_pattern_topology again')
    return current, matches[0]


def move_reference(reference, x, y):
    import pattern_api as p
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (x,y)):
        raise ValueError('Finite coordinates required')
    before, point = resolve(reference, 'point')
    if not point['mutable']:
        raise NotImplementedError('Internal/control point mutation API is not verified')
    p.MovePatternPoint(before['runtime_index'], point['runtime_index'], x, y)
    after = read_topology(before['pattern_id'])
    found = [v for v in after['points'] if v['id'] == point['id']]
    if len(found) != 1 or not same_xy(found[0]['position'], dict(x=x,y=y)):
        raise RuntimeError('Point postcondition failed; inspect before retrying')
    return dict(verified=True, topology=after)


def sew_references(side_a, side_b, direction_a, direction_b):
    import pattern_api as p
    if type(direction_a) is not bool or type(direction_b) is not bool:
        raise ValueError('Explicit boolean directions required')
    def side(value):
        if isinstance(value, str):
            return resolve(value, 'edge')
        if not isinstance(value,dict) or set(value) - {'edge_ref','range_start','range_end'}:
            raise ValueError('Expected edge_ref with optional full range 0..1')
        if value.get('range_start',0) != 0 or value.get('range_end',1) != 1:
            raise NotImplementedError('Partial/free sewing has no verified runtime API')
        return resolve(value['edge_ref'], 'edge')
    a, ea = side(side_a)
    b, eb = side(side_b)
    if ea['child_index'] is not None and eb['child_index'] is None:
        a,b,ea,eb,direction_a,direction_b=b,a,eb,ea,direction_b,direction_a
    args = [a['runtime_index']]
    if ea['child_index'] is not None: args.append(ea['child_index'])
    args += [ea['runtime_index'], b['runtime_index']]
    if eb['child_index'] is not None: args.append(eb['child_index'])
    args += [eb['runtime_index'], direction_a, direction_b]
    before = p.GetSeamlinePairGroupCount()
    returned = p.AddSeamlinePairGroup(*args)
    if not returned or p.GetSeamlinePairGroupCount() != before+1:
        raise RuntimeError('Sewing postcondition failed; use checkpoint recovery')
    import tempfile, os
    fd,path=tempfile.mkstemp(suffix='.json')
    os.close(fd)
    try:
        if not p.ExportPatternJSON(path):
            raise RuntimeError('Sewing readback export failed')
        with open(path,encoding='utf-8-sig') as f: raw=json.load(f)
    finally:
        os.unlink(path)
    groups=[g for g in raw.get('SeamLinePairGroupList',[]) if g.get('Name')==p.GetSeamlinePairGroupName(before)]
    def expected(top,edge,direction):
        shapes=top['internal_lines']+top['internal_shapes']
        parent=next((s for s in shapes if s['child_index']==edge['child_index']),None) if edge['child_index'] is not None else None
        edges=parent['edges'] if parent else top['outer_boundary']
        total=sum(e['length_mm'] for e in edges)
        start=sum(e['length_mm'] for e in edges[:edge['runtime_index']])/total
        end=start+edge['length_mm']/total
        return parent['id'] if parent else top['pattern_id'],start,end,direction
    def matches(actual,want):
        bounds=sorted(actual['LengthParam'].values())
        return actual['ShapeID']==want[0] and actual['Direction']==want[3] and all(math.isclose(x,y,abs_tol=1e-5) for x,y in zip(bounds,want[1:3]))
    wa,wb=expected(a,ea,direction_a),expected(b,eb,direction_b)
    if len(groups)!=1 or not any(matches(pair['First'],wa) and matches(pair['Second'],wb) for pair in groups[0]['PairList']):
        raise RuntimeError('Sewing shape/range/direction readback failed; restore checkpoint before retrying')
    return dict(verified=True, group_index=before, group_name=p.GetSeamlinePairGroupName(before),
                side_a=ea, side_b=eb, direction_a=direction_a, direction_b=direction_b,
                raw_properties=groups[0],verification_scope='API success, group count, shape IDs, normalized length ranges and directions')
