#!/usr/bin/env python3
"""
Download models for the AVA Voice Agent pipeline.

- Creates directory structure: models/stt/, models/llm/, models/vad/
- Downloads Faster Whisper "base" model (caches via faster_whisper)
- Downloads Silero VAD model from torch hub (snakers4/silero-vad)
- Prints instructions for manually downloading Llama 3 8B GGUF
"""

import os
import sys

# Project root is one level up from scripts/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(PROJECT_ROOT, "voice_agent", "models")


def create_directories():
    """Create the model directory structure."""
    print("=" * 60)
    print("Creating Model Directories")
    print("=" * 60)

    dirs = [
        os.path.join(MODELS_DIR, "stt"),
        os.path.join(MODELS_DIR, "llm"),
        os.path.join(MODELS_DIR, "vad"),
    ]

    for d in dirs:
        rel = os.path.relpath(d, PROJECT_ROOT)
        os.makedirs(d, exist_ok=True)
        print(f"  [OK] {rel}/")

    print()


def download_faster_whisper():
    """Download and cache the Faster Whisper 'base' model."""
    print("=" * 60)
    print("Downloading Faster Whisper 'base' Model")
    print("=" * 60)

    try:
        from faster_whisper import WhisperModel
        import numpy as np
        print("  Loading 'base' model (will download if not cached)...")
        print("  This may take a few minutes on first run...")

        model = WhisperModel("base", device="cpu", compute_type="int8")
        # Force a dummy transcription to ensure model is fully loaded
        segments, info = model.transcribe(
            np.zeros(16000, dtype=np.float32),
            language="en",
        )
        # Consume the generator to force actual inference
        _ = list(segments)

        print(f"  [OK] Faster Whisper 'base' model downloaded and cached")
        print(f"  Language detected: {info.language} (p={info.language_probability:.2f})")
    except ImportError:
        print("  [FAIL] faster_whisper not installed -- run install_dependencies.py first")
        return False
    except Exception as e:
        print(f"  [FAIL] Error downloading Faster Whisper model: {e}")
        return False

    print()
    return True


def download_silero_vad():
    """Download Silero VAD model from torch hub."""
    print("=" * 60)
    print("Downloading Silero VAD Model")
    print("=" * 60)

    try:
        import torch
        print("  Loading Silero VAD from torch hub (snakers4/silero-vad)...")
        print("  This may take a few minutes on first run...")

        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )

        # Save to models/vad/
        vad_path = os.path.join(MODELS_DIR, "vad")
        model_path = os.path.join(vad_path, "silero_vad.pt")
        torch.save(model.state_dict(), model_path)
        print(f"  [OK] Silero VAD model saved to: {os.path.relpath(model_path, PROJECT_ROOT)}")

        # Verify it loads
        loaded = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
        print(f"  [OK] Silero VAD model verified (loaded successfully)")

    except ImportError:
        print("  [FAIL] torch not installed -- run install_dependencies.py first")
        return False
    except Exception as e:
        print(f"  [FAIL] Error downloading Silero VAD model: {e}")
        return False

    print()
    return True


def print_llm_instructions():
    """Print manual download instructions for the Llama 3 8B GGUF model."""
    print("=" * 60)
    print("LLM Model -- Manual Download Required")
    print("=" * 60)
    print()
    print("  The Llama 3 8B Instruct GGUF model requires HuggingFace")
    print("  authentication and must be downloaded manually.")
    print()
    print("  Steps:")
    print("  1. Visit: https://huggingface.co/QuantFactory/Meta-Llama-3-8B-Instruct-GGUF")
    print("  2. Accept the Meta Llama 3 license agreement if prompted")
    print("  3. Download: Meta-Llama-3-8B-Instruct.Q4_K_M.gguf")
    print(f"  4. Place it at:  voice_agent/models/llm/Meta-Llama-3-8B-Instruct.Q4_K_M.gguf")
    print()
    print("  Expected path:")
    expected = os.path.join(MODELS_DIR, "llm", "Meta-Llama-3-8B-Instruct.Q4_K_M.gguf")
    print(f"    {os.path.relpath(expected, PROJECT_ROOT)}")
    print()

    if os.path.isfile(expected):
        size_mb = os.path.getsize(expected) / (1024 * 1024)
        print(f"  [OK] Model file already exists ({size_mb:.0f} MB)")
    else:
        print("  [PENDING] Model file not yet downloaded")
    print()


def main():
    print("+" + "=" * 58 + "+")
    print("|        AVA Voice Agent -- Model Downloader              |")
    print("+" + "=" * 58 + "+\n")

    create_directories()
    download_faster_whisper()
    download_silero_vad()
    print_llm_instructions()

    print("=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
