export function shareUrl(gameId: string, t?: number): string {
  const base = `${window.location.origin}/g/${gameId}`;
  return t != null ? `${base}?t=${Math.floor(t)}` : base;
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
