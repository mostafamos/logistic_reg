# train.py
from pathlib import Path
import joblib, re, pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import log_loss, f1_score, accuracy_score

DATA_CSV = Path("data/preparing.csv")
MODEL_DIR = Path("model"); MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "model_pipeline.pkl"

def normalize_tf(s: str) -> str:
    s = re.sub(r'#.*', ' ', s)       # strip comments
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def load_data():
    df = pd.read_csv(DATA_CSV)
    assert {"group_id","label","tf_snippet"}.issubset(df.columns)
    df["tf_snippet"] = df["tf_snippet"].fillna("").astype(str).map(normalize_tf)
    return df

def build_features():
    word_vec = TfidfVectorizer(lowercase=True, ngram_range=(1,2), max_features=50000, min_df=1)
    char_vec = TfidfVectorizer(lowercase=True, analyzer="char_wb", ngram_range=(3,6), max_features=70000)
    return FeatureUnion([("w", word_vec), ("c", char_vec)])

if __name__ == "__main__":
    df = load_data()
    X = df["tf_snippet"].values
    y = df["label"].values
    groups = df["group_id"].values

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr_idx, va_idx = next(gss.split(X, y, groups))
    X_tr, X_va, y_tr, y_va = X[tr_idx], X[va_idx], y[tr_idx], y[va_idx]

    base = Pipeline([
        ("feats", build_features()),
        ("clf", SGDClassifier(
            loss="log_loss", penalty="l2",
            max_iter=13, tol=None,
            class_weight="balanced", random_state=42
        ))
    ])

    # ✅ sklearn>=1.4 uses 'estimator=', not 'base_estimator'
    model = CalibratedClassifierCV(estimator=base, cv=3, method="isotonic")
    model.fit(X_tr, y_tr)

    y_proba = model.predict_proba(X_va)[:, 1]
    y_pred  = (y_proba >= 0.5).astype(int)

    print(f"Validation log loss: {log_loss(y_va, y_proba, labels=[0,1]):.4f}")
    print(f"Validation F1:       {f1_score(y_va, y_pred):.4f}")
    print(f"Validation accuracy: {accuracy_score(y_va, y_pred):.4f}")

    joblib.dump(model, MODEL_PATH)
    print(f"Saved pipeline to {MODEL_PATH}")
