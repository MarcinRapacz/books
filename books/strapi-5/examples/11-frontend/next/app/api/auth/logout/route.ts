import { callStrapiAuth, clearRefreshToken, readRefreshToken } from '@/lib/session';

export async function POST() {
  const refreshToken = await readRefreshToken();
  await clearRefreshToken();
  if (!refreshToken) {
    return Response.json({ ok: true });
  }

  // Strapi's logout needs a valid access token, which the browser may no longer have,
  // so the server refreshes once and revokes the session it just received.
  const refreshed = await callStrapiAuth('refresh', { refreshToken });
  if (refreshed.status === 200 && typeof refreshed.body.jwt === 'string') {
    await callStrapiAuth('logout', { refreshToken: refreshed.refreshToken }, refreshed.body.jwt);
  }
  return Response.json({ ok: true });
}
