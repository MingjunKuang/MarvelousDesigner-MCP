import json
import socket
import uuid
import time
from typing import Any

from .config import MD_HOST, MD_PORT, MD_TIMEOUT


class BridgeError(RuntimeError):
    def __init__(self, message, code='bridge_error', **details):
        super().__init__(message)
        self.details = {'code':code, 'message':message, **details}

    def as_dict(self):
        return self.details


def _recv_line(sock: socket.socket) -> bytes:
    buf = bytearray()
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            raise BridgeError("connection closed before response", 'connection_lost', outcome='unknown', retry_safe=False)
        buf.extend(chunk)
        if len(buf) > 32 * 1024 * 1024:
            raise BridgeError('response exceeds 32 MiB', 'protocol_error')
    return bytes(buf).split(b"\n", 1)[0]


def call(method: str, params: dict[str, Any] | None = None, *, timeout: float | None = None) -> Any:
    """Send a JSON request to the MD listener and return the result.

    Wire format: one JSON object per line.
    Request:  {"id": str, "method": str, "params": dict}
    Response: {"id": str, "result": any} or {"id": str, "error": str}
    """
    payload = {
        "id": uuid.uuid4().hex,
        "method": method,
        "params": params or {},
    }
    data = (json.dumps(payload) + "\n").encode("utf-8")

    seconds = MD_TIMEOUT if timeout is None else timeout
    if seconds <= 0:
        raise BridgeError('timeout must be positive', 'invalid_parameter')
    started = time.monotonic()
    phase = 'connect'
    try:
        with socket.create_connection((MD_HOST, MD_PORT), timeout=seconds) as sock:
            phase = 'execute'
            sock.sendall(data)
            line = _recv_line(sock)
    except socket.timeout as e:
        raise BridgeError('MD did not respond within the bridge deadline', 'bridge_timeout',
            phase=phase, timeout_seconds=seconds, elapsed_seconds=time.monotonic()-started,
            outcome='unknown', retry_safe=False,
            possible_causes=['long_running_api', 'modal_deadlock_suspected', 'listener_unresponsive'],
            guidance='Timeout does not cancel execution. Inspect MD before retrying mutations.') from e
    except ConnectionRefusedError as e:
        raise BridgeError('Listener is not accepting connections', 'listener_unavailable',
            possible_causes=['listener_not_started','listener_dead']) from e
    except OSError as e:
        raise BridgeError(str(e), 'connection_lost', phase=phase, outcome='unknown', retry_safe=False) from e

    try:
        resp = json.loads(line.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise BridgeError(f"invalid JSON from listener: {e}") from e

    if not isinstance(resp, dict) or resp.get('id') != payload['id']:
        raise BridgeError('Invalid response envelope or request ID', 'protocol_error')

    if "error" in resp:
        raise BridgeError(str(resp["error"]), 'md_exception')
    return resp.get("result")
