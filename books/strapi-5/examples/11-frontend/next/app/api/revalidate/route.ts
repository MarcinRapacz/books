import { revalidateTag } from 'next/cache';
import { secretMatches } from '@/lib/secrets';

type StrapiWebhook = {
  event: string;
  model?: string;
  entry?: { documentId?: string; slug?: string; locale?: string };
};

export async function POST(request: Request) {
  if (!secretMatches(request.headers.get('x-webhook-secret'), process.env.STRAPI_WEBHOOK_SECRET)) {
    return Response.json({ error: 'Invalid secret' }, { status: 401 });
  }

  const payload = (await request.json()) as StrapiWebhook;
  if (!payload.model) {
    return Response.json({ revalidated: false, reason: 'no model in payload' });
  }

  // One tag per content type: a publication refreshes the list and every page of that type.
  // The editor expects the change on the next request, so stale content is not served.
  const tag = `strapi:${payload.model}`;
  revalidateTag(tag, { expire: 0 });
  console.log(`[revalidate] ${payload.event} ${payload.entry?.slug ?? payload.entry?.documentId} -> ${tag}`);
  return Response.json({ revalidated: true, tag });
}
