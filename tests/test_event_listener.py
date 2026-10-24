import importlib.util
import json
from pathlib import Path
import socket
import sys
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('event_listener', Path(__file__).resolve().parents[1] / 'md_addon/md_event_listener.py')
event = importlib.util.module_from_spec(spec)
spec.loader.exec_module(event)


def settle():
    # Let loopback connects and bytes land before the next single poll. Without this a
    # poll can run before the data arrives and the test races (seen intermittently).
    time.sleep(0.03)


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
        settle()
        return conn

    def request(self, method='ping', params=None):
        return self.connect((json.dumps(dict(id='test', method=method, params=params or {})) + '\n').encode())

    def response(self, conn):
        buf = b''
        while b'\n' not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                raise AssertionError('connection closed without a response')
            buf += chunk
        return json.loads(buf)

    def test_idle_and_partial_peer_do_not_block_other_requests(self):
        partial = self.connect(b'{"id":')
        conn = self.request()
        self.listener.poll()
        self.assertTrue(self.response(conn)['result']['pong'])
        self.assertEqual(len(self.listener.clients), 1)
        partial.sendall(b'"partial", "method":"ping"}\n')
        settle()
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
        settle()
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
        settle()
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
        self.assertEqual(self.listener.srv.fileno(), -1)
        # Immediate same-port restart is a Windows bridge guarantee. POSIX
        # retains accepted TCP connections in TIME_WAIT after active close.
        port = self.address[1] if sys.platform == 'win32' else 0
        new = event.Listener({}, port=port)
        new.stop()

    def test_capacity_bound(self):
        for _ in range(event.MAX_CLIENTS):
            self.connect(b'{')
        self.listener.poll()
        self.assertEqual(len(self.listener.clients), event.MAX_CLIENTS)

    def test_queued_request_survives_a_long_call(self):
        # Both requests are complete before the first poll; the first call "takes" longer
        # than CLIENT_TIMEOUT, yet the queued second request must still run.
        first, second = self.request('record', {'n': 1}), self.request('record', {'n': 2})
        self.listener.poll()
        self.assertEqual(len(self.calls), 1)
        later = event.time.monotonic() + event.CLIENT_TIMEOUT * 10
        with patch.object(event.time, 'monotonic', return_value=later):
            self.listener.poll()
        self.assertEqual(self.response(first)['result'], {'n': 1})
        self.assertEqual(self.response(second)['result'], {'n': 2})
        self.assertEqual(len(self.calls), 2)

    def test_request_arriving_during_a_long_call_in_the_same_tick_is_kept(self):
        # Live failure in MD: both connections are accepted in one tick, the first runs
        # longer than CLIENT_TIMEOUT, then the second was expired before being read.
        clock = [event.time.monotonic()]
        def slow(params):
            clock[0] += event.CLIENT_TIMEOUT * 2
            return 'slow done'
        self.listener.handlers['slow'] = slow
        with patch.object(event.time, 'monotonic', side_effect=lambda: clock[0]):
            first = self.request('slow')
            second = self.request('record', {'n': 2})
            self.listener.poll()
            self.listener.poll()
        self.assertEqual(self.response(first)['result'], 'slow done')
        self.assertEqual(self.response(second)['result'], {'n': 2})

    def test_incomplete_request_still_expires_while_others_queue(self):
        partial = self.connect(b'{"id":')
        self.listener.poll()
        later = event.time.monotonic() + event.CLIENT_TIMEOUT + 1
        with patch.object(event.time, 'monotonic', return_value=later):
            self.listener.poll()
        self.assertEqual(len(self.listener.clients), 0)

    def test_full_queue_answers_busy_without_executing(self):
        with patch.object(event, 'MAX_QUEUED', 1):
            clients = [self.request('record', {'n': n}) for n in range(3)]
            self.listener.poll()
            busy = self.response(clients[2])
            self.assertEqual(busy['code'], 'busy')
            self.assertEqual(len(self.calls), 1)
            self.listener.poll()
        self.assertEqual(self.response(clients[0])['result'], {'n': 0})
        self.assertEqual(self.response(clients[1])['result'], {'n': 1})
        self.assertEqual([c['n'] for c in self.calls], [0, 1])

    def test_unserializable_handler_response_recovers(self):
        self.listener.handlers['bad'] = lambda p: {1, 2}
        conn = self.request('bad')
        self.listener.poll()
        self.assertIn('error', self.response(conn))
        conn = self.request()
        self.listener.poll()
        self.assertTrue(self.response(conn)['result']['pong'])


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.listener = event.Listener({'record': lambda p: self.calls.append(p) or p}, port=0, token='s3cret')
        self.address = self.listener.srv.getsockname()
        self.addCleanup(self.listener.stop)

    def ask(self, request):
        conn = socket.create_connection(self.address, timeout=1)
        self.addCleanup(conn.close)
        conn.sendall((json.dumps(request) + '\n').encode())
        settle()
        self.listener.poll()
        buf = b''
        while b'\n' not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                raise AssertionError('connection closed without a response')
            buf += chunk
        return json.loads(buf)

    def test_missing_or_wrong_token_is_rejected_unexecuted(self):
        for token in (None, 'wrong', 123):
            request = dict(id='t', method='record', params={'x': 1})
            if token is not None:
                request['token'] = token
            response = self.ask(request)
            self.assertEqual(response['code'], 'unauthorized')
            self.assertEqual(response['id'], 't')
        self.assertEqual(self.calls, [])

    def test_ping_and_shutdown_need_the_token_too(self):
        self.assertEqual(self.ask(dict(id='p', method='ping'))['code'], 'unauthorized')
        self.assertEqual(self.ask(dict(id='s', method='shutdown'))['code'], 'unauthorized')
        self.assertTrue(self.listener.running)

    def test_correct_token_runs(self):
        response = self.ask(dict(id='ok', method='record', params={'x': 1}, token='s3cret'))
        self.assertEqual(response['result'], {'x': 1})
        self.assertTrue(self.ask(dict(id='p', method='ping', token='s3cret'))['result']['listener']['auth'])


if __name__ == '__main__':
    unittest.main()
