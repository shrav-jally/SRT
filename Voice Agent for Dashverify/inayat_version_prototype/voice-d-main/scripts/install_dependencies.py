#!/usr/bin/env python3
"""
Install and verify all Python dependencies for the AVA Voice Agent pipeline.

- Checks Python version (requires 3.10+)
- Installs packages from voice_agent/requirements.txt
- Detects CUDA and sets CMAKE_ARGS for llama-cpp-python if available
- Verifies each critical import works after install
- Prints PASS/FAIL summary
- Exits with code 1 if any critical dependency fails
"""

import subprocess
import sys
import importlib
import os
import shutil

# -- Config ----------------------------------------------------------------
REQUIREMENTS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "voice_agent",
    "requirements.txt",
)

CRITICAL_IMPORTS = {
    "faster_whisper": "faster_whisper",
    "kokoro": "kokoro",
    "llama_cpp": "llama_cpp",
    "torch": "torch",
    "soundfile": "soundfile",
}

OPTIONAL_IMPORTS = {
    "groq": "groq",
}


def check_python_version():
    """Ensure Python 3.10+ is running."""
    print("=" * 60)
    print("Python Version Check")
    print("=" * 60)
    major, minor = sys.version_info[:2]
    print(f"  Current: Python {major}.{minor}")

    if major < 3 or (major == 3 and minor < 10):
        print("  [FAIL] Python 3.10+ is required")
        sys.exit(1)

    print("  [PASS] Python 3.10+ detected")
    return True


def detect_cuda():
    """Check if CUDA is available on the system."""
    print("\n" + "=" * 60)
    print("CUDA Detection")
    print("=" * 60)

    # Check for nvidia-smi
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        print("  nvidia-smi found -- CUDA GPU likely available")
        try:
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                print(f"  GPU: {result.stdout.strip()}")
        except Exception:
            pass
        return True

    # Check via torch if already installed
    try:
        import torch
        if torch.cuda.is_available():
            print(f"  torch.cuda.is_available() = True ({torch.cuda.get_device_name(0)})")
            return True
    except ImportError:
        pass

    print("  No CUDA detected -- will use CPU-only builds")
    return False


def install_requirements(cuda_available):
    """Install all packages from requirements.txt."""
    print("\n" + "=" * 60)
    print("Installing Dependencies")
    print("=" * 60)

    if not os.path.isfile(REQUIREMENTS_FILE):
        print(f"  [FAIL] Requirements file not found: {REQUIREMENTS_FILE}")
        sys.exit(1)

    print(f"  Requirements file: {REQUIREMENTS_FILE}")

    # Build pip install command
    cmd = [sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS_FILE]

    # If CUDA is available, reinstall llama-cpp-python with CUDA support
    env = os.environ.copy()
    if cuda_available:
        print("  Setting CMAKE_ARGS for llama-cpp-python CUDA build...")
        env["CMAKE_ARGS"] = "-DGGML_CUDA=on"
        # We'll do a two-pass: first all deps normally, then llama-cpp-python with CUDA
        print("  Phase 1: Installing all dependencies...")
        normal_cmd = [sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS_FILE]
        result = subprocess.run(normal_cmd, env=env)
        if result.returncode != 0:
            print("  [WARN] pip install had errors (non-zero exit), continuing verification...")

        print("  Phase 2: Reinstalling llama-cpp-python with CUDA support...")
        cuda_cmd = [
            sys.executable, "-m", "pip", "install",
            "llama-cpp-python>=0.3.31",
            "--force-reinstall", "--no-cache-dir",
        ]
        result = subprocess.run(cuda_cmd, env=env)
        if result.returncode != 0:
            print("  [WARN] CUDA llama-cpp-python install failed, continuing verification...")
        return

    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        print("  [WARN] pip install had errors (non-zero exit), continuing verification...")


def verify_imports():
    """Verify each critical and optional import works. Return (passed, failed) lists."""
    print("\n" + "=" * 60)
    print("Verifying Imports")
    print("=" * 60)

    passed = []
    failed = []

    for label, module_name in {**CRITICAL_IMPORTS, **OPTIONAL_IMPORTS}.items():
        is_critical = label in CRITICAL_IMPORTS
        try:
            mod = importlib.import_module(module_name)
            version = getattr(mod, "__version__", "unknown")
            print(f"  [PASS] {label:20s} import OK  (v{version})")
            passed.append(label)
        except ImportError as e:
            status = "[FAIL] (critical)" if is_critical else "[WARN] (optional)"
            print(f"  {status}  {label:20s} import FAILED: {e}")
            if is_critical:
                failed.append(label)

    return passed, failed


def print_summary(passed, failed):
    """Print a final PASS/FAIL summary."""
    print("\n" + "=" * 60)
    print("DEPENDENCY SUMMARY")
    print("=" * 60)

    print(f"  Passed: {len(passed)}/{len(CRITICAL_IMPORTS) + len(OPTIONAL_IMPORTS)}")
    for p in passed:
        print(f"    [PASS] {p}")

    if failed:
        print(f"\n  Failed (critical): {len(failed)}")
        for f in failed:
            print(f"    [FAIL] {f}")
        print("\n  [FAIL] INSTALL FAILED -- one or more critical dependencies are missing.")
        sys.exit(1)
    else:
        print("\n  [PASS] ALL CRITICAL DEPENDENCIES PASSED -- ready to proceed.")


def main():
    print("+" + "=" * 58 + "+")
    print("|   AVA Voice Agent -- Dependency Installer & Verifier    |")
    print("+" + "=" * 58 + "+\n")

    check_python_version()
    cuda_available = detect_cuda()
    install_requirements(cuda_available)
    passed, failed = verify_imports()
    print_summary(passed, failed)


if __name__ == "__main__":
    main()
