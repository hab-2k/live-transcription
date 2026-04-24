import { useEffect, useState, type FormEvent } from "react";

import { getBackendUrl } from "../../lib/api/client";
import type { CaptureMode, Persona, SessionSetup } from "../../lib/state/sessionReducer";

type AudioDevice = { id: string; label: string; kind: string };

type SetupScreenProps = {
  errorMessage?: string | null;
  isStarting?: boolean;
  onStart: (setup: SessionSetup) => void;
};

const BACKEND_URL = getBackendUrl();

export function SetupScreen({ errorMessage = null, isStarting = false, onStart }: SetupScreenProps) {
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${BACKEND_URL}/api/devices`)
      .then((res) => res.json())
      .then((data: AudioDevice[]) => {
        setDevices(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const microphones = devices.filter((d) => d.kind === "input");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const formData = new FormData(event.currentTarget);

    onStart({
      captureMode: formData.get("capture_mode") as CaptureMode,
      persona: formData.get("persona") as Persona,
      microphoneDeviceId: String(formData.get("microphone_device_id") ?? ""),
    });
  }

  return (
    <main className="setup-shell">
      <section className="setup-card">
        <p className="eyebrow">Live coaching demo</p>
        <h1>Start Session</h1>
        <p className="setup-copy">
          Configure the call session and choose the coaching persona. Model and endpoint settings
          are managed in the backend environment.
        </p>
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
            <select defaultValue="mic_plus_blackhole" name="capture_mode">
              <option value="mic_only">Microphone only</option>
              <option value="mic_plus_blackhole">Microphone + BlackHole</option>
            </select>
          </label>

          <label className="field">
            <span>Persona</span>
            <select defaultValue="colleague_contact" name="persona">
              <option value="colleague_contact">Colleague contact</option>
              <option value="manager">Manager</option>
            </select>
          </label>
          <button className="primary-button" type="submit" disabled={loading || isStarting}>
            {isStarting ? "Starting..." : "Start session"}
          </button>
        </form>
      </section>
    </main>
  );
}
