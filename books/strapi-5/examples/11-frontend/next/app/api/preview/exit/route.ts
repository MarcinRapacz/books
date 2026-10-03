import { draftMode } from 'next/headers';

export async function POST(request: Request) {
  (await draftMode()).disable();
  // 303 turns the form POST into a GET of the home page.
  return Response.redirect(new URL('/', request.url), 303);
}
