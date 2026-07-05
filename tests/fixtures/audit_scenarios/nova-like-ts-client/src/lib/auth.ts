export function validateBearerToken(header: string | null) {
  const expected = process.env.ARC_ONE_DEMO_TOKEN;
  if (!expected) return true;
  return header === `Bearer ${expected}`;
}
