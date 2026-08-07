import { tool } from "@opencode-ai/plugin"
import { locateEvidence, resolveRoot } from "../lib/locate-evidence"

export default tool({
  description:
    "Find target files matching a glob and locate the first line matching an optional regex pattern. " +
    "Returns a tool-computed file:line reference for a match, or the literal glob/pattern searched when " +
    "nothing matches -- use this to cite evidence instead of recalling a line number from an earlier read.",
  args: {
    glob: tool.schema.string(),
    path: tool.schema.string().optional(),
    pattern: tool.schema.string().optional(),
  },
  async execute(args, context) {
    const root = await resolveRoot(context.worktree, args.path)
    const fact = await locateEvidence({
      worktree: context.worktree,
      root,
      glob: args.glob,
      pattern: args.pattern,
    })
    return JSON.stringify(fact)
  },
})
