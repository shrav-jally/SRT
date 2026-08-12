#!/usr/bin/env python3
"""Utility script to convert audio file sample rates using Pipecat's resampler."""

import asyncio
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

# Add pipecat to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "pipecat" / "src"))

from pipecat.audio.utils import create_file_resampler


async def convert_audio_sample_rate(input_path: str, output_sample_rates: list[int]):
    """Convert an audio file to different sample rates.

    Args:
        input_path: Path to the input audio file
        output_sample_rates: List of target sample rates to convert to
    """
    input_file = Path(input_path)
    if not input_file.exists():
        print(f"Error: Input file '{input_path}' not found")
        return

    # Load the audio file using soundfile
    print(f"Loading audio file: {input_path}")
    audio_data, original_sample_rate = sf.read(input_path, dtype="int16")

    print(f"Original sample rate: {original_sample_rate} Hz")
    print(f"Shape: {audio_data.shape}")
    print(f"Duration: {len(audio_data) / original_sample_rate:.2f} seconds")

    # Convert to mono if stereo
    if len(audio_data.shape) > 1 and audio_data.shape[1] > 1:
        print("Converting to mono...")
        audio_data = np.mean(audio_data, axis=1).astype(np.int16)

    # Convert numpy array to bytes for resampler
    raw_audio = audio_data.tobytes()

    # Create resampler
    resampler = create_file_resampler()

    # Convert to each target sample rate
    for target_rate in output_sample_rates:
        print(f"\nConverting to {target_rate} Hz...")

        # Resample the audio
        resampled_audio = await resampler.resample(
            raw_audio, original_sample_rate, target_rate
        )

        # Convert bytes back to numpy array
        resampled_data = np.frombuffer(resampled_audio, dtype=np.int16)

        # Generate output filename
        output_name = input_file.stem.replace("24000", str(target_rate))
        if "24000" not in input_file.stem:
            output_name = f"{input_file.stem}-{target_rate}-mono"

        # Save as MP3 using ffmpeg if available, otherwise WAV
        output_path = input_file.parent / f"{output_name}.mp3"
        wav_path = input_file.parent / f"{output_name}.wav"

        # First save as WAV
        sf.write(wav_path, resampled_data, target_rate, subtype="PCM_16")
        print(f"Saved WAV: {wav_path}")


async def main():
    """Main function to convert the office ambience file."""
    input_file = "/Users/abhishekkumar/Projects/dograh/dograh/api/assets/office-ambience-24000-mono.mp3"
    target_rates = [8000, 16000]

    await convert_audio_sample_rate(input_file, target_rates)
    print("\nConversion complete!")


if __name__ == "__main__":
    asyncio.run(main())
