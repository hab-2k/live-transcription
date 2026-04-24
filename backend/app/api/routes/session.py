import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket

from app.core.config import settings
from app.contracts.session import CoachingPauseRequest, SessionConfig
from app.services.audio.device_service import DeviceService
from app.services.audio.sounddevice_capture import SoundDeviceCaptureService
from app.services.coaching.llm_client import OpenAICompatibleClient
from app.services.coaching.nudge_service import NudgeService
from app.services.coaching.prompt_builder import PromptBuilder
from app.services.coaching.rule_engine import RuleEngine
from app.services.coaching.summary_service import SummaryService
from app.services.debug.debug_store import DebugStore
from app.services.diarization.noop_diarizer import NoopDiarizer
from app.services.events.broadcaster import broadcaster
from app.services.session_manager import SessionManager
from app.services.transcription.registry import build_provider

router = APIRouter()
PERSONA_DIR = Path("backend/config/personas")
RULES_PATH = Path("backend/config/rules/default.yaml")
logger = logging.getLogger(__name__)

device_service = DeviceService()


def build_prompt_builder(persona: str) -> PromptBuilder:
    path = PERSONA_DIR / f"{persona}.yaml"
    if not path.is_file():
        raise ValueError(f"Unknown persona: {persona}")
    return PromptBuilder.from_file(path)


def build_llm_client(config: SessionConfig) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key or None,
        timeout=settings.llm_timeout,
    )

session_manager = SessionManager(
    capture_service=SoundDeviceCaptureService(),
    provider=build_provider(provider_name=settings.default_asr_provider, settings=settings),
    broadcaster=broadcaster,
    device_service=device_service,
    diarizer=NoopDiarizer(),
    rule_engine=RuleEngine.from_file(RULES_PATH),
    prompt_builder_factory=build_prompt_builder,
    llm_client_factory=build_llm_client,
    nudge_service=NudgeService(),
    summary_service=SummaryService(),
    debug_store=DebugStore(),
)


@router.get("/api/devices")
def list_devices() -> list[dict[str, str]]:
    logger.info("list_devices requested")
    return [{"id": d.id, "label": d.label, "kind": d.kind} for d in device_service.list_devices()]


@router.post("/api/sessions", status_code=201)
async def start_session(config: SessionConfig) -> dict[str, str]:
    logger.info(
        "start_session requested: capture_mode=%s persona=%s microphone=%s asr_provider=%s",
        config.capture_mode,
        config.persona,
        config.microphone_device_id,
        config.asr_provider,
    )
    try:
        session_id = await session_manager.start_session(config)
    except FileNotFoundError as exc:
        logger.warning("start_session failed: nemo model is not configured")
        raise HTTPException(
            status_code=503,
            detail=(
                "NeMo is not configured. Set LTD_NEMO_MODEL_PATH to the local .nemo file "
                "before starting a session."
            ),
        ) from exc
    except ValueError as exc:
        logger.warning("start_session failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("start_session completed: session_id=%s", session_id)
    return {"session_id": session_id}


@router.post("/api/sessions/{session_id}/pause-coaching")
async def pause_coaching(session_id: str, request: CoachingPauseRequest) -> dict[str, str]:
    logger.info("pause_coaching requested: session_id=%s paused=%s", session_id, request.paused)
    try:
        status = await session_manager.set_coaching_paused(session_id, paused=request.paused)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc

    logger.info("pause_coaching completed: session_id=%s status=%s", session_id, status)
    return {"status": status, "session_id": session_id}


@router.post("/api/sessions/{session_id}/stop")
async def stop_session(session_id: str) -> dict[str, object]:
    logger.info("stop_session requested: session_id=%s", session_id)
    summary = await session_manager.stop_session(session_id)
    logger.info("stop_session completed: session_id=%s summary_present=%s", session_id, summary is not None)
    return {
        "status": "stopped",
        "session_id": session_id,
        "summary": summary.model_dump() if summary is not None else None,
    }


@router.websocket("/api/sessions/{session_id}/events")
async def session_events(websocket: WebSocket, session_id: str) -> None:
    logger.info("session_events websocket connect requested: session_id=%s", session_id)
    await broadcaster.connect(session_id, websocket)
