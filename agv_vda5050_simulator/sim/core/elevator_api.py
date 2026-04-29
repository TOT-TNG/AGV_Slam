from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional


CommandHandler = Callable[[str, str, dict[str, Any]], dict[str, Any]]
StateHandler = Callable[[Optional[str]], Any]


class ElevatorAPIServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        command_handler: CommandHandler,
        state_handler: StateHandler,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.command_handler = command_handler
        self.state_handler = state_handler
        self.httpd: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.last_error = ''

    @property
    def url(self) -> str:
        return f'http://{self.host}:{self.port}'

    def start(self) -> bool:
        handler = self._build_handler()
        try:
            self.httpd = ThreadingHTTPServer((self.host, self.port), handler)
        except Exception as exc:
            self.last_error = str(exc)
            return False

        self.thread = threading.Thread(target=self.httpd.serve_forever, name='elevator-api', daemon=True)
        self.thread.start()
        self.last_error = ''
        return True

    def stop(self) -> None:
        if self.httpd is None:
            return
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = None

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        command_handler = self.command_handler
        state_handler = self.state_handler

        class Handler(BaseHTTPRequestHandler):
            command_re = re.compile(r'^/elevators/([^/]+)/(call|open-door|close-door|go|release)$')
            state_re = re.compile(r'^/elevators(?:/([^/]+)/state)?$')

            def do_GET(self) -> None:
                match = self.state_re.match(self.path)
                if not match:
                    self._send_json(404, {'error': 'not_found'})
                    return
                try:
                    payload = state_handler(match.group(1))
                except KeyError as exc:
                    self._send_json(404, {'error': str(exc)})
                    return
                self._send_json(200, payload)

            def do_POST(self) -> None:
                match = self.command_re.match(self.path)
                if not match:
                    self._send_json(404, {'error': 'not_found'})
                    return

                try:
                    body = self._read_json()
                    payload = command_handler(match.group(1), match.group(2), body)
                except KeyError as exc:
                    self._send_json(404, {'error': str(exc)})
                    return
                except ValueError as exc:
                    self._send_json(400, {'error': str(exc)})
                    return
                except Exception as exc:
                    self._send_json(500, {'error': str(exc)})
                    return
                self._send_json(200, payload)

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get('Content-Length', '0') or '0')
                if length <= 0:
                    return {}
                raw = self.rfile.read(length).decode('utf-8')
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError('Request body must be a JSON object')
                return payload

            def _send_json(self, status: int, payload: Any) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler
