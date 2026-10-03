import { callStrapiAuth, clearRefreshToken, readRefreshToken, storeRefreshToken } from '@/lib/session';

export async function POST() {
  const refreshToken = await readRefreshToken();
  if (!refreshToken) {
    return Response.json({ error: 'Not logged in' }, { status: 401 });
  }

  const result = await callStrapiAuth('refresh', { refreshToken });
  if (result.status !== 200 || !result.refreshToken) {
    await clearRefreshToken();
    return Response.json({ error: 'Session expired' }, { status: 401 });
  }

  // Strapi rotates the token on every refresh; the old one is invalid from now on.
  await storeRefreshToken(result.refreshToken);
  return Response.json({ jwt: result.body.jwt });
}
