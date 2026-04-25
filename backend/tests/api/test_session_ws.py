import logging
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.routes.session import session_manager
from app.main import app
from app.services.audio.device_service import DeviceService, AudioDevice
from app.services.audio.system_audio_provider import SystemAudioProviderStatus, SystemAudioTarget
from app.services.coaching.summary_service import CallSummary
from tests.fakes.fake_capture import FakeCapture
from tests.fakes.fake_provider import FakeProvider

fake_device_service = DeviceService(devices=[
    AudioDevice(id="Built-in Microphone", label="Built-in Microphone", kind="input"),
])


class SummaryLLMClient:
    async def complete(self, *, prompt: str) -> dict[str, str]:
        return {
            "message": """
            {
              "recap": "The customer called about a payment query.",
              "strengths": ["Polite opening."],
              "weaknesses": ["Could have confirmed the resolution more clearly."],
              "flagged_moments": ["The caller ended the call without a firm resolution."]
            }
            """
        }


def test_start_session_returns_session_id() -> None:
    client = TestClient(app)

    with (
        patch("app.api.routes.session.session_manager.capture_service", FakeCapture()),
        patch("app.api.routes.session.session_manager.device_service", fake_device_service),
        patch("app.api.routes.session.session_manager.provider", FakeProvider()),
    ):
        response = client.post(
            "/api/sessions",
            json={
                "capture_mode": "mic_only",
                "microphone_device_id": "Built-in Microphone",
                "persona": "colleague_contact",
                "coaching_profile": "empathy",
                "asr_provider": "nemo",
            },
        )

    assert response.status_code == 201
    assert "session_id" in response.json()


def test_system_audio_route_returns_status_and_targets() -> None:
    client = TestClient(app)

    class FakeSystemAudioProvider:
        def get_status(self) -> SystemAudioProviderStatus:
            return SystemAudioProviderStatus(
                provider="screen_capture_kit",
                state="available",
                message="Ready to capture system audio.",
            )

        def list_targets(self) -> list[SystemAudioTarget]:
            return [
                SystemAudioTarget(
                    id="screen_capture_kit:1234",
                    name="Microsoft Teams",
                    kind="application",
                    metadata={"pid": 1234},
                )
            ]

    with patch("app.api.routes.session.system_audio_provider", FakeSystemAudioProvider()):
        response = client.get("/api/system-audio")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "screen_capture_kit",
        "state": "available",
        "message": "Ready to capture system audio.",
        "targets": [
            {
                "id": "screen_capture_kit:1234",
                "name": "Microsoft Teams",
                "kind": "application",
                "icon_hint": None,
            }
        ],
    }


def test_request_system_audio_permission_returns_updated_status() -> None:
    client = TestClient(app)

    class FakeSystemAudioProvider:
        def request_permission(self) -> SystemAudioProviderStatus:
            return SystemAudioProviderStatus(
                provider="screen_capture_kit",
                state="available",
                message="Ready to capture system audio.",
            )

        def list_targets(self) -> list[SystemAudioTarget]:
            return [
                SystemAudioTarget(
                    id="screen_capture_kit:system",
                    name="Entire system audio",
                    kind="system",
                )
            ]

    with patch("app.api.routes.session.system_audio_provider", FakeSystemAudioProvider()):
        response = client.post("/api/system-audio/request-permission")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "screen_capture_kit",
        "state": "available",
        "message": "Ready to capture system audio.",
        "targets": [
            {
                "id": "screen_capture_kit:system",
                "name": "Entire system audio",
                "kind": "system",
                "icon_hint": None,
            }
        ],
    }


def test_start_session_passes_nested_transcription_config_to_session_manager() -> None:
    client = TestClient(app)
    captured: dict[str, object] = {}

    async def fake_start_session(config) -> str:  # noqa: ANN001
        captured.update(config.model_dump())
        return "session-123"

    with (
        patch("app.api.routes.session.session_manager.capture_service", FakeCapture(frames=[])),
        patch("app.api.routes.session.session_manager.device_service", fake_device_service),
        patch("app.api.routes.session.session_manager.provider", FakeProvider()),
        patch("app.api.routes.session.session_manager.start_session", side_effect=fake_start_session),
    ):
        response = client.post(
            "/api/sessions",
            json={
                "capture_mode": "mic_only",
                "microphone_device_id": "Built-in Microphone",
                "persona": "colleague_contact",
                "coaching_profile": "empathy",
                "asr_provider": "parakeet_unified",
                "transcription": {
                    "provider": "parakeet_unified",
                    "latency_preset": "balanced",
                    "segmentation": {"policy": "source_turns"},
                    "coaching": {"window_policy": "finalized_turns"},
                    "vad": {
                        "provider": "silero_vad",
                        "threshold": 0.5,
                        "min_silence_ms": 600,
                    },
                },
            },
        )

    assert response.status_code == 201
    assert captured.get("transcription", {}).get("provider") == "parakeet_unified"


def test_start_session_logs_request_details(caplog) -> None:  # noqa: ANN001
    client = TestClient(app)
    caplog.set_level(logging.INFO)

    with (
        patch("app.api.routes.session.session_manager.capture_service", FakeCapture()),
        patch("app.api.routes.session.session_manager.device_service", fake_device_service),
        patch("app.api.routes.session.session_manager.provider", FakeProvider()),
    ):
        response = client.post(
            "/api/sessions",
            json={
                "capture_mode": "mic_only",
                "microphone_device_id": "Built-in Microphone",
                "persona": "colleague_contact",
                "coaching_profile": "empathy",
                "asr_provider": "nemo",
            },
        )

    assert response.status_code == 201
    assert "start_session requested" in caplog.text
    assert "capture_mode=mic_only" in caplog.text
    assert "persona=colleague_contact" in caplog.text


def test_start_session_returns_service_unavailable_when_nemo_model_is_unconfigured() -> None:
    class MissingModelProvider:
        name = "nemo"

        async def start(self, *, emit_event) -> None:  # noqa: ANN001
            raise FileNotFoundError(
                "NeMo model path does not exist or is not a file: <unset>"
            )

    client = TestClient(app)

    with (
        patch("app.api.routes.session.session_manager.capture_service", FakeCapture(frames=[])),
        patch("app.api.routes.session.session_manager.device_service", fake_device_service),
        patch("app.api.routes.session.session_manager.provider", MissingModelProvider()),
    ):
        response = client.post(
            "/api/sessions",
            json={
                "capture_mode": "mic_only",
                "microphone_device_id": "Built-in Microphone",
                "persona": "colleague_contact",
                "coaching_profile": "empathy",
                "asr_provider": "nemo",
            },
        )

    assert response.status_code == 503
    assert "LTD_NEMO_MODEL_PATH" in response.json()["detail"]


def test_start_session_returns_service_unavailable_when_parakeet_model_is_unconfigured() -> None:
    class MissingModelProvider:
        name = "parakeet_unified"

        async def start(self, *, emit_update=None, emit_event=None) -> None:  # noqa: ANN001
            raise FileNotFoundError("Parakeet model path does not exist or is not a file: <unset>")

        async def push_audio(self, *, source: str, pcm, sample_rate: int) -> None:  # noqa: ANN001
            return None

        async def stop(self) -> None:
            return None

    client = TestClient(app)

    with (
        patch("app.api.routes.session.session_manager.capture_service", FakeCapture(frames=[])),
        patch("app.api.routes.session.session_manager.device_service", fake_device_service),
        patch("app.api.routes.session.session_manager.provider", MissingModelProvider()),
    ):
        response = client.post(
            "/api/sessions",
            json={
                "capture_mode": "mic_only",
                "microphone_device_id": "Built-in Microphone",
                "persona": "colleague_contact",
                "coaching_profile": "empathy",
                "asr_provider": "parakeet_unified",
                "transcription": {
                    "provider": "parakeet_unified",
                    "latency_preset": "balanced",
                    "segmentation": {"policy": "fixed_lines"},
                    "coaching": {"window_policy": "finalized_turns"},
                    "vad": {
                        "provider": "silero_vad",
                        "threshold": 0.5,
                        "min_silence_ms": 700,
                    },
                },
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Parakeet model not found. Select a model in the transcription settings."


def test_session_websocket_accepts_connections() -> None:
    client = TestClient(app)

    with client.websocket_connect("/api/sessions/test-session/events") as socket:
        socket.send_text("ping")


def test_stop_session_returns_backend_summary() -> None:
    client = TestClient(app)

    with (
        patch("app.api.routes.session.session_manager.capture_service", FakeCapture()),
        patch("app.api.routes.session.session_manager.device_service", fake_device_service),
        patch("app.api.routes.session.session_manager.provider", FakeProvider()),
        patch("app.api.routes.session.session_manager.summary_llm_client", SummaryLLMClient()),
    ):
        start_response = client.post(
            "/api/sessions",
            json={
                "capture_mode": "mic_only",
                "microphone_device_id": "Built-in Microphone",
                "persona": "colleague_contact",
                "coaching_profile": "empathy",
                "asr_provider": "nemo",
            },
        )
        session_id = start_response.json()["session_id"]

        stop_response = client.post(f"/api/sessions/{session_id}/stop")

    assert stop_response.status_code == 200
    assert stop_response.json() == {
        "status": "stopped",
        "session_id": session_id,
        "summary": CallSummary(
            recap="The customer called about a payment query.",
            strengths=["Polite opening."],
            weaknesses=["Could have confirmed the resolution more clearly."],
            flagged_moments=["The caller ended the call without a firm resolution."],
        ).model_dump(),
    }


def test_pause_coaching_route_returns_session_state() -> None:
    client = TestClient(app)

    with (
        patch("app.api.routes.session.session_manager.capture_service", FakeCapture(frames=[])),
        patch("app.api.routes.session.session_manager.device_service", fake_device_service),
        patch("app.api.routes.session.session_manager.provider", FakeProvider()),
    ):
        start_response = client.post(
            "/api/sessions",
            json={
                "capture_mode": "mic_only",
                "microphone_device_id": "Built-in Microphone",
                "persona": "colleague_contact",
                "coaching_profile": "empathy",
                "asr_provider": "nemo",
            },
        )
        session_id = start_response.json()["session_id"]

        pause_response = client.post(
            f"/api/sessions/{session_id}/pause-coaching",
            json={"paused": True},
        )

    assert pause_response.status_code == 200
    assert pause_response.json() == {"status": "coaching_paused", "session_id": session_id}


def test_transcription_config_route_restarts_only_transcription_pipeline() -> None:
    class RestartableProvider:
        name = "fake"

        def __init__(self) -> None:
            self.start_calls = 0
            self.stop_calls = 0

        async def start(self, *, emit_update=None, emit_event=None) -> None:  # noqa: ANN001
            self.start_calls += 1

        async def push_audio(self, *, source: str, pcm, sample_rate: int) -> None:  # noqa: ANN001
            return None

        async def stop(self) -> None:
            self.stop_calls += 1

    client = TestClient(app)
    provider = RestartableProvider()

    with (
        patch("app.api.routes.session.session_manager.capture_service", FakeCapture(frames=[])),
        patch("app.api.routes.session.session_manager.device_service", fake_device_service),
        patch("app.api.routes.session.session_manager.provider", provider),
    ):
        start_response = client.post(
            "/api/sessions",
            json={
                "capture_mode": "mic_only",
                "microphone_device_id": "Built-in Microphone",
                "persona": "colleague_contact",
                "coaching_profile": "empathy",
                "asr_provider": "parakeet_unified",
            },
        )
        session_id = start_response.json()["session_id"]

        reconfigure_response = client.post(
            f"/api/sessions/{session_id}/transcription-config",
            json={
                "provider": "parakeet_unified",
                "latency_preset": "balanced",
                "segmentation": {"policy": "source_turns"},
                "coaching": {"window_policy": "finalized_turns"},
                "vad": {
                    "provider": "silero_vad",
                    "threshold": 0.5,
                    "min_silence_ms": 600,
                },
            },
        )

    assert reconfigure_response.status_code == 200
    assert provider.start_calls == 2
    assert provider.stop_calls == 1


def test_start_session_uses_transcription_provider_selection() -> None:
    class NamedProvider:
        def __init__(self, name: str) -> None:
            self.name = name
            self.start_calls = 0

        async def start(self, *, emit_update=None, emit_event=None) -> None:  # noqa: ANN001
            self.start_calls += 1

        async def push_audio(self, *, source: str, pcm, sample_rate: int) -> None:  # noqa: ANN001
            return None

        async def stop(self) -> None:
            return None

    client = TestClient(app)
    providers = {
        "parakeet_unified": NamedProvider("parakeet_unified"),
        "nemo": NamedProvider("nemo"),
    }

    with (
        patch("app.api.routes.session.session_manager.capture_service", FakeCapture(frames=[])),
        patch("app.api.routes.session.session_manager.device_service", fake_device_service),
        patch("app.api.routes.session.session_manager.provider", None),
        patch.object(
            session_manager,
            "provider_factory",
            side_effect=lambda provider_name, model="": providers[provider_name],
            create=True,
        ),
    ):
        response = client.post(
            "/api/sessions",
            json={
                "capture_mode": "mic_only",
                "microphone_device_id": "Built-in Microphone",
                "persona": "colleague_contact",
                "coaching_profile": "empathy",
                "asr_provider": "nemo",
                "transcription": {
                    "provider": "parakeet_unified",
                    "latency_preset": "balanced",
                    "segmentation": {"policy": "source_turns"},
                    "coaching": {"window_policy": "finalized_turns"},
                    "vad": {
                        "provider": "silero_vad",
                        "threshold": 0.5,
                        "min_silence_ms": 600,
                    },
                },
            },
        )

    assert response.status_code == 201
    assert providers["parakeet_unified"].start_calls == 1
    assert providers["nemo"].start_calls == 0
