import { describe, expect, test } from "bun:test"
import { mkdtempSync, symlinkSync, writeFileSync, mkdirSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import { isSafeWithin, isWithin, realpathDeepest } from "./safe-path"

// read.ts and glob.ts both compute their candidate path with resolve() before
// calling isSafeWithin(), so a plain ".." escape is already rejected by the
// lexical isWithin() check -- these tests exercise the symlink/junction case
// that resolve() alone cannot catch, which is the SEC-002 gap.

function makeFixture() {
  const base = mkdtempSync(join(tmpdir(), "sec-002-"))
  const worktree = join(base, "target")
  const outside = join(base, "outside")
  mkdirSync(worktree, { recursive: true })
  mkdirSync(outside, { recursive: true })
  writeFileSync(join(outside, "secret.txt"), "outside-secret\n")
  return { base, worktree, outside }
}

describe("isWithin", () => {
  test("accepts a path lexically inside root", () => {
    expect(isWithin("/a/b", "/a/b/c")).toBe(true)
  })
  test("rejects a path lexically outside root", () => {
    expect(isWithin("/a/b", "/a/c")).toBe(false)
  })
})

describe("isSafeWithin: directory junction escape (reproducible without OS symlink privilege)", () => {
  test("rejects a candidate reached through a junction that targets outside root", async () => {
    const { base, worktree, outside } = makeFixture()
    try {
      const link = join(worktree, "evidence_dir")
      symlinkSync(resolve(outside), link, "junction")
      const candidate = join(link, "secret.txt")
      expect(await isSafeWithin(worktree, candidate)).toBe(false)
    } finally {
      rmSync(base, { recursive: true, force: true })
    }
  })

  test("accepts a plain path that stays inside root", async () => {
    const { base, worktree } = makeFixture()
    try {
      writeFileSync(join(worktree, "file.txt"), "ok\n")
      const candidate = join(worktree, "file.txt")
      expect(await isSafeWithin(worktree, candidate)).toBe(true)
    } finally {
      rmSync(base, { recursive: true, force: true })
    }
  })

  test("accepts a candidate under an extra trusted root", async () => {
    const { base, worktree, outside } = makeFixture()
    try {
      writeFileSync(join(outside, "trusted.txt"), "ok\n")
      const candidate = join(outside, "trusted.txt")
      expect(await isSafeWithin(worktree, candidate, [outside])).toBe(true)
    } finally {
      rmSync(base, { recursive: true, force: true })
    }
  })
})

describe("isSafeWithin: file symlink escape", () => {
  test("rejects a file symlink inside root that targets outside root", async () => {
    const { base, worktree, outside } = makeFixture()
    try {
      const link = join(worktree, "evidence")
      try {
        symlinkSync(join(outside, "secret.txt"), link, "file")
      } catch (error) {
        if ((error as NodeJS.ErrnoException)?.code === "EPERM") {
          // File symlinks require elevated privilege or Developer Mode on
          // Windows; this environment doesn't have either. The junction
          // test above exercises the same isSafeWithin() code path this
          // fix relies on, so the fix itself is still covered -- this case
          // just can't be reproduced end-to-end on this machine.
          console.warn("skipping: file symlinks require elevated privilege on this machine")
          return
        }
        throw error
      }
      const candidate = link
      expect(await isSafeWithin(worktree, candidate)).toBe(false)
    } finally {
      rmSync(base, { recursive: true, force: true })
    }
  })
})

describe("realpathDeepest", () => {
  test("resolves a not-yet-existing path by dereferencing its existing ancestors", async () => {
    const { base, worktree, outside } = makeFixture()
    try {
      const link = join(worktree, "evidence_dir")
      symlinkSync(resolve(outside), link, "junction")
      const notYetCreated = join(link, "does-not-exist.txt")
      const real = await realpathDeepest(notYetCreated)
      const expectedParent = await realpathDeepest(outside)
      expect(real).toBe(join(expectedParent, "does-not-exist.txt"))
    } finally {
      rmSync(base, { recursive: true, force: true })
    }
  })
})
