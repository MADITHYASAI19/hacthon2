"""Build a portable submission archive with normalized forward-slash paths."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent
archive = root / "code.zip"
excluded_parts = {"dataset", "__pycache__", ".pytest_cache", ".venv", "venv", "scratch", ".git", ".cache", "llm_cache"}

def include(path: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in excluded_parts for part in rel.parts):
        return False
    return path.suffix not in {".pyc", ".zip", ".csv"} and path.name not in {".env", "log.txt", "output.csv"}

with ZipFile(archive, "w", ZIP_DEFLATED) as zf:
    for path in [root / "README.md", root / ".env.example"]:
        zf.write(path, path.relative_to(root).as_posix())
    for path in (root / "code").rglob("*"):
        if path.is_file() and include(path):
            zf.write(path, path.relative_to(root).as_posix())
