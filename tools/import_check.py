import importlib
import sys

sys.path.insert(0, r"d:\git\paper-pipeline")
try:
    m = importlib.import_module("paper_pipeline")
    print(getattr(m, "__file__", repr(m)))
except Exception as e:
    print("IMPORT_ERROR:", e)
    raise
