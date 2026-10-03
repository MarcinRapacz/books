import 'server-only';
import { cookies } from 'next/headers';

const STRAPI_URL = process.env.STRAPI_URL;
const STRAPI_COOKIE = 'strapi_up_refresh';
export const REFRESH_COOKIE = 'redakcja_refresh';

type StrapiAuthResult = { status: number; body: Record<string, unknown>; refreshToken: string | null };

/** Calls a users-permissions auth route server-to-server and picks the refresh token out of Set-Cookie. */
export async function callStrapiAuth(path: string, body: object, jwt?: string): Promise<StrapiAuthResult> {
  const response = await fetch(`${STRAPI_URL}/api/auth/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(jwt ? { Authorization: `Bearer ${jwt}` } : {}) },
    body: JSON.stringify(body),
    cache: 'no-store',
  });
  // With sessions.httpOnly Strapi sends the refresh token only as a cookie for its own domain.
  const strapiCookie = response.headers
    .getSetCookie()
    .find((cookie) => cookie.startsWith(`${STRAPI_COOKIE}=`));
  const refreshToken = strapiCookie?.split(';')[0].slice(STRAPI_COOKIE.length + 1) || null;
  return { status: response.status, body: (await response.json()) as Record<string, unknown>, refreshToken };
}

export async function storeRefreshToken(token: string) {
  (await cookies()).set(REFRESH_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/api/auth',
    // Strapi's absolute session limit (maxRefreshTokenLifespan); the idle limit is enforced by Strapi.
    maxAge: 30 * 24 * 60 * 60,
  });
}

export async function readRefreshToken(): Promise<string | undefined> {
  return (await cookies()).get(REFRESH_COOKIE)?.value;
}

export async function clearRefreshToken() {
  (await cookies()).delete({ name: REFRESH_COOKIE, path: '/api/auth' });
}
