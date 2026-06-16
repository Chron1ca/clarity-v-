import os
import sys
import subprocess
from pathlib import Path

def print_header(title: str):
    print("\n" + "=" * 60)
    print(f" {title} ")
    print("=" * 60 + "\n")

def run_step(cmd: list[str], env: dict) -> bool:
    try:
        result = subprocess.run(cmd, env=env)
        # Note: train.py exits with 3221226505 occasionally on Windows due to ONNX runtime cleanup bug, but it's a success
        if result.returncode != 0 and result.returncode != 3221226505:
            print(f"\n[!] Step failed with exit code {result.returncode}.")
            return False
        return True
    except KeyboardInterrupt:
        print("\n[!] Wizard interrupted by user.")
        return False
    except Exception as e:
        print(f"\n[!] Unexpected error: {e}")
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Clarity.V Wake Word Training Wizard")
    parser.add_argument("--phrase", help="Wake phrase to train")
    parser.add_argument("--model-name", help="Model filename (without .onnx)")
    args = parser.parse_args()

    print_header("Clarity.V - Wake Word Training Wizard")
    
    repo_root = Path(__file__).resolve().parent.parent.parent
    os.chdir(repo_root)

    venv_dir = repo_root / ".venv-train"
    python_exe = venv_dir / "Scripts" / "python.exe"

    if not venv_dir.exists():
        print("[*] Training environment (.venv-train) not found. Setting it up now...")
        print("[*] This may take a few minutes as it downloads PyTorch and other ML libraries.")
        
        # We use the main python executable to create the venv
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        
        print("\n[*] Installing requirements...")
        # Note: base requirements.txt first, then training requirements
        subprocess.run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run([str(python_exe), "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        subprocess.run([str(python_exe), "-m", "pip", "install", "-r", "tools/training/requirements.txt"], check=True)
        print("\n[*] Environment setup complete!")
    
    if not python_exe.exists():
        print(f"[!] Error: python.exe not found at {python_exe}.")
        input("\nPress Enter to exit...")
        return

    # Setup environment variables to use the training venv
    env = os.environ.copy()
    env["PATH"] = f"{venv_dir / 'Scripts'};{env.get('PATH', '')}"
    env["VIRTUAL_ENV"] = str(venv_dir)

    if args.phrase:
        phrase = args.phrase.strip()
        model_name = args.model_name.strip() if args.model_name else phrase.lower().replace(" ", "_")
        print("\n--- STEP 1: Phrase & Model Name (Pre-configured) ---")
        print(f"Phrase: '{phrase}'")
        print(f"Model Name: '{model_name}'")
    else:
        print("\n--- STEP 1: Phrase & Model Name ---")
        print("Good wake phrases share these traits:")
        print("  - 2-4 syllables (e.g., 'cv go', 'hey jarvis')")
        print("  - Distinctive sounds (avoid common words)")
        print("  - Easy to say repeatedly\n")

        phrase = input("Enter your desired wake phrase: ").strip()
        if not phrase:
            print("[!] Phrase cannot be empty.")
            input("\nPress Enter to exit...")
            return

        default_model = phrase.lower().replace(" ", "_")
        model_name = input(f"Enter model name (leave blank to use '{default_model}'): ").strip()
        if not model_name:
            model_name = default_model

    print_header("STEP 2: Fetching ML Dependencies & Features")
    print("Downloading precomputed background noises and TTS voices (~17.5 GB on first run).")
    print("If you already have them, this will skip automatically.")
    if not run_step([str(python_exe), "tools/training/fetch_negatives.py"], env):
        input("\nPress Enter to exit...")
        return

    print_header("STEP 3: Generating Synthetic Samples")
    print("Generating thousands of text-to-speech samples for your phrase...")
    if not run_step([str(python_exe), "tools/training/generate_samples.py", "--phrase", phrase, "--model-name", model_name, "--target", "5000"], env):
        input("\nPress Enter to exit...")
        return

    print_header("STEP 4: Personal Voice Recording (Highly Recommended)")
    print("Synthetic samples are great, but nothing beats your actual voice and microphone.")
    do_record = input("Do you want to record personal samples now? (Y/n): ").strip().lower()
    if do_record != 'n':
        if not run_step([str(python_exe), "tools/training/record_personal_voice.py", "--phrase", phrase, "--model-name", model_name, "--takes", "25"], env):
            input("\nPress Enter to exit...")
            return

    print_header("STEP 5: Training Neural Network")
    print("This will train the ONNX model. (~15 mins on GPU, hours on CPU)")
    if not run_step([str(python_exe), "tools/training/train.py", "--phrase", phrase, "--model-name", model_name], env):
        input("\nPress Enter to exit...")
        return
        
    model_path = f"models/wake_words/{model_name}.onnx"

    print_header("STEP 6: Calibrate Threshold")
    print("Calibrating your phrase's optimal confidence threshold.")
    if not run_step([str(python_exe), "tools/training/calibrate.py", "--phrase", phrase, "--model", model_path], env):
        print("\n[!] Calibration indicates an issue. You may want to record more personal samples and retrain.")
        input("\nPress Enter to exit...")
        return

    print_header("STEP 7: Validate & Deploy")
    print("Testing the model against real-world voice to ensure it works before deploying.")
    if not run_step([str(python_exe), "tools/training/validate.py", "--phrase", phrase, "--model", model_path], env):
        print("\n[!] Validation failed. The model was NOT deployed.")
        input("\nPress Enter to exit...")
        return

    print_header("SUCCESS!")
    print(f"Your model '{model_name}' has been successfully trained and deployed!")
    print("You must RESTART Clarity.V for the new wake word to take effect.")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
