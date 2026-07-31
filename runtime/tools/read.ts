import { tool } from "@opencode-ai/plugin"
import { readFile, readdir, stat } from "node:fs/promises"
import { relative, resolve, sep } from "node:path"

const SECRET = /((?i:password|passwd|token|api[_ -]?key)\s*[=:])\s*[^\s,;]+/g
const SQL_LITERAL = /'(?:''|[^'])*'/g

function isWithin(root: string, path: string) {
  const pathFromRoot = relative(root, path)
  return pathFromRoot !== ".." && !pathFromRoot.startsWith(".." + sep)
}

function safePath(worktree: string, path: string) {
  const value = resolve(worktree, path)
  const configDir = process.env.OPENCODE_CONFIG_DIR
  const trustedSkillRoots = [
    configDir && resolve(configDir, "skill/analyze-repo-for-kubernetes"),
    resolve(process.env.HOME ?? ".", ".config/opencode/skill/analyze-repo-for-kubernetes"),
    resolve(worktree, ".opencode/skill/analyze-repo-for-kubernetes"),
  ].filter((root): root is string => Boolean(root))
  if (!isWithin(worktree, value) && !trustedSkillRoots.some(root => isWithin(root, value))) {
    throw new Error("path is outside the target or trusted Skill")
  }
  return value
}

function redact(line: string, path: string) {
  const credentialSafe = line.replace(SECRET, "$1 [REDACTED]")
  return path.endsWith(".sql") ? credentialSafe.replace(SQL_LITERAL, "'[REDACTED]'") : credentialSafe
}

export default tool({
  description: "Read target evidence after redacting credential literals. Use for every file or directory read.",
  args: {
    path: tool.schema.string(),
    offset: tool.schema.number().optional(),
    limit: tool.schema.number().optional(),
  },
  async execute(args, context) {
    const path = safePath(context.worktree, args.path)
    if ((await stat(path)).isDirectory()) return (await readdir(path)).join("\n")
    const lines = (await readFile(path, "utf8")).split(/\r?\n/)
    const offset = Math.max(0, args.offset ?? 0)
    const limit = Math.max(1, args.limit ?? lines.length)
    return lines.slice(offset, offset + limit).map((line, index) =>
      `${offset + index + 1}: ${redact(line, path)}`
    ).join("\n")
  },
})
