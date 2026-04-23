"""
1:1 채팅용 Socket.IO 서버 (python-socketio + ASGI).

실행: python chat_server.py  (기본 0.0.0.0:8000 — 같은 네트워크의 다른 PC·휴대폰에서 접속 가능)
기존 웹사이트에서는 socket.io-client(JS)만 로드해 이 서버 URL로 연결하면 됩니다.
연동 시 클라이언트에서 room_id는 "메인 사이트 백엔드가 발급·검증한 값"을 쓰는 것을 권장합니다.
"""

from __future__ import annotations

import socket
from contextlib import asynccontextmanager

try:
    from zeroconf import ServiceInfo
    from zeroconf.asyncio import AsyncZeroconf

    HAS_ZEROCONF = True
except ImportError:  # requirements 설치 전에도 서버는 기동되도록
    HAS_ZEROCONF = False
import os
import re
from pathlib import Path
from typing import Any

import socketio
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse
from starlette.routing import Route

load_dotenv()

_DEFAULT_CHAT_PORT = int(os.getenv("CHAT_PORT", "8000"))

ROOM_PATTERN = re.compile(r"^[a-zA-Z0-9:_\-]{1,128}$")


def _cors_origins() -> str | list[str]:
    raw = os.getenv("CHAT_CORS_ORIGINS", "").strip()
    if not raw:
        return "*"
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts if parts else "*"


def _valid_room(room_id: str) -> bool:
    return bool(room_id and ROOM_PATTERN.match(room_id))


sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=_cors_origins(),
)


@sio.event
async def connect(sid: str, environ: dict, auth: Any) -> bool:
    """
    선택: auth 딕셔너리에 토큰을 넣어 검증할 수 있습니다.
    기존 사이트 세션과 맞추려면 여기서 JWT/세션 쿠키를 검증하세요.
    """
    # 예시: os.getenv("CHAT_CONNECT_SECRET") 과 auth.get("secret") 비교 등
    return True


@sio.event
async def disconnect(sid: str) -> None:
    return None


@sio.event
async def join_room(sid: str, data: dict[str, Any]) -> None:
    room_id = str(data.get("room_id") or "")
    if not _valid_room(room_id):
        await sio.emit("error", {"code": "invalid_room", "message": "room_id 형식이 올바르지 않습니다."}, to=sid)
        return
    await sio.enter_room(sid, room_id)
    await sio.emit("joined", {"room_id": room_id}, to=sid)


@sio.event
async def leave_room(sid: str, data: dict[str, Any]) -> None:
    room_id = str(data.get("room_id") or "")
    if _valid_room(room_id):
        await sio.leave_room(sid, room_id)
        await sio.emit("left", {"room_id": room_id}, to=sid)


@sio.event
async def chat_message(sid: str, data: dict[str, Any]) -> None:
    room_id = str(data.get("room_id") or "")
    text = str(data.get("text") or "").strip()
    if not _valid_room(room_id):
        await sio.emit("error", {"code": "invalid_room", "message": "room_id 형식이 올바르지 않습니다."}, to=sid)
        return
    if not text:
        await sio.emit("error", {"code": "empty_message", "message": "메시지가 비어 있습니다."}, to=sid)
        return
    if len(text) > 8000:
        await sio.emit("error", {"code": "message_too_long", "message": "메시지가 너무 깁니다."}, to=sid)
        return

    if room_id not in sio.manager.get_rooms(sid, "/"):
        await sio.emit("error", {"code": "not_in_room", "message": "먼저 join_room으로 방에 입장해야 합니다."}, to=sid)
        return

    session = await sio.get_session(sid)
    sender_id = (session or {}).get("user_id")
    role = (session or {}).get("role")

    await sio.emit(
        "chat_message",
        {
            "room_id": room_id,
            "text": text,
            "sender_id": sender_id,
            "role": role,
        },
        room=room_id,
        skip_sid=sid,
    )
    await sio.emit(
        "chat_message",
        {
            "room_id": room_id,
            "text": text,
            "sender_id": sender_id,
            "role": role,
            "me": True,
        },
        to=sid,
    )


@sio.event
async def identify(sid: str, data: dict[str, Any]) -> None:
    """
    연결 직후 한 번 호출해 세션에 표시용 정보를 저장합니다.
    운영에서는 토큰 검증 후 user_id/role을 세팅하세요.
    """
    user_id = str(data.get("user_id") or "").strip()
    role = str(data.get("role") or "").strip()
    if not user_id or len(user_id) > 128:
        await sio.emit("error", {"code": "invalid_user", "message": "user_id가 필요합니다."}, to=sid)
        return
    if role not in ("patient", "therapist"):
        await sio.emit("error", {"code": "invalid_role", "message": "role은 patient 또는 therapist 여야 합니다."}, to=sid)
        return
    await sio.save_session(sid, {"user_id": user_id, "role": role})
    await sio.emit("identified", {"user_id": user_id, "role": role}, to=sid)


_BASE = Path(__file__).resolve().parent


def _html(filename: str):
    async def handler(_: Request) -> FileResponse:
        return FileResponse(_BASE / filename, media_type="text/html; charset=utf-8")

    return handler


async def _root_index(request: Request) -> HTMLResponse:
    base = str(request.base_url).rstrip("/")
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>1:1 채팅</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 38rem; margin: 2rem auto; padding: 0 1rem;
            line-height: 1.55; color: #0f172a; background: #f8fafc; }}
    h1 {{ font-size: 1.25rem; margin-bottom: 0.5rem; }}
    p {{ color: #475569; font-size: 0.95rem; margin: 0.65rem 0; }}
    .btns {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1rem 0; }}
    a {{ display: inline-block; padding: 0.5rem 1rem; border-radius: 8px; text-decoration: none;
         font-weight: 600; font-size: 0.9rem; color: #fff; }}
    a.p {{ background: #2563eb; }}
    a.t {{ background: #0d9488; }}
    code {{ background: #e2e8f0; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.85rem; }}
    .hint {{ font-size: 0.82rem; color: #64748b; }}
  </style>
</head>
<body>
  <h1>1:1 채팅</h1>
  <p>같은 Wi‑Fi나 사내망에서 <strong>다른 컴퓨터·휴대폰</strong>으로도 접속하려면, 채팅 서버를
     <code>python chat_server.py</code> 로 실행해 두고 아래 주소를 그 기기 브라우저에 입력하세요.</p>
  <p class="hint">접속이 안 되면 Windows 방화벽에서 이 PC의 포트(기본 8000) 허용이 필요할 수 있습니다.</p>
  <div class="btns">
    <a class="p" href="{base}/preview/patient">환자 화면</a>
    <a class="t" href="{base}/preview/therapist">상담사 화면</a>
  </div>
  <p class="hint">이 서버 주소: <code>{base}/</code></p>
</body>
</html>"""
    return HTMLResponse(html)

def get_local_ip() -> str:
    """내 컴퓨터의 공유기 내부 IP를 자동으로 찾아냅니다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 구글 DNS로 가짜 연결을 맺어 내 IP를 알아내는 꼼수입니다.
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

@asynccontextmanager
async def app_lifespan(app: Starlette):
    """서버가 켜지고 꺼질 때 mDNS 방송을 관리합니다 (비동기 방식)."""
    if not HAS_ZEROCONF:
        yield
        return
    # 일반 Zeroconf 대신 비동기용 AsyncZeroconf 사용
    aio_zc = AsyncZeroconf()
    ip = get_local_ip()
    
    info = ServiceInfo(
        "_http._tcp.local.",
        "ChatApp._http._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=_DEFAULT_CHAT_PORT,
        server="chatserver.local.",
    )
    
    # 비동기(await)로 서비스 등록 (서버 멈춤 방지)
    await aio_zc.async_register_service(info)
    print("=" * 50)
    print(
        "[mDNS] Service registered. Same LAN devices may use: "
        f"http://chatserver.local:{_DEFAULT_CHAT_PORT}"
    )
    print("=" * 50)
    
    yield  # 서버 실행 구간
    
    # 서버 꺼질 때 비동기(await)로 방송 종료
    await aio_zc.async_unregister_service(info)
    await aio_zc.async_close()
    
#_starlette = Starlette(
#    routes=[
#        Route("/", _root_index),
#        Route("/preview/patient", _html("preview_patient.html")),
#        Route("/preview/patient/", _html("preview_patient.html")),
#        Route("/preview/therapist", _html("preview_therapist.html")),
#        Route("/preview/therapist/", _html("preview_therapist.html")),
 #   ]
#)

# 기존 코드:
# _starlette = Starlette(
#     routes=[ ... ]
# )

# 수정할 코드:
_starlette = Starlette(
    routes=[
        Route("/", _root_index),
        Route("/preview/patient", _html("preview_patient.html")),
        Route("/preview/patient/", _html("preview_patient.html")),
        Route("/preview/therapist", _html("preview_therapist.html")),
        Route("/preview/therapist/", _html("preview_therapist.html")),
    ],
    lifespan=app_lifespan  # ★ 여기에 방금 만든 lifespan 함수를 연결합니다.
)

_sio_asgi = socketio.ASGIApp(sio)


def _is_socketio_path(path: str) -> bool:
    p = path if path.endswith("/") else path + "/"
    return p.startswith("/socket.io/")


async def app(scope, receive, send):  # type: ignore[no-untyped-def]
    """
    Socket.IO(/socket.io/*)만 python-socketio로 보내고, 나머지 HTTP는 Starlette로 넘깁니다.
    (한 앱에 묶을 때 경로가 꼬이면서 404가 나는 경우를 피하기 위함입니다.)
    """
    if scope["type"] == "lifespan":
        await _starlette(scope, receive, send)
        return
    if scope["type"] in ("http", "websocket") and _is_socketio_path(scope.get("path") or ""):
        await _sio_asgi(scope, receive, send)
        return
    await _starlette(scope, receive, send)


if __name__ == "__main__":
    import uvicorn

    _host = os.getenv("CHAT_HOST", "0.0.0.0")
    _port = _DEFAULT_CHAT_PORT
    _reload = os.getenv("CHAT_RELOAD", "").lower() in ("1", "true", "yes")
    uvicorn.run("chat_server:app", host=_host, port=_port, reload=_reload)
