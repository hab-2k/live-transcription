import importlib
import importlib.util


def test_mic_only_segmentation_breaks_long_running_text_after_silence() -> None:
    assert importlib.util.find_spec("app.services.transcription.segmentation") is not None

    segmentation = importlib.import_module("app.services.transcription.segmentation")
    policy = segmentation.SegmentationPolicy.for_capture_mode("mic_only")

    assert (
        policy.should_finalize(
            current_text="I can help with that payment today",
            silence_ms=700,
            source="microphone",
        )
        is True
    )


def test_dual_source_segmentation_splits_on_source_change() -> None:
    segmentation = importlib.import_module("app.services.transcription.segmentation")
    policy = segmentation.SegmentationPolicy.for_capture_mode("mic_plus_system")

    assert policy.should_split_on_source_change(current_source="microphone", incoming_source="system") is True
