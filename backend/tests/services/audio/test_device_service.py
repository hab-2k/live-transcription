from app.services.audio.device_service import AudioDevice, DeviceService


def test_preflight_rejects_unknown_microphone() -> None:
    service = DeviceService(
        devices=[
            AudioDevice(id="Built-in Microphone", label="Built-in Microphone", kind="input"),
        ]
    )

    result = service.validate_microphone("Missing Mic")

    assert result.is_valid is False
