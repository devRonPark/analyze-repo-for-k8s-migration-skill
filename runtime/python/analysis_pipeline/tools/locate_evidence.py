import re
from pathlib import Path
from .safe_paths import safe_path
from .read import redact_text
def locate_evidence(worktree,glob,path=".",pattern=None,observation_registry=None,stage=None):
    root=safe_path(worktree,path); rx=re.compile(pattern) if pattern else None
    if root.is_file():
        filename_pattern = glob.rsplit("/", 1)[-1]
        candidates = [root] if root.match(glob) or root.match(filename_pattern) else []
    else:
        candidates=sorted(x for x in root.glob(glob) if x.is_file())[:100]
    scope=Path(root).relative_to(Path(worktree).resolve()).as_posix() or "."
    for f in candidates:
        relative=f.relative_to(Path(worktree).resolve()).as_posix()
        for n,line in enumerate(f.read_text(encoding="utf-8",errors="replace").splitlines(),1):
            if rx is None or rx.search(line):
                result = {"status":"found","value":redact_text(line.strip(), f.suffix),"reference":f"{relative}:{n}"}
                if observation_registry is not None:
                    result.update(observation_registry.issue_present(stage, f, n, n, result["value"]))
                return result
    result = {"status":"not_found","searched":{"scope":scope,"glob":glob,"pattern":pattern}}
    if observation_registry is not None:
        result.update(observation_registry.issue_absence(stage, scope, glob, pattern))
    return result
