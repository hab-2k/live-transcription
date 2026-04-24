from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LTD_", env_file=".env", extra="ignore")

    log_level: str = "INFO"
    default_asr_provider: str = "nemo"
    nemo_model_path: str = ""
    nemo_python_executable: str = ""
    nemo_min_audio_secs: float = 1.6
    nemo_decode_hop_secs: float = 1.6
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "local-model"
    llm_api_key: str = ""
    llm_timeout: float = 30.0


settings = Settings()
