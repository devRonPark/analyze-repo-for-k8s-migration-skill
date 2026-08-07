const SECRET = /((?i:password|passwd|token|api[_ -]?key)\s*[=:])\s*[^\s,;]+/g
const SQL_LITERAL = /'(?:''|[^'])*'/g

export function redact(line: string, path: string) {
  const credentialSafe = line.replace(SECRET, "$1 [REDACTED]")
  return path.endsWith(".sql") ? credentialSafe.replace(SQL_LITERAL, "'[REDACTED]'") : credentialSafe
}
