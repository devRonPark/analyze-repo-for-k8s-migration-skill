from pathlib import Path
def safe_path(worktree, value, trusted_roots=()):
    root=Path(worktree).resolve(); target=(root/value).resolve(); allowed=[root,*[Path(x).resolve() for x in trusted_roots]]
    if not any(target==x or x in target.parents for x in allowed): raise ValueError("path is outside the target or trusted Skill")
    return target
