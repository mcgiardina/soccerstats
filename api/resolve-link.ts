// Follows ONE redirect of a camera vendor's short share link and returns where it points, because a
// browser cannot read a cross-origin redirect. Strict allowlist on both ends, so this cannot be used
// to make the server fetch arbitrary addresses.
const SHORT = /^https:\/\/blrcam\.co\/[A-Za-z0-9]{4,32}$/;
const TARGET_HOSTS = new Set(["app.ballercam.com"]);

export async function GET(request: Request): Promise<Response> {
  const u = new URL(request.url).searchParams.get("u") ?? "";
  if (!SHORT.test(u)) return Response.json({ error: "unsupported link" }, { status: 400 });
  // The link service answers a browser-like client with a JavaScript interstitial; a plain
  // command-line client gets the real destination in one redirect.
  const r = await fetch(u, { redirect: "manual", headers: { "user-agent": "curl/8.4.0" } });
  const loc = r.headers.get("location");
  if (!loc) return Response.json({ error: "link did not redirect" }, { status: 502 });
  let target: URL;
  try { target = new URL(loc); } catch { return Response.json({ error: "bad redirect" }, { status: 502 }); }
  if (target.protocol !== "https:" || !TARGET_HOSTS.has(target.hostname)) return Response.json({ error: "unexpected destination" }, { status: 502 });
  return Response.json({ url: `${target.origin}${target.pathname}` }, { headers: { "cache-control": "public, max-age=86400" } });
}
