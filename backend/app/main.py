from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from .machine import ESP32Adapter, SimulationAdapter
from .models import (
    Area,
    FrameResult,
    JobRole,
    LatencyMetric,
    LoginRequest,
    LoginResponse,
    MachineCommand,
    MonitoringSession,
    PPE,
    Preset,
    QualityReport,
    SessionCreate,
    SessionEnd,
    SessionStatus,
    User,
    UserCreate,
    UserPublic,
    UserRole,
    UserUpdate,
)
from .monitoring import MonitoringEngine
from .reports import ReportService
from .security import create_token, decode_token, hash_password, verify_password
from .store import JsonStore
from .vision import VisionService


BASE_DIR = Path(__file__).resolve().parents[1]
STORE_PATH = BASE_DIR / "data" / "store.json"
MODEL_PATH = BASE_DIR / "models" / "best.pt"
FRONTEND_DIST = BASE_DIR.parents[0] / "frontend" / "dist"

store = JsonStore(STORE_PATH)
esp32_base_url = os.getenv("ESP32_BASE_URL", "http://172.22.0.13/").strip()
esp32_timeout = float(os.getenv("ESP32_TIMEOUT_SECONDS", "2.5"))
machine = ESP32Adapter(store, esp32_base_url, esp32_timeout) if esp32_base_url else SimulationAdapter(store)
engine = MonitoringEngine(store, machine)
reports = ReportService(store)
vision = VisionService(MODEL_PATH)

app = FastAPI(title="EPI Guard", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer = HTTPBearer()


@app.on_event("startup")
def startup() -> None:
    vision.load()


def public_user(user: User) -> UserPublic:
    data = user.model_dump(exclude={"password_hash"})
    if not data.get("preset_id"):
        preset = auto_preset_for_user(user)
        if preset:
            data["preset_id"] = preset.id
    return UserPublic.model_validate(data)


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> User:
    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    user = store.get("users", user_id, User)
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Usuário inativo ou inexistente")
    return user


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador")
    return user


def auto_preset_for_user(user: User) -> Preset | None:
    if user.preset_id:
        preset = store.get("presets", user.preset_id, Preset)
        if preset and preset.active:
            return preset
    if user.area_id:
        area = store.get("areas", user.area_id, Area)
        if area and area.preset_id:
            preset = store.get("presets", area.preset_id, Preset)
            if preset and preset.active:
                return preset
    if user.job_role_id:
        job = store.get("job_roles", user.job_role_id, JobRole)
        if job and job.preset_id:
            preset = store.get("presets", job.preset_id, Preset)
            if preset and preset.active:
                return preset
    return None


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "model_ready": vision.ready,
        "model_error": vision.error,
        "model_path": str(MODEL_PATH),
    }


@app.post("/api/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    user = next((item for item in store.list("users", User) if item.username == payload.username), None)
    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    return LoginResponse(access_token=create_token(user.id), user=public_user(user))


@app.get("/api/auth/me", response_model=UserPublic)
def me(user: Annotated[User, Depends(current_user)]) -> UserPublic:
    return public_user(user)


@app.get("/api/ppe", response_model=list[PPE])
def list_ppe(_: Annotated[User, Depends(current_user)]) -> list[PPE]:
    return store.list("ppe", PPE)


@app.get("/api/presets", response_model=list[Preset])
def list_presets(_: Annotated[User, Depends(current_user)]) -> list[Preset]:
    return store.list("presets", Preset)


@app.post("/api/presets", response_model=Preset)
def create_preset(payload: Preset, _: Annotated[User, Depends(require_admin)]) -> Preset:
    store.upsert("presets", payload)
    return payload


@app.get("/api/job-roles", response_model=list[JobRole])
def list_job_roles(_: Annotated[User, Depends(current_user)]) -> list[JobRole]:
    return store.list("job_roles", JobRole)


@app.post("/api/job-roles", response_model=JobRole)
def create_job_role(payload: JobRole, _: Annotated[User, Depends(require_admin)]) -> JobRole:
    store.upsert("job_roles", payload)
    return payload


@app.get("/api/areas", response_model=list[Area])
def list_areas(_: Annotated[User, Depends(current_user)]) -> list[Area]:
    return store.list("areas", Area)


@app.post("/api/areas", response_model=Area)
def create_area(payload: Area, _: Annotated[User, Depends(require_admin)]) -> Area:
    store.upsert("areas", payload)
    return payload


@app.get("/api/users", response_model=list[UserPublic])
def list_users(_: Annotated[User, Depends(require_admin)]) -> list[UserPublic]:
    return [public_user(user) for user in store.list("users", User)]


@app.post("/api/users", response_model=UserPublic)
def create_user(payload: UserCreate, _: Annotated[User, Depends(require_admin)]) -> UserPublic:
    if any(user.username == payload.username for user in store.list("users", User)):
        raise HTTPException(status_code=409, detail="Login já existe")
    user = User(
        name=payload.name,
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        job_role_id=payload.job_role_id,
        area_id=payload.area_id,
        preset_id=payload.preset_id,
        active=payload.active,
    )
    store.upsert("users", user)
    return public_user(user)


@app.patch("/api/users/{user_id}", response_model=UserPublic)
def update_user(
    user_id: str,
    payload: UserUpdate,
    _: Annotated[User, Depends(require_admin)],
) -> UserPublic:
    user = store.get("users", user_id, User)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    values = payload.model_dump(exclude_unset=True)
    if "password" in values:
        values["password_hash"] = hash_password(values.pop("password"))
    user = user.model_copy(update=values)
    store.upsert("users", user)
    return public_user(user)


@app.get("/api/sessions", response_model=list[MonitoringSession])
def list_sessions(user: Annotated[User, Depends(current_user)]) -> list[MonitoringSession]:
    sessions = store.list("sessions", MonitoringSession)
    if user.role == UserRole.admin:
        return sessions
    return [session for session in sessions if session.user_id == user.id]


@app.post("/api/sessions", response_model=MonitoringSession)
def create_session(
    payload: SessionCreate,
    user: Annotated[User, Depends(current_user)],
) -> MonitoringSession:
    preset = auto_preset_for_user(user)
    additional_ppe = payload.additional_ppe if user.role == UserRole.admin else []
    ppe_codes = list(dict.fromkeys([*(preset.ppe_codes if preset else []), *additional_ppe]))
    if not ppe_codes:
        ppe_codes = [item.code for item in store.list("ppe", PPE)]
    session = MonitoringSession(
        user_id=user.id,
        mode=payload.mode,
        preset_id=preset.id if preset else None,
        required_ppe=ppe_codes,
    )
    store.upsert("sessions", session)
    return session


@app.get("/api/sessions/{session_id}", response_model=MonitoringSession)
def get_session(session_id: str, user: Annotated[User, Depends(current_user)]) -> MonitoringSession:
    session = store.get("sessions", session_id, MonitoringSession)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if user.role != UserRole.admin and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Sessão de outro usuário")
    return session


@app.post("/api/sessions/{session_id}/end", response_model=QualityReport)
def end_session(
    session_id: str,
    _: SessionEnd,
    user: Annotated[User, Depends(current_user)],
) -> QualityReport:
    session = get_session(session_id, user)
    session.status = SessionStatus.finished
    session.ended_at = datetime.now(timezone.utc)
    store.upsert("sessions", session)
    return reports.generate(session)


@app.post("/api/sessions/{session_id}/reset-machine", response_model=MachineCommand)
def reset_machine(session_id: str, user: Annotated[User, Depends(current_user)]) -> MachineCommand:
    session = get_session(session_id, user)
    if not session.machine_locked:
        raise HTTPException(status_code=400, detail="Maquinário não está travado")
    if not engine.all_tracks_compliant(session):
        raise HTTPException(status_code=409, detail="Ainda há EPIs ausentes")
    session.machine_locked = False
    store.upsert("sessions", session)
    return machine.reset(session, user.id)


@app.get("/api/reports/{session_id}", response_model=QualityReport)
def get_report(session_id: str, user: Annotated[User, Depends(current_user)]) -> QualityReport:
    session = get_session(session_id, user)
    if session.status == SessionStatus.finished:
        return reports.generate(session)
    existing = next((item for item in store.list("reports", QualityReport) if item.session_id == session.id), None)
    return existing or reports.generate(session)


@app.get("/api/reports/{session_id}/pdf")
def get_report_pdf(session_id: str, user: Annotated[User, Depends(current_user)]) -> Response:
    report = get_report(session_id, user)
    return Response(
        reports.pdf(report),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="relatorio-{session_id}.pdf"'},
    )


@app.get("/api/dashboard")
def dashboard(_: Annotated[User, Depends(require_admin)]) -> dict:
    sessions = store.list("sessions", MonitoringSession)
    commands = store.list("machine_commands", MachineCommand)
    active = [session for session in sessions if session.status == SessionStatus.active]
    latencies = [
        metric.server_total_ms for session in sessions for metric in session.latency_metrics[-20:]
    ]
    return {
        "users": len(store.list("users", User)),
        "active_sessions": len(active),
        "total_sessions": len(sessions),
        "infractions": len(store.data["infractions"]),
        "simulated_cuts": sum(1 for command in commands if command.action == "CUT"),
        "average_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "active": [session.model_dump(mode="json") for session in active],
    }


@app.websocket("/api/ws/inference")
async def inference_ws(
    websocket: WebSocket,
    token: str = Query(...),
    session_id: str = Query(...),
) -> None:
    user_id = decode_token(token)
    user = store.get("users", user_id, User) if user_id else None
    session = store.get("sessions", session_id, MonitoringSession)
    if not user or not session or session.status != SessionStatus.active:
        await websocket.close(code=4401)
        return
    if user.role != UserRole.admin and session.user_id != user.id:
        await websocket.close(code=4403)
        return
    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            latest_session = store.get("sessions", session_id, MonitoringSession)
            if not latest_session or latest_session.status != SessionStatus.active:
                await websocket.close(code=4401)
                return
            session = latest_session
            received_at_ms = time.time() * 1000
            processing_started = time.perf_counter()
            frame_id = str(payload["frame_id"])
            frame = vision.decode(str(payload["image"]))
            ppe_items = [ppe for ppe in store.list("ppe", PPE) if ppe.code in session.required_ppe]
            detections, assignments, inference_ms = vision.infer(session.id, frame, ppe_items)
            tracks = engine.process(session, assignments)
            processing_ms = (time.perf_counter() - processing_started) * 1000 - inference_ms
            server_total_ms = (time.time() * 1000) - received_at_ms
            session.latency_metrics.append(
                LatencyMetric(
                    frame_id=frame_id,
                    captured_at_ms=float(payload.get("captured_at_ms", received_at_ms)),
                    received_at_ms=received_at_ms,
                    inference_ms=inference_ms,
                    processing_ms=max(0, processing_ms),
                    server_total_ms=server_total_ms,
                )
            )
            session.latency_metrics = session.latency_metrics[-500:]
            store.upsert("sessions", session)
            result = FrameResult(
                frame_id=frame_id,
                image_width=int(frame.shape[1]),
                image_height=int(frame.shape[0]),
                detections=detections,
                tracks=tracks,
                machine_locked=session.machine_locked,
                inference_ms=inference_ms,
                processing_ms=max(0, processing_ms),
                server_total_ms=server_total_ms,
                server_sent_at_ms=time.time() * 1000,
            )
            await websocket.send_json(result.model_dump(mode="json"))
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"error": str(exc)})


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")




