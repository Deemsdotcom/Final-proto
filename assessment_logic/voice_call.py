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
* The MediaStream for VAD is requested ONCE per call via getUserMedia
  and cached on window.parent so the browser only prompts for mic
  permission on the first turn. Every subsequent turn's iframe reuses
  the cached stream without re-prompting. The stream is explicitly
  released at end-of-call via release_call_mic().
* st.audio_input opens its own MediaStream when the candidate records.
  That's independent of our VAD stream, but mic permission is already
  granted for the origin so it doesn't re-prompt either.
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
    speak: bool = True,
    turn_id: str = "",
    silence_ms: int = 6000,
    hard_cap_seconds: int = 90,
    voice_hint: str = "en",
) -> Optional[object]:
    """Render one AI-speak + candidate-answer turn. Returns the audio file or None.

    Sequence:
      1. The candidate's audio_input widget is rendered (idle / waiting).
      2. If `speak` is True: a components.html block speaks ai_text via
         Web Speech, then auto-arms the recorder and runs VAD.
         If `speak` is False: the audio_input widget is rendered but no
         JS runs. This is used on the consuming rerun (when the
         candidate's audio has just been delivered to Python and the
         turn is about to advance) so the AI line doesn't replay while
         transcription is in flight.
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

    if speak:
        _render_drive_script(
            ai_text=ai_text,
            silence_ms=silence_ms,
            hard_cap_seconds=hard_cap_seconds,
            voice_hint=voice_hint,
            turn_id=turn_id,
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
    turn_id: str = "",
) -> None:
    """Inject the JS that speaks the AI line and drives VAD on the recorder."""
    safe_text = json.dumps(ai_text)
    safe_lang = json.dumps(voice_hint)
    uid = uuid.uuid4().hex[:8]
    speak_only_flag = "true" if speak_only else "false"
    silence_ms_js = json.dumps(int(silence_ms))
    cap_ms_js = json.dumps(int(hard_cap_seconds) * 1000)
    # turn_id is used by the JS to dedupe: if this turn's TTS has already
    # fired in a prior iframe (Streamlit can briefly leave the old iframe
    # alive during a rerun), the new iframe sees the same turn_id on
    # window.parent.__capLastTurn and bails out instead of speaking again.
    safe_turn_id = json.dumps(turn_id or uid)

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
      const TURN_ID = {safe_turn_id};
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

        // Per-turn idempotency. Streamlit can briefly keep the previous
        // iframe alive while mounting the new one, or re-render the same
        // iframe twice on slow browsers. Without this guard the AI line
        // plays twice (and the recorder gets armed and immediately
        // closed, locking the candidate out). The mark lives on
        // window.parent so it survives iframe re-mounts.
        try {{
          const w = window.parent || window;
          if (TURN_ID && w.__capLastTurn === TURN_ID) {{
            // Already spoken for this turn. Just chain into the callback
            // so the recorder still arms if it hasn't already.
            if (cb) cb();
            return;
          }}
          if (TURN_ID) w.__capLastTurn = TURN_ID;
        }} catch (e) {{ /* same-origin only; ignore */ }}

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

        // Single-fire guard for the voices-loading race. Some browsers fire
        // voiceschanged BEFORE the 400ms fallback timeout - without this
        // both paths would call speak() and the utterance plays twice.
        let speakFired = false;
        const fireSpeak = function() {{
          if (speakFired) return;
          speakFired = true;
          try {{ window.speechSynthesis.speak(utter); }} catch (e) {{}}
        }};

        if (window.speechSynthesis.getVoices().length === 0) {{
          window.speechSynthesis.addEventListener(
            "voiceschanged",
            fireSpeak,
            {{ once: true }}
          );
          setTimeout(fireSpeak, 400);
        }} else {{
          fireSpeak();
        }}
      }}

      if (SPEAK_ONLY) {{ speakThen(null); return; }}

      // The candidate's mic stream is held on window.parent for the full
      // duration of the call, so the browser only asks for microphone
      // permission ONCE - on the first turn - and every subsequent turn
      // reuses it silently. Each turn creates its own short-lived
      // AudioContext / AnalyserNode on top of the cached stream.
      let belowSinceMs = null;
      let recordingStartedMs = null;
      let pollId = null;
      let armed = false;

      function stopVad() {{
        if (pollId) {{ clearInterval(pollId); pollId = null; }}
        // Deliberately do NOT release window.parent.__capMicStream - it
        // stays alive across turns. Release happens at end of call via
        // release_call_mic() from Python.
      }}

      function clickStop() {{
        const btn = findRecorderButton();
        if (btn && isRecording(btn)) btn.click();
        stopVad();
      }}

      function ensureMicStream(cb) {{
        const w = window.parent || window;
        if (w.__capMicStream && w.__capMicStream.active) {{
          cb(w.__capMicStream);
          return;
        }}
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
          setStatus("Mic API unavailable.");
          return;
        }}
        navigator.mediaDevices.getUserMedia({{
          audio: {{ echoCancellation: true, noiseSuppression: true, autoGainControl: true }}
        }}).then(function(stream) {{
          w.__capMicStream = stream;
          cb(stream);
        }}).catch(function(err) {{
          setStatus("Mic permission denied - tap the recorder to record manually.");
        }});
      }}

      function startVad() {{
        ensureMicStream(function(stream) {{
          // Build the AudioContext via window.parent's constructor so it
          // inherits the user-activation state from the original Begin
          // call click. Without this, the second (and later) turns'
          // contexts start 'suspended' and analyser data is all-zero,
          // so VAD never detects speech and the silence timer never
          // resets - exactly the 'didn't restart the 4s window' bug.
          const ParentAC = (window.parent && (window.parent.AudioContext || window.parent.webkitAudioContext)) || window.AudioContext || window.webkitAudioContext;
          const ctx = new ParentAC();
          const src = ctx.createMediaStreamSource(stream);
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 512;
          analyser.smoothingTimeConstant = 0.4;
          src.connect(analyser);
          const dataArray = new Uint8Array(analyser.fftSize);
          // Explicit resume in case the context started suspended.
          try {{ if (ctx.state === 'suspended') ctx.resume(); }} catch (e) {{}}
          recordingStartedMs = Date.now();
          belowSinceMs = null;
          // Sample every 100ms. RMS threshold 8 on the 0-255 time-domain
          // scale (data byte minus 128) is calibrated to typical room
          // noise floors.
          pollId = setInterval(function() {{
            analyser.getByteTimeDomainData(dataArray);
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) {{
              const d = dataArray[i] - 128;
              sum += d * d;
            }}
            const rms = Math.sqrt(sum / dataArray.length);
            const now = Date.now();
            const elapsed = now - recordingStartedMs;
            // Don't auto-stop in the first 2.5s - gives the candidate
            // plenty of time to start speaking.
            if (elapsed < 2500) {{ belowSinceMs = null; return; }}
            if (rms < 5) {{
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


def release_call_mic() -> None:
    """Release the cached MediaStream held on window.parent across turns.

    Call this when the call ends (End call button, transition into the
    closing / scoring / done phases). Without this the browser keeps
    showing 'this tab is using your microphone' even after the candidate
    is done. Also clears __capLastTurn so a re-take of the call starts
    its own per-turn TTS dedupe state.
    """
    components.html(
        "<script>"
        "(function(){"
        "try{"
        "const w=window.parent||window;"
        "if(w.__capMicStream){"
        "w.__capMicStream.getTracks().forEach(function(t){try{t.stop();}catch(e){}});"
        "w.__capMicStream=null;"
        "}"
        "w.__capLastTurn=null;"
        "if(\"speechSynthesis\" in window){window.speechSynthesis.cancel();}"
        "}catch(e){}"
        "})();"
        "</script>",
        height=0,
    )


def prewarm_tts() -> None:
    """Kick the browser's TTS engine so voices are cached by Begin call.

    Renders an invisible components.html block that does three things:
    1. Calls getVoices() to start asynchronous voice loading.
    2. Listens for the voiceschanged event so the browser actually
       commits to loading the voices list (some browsers won't load
       until something subscribes).
    3. Speaks one silent (volume=0) very short utterance which forces
       the speech synthesis pipeline to spin up. The candidate hears
       nothing; the engine is warm when the call starts.

    Call this on every pre-call screen that the candidate sits on
    before clicking Begin call (the Layer 3 intro). Cost: zero API
    calls, less than 1ms of CPU, completely silent to the candidate.
    """
    components.html(
        "<script>"
        "(function(){"
        "try{"
        "if(!('speechSynthesis' in window))return;"
        "const w=window.parent||window;"
        "if(w.__capTtsWarmed)return;"
        "w.__capTtsWarmed=true;"
        "try{window.speechSynthesis.getVoices();}catch(e){}"
        "try{window.speechSynthesis.addEventListener('voiceschanged',function(){},{once:true});}catch(e){}"
        "try{"
        "const u=new SpeechSynthesisUtterance(' ');"
        "u.volume=0;u.rate=10;"
        "window.speechSynthesis.speak(u);"
        "setTimeout(function(){try{window.speechSynthesis.cancel();}catch(e){}},150);"
        "}catch(e){}"
        "}catch(e){}"
        "})();"
        "</script>",
        height=0,
    )
