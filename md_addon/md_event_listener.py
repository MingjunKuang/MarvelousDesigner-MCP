"""Nonblocking TCP transport, dispatched by a Windows GUI-thread timer.

No worker calls MD APIs and no nested event pump is introduced. Each timer turn
dispatches at most one request. A synchronous MD API still occupies the GUI for
its own duration. Timer callbacks remain rooted until process exit because
KillTimer does not remove already posted WM_TIMER messages.

CLIENT_TIMEOUT bounds how long a peer may take to send a complete request and to
read its response. Once a request is complete it is queued without a deadline,
so a long API call cannot make the requests waiting behind it expire. At most
MAX_QUEUED complete requests may wait; further ones get a "busy" error at once
and are not executed.

When a token is configured, every request (including ping and shutdown) must
carry it in a top-level "token" field; otherwise it is rejected unexecuted.
"""
import ctypes
import hmac
import json
import socket
import sys
import time
import traceback

MAX_REQUEST = 16 * 1024 * 1024
MAX_RESPONSE = 32 * 1024 * 1024
MAX_CLIENTS = 8
MAX_QUEUED = 4
IO_CHUNK = 65536
CLIENT_TIMEOUT = 15
STATE_KEY = '_md_mcp_event_listener'
ROOTS_KEY = '_md_mcp_timer_roots'


class Listener:
    def __init__(self, handlers, host='127.0.0.1', port=7421, token=None):
        self.handlers = handlers
        self.token = token
        self.clients = {}
        self.running = False
        self.busy = False
        self.timer = 0
        self.ticks = 0
        self.calls = 0
        self.last_error = None
        self.owner_thread = None
        self.callback_thread = None
        self.user32 = None
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            self.srv.bind((host, port))
            self.srv.listen(MAX_CLIENTS)
            self.srv.setblocking(False)
        except BaseException:
            self.srv.close()
            raise
        self.running = True

    def status(self):
        return dict(mode='windows_main_thread_timer', running=self.running,
                    owner_thread=self.owner_thread, callback_thread=self.callback_thread,
                    ticks=self.ticks, calls=self.calls, clients=len(self.clients),
                    queued=sum(1 for s in self.clients.values() if s['queued']),
                    auth=self.token is not None, last_error=self.last_error, interval_ms=25)

    def install_timer(self):
        if sys.platform != 'win32':
            raise RuntimeError('GUI listener currently requires Windows')
        from ctypes import wintypes as w
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel32.GetCurrentThreadId.restype = w.DWORD
        self.owner_thread = self.kernel32.GetCurrentThreadId()
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(None, w.HWND, w.UINT, ctypes.c_size_t, w.DWORD)
        self.user32.SetTimer.argtypes = [w.HWND, ctypes.c_size_t, w.UINT, callback_type]
        self.user32.SetTimer.restype = ctypes.c_size_t
        self.user32.KillTimer.argtypes = [w.HWND, ctypes.c_size_t]
        self.user32.KillTimer.restype = w.BOOL

        def on_timer(hwnd, message, timer_id, milliseconds):
            if not self.running or self.busy or timer_id != self.timer:
                return
            self.callback_thread = self.kernel32.GetCurrentThreadId()
            if self.callback_thread != self.owner_thread:
                self.last_error = 'Timer callback changed thread'
                self.stop()
                return
            try:
                self.poll()
            except BaseException:
                # Exceptions must never cross the native callback boundary.
                self.last_error = traceback.format_exc()
                self.stop()

        self.callback = callback_type(on_timer)
        roots = getattr(sys, ROOTS_KEY, None)
        if roots is None:
            roots = []
            setattr(sys, ROOTS_KEY, roots)
        roots.append(self.callback)
        self.timer = self.user32.SetTimer(None, 0, 25, self.callback)
        if not self.timer:
            raise ctypes.WinError(ctypes.get_last_error())

    def close_client(self, conn):
        self.clients.pop(conn, None)
        conn.close()

    def stop(self):
        self.running = False
        if self.timer:
            self.user32.KillTimer(None, self.timer)
            self.timer = 0
        for conn in list(self.clients):
            self.close_client(conn)
        self.srv.close()

    def dispatch(self, line):
        req_id = None
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError('request must be an object')
            req_id = req.get('id')
            if self.token is not None:
                supplied = req.get('token')
                if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), self.token.encode()):
                    return {'id': req_id, 'code': 'unauthorized',
                            'error': 'unauthorized: missing or wrong listener token'}, False
            method = req.get('method')
            params = req.get('params', {})
            if not isinstance(method, str) or not isinstance(params, dict):
                raise ValueError('method must be a string; params must be an object')
            if method == 'shutdown':
                return {'id': req_id, 'result': {'bye': True}}, True
            if method == 'ping':
                return {'id': req_id, 'result': {'pong': True, 'listener': self.status()}}, False
            handler = self.handlers.get(method)
            if handler is None:
                raise ValueError('unknown method: ' + method)
            self.calls += 1
            return {'id': req_id, 'result': handler(params)}, False
        except Exception:
            return {'id': req_id, 'error': traceback.format_exc()}, False

    @staticmethod
    def encode(response):
        try:
            output = (json.dumps(response) + '\n').encode('utf-8')
        except (TypeError, ValueError):
            output = (json.dumps({'id': response.get('id'), 'error': 'Result is not JSON serializable'}) + '\n').encode()
        if len(output) > MAX_RESPONSE:
            output = (json.dumps({'id': response.get('id'), 'error': 'Response exceeds 32 MiB'}) + '\n').encode()
        return output

    def reply(self, state, response):
        state['out'] = self.encode(response)
        state['data'].clear()
        state['queued'] = False
        state['deadline'] = time.monotonic() + CLIENT_TIMEOUT   # time allowed to read the response

    def poll(self):
        if not self.running or self.busy:
            return
        self.busy = True
        self.ticks += 1
        try:
            # Bound work even when peers continuously send data or never read.
            for _ in range(MAX_CLIENTS - len(self.clients)):
                try:
                    conn, _ = self.srv.accept()
                except BlockingIOError:
                    break
                conn.setblocking(False)
                self.clients[conn] = dict(data=bytearray(), out=None, sent=0, queued=False,
                                          deadline=time.monotonic() + CLIENT_TIMEOUT, stop=False)
            dispatched = False
            for conn, state in list(self.clients.items()):
                try:
                    # Read first, check the deadline second: bytes that arrived while an
                    # earlier request in this same tick was running must still count.
                    if state['out'] is None and not state['queued']:
                        chunk = None
                        if b'\n' not in state['data']:
                            try:
                                chunk = conn.recv(IO_CHUNK)
                            except BlockingIOError:
                                pass
                        if chunk == b'':
                            self.close_client(conn)
                            continue
                        if chunk:
                            state['data'].extend(chunk)
                        if len(state['data']) > MAX_REQUEST:
                            self.close_client(conn)
                            continue
                        if b'\n' in state['data']:
                            waiting = sum(1 for s in self.clients.values() if s['queued'])
                            if waiting >= MAX_QUEUED:
                                req_id = None
                                try:
                                    req_id = json.loads(bytes(state['data']).split(b'\n', 1)[0]).get('id')
                                except Exception:
                                    pass
                                self.reply(state, {'id': req_id, 'code': 'busy', 'error':
                                                   'listener busy: %d requests already queued; not executed' % waiting})
                            else:
                                # Complete request: wait for its turn without a deadline.
                                state['queued'] = True
                                state['deadline'] = None
                    if state['deadline'] is not None and time.monotonic() > state['deadline']:
                        stop = state['stop']
                        self.close_client(conn)
                        if stop:
                            self.stop()
                            return
                        continue
                    if state['queued'] and not dispatched:
                        response, state['stop'] = self.dispatch(bytes(state['data']).split(b'\n', 1)[0])
                        dispatched = True
                        self.reply(state, response)
                    if state['out'] is not None:
                        start = state['sent']
                        try:
                            state['sent'] += conn.send(state['out'][start:start + IO_CHUNK])
                        except BlockingIOError:
                            pass
                        if state['sent'] == len(state['out']):
                            self.close_client(conn)
                            if state['stop']:
                                self.stop()
                                return
                except OSError:
                    self.close_client(conn)
                    if state['stop']:
                        self.stop()
                        return
        finally:
            self.busy = False


def start(handlers, host='127.0.0.1', port=7421, token=None):
    previous = getattr(sys, STATE_KEY, None)
    if previous is not None and previous.running:
        return previous.status()
    listener = Listener(handlers, host, port, token)
    try:
        listener.install_timer()
    except BaseException:
        listener.stop()
        raise
    setattr(sys, STATE_KEY, listener)
    return listener.status()
