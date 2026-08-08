import re
from .safe_paths import safe_path
SECRET=re.compile(r"(password|secret|token|api[_-]?key|private[_-]?key)(\s*[:=]\s*)([^\s]+)",re.I)
def read(worktree,path,offset=0,limit=None):
    target=safe_path(worktree,path)
    if target.is_dir(): return "\n".join(sorted(x.name for x in target.iterdir()))
    lines=target.read_text(encoding="utf-8").splitlines(); start=max(0,int(offset or 0)); count=max(1,int(limit or len(lines)))
    return "\n".join(f"{start+i+1}: {SECRET.sub(lambda m:m.group(1)+m.group(2)+'[REDACTED]',line)}" for i,line in enumerate(lines[start:start+count]))
