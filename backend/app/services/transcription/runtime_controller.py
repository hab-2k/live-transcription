from __future__ import annotations

from app.contracts.session import SessionConfig, TranscriptionConfig
from app.services.transcription.base import EventSink, TranscriptionProvider
from app.services.transcription.provider_updates import UpdateSink


def resolve_provider_name(config: SessionConfig) -> str:
    if config.transcription is not None and config.transcription.provider:
        return config.transcription.provider
    return config.asr_provider


class TranscriptionRuntimeController:
    async def start(
        self,
        *,
        config: SessionConfig,
        provider: TranscriptionProvider | None,
        provider_factory,
        emit_update: UpdateSink | None,
        emit_event: EventSink | None,
    ) -> TranscriptionProvider:
        active_provider = self._build_provider(
            config=config,
            provider=provider,
            provider_factory=provider_factory,
        )

        try:
            await active_provider.start(
                emit_update=emit_update,
                emit_event=emit_event,
            )
        except TypeError:
            if emit_event is None:
                raise
            await active_provider.start(emit_event=emit_event)

        return active_provider

    async def stop(self, provider: TranscriptionProvider | None) -> None:
        if provider is None:
            return
        await provider.stop()

    async def reconfigure(
        self,
        *,
        current_provider: TranscriptionProvider | None,
        current_config: SessionConfig,
        transcription: TranscriptionConfig,
        provider: TranscriptionProvider | None,
        provider_factory,
        emit_update: UpdateSink | None,
        emit_event: EventSink | None,
    ) -> tuple[TranscriptionProvider, SessionConfig]:
        await self.stop(current_provider)
        next_config = current_config.model_copy(
            update={
                "transcription": transcription,
                "asr_provider": transcription.provider,
            }
        )
        next_provider = await self.start(
            config=next_config,
            provider=provider,
            provider_factory=provider_factory,
            emit_update=emit_update,
            emit_event=emit_event,
        )
        return next_provider, next_config

    def _build_provider(
        self,
        *,
        config: SessionConfig,
        provider: TranscriptionProvider | None,
        provider_factory,
    ) -> TranscriptionProvider:
        if provider is not None:
            return provider

        if provider_factory is None:
            raise ValueError("No transcription provider factory configured")

        model = config.transcription.model if config.transcription else ""
        return provider_factory(resolve_provider_name(config), model)
