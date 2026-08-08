import re
from .safe_paths import safe_path
SECRET=re.compile(r"(password|passwd|secret|token|api[_ -]?key|private[_ -]?key)(\s*[:=]\s*)([^\s,;]+)",re.I)
SQL=re.compile(r"'(?:''|[^'])*'")
def read(worktree,path,offset=0,limit=None,trusted_roots=()):
    target=safe_path(worktree,path,trusted_roots)
    if target.is_dir(): return "\n".join(sorted(x.name for x in target.iterdir()))
    lines=target.read_text(encoding="utf-8").splitlines(); start=max(0,int(offset or 0)); count=max(1,int(limit or len(lines)))
    def clean(line):
        value=SECRET.sub(lambda m:m.group(1)+m.group(2)+'[REDACTED]',line)
        return SQL.sub("'[REDACTED]'",value) if target.suffix.lower()=='.sql' else value
    return "\n".join(f"{start+i+1}: {clean(line)}" for i,line in enumerate(lines[start:start+count]))
