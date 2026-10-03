import { callStrapiAuth, storeRefreshToken } from '@/lib/session';

type Credentials = { identifier?: unknown; password?: unknown };

export async function POST(request: Request) {
  const { identifier, password } = (await request.json()) as Credentials;
  if (typeof identifier !== 'string' || typeof password !== 'string') {
    return Response.json({ error: 'identifier and password are required' }, { status: 400 });
  }

  const result = await callStrapiAuth('local', { identifier, password });
  if (result.status !== 200 || !result.refreshToken) {
    return Response.json(result.body, { status: result.status });
  }

  await storeRefreshToken(result.refreshToken);
  // The short-lived access token goes to the browser's memory; the refresh token never does.
  return Response.json({ jwt: result.body.jwt, user: result.body.user });
}
