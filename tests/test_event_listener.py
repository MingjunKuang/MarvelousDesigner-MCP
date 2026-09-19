import importlib.util
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('event_listener', Path(__file__).resolve().parents[1] / 'md_addon/md_event_listener.py')
event = importlib.util.module_from_spec(spec)
spec.loader.exec_module(event)


class EventListenerTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.listener = event.Listener({'record': lambda p: self.calls.append(p) or p}, port=0)
        self.address = self.listener.srv.getsockname()
        self.addCleanup(self.listener.stop)

    def connect(self, data=b''):
        conn = socket.create_connection(self.address, timeout=1)
        self.addCleanup(conn.close)
        if data:
            conn.sendall(data)
        return conn

    def request(self, method='ping', params=None):
        return self.connect((json.dumps(dict(id='test', method=method, params=params or {})) + '\n').encode())

    def response(self, conn):
        buf = b''
        while b'\n' not in buf:
            buf += conn.recv(65536)
        return json.loads(buf)

    def test_idle_and_partial_peer_do_not_block_other_requests(self):
        partial = self.connect(b'{"id":')
        conn = self.request()
        self.listener.poll()
        self.assertTrue(self.response(conn)['result']['pong'])
        self.assertEqual(len(self.listener.clients), 1)
        partial.sendall(b'"partial", "method":"ping"}\n')
        self.listener.poll()
        self.assertEqual(self.response(partial)['id'], 'partial')

    def test_only_one_dispatch_per_tick(self):
        clients = [self.request('record', {'n': n}) for n in range(4)]
        for n in range(4):
            self.listener.poll()
            self.assertEqual(len(self.calls), n + 1)
        self.assertEqual([self.response(c)['result']['n'] for c in clients], list(range(4)))

    def test_nested_poll_does_not_reenter_handler(self):
        def nested(params):
            self.listener.poll()
            self.assertEqual(len(self.calls), 0)
            return True
        self.listener.handlers['nested'] = nested
        first, second = self.request('nested'), self.request('record')
        self.listener.poll()
        self.assertTrue(self.response(first)['result'])
        self.assertEqual(self.calls, [])
        self.listener.poll()
        self.assertEqual(self.response(second)['result'], {})

    def test_half_closed_peer_preserves_queued_complete_request(self):
        first, second = self.request('record'), self.request('record')
        second.shutdown(socket.SHUT_WR)
        self.listener.poll()
        self.listener.poll()
        self.assertEqual(self.response(first)['result'], {})
        self.assertEqual(self.response(second)['result'], {})
        self.assertEqual(len(self.calls), 2)

    def test_malformed_requests_leave_listener_running(self):
        for raw in [b'bad\n', b'[]\n', b'\xff\n', b'{"method": []}\n', b'{"method":"record","params":[]}\n']:
            conn = self.connect(raw)
            self.listener.poll()
            self.assertIn('error', self.response(conn))
            self.assertTrue(self.listener.running)

    def test_expiration_is_absolute_even_for_slow_sender(self):
        conn = self.connect(b'{')
        self.listener.poll()
        state = next(iter(self.listener.clients.values()))
        state['deadline'] = 0
        conn.sendall(b' ')
        self.listener.poll()
        self.assertEqual(len(self.listener.clients), 0)

    def test_input_limit(self):
        conn = self.connect(b'x' * 100)
        with patch.object(event, 'MAX_REQUEST', 50):
            self.listener.poll()
        self.assertEqual(len(self.listener.clients), 0)

    def test_response_spans_ticks_without_duplicate_execution(self):
        conn = self.request('record', {'value': 'a' * 100})
        with patch.object(event, 'IO_CHUNK', 16):
            for _ in range(30):
                self.listener.poll()
        self.assertEqual(self.response(conn)['result']['value'], 'a' * 100)
        self.assertEqual(len(self.calls), 1)

    def test_disconnect_does_not_kill_listener(self):
        client = self.connect()
        client.close()
        self.listener.poll()
        conn = self.request()
        self.listener.poll()
        self.assertTrue(self.response(conn)['result']['pong'])

    def test_shutdown_closes_partial_connections_and_allows_restart(self):
        self.connect(b'{')
        conn = self.request('shutdown')
        self.listener.poll()
        self.assertTrue(self.response(conn)['result']['bye'])
        self.assertFalse(self.listener.running)
        self.assertFalse(self.listener.clients)
        new = event.Listener({}, port=self.address[1])
        new.stop()

    def test_capacity_bound(self):
        for _ in range(event.MAX_CLIENTS):
            self.connect(b'{')
        self.listener.poll()
        self.assertEqual(len(self.listener.clients), event.MAX_CLIENTS)

    def test_unserializable_handler_response_recovers(self):
        self.listener.handlers['bad'] = lambda p: {1, 2}
        conn = self.request('bad')
        self.listener.poll()
        self.assertIn('error', self.response(conn))
        conn = self.request()
        self.listener.poll()
        self.assertTrue(self.response(conn)['result']['pong'])


if __name__ == '__main__':
    unittest.main()
