"""Hands-free voice-turn helper for Layer 3.

Plays an AI utterance through Web Speech, then auto-arms st.audio_input,
runs in-browser Voice Activity Detection on the candidate's mic, and
auto-clicks the recorder's stop button when the candidate goes silent for
~1.5 seconds. The candidate only needs to grant mic permission once at the
start of the call - after that, the entire interview is hands-free.

Architecture notes
------------------
* No custom Streamlit component, no WebRTC. We instrument the native
  st.audio_input widget by clicking its DOM buttons - same pattern as
  recording_cap.py.
* The JS holds its own MediaStream via getUserMedia for VAD analysis.
  This is separate from the stream st.audio_input opens for the actual
  recording - they happen to point at the same physical mic but are
  independent AudioContext graphs.
* TTS plays BEFORE the recorder is armed. We wait for utter.onend before
  clicking record, so the AI's voice doesn't bleed into the candidate's
  recording (assuming reasonable speaker/mic separation - headphones
  recommended in the call intro).
* Hard safety cap at 90s per turn even if VAD never fires.

Public API
----------
render_voice_turn(ai_text, mic_key) - call once per page render in the
in-call view. Speaks ai_text, returns the audio file delivered by
st.audio_input when the turn completes.
"""

from __future__ import annotations

import json
import uuid
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components


def render_voice_turn(
    ai_text: str,
    mic_key: str,
    *,
    silence_ms: int = 1500,
    hard_cap_seconds: int = 90,
    voice_hint: str = "en",
) -> Optional[object]:
    """Render one AI-speak + candidate-answer turn. Returns the audio file or None.

    Sequence:
      1. The candidate's audio_input widget is rendered (idle / waiting).
      2. A components.html block speaks ai_text via Web Speech.
      3. On utterance end, JS programmatically clicks the recorder's start
         button. Then it asks getUserMedia for its own VAD stream.
      4. VAD watches RMS level. Once the level stays below threshold for
         silence_ms, JS clicks the recorder's stop button.
      5. Streamlit's audio_input delivers the file to Python on the next
         rerun and this function returns it.
    """
    audio_input_kwargs = {
        "key": mic_key,
        "label_visibility": "collapsed",
    }
    try:
        audio_file = st.audio_input(
            "Microphone",
            sample_rate=16000,
            **audio_input_kwargs,
        )
    except TypeError:
        # Older Streamlit without sample_rate kwarg.
        audio_file = st.audio_input("Microphone", **audio_input_kwargs)

    _render_drive_script(
        ai_text=ai_text,
        silence_ms=silence_ms,
        hard_cap_seconds=hard_cap_seconds,
        voice_hint=voice_hint,
    )
    return audio_file


def render_silent_turn(
    ai_text: str,
    *,
    voice_hint: str = "en",
) -> None:
    """Speak ai_text without arming a recorder. Used for the closer."""
    _render_drive_script(
        ai_text=ai_text,
        silence_ms=0,
        hard_cap_seconds=0,
        voice_hint=voice_hint,
        speak_only=True,
    )


def _render_drive_script(
    *,
    ai_text: str,
    silence_ms: int,
    hard_cap_seconds: int,
    voice_hint: str,
    speak_only: bool = False,
) -> None:
    """Inject the JS that speaks the AI line and drives VAD on the recorder."""
    safe_text = json.dumps(ai_text)
    safe_lang = json.dumps(voice_hint)
    uid = uuid.uuid4().hex[:8]
    speak_only_flag = "true" if speak_only else "false"
    silence_ms_js = json.dumps(int(silence_ms))
    cap_ms_js = json.dumps(int(hard_cap_seconds) * 1000)

    component_html = f"""
    <div style="margin:4px 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13px;color:#94a3b8;">
      <span id="vc_status_{uid}">&nbsp;</span>
    </div>
    <script>
    (function() {{
      const TEXT = {safe_text};
      const LANG = {safe_lang};
      const SPEAK_ONLY = {speak_only_flag};
      const SILENCE_MS = {silence_ms_js};
      const HARD_CAP_MS = {cap_ms_js};
      const statusEl = document.getElementById("vc_status_{uid}");

      let parentDoc;
      try {{ parentDoc = window.parent.document; }}
      catch (e) {{
        if (statusEl) statusEl.textContent = "Voice drive unavailable - use the mic manually.";
        return;
      }}

      function setStatus(msg) {{ if (statusEl) statusEl.textContent = msg; }}

      function findRecorderButton() {{
        const buttons = parentDoc.querySelectorAll('button[data-testid="stAudioInputActionButton"]');
        if (buttons.length === 0) {{
          return parentDoc.querySelector('button[aria-label*="ecord"]');
        }}
        for (const b of buttons) {{
          const label = (b.getAttribute("aria-label") || "").toLowerCase();
          if (label.includes("stop")) return b;
        }}
        return buttons[0];
      }}

      function isRecording(btn) {{
        if (!btn) return false;
        const label = (btn.getAttribute("aria-label") || "").toLowerCase();
        return label.includes("stop");
      }}

      function pickVoice() {{
        const voices = window.speechSynthesis.getVoices();
        if (!voices || voices.length === 0) return null;
        const preferred = [
          "Google US English",
          "Microsoft Aria Online (Natural) - English (United States)",
          "Microsoft Jenny Online (Natural) - English (United States)",
          "Samantha", "Alex", "Karen", "Daniel"
        ];
        for (const name of preferred) {{
          const v = voices.find(v => v.name === name);
          if (v) return v;
        }}
        return voices.find(v => v.lang && v.lang.startsWith(LANG)) || voices[0];
      }}

      function speakThen(cb) {{
        if (!("speechSynthesis" in window)) {{
          setStatus("Voice playback not supported.");
          if (cb) cb();
          return;
        }}
        window.speechSynthesis.cancel();
        const utter = new SpeechSynthesisUtterance(TEXT);
        const v = pickVoice();
        if (v) utter.voice = v;
        utter.lang = LANG;
        utter.rate = 0.98;
        utter.pitch = 1.0;
        utter.onstart = () => setStatus("Interviewer speaking...");
        utter.onend   = () => {{ setStatus(""); if (cb) cb(); }};
        utter.onerror = () => {{ setStatus(""); if (cb) cb(); }};
        if (window.speechSynthesis.getVoices().length === 0) {{
          window.speechSynthesis.addEventListener(
            "voiceschanged",
            () => window.speechSynthesis.speak(utter),
            {{ once: true }}
          );
          setTimeout(() => {{ try {{ window.speechSynthesis.speak(utter); }} catch (e) {{}} }}, 400);
        }} else {{
          window.speechSynthesis.speak(utter);
        }}
      }}

      if (SPEAK_ONLY) {{ speakThen(null); return; }}

      let audioCtx = null;
      let analyser = null;
      let dataArray = null;
      let micStream = null;
      let belowSinceMs = null;
      let recordingStartedMs = null;
      let pollId = null;
      let armed = false;

      function stopVad() {{
        if (pollId) {{ clearInterval(pollId); pollId = null; }}
        try {{ if (audioCtx) audioCtx.close(); }} catch (e) {{}}
        try {{ if (micStream) micStream.getTracks().forEach(t => t.stop()); }} catch (e) {{}}
        audioCtx = null; analyser = null; dataArray = null; micStream = null;
      }}

      function clickStop() {{
        const btn = findRecorderButton();
        if (btn && isRecording(btn)) btn.click();
        stopVad();
      }}

      function startVad() {{
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
          setStatus("Mic API unavailable.");
          return;
        }}
        navigator.mediaDevices.getUserMedia({{
          audio: {{ echoCancellation: true, noiseSuppression: true, autoGainControl: true }}
        }}).then(function(stream) {{
          micStream = stream;
          audioCtx = new (window.AudioContext || window.webkitAudioContext)();
          const src = audioCtx.createMediaStreamSource(stream);
          analyser = audioCtx.createAnalyser();
          analyser.fftSize = 512;
          analyser.smoothingTimeConstant = 0.4;
          src.connect(analyser);
          dataArray = new Uint8Array(analyser.fftSize);
          recordingStartedMs = Date.now();
          belowSinceMs = null;
          // We sample every 100ms. The RMS threshold is calibrated against
          // typical room noise floors. 8 is a sensible floor on the 0-255
          // time-domain scale Web Audio returns (data byte minus 128).
          pollId = setInterval(function() {{
            if (!analyser) return;
            analyser.getByteTimeDomainData(dataArray);
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) {{
              const d = dataArray[i] - 128;
              sum += d * d;
            }}
            const rms = Math.sqrt(sum / dataArray.length);
            const now = Date.now();
            const elapsed = now - recordingStartedMs;
            // Don't auto-stop in the first 1.2s - gives the candidate
            // time to start speaking.
            if (elapsed < 1200) {{ belowSinceMs = null; return; }}
            if (rms < 8) {{
              if (belowSinceMs === null) belowSinceMs = now;
              const quietFor = now - belowSinceMs;
              if (quietFor >= SILENCE_MS) {{ clickStop(); return; }}
              setStatus("Listening - " + Math.max(0, Math.floor((SILENCE_MS - quietFor)/100)/10) + "s of silence");
            }} else {{
              belowSinceMs = null;
              setStatus("Listening...");
            }}
            if (HARD_CAP_MS > 0 && elapsed >= HARD_CAP_MS) {{ clickStop(); }}
          }}, 100);
        }}).catch(function(err) {{
          setStatus("Mic permission denied - tap the recorder to record manually.");
        }});
      }}

      function armRecorder() {{
        if (armed) return;
        armed = true;
        const btn = findRecorderButton();
        if (!btn) {{ setStatus("Recorder not found - retrying..."); setTimeout(armRecorder, 300); return; }}
        // Don't double-arm if the recorder is already in 'stop' state
        // for some reason (stale recording from a previous run).
        if (isRecording(btn)) {{ startVad(); return; }}
        btn.click();
        // Small delay so the click propagates to Streamlit and the mic
        // permission grant (first turn only) resolves before VAD starts.
        setTimeout(startVad, 250);
      }}

      speakThen(armRecorder);
      window.addEventListener("beforeunload", stopVad);
    }})();
    </script>
    """
    components.html(component_html, height=28)
