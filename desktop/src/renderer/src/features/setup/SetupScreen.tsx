import { useEffect, useState, type FormEvent } from "react";

import { getBackendUrl, getSystemAudio } from "../../lib/api/client";
import {
  createDefaultTranscriptionConfig,
  type CaptureMode,
  type Persona,
  type SessionSetup,
} from "../../lib/state/sessionReducer";
import type { SystemAudioAvailability } from "../../lib/types/session";
import { TranscriptionSettingsFields } from "../transcription/TranscriptionSettingsFields";

type AudioDevice = { id: string; label: string; kind: string };

type SetupScreenProps = {
  debugEnabled?: boolean;
  errorMessage?: string | null;
  isStarting?: boolean;
  onStart: (setup: SessionSetup) => void;
};

const BACKEND_URL = getBackendUrl();

export function SetupScreen({
  debugEnabled = false,
  errorMessage = null,
  isStarting = false,
  onStart,
}: SetupScreenProps) {
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [systemAudio, setSystemAudio] = useState<SystemAudioAvailability | null>(null);
  const [selectedTargetId, setSelectedTargetId] = useState("");
  const [loading, setLoading] = useState(true);
  const [captureMode, setCaptureMode] = useState<CaptureMode>("mic_plus_system");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [transcription, setTranscription] = useState(createDefaultTranscriptionConfig("mic_plus_system"));

  useEffect(() => {
    Promise.all([
      fetch(`${BACKEND_URL}/api/devices`)
        .then((res) => res.json())
        .then((data: AudioDevice[]) => setDevices(data)),
      getSystemAudio(BACKEND_URL)
        .then((data) => setSystemAudio(data))
        .catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  const microphones = devices.filter((d) => d.kind === "input");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const formData = new FormData(event.currentTarget);

    onStart({
      captureMode,
      persona: formData.get("persona") as Persona,
      microphoneDeviceId: String(formData.get("microphone_device_id") ?? ""),
      transcription,
      ...(captureMode === "mic_plus_system" &&
        selectedTargetId &&
        systemAudio && {
          systemAudioSelection: {
            provider: systemAudio.provider,
            targetId: selectedTargetId,
          },
        }),
    });
  }

  return (
    <main className="setup-shell">
      <section className="setup-card">
        <p className="eyebrow">Live coaching demo</p>
        {debugEnabled ? (
          <button
            aria-label={advancedOpen ? "Close advanced transcription" : "Advanced transcription"}
            className="menu-button"
            onClick={() => setAdvancedOpen((current) => !current)}
            type="button"
          >
            <span />
            <span />
            <span />
          </button>
        ) : null}
        <h1>Start Session</h1>
        <p className="setup-copy">
          Configure the call session and choose the coaching persona. Model and endpoint settings
          are managed in the backend environment.
        </p>
        {systemAudio?.message ? <p className="setup-copy">{systemAudio.message}</p> : null}
        {errorMessage ? (
          <p className="setup-error" role="alert">
            {errorMessage}
          </p>
        ) : null}

        <form className="setup-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Microphone</span>
            {loading ? (
              <select disabled>
                <option>Loading devices...</option>
              </select>
            ) : (
              <select name="microphone_device_id" defaultValue={microphones[0]?.id}>
                {microphones.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </select>
            )}
          </label>

          <label className="field">
            <span>Capture Mode</span>
            <select
              name="capture_mode"
              onChange={(event) => {
                const nextCaptureMode = event.target.value as CaptureMode;
                setCaptureMode(nextCaptureMode);
                setTranscription((current) => ({
                  ...current,
                  segmentation: createDefaultTranscriptionConfig(nextCaptureMode).segmentation,
                  vad: {
                    ...current.vad,
                    minSilenceMs: createDefaultTranscriptionConfig(nextCaptureMode).vad.minSilenceMs,
                  },
                }));
              }}
              value={captureMode}
            >
              <option value="mic_only">Microphone only</option>
              <option value="mic_plus_system">Microphone + System Audio</option>
            </select>
          </label>

          {captureMode === "mic_plus_system" && (
            <label className="field">
              <span>Target Application</span>
              <select
                name="system_audio_app"
                onChange={(event) => {
                  setSelectedTargetId(event.target.value);
                }}
                value={selectedTargetId}
                disabled={systemAudio?.state !== "available"}
              >
                <option value="">Select an application...</option>
                {systemAudio?.targets.map((app) => (
                  <option key={app.id} value={app.id}>
                    {app.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="field">
            <span>Persona</span>
            <select defaultValue="colleague_contact" name="persona">
              <option value="colleague_contact">Colleague contact</option>
              <option value="manager">Manager</option>
            </select>
          </label>
          {debugEnabled && advancedOpen ? (
            <section aria-label="Advanced transcription settings" className="debug-section">
              <h2>Advanced transcription</h2>
              <p>Developer controls for provider selection, segmentation, and Silero VAD tuning.</p>
              <TranscriptionSettingsFields config={transcription} onChange={setTranscription} />
            </section>
          ) : null}
          <button className="primary-button" type="submit" disabled={loading || isStarting}>
            {isStarting ? "Starting..." : "Start session"}
          </button>
        </form>
      </section>
    </main>
  );
}
