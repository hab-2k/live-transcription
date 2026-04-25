from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LTD_", env_file=".env", extra="ignore")

    log_level: str = "INFO"
    default_asr_provider: str = "parakeet_unified"
    transcription_latency_preset: str = "balanced"
    transcription_segmentation_policy: str = "source_turns"
    transcription_coaching_window_policy: str = "finalized_turns"
    transcription_vad_provider: str = "silero_vad"
    transcription_vad_threshold: float = 0.5
    transcription_vad_min_silence_ms: int = 600
    parakeet_model_path: str = ""
    parakeet_python_executable: str = ""
    parakeet_min_audio_secs: float = 1.6
    parakeet_decode_hop_secs: float = 1.6
    nemo_model_path: str = ""
    nemo_python_executable: str = ""
    nemo_min_audio_secs: float = 1.6
    nemo_decode_hop_secs: float = 1.6
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "local-model"
    llm_api_key: str = ""
    llm_timeout: float = 30.0
    summary_llm_model: str = ""


settings = Settings()
