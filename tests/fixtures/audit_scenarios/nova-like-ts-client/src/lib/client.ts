import Anthropic from "@anthropic-ai/sdk";

export function getClient() {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error("ANTHROPIC_API_KEY no está configurada");
  return new Anthropic({ apiKey });
}
