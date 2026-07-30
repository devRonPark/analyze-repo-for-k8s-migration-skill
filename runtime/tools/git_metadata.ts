import { tool } from "@opencode-ai/plugin"

export default tool({
  description: "Return only the current target Git branch and commit for report metadata.",
  args: {},
  async execute(_, context) {
    const branch = (await Bun.$`git -C ${context.worktree} branch --show-current`.text()).trim() || "detached"
    const commit = (await Bun.$`git -C ${context.worktree} rev-parse HEAD`.text()).trim()
    return `branch: ${branch}\ncommit: ${commit}`
  },
})
