export function projectIdFromQuery(value: unknown, fallback = 1): number {
  if (typeof value !== "string" || !/^[1-9]\d*$/.test(value)) return fallback
  const parsed = Number(value)
  return Number.isSafeInteger(parsed) ? parsed : fallback
}
