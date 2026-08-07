import { tool } from "@opencode-ai/plugin"
import { resolve } from "node:path"
import { isSafeWithin } from "../lib/safe-path"

async function safeRoot(worktree: string, path?: string) {
  const value = resolve(worktree, path ?? ".")
  if (!(await isSafeWithin(worktree, value))) throw new Error("path is outside the target")
  return value
}

export default tool({
  description: "List target paths only. Use this instead of native glob; read file contents with trusted read.",
  args: {
    pattern: tool.schema.string(),
    path: tool.schema.string().optional(),
  },
  async execute(args, context) {
    const root = await safeRoot(context.worktree, args.path)
    const matches: string[] = []
    for await (const entry of new Bun.Glob(args.pattern).scan({ cwd: root })) {
      matches.push(entry)
      if (matches.length === 100) break
    }
    return matches.sort().join("\n")
  },
})
