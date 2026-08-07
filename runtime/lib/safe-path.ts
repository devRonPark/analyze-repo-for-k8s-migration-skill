import { realpath } from "node:fs/promises"
import { basename, dirname, relative, sep } from "node:path"

export function isWithin(root: string, path: string) {
  const pathFromRoot = relative(root, path)
  return pathFromRoot !== ".." && !pathFromRoot.startsWith(".." + sep)
}

// Resolves symlinks (and, on Windows, junctions) in `path`. Node's realpath()
// throws ENOENT for a path whose final segment(s) don't exist yet -- in that
// case, resolve the deepest existing ancestor and reapply the remaining
// lexical segments, so a not-yet-existing target still gets its existing
// symlinked ancestors dereferenced.
export async function realpathDeepest(path: string): Promise<string> {
  try {
    return await realpath(path)
  } catch (error) {
    if ((error as NodeJS.ErrnoException)?.code !== "ENOENT") throw error
    const parent = dirname(path)
    if (parent === path) return path
    return `${await realpathDeepest(parent)}${sep}${basename(path)}`
  }
}

// True if `candidate` resolves (after dereferencing symlinks/junctions) to a
// location within `root` or one of `extraRoots`, comparing realpath-to-realpath
// so a symlink inside root that targets outside it is rejected.
export async function isSafeWithin(root: string, candidate: string, extraRoots: string[] = []) {
  const realRoot = await realpathDeepest(root)
  const realCandidate = await realpathDeepest(candidate)
  if (isWithin(realRoot, realCandidate)) return true
  for (const extraRoot of extraRoots) {
    if (isWithin(await realpathDeepest(extraRoot), realCandidate)) return true
  }
  return false
}
