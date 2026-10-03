import { draftMode } from 'next/headers';
import { redirect } from 'next/navigation';
import { secretMatches } from '@/lib/secrets';

// Strapi's preview handler (config/admin.ts, chapter 8) builds /api/preview?url=...&secret=...&status=...
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  if (!secretMatches(searchParams.get('secret'), process.env.PREVIEW_SECRET)) {
    return new Response('Invalid preview secret', { status: 401 });
  }

  // Only paths of this site, never another origin: the URL comes from a link that can be copied.
  const url = searchParams.get('url') ?? '/';
  if (!url.startsWith('/') || url.startsWith('//')) {
    return new Response('Invalid preview url', { status: 400 });
  }

  const draft = await draftMode();
  if (searchParams.get('status') === 'published') {
    draft.disable();
  } else {
    draft.enable();
  }
  redirect(url);
}
