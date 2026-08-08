from .safe_paths import safe_path
def glob_paths(worktree,pattern,path="."):
    root=safe_path(worktree,path); out=[]
    for item in root.glob(pattern):
        out.append(item.relative_to(root).as_posix())
        if len(out)>=100: break
    return "\n".join(sorted(out))
