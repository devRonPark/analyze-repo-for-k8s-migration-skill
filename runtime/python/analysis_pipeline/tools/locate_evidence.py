import re
from .safe_paths import safe_path
def locate_evidence(worktree,glob,path=".",pattern=None):
    root=safe_path(worktree,path); rx=re.compile(pattern) if pattern else None
    for f in sorted(x for x in root.glob(glob) if x.is_file()):
        for n,line in enumerate(f.read_text(encoding="utf-8",errors="replace").splitlines(),1):
            if rx is None or rx.search(line): return {"location":f"{f}:{n}","glob":glob,"pattern":pattern}
    return {"location":None,"glob":glob,"pattern":pattern}
