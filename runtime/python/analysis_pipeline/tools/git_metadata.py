import subprocess
def git_metadata(worktree):
    def run(*args):
        return subprocess.run(["git","-C",str(worktree),*args],capture_output=True,text=True,check=True).stdout.strip()
    return f"branch: {run('branch','--show-current') or 'detached'}\ncommit: {run('rev-parse','HEAD')}"
