import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from marvelous_designer_mcp import bridge

spec = importlib.util.spec_from_file_location('md_listener_mod', Path(__file__).resolve().parents[1] / 'md_addon/md_listener.py')
md_listener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(md_listener)


class FakeSocket:
    """Echoes the request id back with a canned response body."""
    def __init__(self, body):
        self.body, self.sent = body, b''

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def sendall(self, data):
        self.sent += data

    def recv(self, _n):
        if self.body is None:
            return b''
        request = json.loads(self.sent)
        out = (json.dumps(dict(self.body, id=request['id'])) + '\n').encode()
        self.body = None
        return out


class TokenFileTests(unittest.TestCase):
    def test_write_token_creates_fresh_token_file(self):
        with tempfile.TemporaryDirectory() as d:
            first = md_listener.write_token(d)
            self.assertEqual((Path(d) / 'listener.token').read_text(encoding='utf-8'), first)
            second = md_listener.write_token(d)
            self.assertNotEqual(first, second)
            self.assertGreaterEqual(len(second), 40)
            self.assertFalse(list(Path(d).glob('*.tmp')))


class BridgeTokenTests(unittest.TestCase):
    def call_with(self, body, token_file_text=None, env_token=None):
        sock = FakeSocket(body)
        with tempfile.TemporaryDirectory() as d:
            if token_file_text is not None:
                (Path(d) / 'listener.token').write_text(token_file_text, encoding='utf-8')
            env = {k: v for k, v in os.environ.items() if k != 'MD_MCP_TOKEN'}
            if env_token:
                env['MD_MCP_TOKEN'] = env_token
            with patch.object(bridge, 'DATA_DIR', Path(d)), patch.dict(os.environ, env, clear=True), \
                    patch('socket.create_connection', return_value=sock):
                try:
                    return bridge.call('ping'), json.loads(sock.sent)
                except bridge.BridgeError as e:
                    return e, json.loads(sock.sent)

    def test_token_from_file_is_sent(self):
        result, sent = self.call_with({'result': {'pong': True}}, token_file_text='abc\n')
        self.assertEqual(sent['token'], 'abc')
        self.assertEqual(result, {'pong': True})

    def test_env_token_wins(self):
        _, sent = self.call_with({'result': {}}, token_file_text='file', env_token='env')
        self.assertEqual(sent['token'], 'env')

    def test_no_token_file_sends_no_token(self):
        _, sent = self.call_with({'result': {}})
        self.assertNotIn('token', sent)

    def test_unauthorized_and_busy_are_not_executed(self):
        err, _ = self.call_with({'code': 'unauthorized', 'error': 'unauthorized'}, token_file_text='x')
        self.assertEqual(err.details['code'], 'unauthorized')
        self.assertEqual(err.details['outcome'], 'not_executed')
        self.assertTrue(err.details['retry_safe'])
        err, _ = self.call_with({'code': 'busy', 'error': 'busy'}, token_file_text='x')
        self.assertEqual(err.details['code'], 'listener_busy')
        self.assertTrue(err.details['retry_safe'])

    def test_other_errors_unchanged(self):
        err, _ = self.call_with({'error': 'Traceback ...'}, token_file_text='x')
        self.assertEqual(err.details['code'], 'md_exception')


if __name__ == '__main__':
    unittest.main()
