// One-shot guard for the D14 host-owned continuation experiment.
//
// OpenCode 1.18.14 exposes one native `skill` tool whose `name` parameter
// selects a Skill. A host-loaded successor must therefore suppress only the
// exact pending name, not the entire tool or unrelated Skills.
import fs from "node:fs"

const statePath = process.env.ANALYSIS_HOST_ACTIVATION_STATE
const blockedName = "__host_owned_duplicate_skill_blocked__"

function pendingActivation() {
  if (!statePath) return undefined
  try {
    const value = JSON.parse(fs.readFileSync(statePath, "utf8"))
    if (
      value?.version !== 1 ||
      value.state !== "pending" ||
      value.transition_owner !== "host" ||
      typeof value.analysis_id !== "string" || !value.analysis_id ||
      !Number.isInteger(value.revision) || value.revision < 0 ||
      typeof value.transition_token !== "string" || !value.transition_token ||
      typeof value.next_skill !== "string" || !value.next_skill
    ) return undefined
    return value
  } catch {
    return undefined
  }
}

function writeState(value) {
  if (!statePath) return
  const temporary = `${statePath}.${process.pid}.tmp`
  fs.writeFileSync(temporary, `${JSON.stringify(value)}\n`, "utf8")
  fs.renameSync(temporary, statePath)
}

function consumeForSuccessorAction() {
  const pending = pendingActivation()
  if (!pending) return
  writeState({ ...pending, state: "consumed" })
}

function blockDuplicate(args) {
  const pending = pendingActivation()
  if (!pending || !args || args.name !== pending.next_skill) return false
  // `tool.execute.before` mutates the live argument object used by the native
  // executor. The Skill service consequently cannot return the successor
  // content a second time, while all other native Skills retain their name.
  args.name = blockedName
  writeState({ ...pending, duplicate_blocked_attempts: (pending.duplicate_blocked_attempts ?? 0) + 1 })
  return true
}

export const HostOwnedSkillGuard = async () => ({
  "tool.definition": async ({ toolID }, output) => {
    const pending = pendingActivation()
    if (toolID !== "skill" || !pending || !output.jsonSchema || typeof output.jsonSchema !== "object") return
    const schema = output.jsonSchema
    const properties = schema.properties && typeof schema.properties === "object" ? schema.properties : {}
    const name = properties.name && typeof properties.name === "object" ? properties.name : { type: "string" }
    output.jsonSchema = {
      ...schema,
      properties: {
        ...properties,
        name: {
          ...name,
          not: { const: pending.next_skill },
          description: `${name.description ?? "Skill name"}. ${pending.next_skill} is already host-activated for this transition.`,
        },
      },
    }
  },
  "tool.execute.before": async ({ tool }, output) => {
    if (tool === "skill") {
      blockDuplicate(output.args)
      return
    }
    if (tool.startsWith("analysis_")) consumeForSuccessorAction()
  },
})

// Dependency-free exports keep the actual hook seam directly testable without
// requiring a provider-backed OpenCode session.
export const __test__ = { blockedName, pendingActivation, blockDuplicate, consumeForSuccessorAction }
