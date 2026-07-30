import { tool } from "@opencode-ai/plugin"
import { relative, resolve, sep } from "node:path"

function isWithin(root: string, path: string) {
  const pathFromRoot = relative(root, path)
  return pathFromRoot !== ".." && !pathFromRoot.startsWith(".." + sep)
}

function safeRoot(worktree: string, path?: string) {
  const value = resolve(worktree, path ?? ".")
  if (!isWithin(worktree, value)) throw new Error("path is outside the target")
  return value
}

export default tool({
  description: "List target paths only. Use this instead of native glob; read file contents with trusted read.",
  args: {
    pattern: tool.schema.string(),
    path: tool.schema.string().optional(),
  },
  async execute(args, context) {
    const root = safeRoot(context.worktree, args.path)
    const matches: string[] = []
    for await (const entry of new Bun.Glob(args.pattern).scan({ cwd: root })) {
      matches.push(entry)
      if (matches.length === 100) break
    }
    return matches.sort().join("\n")
  },
})
