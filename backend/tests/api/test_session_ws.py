import logging
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.audio.device_service import DeviceService, AudioDevice
from tests.fakes.fake_capture import FakeCapture
from tests.fakes.fake_provider import FakeProvider

fake_device_service = DeviceService(devices=[
    AudioDevice(id="Built-in Microphone", label="Built-in Microphone", kind="input"),
])


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
    assert stop_response.json()["status"] == "stopped"
    assert stop_response.json()["summary"]["strengths"]


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
