import re
from pathlib import Path
from .safe_paths import safe_path
def locate_evidence(worktree,glob,path=".",pattern=None):
    root=safe_path(worktree,path); rx=re.compile(pattern) if pattern else None
    candidates=sorted(x for x in root.glob(glob) if x.is_file())[:100]
    scope=Path(root).relative_to(Path(worktree).resolve()).as_posix() or "."
    for f in candidates:
        relative=f.relative_to(Path(worktree).resolve()).as_posix()
        for n,line in enumerate(f.read_text(encoding="utf-8",errors="replace").splitlines(),1):
            if rx is None or rx.search(line): return {"status":"found","value":line.strip(),"reference":f"{relative}:{n}"}
    return {"status":"not_found","searched":{"scope":scope,"glob":glob,"pattern":pattern}}
