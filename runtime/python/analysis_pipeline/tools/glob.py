from .safe_paths import safe_path
def glob_paths(worktree,pattern,path="."):
    root=safe_path(worktree,path)
    out=sorted(item.relative_to(root).as_posix() for item in root.glob(pattern) if item.exists())[:100]
    return "\n".join(out)
