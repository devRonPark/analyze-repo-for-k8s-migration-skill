import { readFile } from "node:fs/promises"
import { relative, resolve } from "node:path"
import { isSafeWithin } from "./safe-path"
import { redact } from "./redact"

export type Fact =
  | { status: "found"; value: string; reference: string }
  | { status: "not_found"; searched: { scope: string; glob: string; pattern: string | null } }

const MAX_CANDIDATES = 100

export async function resolveRoot(worktree: string, path?: string) {
  const value = resolve(worktree, path ?? ".")
  if (!(await isSafeWithin(worktree, value))) throw new Error("path is outside the target")
  return value
}

// Finds files under `root` matching `glob`, and within the first one whose
// content matches `pattern` (as a regex), returns the matched line as a
// found Fact -- with a reference computed from this same read, never from
// an earlier one the caller has to remember correctly. If `pattern` is
// omitted, the first glob match itself is the Fact (file-presence evidence).
// If nothing matches, returns not_found with the literal glob/pattern
// searched, so a 검색(...) citation never has to be reconstructed either.
export async function locateEvidence(options: {
  worktree: string
  root: string
  glob: string
  pattern?: string
}): Promise<Fact> {
  const { worktree, root, glob, pattern } = options
  const scope = relative(worktree, root) || "."

  const candidates: string[] = []
  for await (const entry of new Bun.Glob(glob).scan({ cwd: root })) {
    candidates.push(entry)
    if (candidates.length === MAX_CANDIDATES) break
  }
  candidates.sort()

  const regex = pattern ? new RegExp(pattern) : null

  for (const match of candidates) {
    const absolute = resolve(root, match)
    const reportPath = relative(worktree, absolute)
    if (!regex) {
      return { status: "found", value: match, reference: `${reportPath}:1` }
    }
    const lines = (await readFile(absolute, "utf8")).split(/\r?\n/)
    const lineIndex = lines.findIndex(line => regex.test(line))
    if (lineIndex !== -1) {
      return {
        status: "found",
        value: redact(lines[lineIndex].trim(), reportPath),
        reference: `${reportPath}:${lineIndex + 1}`,
      }
    }
  }

  return { status: "not_found", searched: { scope, glob, pattern: pattern ?? null } }
}
