# main.py
from pathlib import Path
import re, joblib

MODEL_PATH = Path("model/model_pipeline.pkl")
INCOMING_DIR = Path("incoming_tf")

def normalize_tf(s: str) -> str:
    s = re.sub(r'#.*', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def load_model():
    if not MODEL_PATH.exists():
        raise SystemExit(f"Model not found at {MODEL_PATH}. Run train.py first.")
    return joblib.load(MODEL_PATH)

def read_tf_files(folder: Path):
    if not folder.exists():
        raise SystemExit(f"Folder {folder} does not exist. Create it and add .tf files.")
    files = sorted(folder.glob("*.tf"))
    if not files:
        raise SystemExit(f"No .tf files found in {folder}. Add a file to score.")
    return files

if __name__ == "__main__":
    model = load_model()
    for tf_path in read_tf_files(INCOMING_DIR):
        raw = tf_path.read_text(encoding="utf-8")
        text = normalize_tf(raw)
        proba_pass = float(model.predict_proba([text])[0, 1])
        proba_issue = 1.0 - proba_pass
        print(f"{tf_path.name}: there is {proba_issue*100:.1f}% that this tf will likely cause issues once merged")
