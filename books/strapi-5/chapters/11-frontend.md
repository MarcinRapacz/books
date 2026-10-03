# Rozdział 11. Integracja z frontendem (Next.js / Nuxt)

> **Cel rozdziału:** połączyć Strapi z frontendem w Next.js tak, żeby strona była szybka dzięki cache, odświeżała się po publikacji, pokazywała szkice redaktorom i logowała czytelników bez wystawiania tokenów w przeglądarce.
>
> **Kod:** `examples/11-frontend/`. **Pakiety poza fundamentem:** w projekcie Next.js `npm install qs` i `npm install -D @types/qs`.

Lista artykułów „Redakcji” nie zmienia się co sekundę, więc nie ma powodu pytać Strapi przy każdym wejściu. Redakcja oczekuje jednak, że opublikowany tekst pojawi się od razu, a przycisk podglądu w panelu (rozdział 8) pokaże szkic, którego nikt inny jeszcze nie widzi. Do tego czytelnicy logują się, a API token frontendu nie może trafić do przeglądarki.

Przykład to minimalny projekt Next.js 16.3 z App Routerem (październik 2026), uruchomiony przez `next build` i `next start` na porcie 3011 obok Strapi z rozdziałów 7 i 8. Wszystkie wyniki poniżej pochodzą z tego zestawu. Zapytania REST i `qs` opisuje rozdział 3, sesje z refresh tokenami – rozdział 7.

## Serwer z tokenem, przeglądarka bez

Kod w Server Components i route handlerach wykonuje się na serwerze Next.js, więc może używać API tokenu. Token podglądu jest potrzebny, bo middleware `published-only` z rozdziału 7 przepuszcza `status=draft` tylko dla strategii `content-api-token`. Ten sam rozdział pokazał, że token read-only czyta adresy e-mail użytkowników, dlatego frontend dostaje token typu Custom z samymi `find` i `findOne` na artykułach i kategoriach (`GET /api/users` z nim daje 403). Całe pobieranie siedzi w jednym module:

```ts
// lib/strapi.ts (fragment)
import 'server-only';

async function strapiGet<T>(path: string, query: object, tags: string[]): Promise<T> {
  const { isEnabled: isDraft } = await draftMode();
  const search = qs.stringify({ ...query, status: isDraft ? 'draft' : 'published' }, { encodeValuesOnly: true });
  const response = await fetch(`${STRAPI_URL}/api/${path}?${search}`, {
    headers: { Authorization: `Bearer ${API_TOKEN}` },
    cache: 'force-cache',
    next: { tags, revalidate: 300 },
  });
  if (!response.ok) {
    throw new Error(`Strapi ${response.status} for /api/${path}: ${await response.text()}`);
  }
  return (await response.json()) as T;
}
```

`import 'server-only'` sprawia, że import modułu w komponencie klienckim przerywa build, więc token nie wycieknie przez pomyłkę. W Next 16 `fetch` domyślnie niczego nie cache'uje; `force-cache` i `next.tags` trzeba podać jawnie. `next build` oznaczył stronę główną jako statyczną z `Revalidate 5m`, a odpowiedź ma nagłówek `x-nextjs-cache: HIT`.

Typy odpowiedzi opisują zapytania, nie typy treści: `ArticleCard` dla listy, `ArticleDetail` ze strefą dynamiczną jako unią po `__component`. Typy generowane przez Strapi (rozdział 12) opisują schemat serwera, a kształt odpowiedzi zależy od `fields` i `populate`; specyfikacja OpenAPI ma usterki z rozdziału 3. Ręczny typ obok zapytania to realistyczny wybór. `@strapi/client` też tu nie pasuje: metody `collection()` przyjmują tylko parametry zapytania, więc nie przekażesz im `next.tags`.

Komentarze pod artykułem ładuje komponent kliencki (`comments.tsx`) zwykłym `fetch` na `NEXT_PUBLIC_STRAPI_URL`, bez tokenu. Widzi tylko to, na co pozwala rola Public, i jako pierwszy potrzebuje CORS.

## Rewalidacja po publikacji

Webhook z rozdziału 8 wysyła `entry.publish`, `entry.unpublish` i `entry.delete` z nagłówkiem `X-Webhook-Secret`. Odbiera go route handler, który unieważnia tag, a następne żądanie strony pobiera świeże dane:

```ts
// app/api/revalidate/route.ts (fragment)
export async function POST(request: Request) {
  if (!secretMatches(request.headers.get('x-webhook-secret'), process.env.STRAPI_WEBHOOK_SECRET)) {
    return Response.json({ error: 'Invalid secret' }, { status: 401 });
  }
  const payload = (await request.json()) as StrapiWebhook;
  if (!payload.model) {
    return Response.json({ revalidated: false, reason: 'no model in payload' });
  }
  // One tag per content type: a publication refreshes the list and every page of that type.
  const tag = `strapi:${payload.model}`;
  revalidateTag(tag, { expire: 0 });
  return Response.json({ revalidated: true, tag });
}
```

`secretMatches` porównuje skróty SHA-256 przez `timingSafeEqual`. HMAC z sekcji „Verifying signatures” dokumentacji musiałby liczyć nadawca, a runner webhooków Strapi wysyła tylko statyczne nagłówki. Jeden tag na typ treści odświeża listę i wszystkie artykuły naraz – przy kilkuset tekstach to tańsze niż pilnowanie tagów per slug, który może się zmienić. Piotr publikuje zmieniony tytuł przez REST:

```text
GET  localhost:3011/          → "Fetching Strapi from Next.js"         x-nextjs-cache: HIT
PUT  localhost:1311/api/articles/stjg4i8olo7vp0jlfofgw74b {"data":{"title":"Fetching Strapi from Next.js 16"}} → 200
log Next: [revalidate] entry.publish fetching-strapi-from-next-js -> strapi:article
GET  localhost:3011/          → "Fetching Strapi from Next.js 16"      x-nextjs-cache: MISS, potem HIT
POST localhost:3011/api/revalidate (zły sekret) → 401 {"error":"Invalid secret"}
```

Zapis szkicu (`?status=draft`) nie wysyła webhooka i nie zmienia strony, co jest zgodne z intencją.

> **Pułapka:** dokumentacja Next.js zaleca `revalidateTag(tag, 'max')`, a jednoargumentowe `revalidateTag(tag)` jest przestarzałe. Profil `max` oznacza stale-while-revalidate: po publikacji z `'max'` pierwsze żądanie zwróciło stary tytuł, dopiero drugie nowy. Redaktor, który odświeża stronę zaraz po publikacji, uzna, że webhook nie działa. Dla webhooka z CMS-a użyj `{ expire: 0 }`.

Druga niespodzianka dotyczy self-hostingu. Domyślny cache handler trzyma unieważnione tagi w pamięci procesu, a dane `fetch` na dysku w `.next/cache`. Po webhooku i restarcie `next start` (a nawet po ponownym `next build` na tej samej maszynie) strona wróciła do tytułu sprzed publikacji, choć Strapi miał już nowy – aż do kolejnej rewalidacji czasowej. Przy kilku replikach `revalidateTag` działa tylko na tej, która odebrała webhook. Dlatego `revalidate: 300` zostaje jako siatka bezpieczeństwa, razem z tym, że Strapi nie ponawia nieudanych webhooków. Pełne rozwiązanie to wspólny cache handler, np. na Redisie (dokumentacja Next.js, „Self-hosting”).

W Dockerze Strapi wysyła webhook na adres w sieci wewnętrznej, np. `http://frontend:3000/api/revalidate`. W produkcji panel odrzuci taki adres jako prywatny (rozdział 8), więc tworzysz webhook kodem w `bootstrap` albo kierujesz go na publiczny URL frontendu.

## Podgląd szkiców

Handler `preview` w `config/admin.ts` (rozdział 8) zwraca panelowi adres `/api/preview?url=/artykuly/<slug>&secret=...&status=draft`. Route handler w Next sprawdza sekret, włącza draft mode i przekierowuje:

```ts
// app/api/preview/route.ts
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
  if (searchParams.get('status') === 'published') draft.disable();
  else draft.enable();
  redirect(url);
}
```

Draft mode to ciasteczko `__prerender_bypass`. Z nim Next pomija cache `fetch`, a `strapiGet` dokłada `status=draft`. Adres wziąłem z Admin API panelu, a stronę pobrałem z ciasteczkiem i bez niego. Zły sekret daje 401, a `url=//evil.example` – 400:

```text
GET /content-manager/preview/url/api::article.article?documentId=stjg4i8o...&status=draft
  → http://localhost:3011/api/preview?url=%2Fartykuly%2Ffetching-strapi-from-next-js&secret=...&status=draft
GET (ten adres) → 307 do /artykuly/fetching-strapi-from-next-js,
  set-cookie: __prerender_bypass=...; Path=/; Secure; HttpOnly; SameSite=none
GET /artykuly/fetching-strapi-from-next-js → z ciasteczkiem "...Next.js (draft v2)", bez "...Next.js 16"
GET /artykuly/self-hosting-strapi-with-docker → z ciasteczkiem 200, bez 404
```

Przykład trasy w dokumentacji Strapi (z demo LaunchPad) woła `draftMode()` bez `await`, czyli API sprzed Next 15, i przekierowuje na `url` bez sprawdzenia. Komentarz w nim ostrzega przed otwartym przekierowaniem, ale kod robi dokładnie to. Ciasteczko `SameSite=none; Secure` pozwala działać podglądowi w ramce panelu. Next nie wysyła `X-Frame-Options`, więc ramka działa bez konfiguracji; jeśli dodasz CSP, wpisz adres panelu do `frame-ancestors`. Baner „Podgląd szkiców” w `layout.tsx` ma formularz `POST /api/preview/exit`, który wyłącza tryb.

## Logowanie przez route handler

Rozdział 7 trzymał token odświeżania w ciasteczku `httpOnly` ustawianym przez Strapi. Gdy frontend i API mają różne domeny, ciasteczko z `SameSite=Lax` nie poleci z `fetch` strony. Rozwiązaniem jest pośrednik: przeglądarka loguje się do Next, a Next rozmawia ze Strapi serwer-serwer. Strapi w trybie `httpOnly` oddaje token odświeżania tylko w `Set-Cookie`, więc Next wyjmuje go z nagłówka i zapisuje we własnym ciasteczku:

```ts
// lib/session.ts (fragment)
const strapiCookie = response.headers
  .getSetCookie()
  .find((cookie) => cookie.startsWith(`${STRAPI_COOKIE}=`));
const refreshToken = strapiCookie?.split(';')[0].slice(STRAPI_COOKIE.length + 1) || null;

// storeRefreshToken(token), called by the login and refresh route handlers
(await cookies()).set(REFRESH_COOKIE, token, {
  httpOnly: true,
  secure: process.env.NODE_ENV === 'production',
  sameSite: 'lax',
  path: '/api/auth',
  maxAge: 30 * 24 * 60 * 60,
});
```

`/api/auth/refresh` w Next czyta to ciasteczko i wysyła je do Strapi w polu `refreshToken` ciała. Strapi szuka tokenu najpierw w podpisanym ciasteczku, którego Next nie ma, a potem w ciele (rozdział 7):

```text
POST :3011/api/auth/login {"identifier":"anna","password":"Passw0rd!"}
  → 200 {"jwt":"eyJhbGciOi...","user":{"username":"anna",...}}
    set-cookie: redakcja_refresh=...; Path=/api/auth; Max-Age=2592000; Secure; HttpOnly; SameSite=lax
POST :3011/api/auth/refresh             → 200 {"jwt":"eyJhbGciOi..."} + nowe redakcja_refresh
POST :3011/api/auth/refresh (stare)     → 401 {"error":"Session expired"} + skasowane ciasteczko
POST :3011/api/auth/logout              → 200 {"ok":true}
```

Token dostępu trafia do pamięci przeglądarki i idzie do Strapi w nagłówku `Authorization`. Z nim `GET /api/articles/mine` zwróciło artykuły Piotra. Klient z rozdziału 7 działa dalej, wystarczy zmienić adres odświeżania na `/api/auth/refresh`; jego pojedyncze odświeżanie jest tu jeszcze ważniejsze, bo nieudany refresh kasuje ciasteczko. Wylogowanie w Strapi wymaga ważnego tokenu dostępu, więc `/api/auth/logout` najpierw odświeża sesję, a potem ją zamyka. Server Component może ciasteczka czytać, ale nie ustawiać, więc rotacja tokenu musi przejść przez route handler albo Server Function.

## CORS

Domyślne `strapi::cors` ma `origin: '*'` i `credentials: true`, a kod middleware zamienia gwiazdkę na origin z żądania:

```text
OPTIONS /api/articles/mine  Origin: https://evil.example
→ 204, Access-Control-Allow-Origin: https://evil.example, Access-Control-Allow-Credentials: true
```

> **Pułapka:** to nie jest „wszyscy, ale bez ciasteczek”, tylko „każda strona, z ciasteczkami”. Przeglądarka z sesją z rozdziału 7 wyśle ciasteczko odświeżania z żądaniem każdej strony, której pozwala na to `SameSite` (np. dowolnej subdomeny tej samej witryny), a ta strona odczyta odpowiedź – łącznie z nowym tokenem dostępu z `/api/auth/refresh`. Ustaw listę originów jawnie.

```ts
// config/middlewares.ts (fragment)
{
  name: 'strapi::cors',
  config: {
    origin: env.array('CORS_ORIGINS', ['http://localhost:3000']),
    credentials: false,
  },
},
```

Po zmianie preflight z `evil.example` dostał 200 bez nagłówków `Access-Control-*`, a z `http://localhost:3011` – zgodę z `Authorization` na liście nagłówków. `credentials: false` pasuje do pośrednika z poprzedniej sekcji. Jeśli przeglądarka ma wysyłać ciasteczko Strapi bezpośrednio (rozdział 7), zostaw `credentials: true`, ale z jawną listą originów.

## Obrazy

Lokalny provider uploadu zwraca URL względny (`/uploads/policies_cover_ce810c5af8.png`), więc `mediaUrl()` dokleja adres Strapi. `next/image` optymalizuje tylko obrazy z dozwolonych źródeł:

```ts
// next.config.ts (fragment)
images: {
  remotePatterns: [
    {
      protocol: strapiUrl.protocol === 'https:' ? 'https' : 'http',
      hostname: strapiUrl.hostname,
      port: strapiUrl.port,
      pathname: '/uploads/**',
    },
  ],
  // Next 16 refuses to optimize images from localhost and private networks (SSRF protection).
  dangerouslyAllowLocalIP: process.env.STRAPI_IMAGES_LOCAL === 'true',
},
```

Bez ostatniej opcji `/_next/image?url=http://localhost:1311/uploads/...` zwrócił 400, a log pokazał `hostname resolved to private IP ["127.0.0.1"]`. Po włączeniu – 200 `image/png`, a ścieżka spoza `/uploads/` nadal 400. To lustrzane odbicie walidatora webhooków w Strapi: w Dockerze z adresem `http://strapi:1337` potrzebujesz tej opcji albo publicznego URL-a obrazów. Provider S3 (rozdział 8) zwraca adresy absolutne i wymaga wpisu z hostem bucketu lub CDN.

> **Nuxt.** Konfiguracja i kod pokazane, nieuruchomione (Nuxt 4.5). Token idzie do `runtimeConfig` (tylko serwer, `NUXT_STRAPI_TOKEN`), adres publiczny do `runtimeConfig.public`. Nie ma odpowiednika `revalidateTag`: cache'ujesz funkcją Nitro i czyścisz jej wpisy w trasie webhooka. `usePreviewMode()` włącza się domyślnie parametrem `?preview=true` w URL-u, więc sekret musi sprawdzić trasa serwera, która dokłada `status=draft`. Obrazy obsługuje `@nuxt/image` z `domains` albo providerem `strapi`.
>
> ```ts
> // server/utils/articles.ts
> export const getArticles = defineCachedFunction(async () => {
>   const { strapiToken, public: { strapiUrl } } = useRuntimeConfig();
>   return $fetch(`${strapiUrl}/api/articles`, { headers: { Authorization: `Bearer ${strapiToken}` } });
> }, { name: 'articles', getKey: () => 'all', maxAge: 300 });
> // server/api/revalidate.post.ts
> export default defineEventHandler(async (event) => {
>   if (getHeader(event, 'x-webhook-secret') !== useRuntimeConfig(event).webhookSecret) {
>     throw createError({ statusCode: 401 });
>   }
>   await useStorage('cache').removeItem('nitro:functions:articles:all.json');
>   return { ok: true };
> });
> ```

## Podsumowanie

- Dane pobieraj na serwerze Next z API tokenem typu Custom w module z `import 'server-only'`; przeglądarka pyta Strapi bez tokenu, tylko o to, co widzi rola Public.
- Typy odpowiedzi pisz per zapytanie; `@strapi/client` nie przekaże `next.tags`.
- W Next 16 `fetch` nie cache'uje domyślnie: `cache: 'force-cache'`, `next.tags` i `revalidate` jako zabezpieczenie.
- Webhook trafia do route handlera, który porównuje sekret w stałym czasie i woła `revalidateTag(tag, { expire: 0 })`; `'max'` pokazuje po publikacji stary stan.
- Unieważnienia tagów żyją w pamięci jednej instancji – restart i repliki wymagają rewalidacji czasowej albo wspólnego cache handlera.
- Podgląd: sekret, ścieżka tylko lokalna, `draftMode().enable()`, `status=draft` w zapytaniu.
- Logowanie przez route handlery Next trzyma token odświeżania w ciasteczku `httpOnly` frontendu; Strapi dostaje go w ciele żądania.
- Domyślny CORS Strapi odbija każdy origin z `credentials: true`; `next/image` w Next 16 blokuje adresy prywatne.

## Co dalej

Frontend działa, ale wszystko sprawdziłeś ręcznie curl-em. Rozdział 12 zamienia takie kontrole w testy: typy generowane przez `strapi ts:generate-types`, testy polityk i middleware na instancji Strapi w teście oraz narzędzia AI dla dewelopera. Jako ćwiczenie możesz dopisać stronę „Moje artykuły”, która korzysta z `/api/articles/mine` i tokenu z `/api/auth/refresh`.

## Źródła

- https://docs.strapi.io/cms/features/preview
- https://docs.strapi.io/cms/backend-customization/webhooks
- https://docs.strapi.io/cms/configurations/middlewares
- https://docs.strapi.io/cms/api/client
- https://docs.strapi.io/cms/features/api-tokens
- https://docs.strapi.io/cms/features/users-permissions
- https://nextjs.org/docs/app/api-reference/functions/revalidateTag
- https://nextjs.org/docs/app/guides/caching-without-cache-components
- https://nextjs.org/docs/app/guides/draft-mode
- https://nextjs.org/docs/app/guides/self-hosting
- https://nextjs.org/docs/app/api-reference/functions/cookies
- https://nextjs.org/docs/app/api-reference/components/image
- https://nuxt.com/docs/4.x/api/composables/use-preview-mode
- https://v2.nitro.build/guide/cache
- https://image.nuxt.com/providers/strapi
