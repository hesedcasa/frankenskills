"""BigCodeBench helpers: dependency environments and hidden unittest execution."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import CACHE_DIR
from .workspace import uv_venv

PYTHON = "3.11"
NLTK_DIR = CACHE_DIR / "nltk_data"

# Import-name -> PyPI package name for common libraries in BigCodeBench `libs`.
PIP_NAMES = {
    "Bio": "biopython",
    "Crypto": "pycryptodome",
    "OpenSSL": "pyopenssl",
    "PIL": "pillow",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python-headless",
    "dateutil": "python-dateutil",
    "docx": "python-docx",
    "dotenv": "python-dotenv",
    "fitz": "pymupdf",
    "flask_restful": "flask-restful",
    "jwt": "pyjwt",
    "pptx": "python-pptx",
    "skimage": "scikit-image",
    "sklearn": "scikit-learn",
    "usb": "pyusb",
    "yaml": "pyyaml",
}

_RUNNER = r'''
import json, sys, unittest

sol_path, test_path = sys.argv[1], sys.argv[2]
ns = {"__name__": "__main__"}
exec(compile(open(sol_path).read(), sol_path, "exec"), ns)
exec(compile(open(test_path).read(), test_path, "exec"), ns)

loader = unittest.TestLoader()
suite = unittest.TestSuite()
for obj in list(ns.values()):
    if isinstance(obj, type) and issubclass(obj, unittest.TestCase) and obj is not unittest.TestCase:
        suite.addTests(loader.loadTestsFromTestCase(obj))

result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
total = result.testsRun
failed = len(result.failures)
errors = len(result.errors)
passed = max(0, total - failed - errors)
print(json.dumps({"passed": passed, "failed": failed, "errors": errors, "total": total}))
'''


def packages_for(inst: dict) -> list[str]:
    """Non-stdlib PyPI packages required by a BigCodeBench instance."""
    stdlib = set(sys.stdlib_module_names) | {"builtins", "__future__", "unittest", "typing"}
    pkgs = set()
    for lib in inst.get("libs") or []:
        top = str(lib).split(".")[0].strip()
        if not top or top in stdlib:
            continue
        pkgs.add(PIP_NAMES.get(top, top))
    return sorted(pkgs)


def _ensure_nltk_data(python: Path) -> None:
    marker = NLTK_DIR / ".ready"
    if marker.exists():
        return
    NLTK_DIR.mkdir(parents=True, exist_ok=True)
    NLTK_DIR.chmod(0o700)
    env = os.environ | {"NLTK_ALLOW_PROXIED_URLOPEN": "1"}
    subprocess.run(
        [str(python), "-c",
         f"import nltk; ok = all(nltk.download(p, download_dir={str(NLTK_DIR)!r}, quiet=True) "
         f"for p in ('punkt', 'punkt_tab', 'stopwords')); assert ok, 'nltk download failed'"],
        check=True, timeout=300, env=env,
    )
    marker.write_text("ok")


def env_for(inst: dict) -> Path:
    """Cached virtualenv with the instance's declared packages plus pytest."""
    pkgs = packages_for(inst)
    if not pkgs:
        return uv_venv("bcb-stdlib", PYTHON, ["pytest"])
    key = hashlib.sha1(" ".join(pkgs).encode()).hexdigest()[:12]
    py = uv_venv(f"bcb-{key}", PYTHON, [*pkgs, "pytest"])
    if "nltk" in pkgs:
        _ensure_nltk_data(py)
    return py


def agent_env(python: Path) -> dict:
    return {"PATH": f"{python.parent}:{os.environ['PATH']}",
            "VIRTUAL_ENV": str(python.parent.parent),
            "MPLBACKEND": "Agg",
            "NLTK_DATA": str(NLTK_DIR)}


def run_tests(solution_src: str, test_src: str, python: Path | None = None,
              timeout: int = 60) -> dict:
    """Execute BigCodeBench's unittest suite against `solution_src`."""
    py = str(python or sys.executable)
    env = os.environ | {"MPLBACKEND": "Agg", "NLTK_DATA": str(NLTK_DIR)}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sol = tmp_path / "solution.py"
        tst = tmp_path / "test_case.py"
        runner = tmp_path / "runner.py"
        sol.write_text(solution_src)
        tst.write_text(test_src)
        runner.write_text(_RUNNER)
        try:
            proc = subprocess.run([py, str(runner), str(sol), str(tst)],
                                  cwd=tmp_path, capture_output=True, text=True,
                                  timeout=timeout, env=env)
            res = json.loads(proc.stdout.strip().splitlines()[-1])
            res["output"] = proc.stderr[-1500:]
        except subprocess.TimeoutExpired:
            res = {"passed": 0, "failed": 0, "errors": 1, "total": 1, "output": "timeout"}
        except (IndexError, json.JSONDecodeError) as e:
            err = proc.stderr[-1500:] if "proc" in locals() else str(e)
            res = {"passed": 0, "failed": 0, "errors": 1, "total": 1, "output": err}
    total = res["total"]
    res["pass_rate"] = res["passed"] / total if total else 0.0
    res["all_pass"] = total > 0 and res["passed"] == total
    return res
