export function splitWords(text: string): string[] {
  return text.split(/\s+/).filter(Boolean);
}
