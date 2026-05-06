"""Quick diagnostic for the Azure transcribe deployment.

Run from the repo root:
    python diagnose_transcribe.py

Reads AZURE_OPENAI_API_KEY from .env or environment, then sends a tiny
synthetic WAV file to the transcribe endpoint to confirm:

  1. The API key is valid
  2. The deployment name (capstone-transcribe) exists
  3. The API version (2025-03-01-preview) is correct
  4. The endpoint can actually accept audio

Prints the response or the exact Azure error.
"""

from __future__ import annotations

import io
import struct
import sys

from assessment_logic.llm_client import (
    CAPSTONE_CONFIG,
    get_client,
    transcribe_audio,
)


def make_silent_wav(duration_seconds: float = 1.5, sample_rate: int = 16000) -> bytes:
    """Build a valid WAV file containing silence. Used as a known-good payload."""
    n_samples = int(duration_seconds * sample_rate)
    data = b"\x00\x00" * n_samples  # 16-bit PCM zeros
    byte_rate = sample_rate * 2
    block_align = 2
    fmt_chunk = struct.pack(
        "<4sIHHIIHH",
        b"fmt ", 16, 1, 1, sample_rate, byte_rate, block_align, 16,
    )
    data_chunk = struct.pack("<4sI", b"data", len(data)) + data
    riff_size = 4 + len(fmt_chunk) + len(data_chunk)
    riff = struct.pack("<4sI4s", b"RIFF", riff_size, b"WAVE")
    return riff + fmt_chunk + data_chunk


def main() -> int:
    print("=" * 60)
    print("CAPSTONE TRANSCRIBE DIAGNOSTIC")
    print("=" * 60)
    print(f"Endpoint:           {CAPSTONE_CONFIG['endpoint']}")
    print(f"API version:        {CAPSTONE_CONFIG['api_version']}")
    print(f"Transcribe deploy:  {CAPSTONE_CONFIG['transcribe_deployment']}")
    print(f"Chat deploy:        {CAPSTONE_CONFIG['chat_deployment']}")
    print()

    try:
        get_client()
        print("✓ Client built successfully (API key present)")
    except Exception as e:
        print(f"✗ Failed to build client: {type(e).__name__}: {e}")
        return 1

    print()
    print("Sending 1.5s of silence to transcribe deployment...")
    wav = make_silent_wav()
    print(f"  WAV payload: {len(wav)} bytes")

    try:
        result = transcribe_audio(wav, filename="diagnostic.wav")
        print(f"✓ Transcribe call succeeded")
        print(f"  Transcript: {result!r}  (empty is expected for silence)")
        print()
        print("If you see this line, the transcribe endpoint is working.")
        print("Any failures inside Streamlit are app-level, not Azure config.")
        return 0
    except Exception as e:
        print(f"✗ Transcribe call failed: {type(e).__name__}")
        print(f"  Error: {e}")
        print()
        print("Common causes:")
        print("  - 401: bad/expired AZURE_OPENAI_API_KEY")
        print("  - 404: capstone-transcribe deployment doesn't exist")
        print("  - 400 unsupported_format on 'messages': API version too old")
        print("  - DNS/network: endpoint unreachable")
        return 1


if __name__ == "__main__":
    sys.exit(main())
