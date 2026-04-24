import type { TranscriptionConfig } from "../../lib/types/session";

type TranscriptionSettingsFieldsProps = {
  config: TranscriptionConfig;
  onChange: (config: TranscriptionConfig) => void;
};

export function TranscriptionSettingsFields({
  config,
  onChange,
}: TranscriptionSettingsFieldsProps) {
  return (
    <div className="transcription-settings-fields">
      <label className="field">
        <span>Transcription Provider</span>
        <select
          aria-label="Transcription provider"
          onChange={(event) =>
            onChange({
              ...config,
              provider: event.target.value as TranscriptionConfig["provider"],
            })
          }
          value={config.provider}
        >
          <option value="parakeet_unified">Parakeet Unified</option>
          <option value="nemo">NeMo</option>
        </select>
      </label>

      <label className="field">
        <span>Latency Preset</span>
        <select
          aria-label="Latency preset"
          onChange={(event) =>
            onChange({
              ...config,
              latencyPreset: event.target.value as TranscriptionConfig["latencyPreset"],
            })
          }
          value={config.latencyPreset}
        >
          <option value="balanced">Balanced</option>
          <option value="low_latency">Low latency</option>
          <option value="high_accuracy">High accuracy</option>
        </select>
      </label>

      <label className="field">
        <span>Segmentation Policy</span>
        <select
          aria-label="Segmentation policy"
          onChange={(event) =>
            onChange({
              ...config,
              segmentation: {
                policy: event.target.value as TranscriptionConfig["segmentation"]["policy"],
              },
            })
          }
          value={config.segmentation.policy}
        >
          <option value="source_turns">Source turns</option>
          <option value="fixed_lines">Fixed lines</option>
        </select>
      </label>

      <label className="field">
        <span>Coaching Window</span>
        <select
          aria-label="Coaching window"
          onChange={(event) =>
            onChange({
              ...config,
              coaching: {
                windowPolicy: event.target.value as TranscriptionConfig["coaching"]["windowPolicy"],
              },
            })
          }
          value={config.coaching.windowPolicy}
        >
          <option value="finalized_turns">Finalized turns</option>
          <option value="recent_text">Recent text</option>
        </select>
      </label>

      <label className="field">
        <span>VAD Provider</span>
        <select
          aria-label="VAD provider"
          onChange={(event) =>
            onChange({
              ...config,
              vad: {
                ...config.vad,
                provider: event.target.value as TranscriptionConfig["vad"]["provider"],
              },
            })
          }
          value={config.vad.provider}
        >
          <option value="silero_vad">Silero VAD</option>
          <option value="disabled">Disabled</option>
        </select>
      </label>

      <label className="field">
        <span>VAD Threshold</span>
        <input
          aria-label="VAD threshold"
          max="1"
          min="0"
          onChange={(event) =>
            onChange({
              ...config,
              vad: {
                ...config.vad,
                threshold: Number(event.target.value),
              },
            })
          }
          step="0.05"
          type="number"
          value={config.vad.threshold}
        />
      </label>

      <label className="field">
        <span>VAD Minimum Silence</span>
        <input
          aria-label="VAD minimum silence"
          min="0"
          onChange={(event) =>
            onChange({
              ...config,
              vad: {
                ...config.vad,
                minSilenceMs: Number(event.target.value),
              },
            })
          }
          step="50"
          type="number"
          value={config.vad.minSilenceMs}
        />
      </label>
    </div>
  );
}
