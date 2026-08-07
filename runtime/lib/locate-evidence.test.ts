import { describe, expect, test } from "bun:test"
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join, sep } from "node:path"
import { locateEvidence, resolveRoot } from "./locate-evidence"

function makeFixture() {
  const worktree = mkdtempSync(join(tmpdir(), "locate-evidence-"))
  return worktree
}

describe("locateEvidence: found", () => {
  test("glob only (no pattern) cites the matched file's first line", async () => {
    const worktree = makeFixture()
    try {
      writeFileSync(join(worktree, "Dockerfile"), "FROM openjdk:25\nCMD [\"catalina.sh\", \"run\"]\n")
      const fact = await locateEvidence({ worktree, root: worktree, glob: "Dockerfile" })
      expect(fact).toEqual({ status: "found", value: "Dockerfile", reference: "Dockerfile:1" })
    } finally {
      rmSync(worktree, { recursive: true, force: true })
    }
  })

  test("glob + pattern cites the real matched line, not line 1", async () => {
    const worktree = makeFixture()
    try {
      writeFileSync(join(worktree, "Dockerfile"), "FROM openjdk:25\nEXPOSE 8080\nCMD [\"catalina.sh\", \"run\"]\n")
      const fact = await locateEvidence({ worktree, root: worktree, glob: "Dockerfile", pattern: "^EXPOSE" })
      expect(fact).toEqual({ status: "found", value: "EXPOSE 8080", reference: "Dockerfile:2" })
    } finally {
      rmSync(worktree, { recursive: true, force: true })
    }
  })

  test("matched line is redacted before being returned as value", async () => {
    const worktree = makeFixture()
    try {
      writeFileSync(join(worktree, "config.env"), "user=app\npassword=hunter2\n")
      const fact = await locateEvidence({ worktree, root: worktree, glob: "config.env", pattern: "^password" })
      expect(fact.status).toBe("found")
      expect((fact as { value: string }).value).toBe("password= [REDACTED]")
    } finally {
      rmSync(worktree, { recursive: true, force: true })
    }
  })

  test("multiple candidates are searched in sorted order", async () => {
    const worktree = makeFixture()
    try {
      writeFileSync(join(worktree, "b.txt"), "target\n")
      writeFileSync(join(worktree, "a.txt"), "target\n")
      const fact = await locateEvidence({ worktree, root: worktree, glob: "*.txt", pattern: "target" })
      expect(fact).toEqual({ status: "found", value: "target", reference: "a.txt:1" })
    } finally {
      rmSync(worktree, { recursive: true, force: true })
    }
  })

  test("reference is worktree-relative even when root is a subdirectory", async () => {
    const worktree = makeFixture()
    try {
      mkdirSync(join(worktree, "service-a"), { recursive: true })
      writeFileSync(join(worktree, "service-a", "Dockerfile"), "FROM openjdk:25\n")
      const root = await resolveRoot(worktree, "service-a")
      const fact = await locateEvidence({ worktree, root, glob: "Dockerfile" })
      expect(fact).toEqual({ status: "found", value: "Dockerfile", reference: `service-a${sep}Dockerfile:1` })
    } finally {
      rmSync(worktree, { recursive: true, force: true })
    }
  })
})

describe("locateEvidence: not_found returns the literal search, not an invented 검색(...)", () => {
  test("no file matches the glob", async () => {
    const worktree = makeFixture()
    try {
      const fact = await locateEvidence({ worktree, root: worktree, glob: "Dockerfile" })
      expect(fact).toEqual({
        status: "not_found",
        searched: { scope: ".", glob: "Dockerfile", pattern: null },
      })
    } finally {
      rmSync(worktree, { recursive: true, force: true })
    }
  })

  test("files match the glob but no line matches the pattern", async () => {
    const worktree = makeFixture()
    try {
      writeFileSync(join(worktree, "Dockerfile"), "FROM openjdk:25\n")
      const fact = await locateEvidence({ worktree, root: worktree, glob: "Dockerfile", pattern: "^EXPOSE" })
      expect(fact).toEqual({
        status: "not_found",
        searched: { scope: ".", glob: "Dockerfile", pattern: "^EXPOSE" },
      })
    } finally {
      rmSync(worktree, { recursive: true, force: true })
    }
  })
})

describe("resolveRoot", () => {
  test("rejects a path argument that lexically escapes the worktree", async () => {
    const worktree = makeFixture()
    try {
      await expect(resolveRoot(worktree, "../outside")).rejects.toThrow("path is outside the target")
    } finally {
      rmSync(worktree, { recursive: true, force: true })
    }
  })

  test("accepts the default root", async () => {
    const worktree = makeFixture()
    try {
      const root = await resolveRoot(worktree)
      expect(root).toBe(worktree)
    } finally {
      rmSync(worktree, { recursive: true, force: true })
    }
  })
})
