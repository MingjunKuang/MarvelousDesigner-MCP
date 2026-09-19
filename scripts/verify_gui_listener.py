"""Read-only live transport checks. Leaves the GUI listener running."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import statistics
import time
from marvelous_designer_mcp.bridge import call

root = Path(__file__).resolve().parents[1]
results = {'started': time.strftime('%Y-%m-%dT%H:%M:%S')}
results['initial'] = call('ping', timeout=3)
status = results['initial']['listener']
assert status['owner_thread'] == status['callback_thread']
assert status['mode'] == 'windows_main_thread_timer'
code = 'import pattern_api as p, utility_api as u, ctypes\nresult=dict(count=p.GetPatternCount(), project=u.GetProjectName(), thread=ctypes.windll.kernel32.GetCurrentThreadId())'
results['scene_before'] = call('execute_python', {'code': code}, timeout=3)
assert results['scene_before']['error'] is None

with socket.create_connection(('127.0.0.1', 7421), timeout=3) as partial:
    partial.sendall(b'{"method":')
    t = time.monotonic()
    assert call('ping', timeout=3)['pong']
    results['partial_peer_ping_ms'] = (time.monotonic() - t) * 1000
    partial.sendall(b'"ping","id":"partial"}\n')
    results['fragmented_response'] = json.loads(partial.recv(65536))

for raw in [b'bad\n', b'[]\n', b'\xff\n', b'{"method":[]}\n']:
    with socket.create_connection(('127.0.0.1', 7421), timeout=3) as conn:
        conn.sendall(raw)
        assert 'error' in json.loads(conn.recv(65536))
results['malformed_requests'] = 4

def query(n):
    start = time.monotonic()
    response = call('execute_python', {'code': code}, timeout=5)
    assert response['error'] is None, response
    assert response['result'] == results['scene_before']['result'], response
    return (time.monotonic() - start) * 1000

with ThreadPoolExecutor(max_workers=4) as pool:
    latencies = list(pool.map(query, range(100)))
results['concurrent_reads'] = dict(count=100, workers=4, median_ms=statistics.median(latencies), max_ms=max(latencies))
large = call('execute_python', {'code': "result='a'*1048576"}, timeout=5)
assert len(large['result']) == 1048576
results['large_response_bytes'] = len(large['result'])
results['scene_after'] = call('execute_python', {'code': code}, timeout=3)
assert results['scene_after'] == results['scene_before']
results['final'] = call('ping', timeout=3)
assert results['final']['listener']['last_error'] is None
path = root / 'evidence' / 'gui-listener-live.json'
path.write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2))
