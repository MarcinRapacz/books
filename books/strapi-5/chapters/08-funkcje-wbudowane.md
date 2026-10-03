# Rozdział 8. Draft & publish, i18n, media, e-mail, webhooki, cron

> **Cel rozdziału:** nauczysz się korzystać z darmowych funkcji wbudowanych w Strapi 5 od strony kodu i klienta API – wersji roboczych, tłumaczeń, plików, poczty, webhooków, zadań cyklicznych i podglądu – oraz poznasz miejsca, w których zachowują się inaczej, niż sugeruje panel.
>
> **Kod:** `examples/08-funkcje-wbudowane/`. **Pakiety poza fundamentem:** `npm install @strapi/provider-email-nodemailer`; opcjonalnie `@strapi/provider-upload-aws-s3` (tylko konfiguracja produkcyjna).

Redakcja ma już reguły zapisu z rozdziałów 4–6. Teraz potrzebuje rzeczy, których nie pisze się od zera: autorka chce poprawić lead opublikowanego artykułu tak, żeby czytelnicy nie widzieli wersji w połowie edycji. Część tekstów ma wersję polską. Okładki trafiają do biblioteki mediów, autor dostaje e-mail o nowym komentarzu, frontend odświeża cache po publikacji, a komentarze, których nikt nie zmoderował przez miesiąc, same przechodzą w stan odrzucony.

Każda z tych funkcji ma swoje „ale”, którego nie widać w panelu. Mechanikę Document Service (`status`, `publish()`, lifecycle hooki i middleware DS) znasz z rozdziału 6, więc tutaj tylko z niej korzystasz.

## Draft & publish od strony klienta

Typ z draft & publish ma dla każdego dokumentu wersję roboczą i – po publikacji – wersję opublikowaną. REST domyślnie czyta wersje opublikowane, odwrotnie niż Document Service. Domyślnie też **publikuje przy zapisie**: `POST` i `PUT` bez parametru `status` zapisują draft i od razu go publikują. Żeby poprawić tylko wersję roboczą, autorka dodaje `?status=draft`:

```bash
curl -X PUT "localhost:1308/api/articles/$DOC?status=draft" -H "Authorization: Bearer $ANNA" \
  -H 'content-type: application/json' -d '{"data":{"excerpt":"Updated intro, not yet live."}}'
curl -g "localhost:1308/api/articles/$DOC?fields[0]=excerpt"                     # still the old one
curl -g "localhost:1308/api/articles?publicationFilter=modified&fields[0]=title" # edited since publication
curl -X PUT "localhost:1308/api/articles/$DOC" -H "Authorization: Bearer $ANNA" \
  -H 'content-type: application/json' -d '{"data":{}}'                           # publish the draft
```

```text
{"excerpt":"Updated intro, not yet live.","publishedAt":null}
"A short introduction to policies in strapi 5."
["Policies in Strapi 5"]
{"excerpt":"Updated intro, not yet live.","publishedAt":"2026-10-03T18:29:43.140Z","id":8}
```

Pusty `PUT` to w REST jedyny sposób na publikację: Content API nie ma tras `publish` ani `unpublish` (`POST /api/articles/:id/actions/publish` zwrócił 405). Wycofanie z publikacji robi redaktor w panelu albo twój kod przez `strapi.documents(uid).unpublish()` – na przykład w akcji niestandardowej z rozdziału 5. Parametr `publicationFilter` (`modified`, `never-published` i inne) wybiera dokumenty według relacji między ich wersjami.

Najważniejsza rzecz dotyczy jednak czytelnika, nie autora. Uprawnienie `find` w roli Public obejmuje oba statusy, więc anonimowy klient czyta szkice:

```bash
curl -g "localhost:1308/api/articles?status=draft&fields[0]=title&fields[1]=publishedAt"
```

```text
{"id":7,"documentId":"fhjgx99rqsclaci4fraebtzj","title":"Self-hosting Strapi with Docker","publishedAt":null}
... 4 documents, including the one that was never published
```

Draft & publish to więc przepływ pracy redakcji, a nie mechanizm poufności. Jeśli szkice nie mogą wyciec przed premierą, zablokuj `status=draft` dla ról bez tokena – jak to zrobić, pokazuje rozdział 7.

## i18n: tłumaczenia na poziomie pól

Internacjonalizacja (i18n) jest w Strapi 5 wbudowana. Włączasz ją w schemacie typu i decydujesz pole po polu, co jest tłumaczone. W Redakcji tłumaczone są `title`, `slug`, `excerpt`, `content` i `seo`; `readingTime` i `cover` są wspólne dla wszystkich języków:

```json
"pluginOptions": { "i18n": { "localized": true } },
"attributes": {
  "title": { "type": "string", "required": true, "maxLength": 160,
             "pluginOptions": { "i18n": { "localized": true } } },
  "readingTime": { "type": "integer", "min": 0,
                   "pluginOptions": { "i18n": { "localized": false } } }
}
```

Domyślnym językiem nowego projektu jest `en`; istniejące artykuły po włączeniu i18n dostały `locale: "en"`. Język polski trzeba dodać – w panelu (Settings → Internationalization) albo w `bootstrap()`, żeby każde środowisko miało go z kodu: `strapi.plugin('i18n').service('locales').create({ code: 'pl', name: 'Polish (pl)' })`, poprzedzone sprawdzeniem `findByCode('pl')`. Tłumaczenie istniejącego dokumentu to `PUT` z parametrem `locale`:

```bash
curl -X PUT "localhost:1308/api/articles/$DOC?locale=pl" -H "Authorization: Bearer $ANNA" \
  -H 'content-type: application/json' \
  -d '{"data":{"title":"Polityki w Strapi 5","slug":"polityki-w-strapi-5","excerpt":"Krótkie wprowadzenie do polityk."}}'
```

```text
{"id":11,"documentId":"zww8ba9zgusomej4xxkrium6","locale":"pl","title":"Polityki w Strapi 5","publishedAt":"2026-10-03T18:30:10.255Z"}
```

Ten sam `documentId`, nowy wiersz, od razu opublikowany. W Document Service odpowiednikiem jest `update({ documentId, locale: 'pl', data })`, które tworzy tłumaczenie jako draft; publikujesz je osobno przez `publish({ documentId, locale: 'pl' })`. Wersje językowe żyją niezależnie: publikacja polskiej nie publikuje angielskiej.

Przy odczycie zwróć uwagę na trzy zachowania. Po pierwsze, nie ma fallbacku: `GET /api/articles/:id?locale=pl` dla artykułu bez polskiej wersji zwraca 404, a nie wersję angielską – frontend musi sam zdecydować, co pokazać. Po drugie, nieznany język (`locale=de`) nie jest błędem, tylko pustą listą. Po trzecie, wszystkie języki naraz daje `locale=*` – zadziałało w REST i w Document Service, choć strona REST dokumentacji wymienia gwiazdkę tylko przy Document Service; `locale=all` zwraca pustą listę, bo „all” jest traktowane jak nazwa języka.

Relacje i pola `uid` są w i18n **zawsze** tłumaczone, niezależnie od `pluginOptions` (kod `isLocalizedAttribute` w pluginie i18n). Polska wersja startuje więc bez kategorii i bez autora: przy tłumaczeniu musisz je podać w `data`, inaczej filtr po kategorii jej nie znajdzie.

> **Pułapka:** pola nietłumaczone są kopiowane między językami tylko w obrębie **tego samego statusu**: zapis draftu aktualizuje drafty innych języków, publikacja – ich wersje opublikowane. REST-owy `PUT` publikujący zwraca wersję opublikowaną, więc synchronizuje tylko wersje opublikowane. W moim teście: `PUT ?status=draft` z `readingTime: 9` dla `en`, potem publikujący `PUT` z `readingTime: 6` dla `en` (polski draft dalej ma 9), a na koniec zmiana samego leadu w wersji `pl`. Publikacja polskiej wersji skopiowała jej nieaktualne `readingTime: 9` do opublikowanej wersji angielskiej, która miała 6. W panelu, sądząc po kodzie (nie klikałem tego), problem nie powstaje: „Publish” najpierw zapisuje draft (rozdział 6), więc drafty innych języków dostają nową wartość. Jeśli edytujesz pola wspólne przez REST, zapisuj je jako draft i dopiero potem publikuj każdy język.

## Media Library: najpierw plik, potem powiązanie

Pliki trafiają do biblioteki mediów osobnym żądaniem `multipart/form-data` na `POST /api/upload`, a do artykułu podpinasz je zwykłym zapisem. Rola potrzebuje uprawnienia `plugin::upload.content-api.upload`, którego seed nie nadaje (anonimowy upload dostaje 403); w przykładzie dodaje je `bootstrap()`. Anna wysyła okładkę 1200×800 px z tekstem alternatywnym:

```bash
curl -X POST localhost:1308/api/upload -H "Authorization: Bearer $ANNA" \
  -F "files=@cover.jpg" -F 'fileInfo={"alternativeText":"Gradient z napisem Redakcja"}'
```

```json
[{ "id": 1, "documentId": "pczbswhmeh4bfuk1y6ziuy3z", "name": "cover.jpg", "mime": "image/jpeg",
   "size": 21.12, "width": 1200, "height": 800, "url": "/uploads/cover_b62e14258a.jpg", "provider": "local",
   "formats": {
     "thumbnail": { "width": 234, "height": 156, "url": "/uploads/thumbnail_cover_b62e14258a.jpg" },
     "large":     { "width": 1000, "height": 667, "url": "/uploads/large_cover_b62e14258a.jpg" },
     "medium":    { "width": 750, "height": 500, "url": "/uploads/medium_cover_b62e14258a.jpg" },
     "small":     { "width": 500, "height": 333, "url": "/uploads/small_cover_b62e14258a.jpg" } } }]
```

Strapi wygenerował miniaturę i trzy wersje responsywne według domyślnych breakpointów 1000/750/500 px (Strapi 5.56, październik 2026); zmienisz je kluczem `breakpoints` w konfiguracji `upload` w `config/plugins.ts`, ale tylko dla nowych plików. `size` jest w kilobajtach. Powiązanie to `PUT /api/articles/:documentId` z `{"data":{"cover":1}}` – przyjęło zarówno numeryczne `id`, jak i `documentId` pliku. Okładkę zobaczysz dopiero z `populate[cover]`.

`allowedTypes` i `deniedTypes` z fundamentu działają: SVG skończył się `400 File type 'image/svg+xml' is not allowed`, a skrypt powłoki wysłany jako `text/plain` – `File type 'application/x-sh' is not allowed`, bo Strapi rozpoznaje typ binarny po zawartości. Tekstowego SVG zawartość nie zdradza: ten sam plik nazwany `fake.png` z typem `image/png` przeszedł. Ryzyko jest tu małe, bo serwer oddaje go jako `image/png` z nagłówkiem `X-Content-Type-Options: nosniff`, więc przeglądarka nie wykona go jako SVG – ale nie traktuj `deniedTypes` jako skanera treści.

### Provider S3-kompatybilny

Lokalny dysk wystarcza na jednym serwerze z wolumenem (rozdział 13). Przy kilku instancjach albo CDN przenosisz media do bucketu: MinIO, Cloudflare R2, Hetzner Object Storage czy AWS S3 obsługuje ten sam provider `@strapi/provider-upload-aws-s3`. Konfiguracja produkcyjna w `config/env/production/plugins.ts` (scalana z bazową, więc `security` i e-mail zostają):

```ts
upload: { config: {
  provider: 'aws-s3',
  providerOptions: {
    baseUrl: env('S3_PUBLIC_URL'), // e.g. https://media.redakcja.example
    s3Options: {
      credentials: { accessKeyId: env('S3_ACCESS_KEY_ID'), secretAccessKey: env('S3_ACCESS_SECRET') },
      region: env('S3_REGION', 'auto'),
      endpoint: env('S3_ENDPOINT'),
      forcePathStyle: env.bool('S3_FORCE_PATH_STYLE', true), // MinIO needs it, R2 does not
      params: { Bucket: env('S3_BUCKET') },
} } } },
```

Plik przechodzi `tsc`, ale nie uruchamiałem go z prawdziwym bucketem. Drugi krok to CSP: panel admina ładuje miniatury z bucketu, więc `strapi::security` w `config/middlewares.ts` zamieniasz na obiekt z `contentSecurityPolicy.directives`, dopisując domenę mediów do `img-src` i `media-src` (obok `'self'`, `data:`, `blob:` i `market-assets.strapi.io`). Przykładowy wynik: po uploadzie `url` w odpowiedzi to `https://media.redakcja.example/cover_b62e14258a.jpg`, a `provider` to `aws-s3`. R2 nie obsługuje ACL, więc nie ustawiaj tam `params.ACL`.

## E-mail: powiadomienie o nowym komentarzu

Domyślny provider e-mail to `sendmail`, który w produkcji się nie sprawdza. Dokumentacja poleca `@strapi/provider-email-nodemailer`, czyli zwykłe SMTP. Konfiguracja w `config/plugins.ts`:

```ts
email: { config: {
  provider: 'nodemailer',
  providerOptions: {
    host: env('SMTP_HOST', 'localhost'),
    port: env.int('SMTP_PORT', 2525),
    secure: env.int('SMTP_PORT', 2525) === 465, // implicit TLS only on 465
    ...(env('SMTP_USERNAME') ? { auth: { user: env('SMTP_USERNAME'), pass: env('SMTP_PASSWORD') } } : {}),
  },
  settings: { defaultFrom: env('EMAIL_FROM', 'Redakcja <no-reply@redakcja.example>') },
} },
```

W developmencie wygodny jest Mailpit w Dockerze; ja użyłem 36-liniowego „zlewu” SMTP na samym module `net` z Node (`tools/smtp-sink.mjs`), który przyjmuje każdą wiadomość i wypisuje ją na konsolę.

Gdzie wysłać powiadomienie? Komentarz może powstać przez REST, panel albo import, więc – zgodnie z rozdziałem 6 – w middleware Document Service, po `await next()`, kiedy zapis jest już w bazie:

```ts
export const newCommentEmail = (strapi: Core.Strapi): Modules.Documents.Middleware.Middleware => {
  return async (context, next) => {
    const result = await next();
    if (context.uid !== 'api::comment.comment' || context.action !== 'create') return result;

    const { documentId } = result as { documentId: string };
    const comment = await strapi.documents('api::comment.comment').findOne({
      documentId,
      fields: ['body'],
      populate: { article: { fields: ['title'], populate: { author: { fields: ['username', 'email'] } } } },
    });
    const article = comment?.article;
    const author = article?.author;
    if (!comment || !article || !author?.email) return result;

    // Fire and forget: a slow or broken SMTP server must not fail or delay the comment request.
    strapi.plugin('email').service('email')
      .sendTemplatedEmail({ to: author.email }, template, {
        comment: { body: comment.body }, article: { title: article.title }, author: { username: author.username },
      })
      .catch((error: Error) => strapi.log.error(`New comment email failed: ${error.message}`));
    return result;
  };
};
```

`sendTemplatedEmail(options, template, data)` wymaga w szablonie wszystkich trzech kluczy: `subject`, `text` i `html`, a składnię bierze z szablonów lodasha. Piotr komentuje artykuł Anny, wpisując w treść znacznik `<script>`. Zlew SMTP odebrał (treść zdekodowana z quoted-printable):

```text
From: Redakcja <no-reply@redakcja.example>
To: anna@example.com
Reply-To: redakcja@redakcja.example
Subject: Nowy komentarz do „Policies in Strapi 5”
Content-Type: multipart/alternative

[text/plain] Świetny tekst! <script>alert(1)</script> Czy będzie część o middleware?
[text/html]  <blockquote>Świetny tekst! &lt;script&gt;alert(1)&lt;/script&gt; Czy będzie część o middleware?</blockquote>
```

W części HTML szablon używa `<%- comment.body %>`, które escapuje HTML. Strapi ogranicza `<%= ... %>` do kluczy z `data`, ale **nie escapuje** – w części tekstowej widać surowy znacznik, a w HTML byłby to wstrzyknięty kod w skrzynce autora. Wysyłka bez `await` jest celowa: przy wyłączonym serwerze SMTP komentarz dalej dostał 201 w 21 ms, a w logu pojawiło się `New comment email failed: connect ECONNREFUSED ::1:2588`. Ceną jest brak ponowień – gdy powiadomienia są ważne, zapisz je w kolejce (tabela + cron niżej) zamiast wysyłać w żądaniu. Pamiętaj też, że middleware działa dla każdego zapisu: seed tworzący komentarze też próbował wysłać maile.

## Webhooki: powiadomienie frontendu o publikacji

Webhook to żądanie `POST`, które Strapi wysyła na twój adres po zdarzeniu w treści: `entry.create`, `entry.update`, `entry.delete`, `entry.publish`, `entry.unpublish`, `entry.draft-discard` oraz `media.*`. Frontend Redakcji chce wiedzieć o publikacji, wycofaniu i usunięciu artykułu, żeby odświeżyć cache (rozdział 11). Zamiast wyklikać webhook w panelu (Settings → Webhooks) w każdym środowisku osobno, w przykładzie `bootstrap()` tworzy webhook `frontend-revalidate` z adresu w `FRONTEND_WEBHOOK_URL`, korzystając z tych samych usług co kontroler panelu:

```ts
const store = strapi.get('webhookStore') as WebhookStore;
const runner = strapi.get('webhookRunner') as WebhookRunner;
const existing = (await store.findWebhooks()).find((webhook) => webhook.name === NAME);
if (!existing) {
  // The store only saves the row; the runner must be told about it, like the admin controller does.
  runner.add(await store.createWebhook({ name: NAME, url, headers: {}, events: EVENTS }));
}
```

`webhookStore` zapisuje wiersz w tabeli `strapi_webhooks`, a `webhookRunner` nasłuchuje zdarzeń. Runner wczytuje webhooki z bazy w swoim `bootstrap`, który działa przed twoim, więc nowy webhook trzeba mu przekazać ręcznie (pełny plik z aktualizacją adresu jest w `examples/`). To API wewnętrzne – typy `WebhookStore` w przykładzie opisałem sam na podstawie kodu `@strapi/core`.

Sekret dokładasz nagłówkiem. `webhooks.defaultHeaders` w `config/server.ts` trafia do każdego webhooka, a nagłówek ustawiony w samym webhooku go nadpisuje:

```ts
webhooks: {
  defaultHeaders: { 'X-Webhook-Secret': env('WEBHOOK_SECRET', '') },
},
```

Odbiorca (`tools/webhook-receiver.mjs`, 28 linii na `node:http`) porównuje nagłówek przez `timingSafeEqual` i bez niego odpowiada 401. Po publikacji artykułu przez REST odebrał:

```json
{ "headers": { "x-webhook-secret": "local-test-secret", "x-strapi-event": "entry.publish",
               "content-type": "application/json", "user-agent": "node" },
  "body": { "event": "entry.publish", "createdAt": "2026-10-03T18:29:43.169Z", "model": "article",
            "uid": "api::article.article",
            "entry": { "id": 8, "documentId": "zww8ba9zgusomej4xxkrium6", "locale": "en",
                       "slug": "policies-in-strapi-5", "publishedAt": "2026-10-03T18:29:43.140Z",
                       "category": { "name": "Backend", "...": "..." }, "comments": ["..."],
                       "author": { "username": "anna", "email": "anna@example.com", "...": "..." } } } }
```

Publikacja polskiej wersji przyszła jako osobne zdarzenie z `locale: "pl"` i `slug: "polityki-w-strapi-5"`, a wycofanie przez Admin API panelu – jako `entry.unpublish`. Payload zawiera cały wpis z relacjami, komponentami i dynamic zones i nie da się tego skonfigurować. Opcja `webhooks.populateRelations`, którą fundament ma w `config/server.ts`, pochodzi ze Strapi 4 – w `node_modules` nie ma żadnego kodu, który by ją czytał, więc w przykładzie ją usunąłem.

> **Pułapka:** dokumentacja zapewnia, że webhooki nie działają dla typu użytkownika „ze względu na prywatność”, a pola prywatne nie trafiają do payloadu. Ale relacja `author` jest wypełniona i niesie `email`, `provider`, `confirmed` i `blocked` autorki – wycięte są tylko hasło i tokeny. Jeśli webhook idzie do usługi zewnętrznej, wysyłasz jej dane osobowe autorów. Gdy odbiorcy wystarczy `documentId` i `slug`, wyślij własne, chude żądanie z middleware Document Service.

Runner jest „wystrzel i zapomnij”: kolejka po pięć żądań naraz, limit 10 sekund, bez ponowień (Strapi 5.56, październik 2026). Gdy wyłączyłem odbiorcę i opublikowałem artykuł, w logu Strapi nie pojawiło się nic – błąd jest połykany. Frontend musi więc mieć rewalidację awaryjną (np. `revalidate` co kilka minut), a nie polegać wyłącznie na webhooku. W produkcji (`NODE_ENV=production`) panel odrzuca też adresy, które rozwiązują się na localhost albo adres prywatny (10.x, 172.16–31.x, 192.168.x) – czyli także nazwę usługi Dockera w tej samej sieci. To ochrona przed SSRF. Kod z `bootstrap()` tej walidacji nie przechodzi, więc jeśli świadomie kierujesz webhook do kontenera obok, zrobisz to tylko z kodu.

## Cron: komentarze, na które nikt nie odpowiedział

Zadania cykliczne to funkcje uruchamiane przez Strapi według reguły w formacie crona (z opcjonalnym polem sekund na początku). Zadanie Redakcji odrzuca komentarze czekające na moderację dłużej niż 30 dni. Masowy `updateMany` przez Query Engine i jego koszty omówił rozdział 6; tutaj ważne jest opakowanie:

```ts
export default {
  rejectStaleComments: {
    async task({ strapi }: { strapi: Core.Strapi }) {
      const cutoff = new Date(Date.now() - pendingDays * DAY_MS);
      const { count } = await strapi.db.query('api::comment.comment').updateMany({
        where: { moderationStatus: 'pending', createdAt: { $lt: cutoff } },
        data: { moderationStatus: 'rejected' },
      });
      strapi.log.info(`[cron] rejectStaleComments: ${count} comment(s) older than ${pendingDays} days rejected`);
    },
    options: { rule: process.env.COMMENT_REJECT_RULE ?? '0 0 3 * * *', tz: 'Europe/Warsaw' },
  },
};
```

Plik `config/cron-tasks.ts` nie jest wczytywany automatycznie – importujesz go w `config/server.ts` i włączasz: `cron: { enabled: env.bool('CRON_ENABLED', false), tasks: cronTasks }`. Bez tego klucza Strapi przyjmuje `enabled: false`; z kodu providera wynika, że flaga dotyczy tylko zadań z konfiguracji – te dodane przez `strapi.cron.add()` ruszą i tak. Do testu uruchomiłem serwer z `COMMENT_REJECT_RULE='*/15 * * * * *'` i przestawiłem w SQLite datę utworzenia dwóch oczekujących komentarzy o 40 dni wstecz:

```text
[2026-10-03 20:32:30.008] info: [cron] rejectStaleComments: 0 comment(s) older than 30 days rejected
[2026-10-03 20:32:45.038] info: [cron] rejectStaleComments: 2 comment(s) older than 30 days rejected
→ GET /api/comments: [[4,"rejected"],[5,"pending"],[6,"rejected"]]
```

Komentarz numer 5 był świeży i został w kolejce. Nazwane zadanie możesz później usunąć przez `strapi.cron.remove('rejectStaleComments')`. Dokumentacja wciąż opisuje bibliotekę `node-schedule`, ale Strapi 5.56 używa `croner` – składnia reguł jest zgodna, a wyjątek rzucony w zadaniu kończy się wpisem `Cron job "..." failed` w logu zamiast awarii procesu.

Cron w Strapi działa w każdym procesie: przy dwóch replikach zadanie wykona się dwa razy. `updateMany` jest idempotentne, więc tu to nie szkodzi, ale wysyłka newslettera już tak. Takie zadania uruchamiaj na jednej instancji (`CRON_ENABLED=true` tylko tam) albo w zewnętrznym harmonogramie wołającym trasę z API tokenem.

## Preview: przycisk podglądu w panelu

Funkcja Preview dodaje w edycji wpisu przycisk otwierający stronę frontendu z aktualnym szkicem. W darmowej wersji to podgląd w ramce obok formularza; Live Preview z edycją w podglądzie wymaga planu Growth lub Enterprise. Konfiguracja leży w `config/admin.ts`: `handler` zamienia dokument na adres frontendu, a `null` ukrywa podgląd dla typu:

```ts
preview: {
  enabled: true,
  config: {
    allowedOrigins: [env('CLIENT_URL', 'http://localhost:3000')],
    async handler(uid, { documentId, locale, status }) {
      if (uid !== 'api::article.article') return null;
      const article = await strapi.documents(uid).findOne({
        documentId, locale, status: status === 'published' ? 'published' : 'draft', fields: ['slug'],
      });
      if (!article) return null;
      const params = new URLSearchParams({ url: `/artykuly/${article.slug}`, secret: env('PREVIEW_SECRET', ''), status: status ?? 'draft' });
      return `${env('CLIENT_URL', 'http://localhost:3000')}/api/preview?${params}`;
    },
  },
},
```

Panel woła handler przez Admin API, więc sprawdziłem go z JWT administratora (`GET /content-manager/preview/url/api::article.article?documentId=...&locale=pl&status=draft`): odpowiedź to `{"data":{"url":"http://localhost:3000/api/preview?url=%2Fartykuly%2Fpolityki-w-strapi-5&secret=&status=draft"}}`, a dla kategorii – 204 bez treści. Strapi dopisał też `CLIENT_URL` do `frame-src` w nagłówku CSP, żeby panel mógł osadzić frontend w ramce. Trasę `/api/preview` po stronie Next.js, która sprawdza sekret i włącza draft mode, buduje rozdział 11.

## Podsumowanie

- REST domyślnie czyta i **zapisuje** wersje opublikowane; `?status=draft` edytuje sam szkic, a publikacja w REST to `PUT` bez `status` – tras publish/unpublish nie ma.
- Public z uprawnieniem `find` czyta szkice przez `status=draft`; ochronę opisuje rozdział 7.
- i18n włączasz w schemacie per pole; relacje i `uid` są zawsze tłumaczone, nie ma fallbacku języka, `locale=*` zwraca wszystkie wersje.
- Pola nietłumaczone synchronizują się tylko w obrębie jednego statusu – publikacja jednego języka przez REST może nadpisać je w innym.
- Upload to osobne `POST /api/upload`, potem powiązanie przez `id` pliku; `deniedTypes` rozpoznaje typy binarne po zawartości, tekstowe po deklaracji.
- E-mail wysyłaj z middleware Document Service po `next()`, bez `await` na SMTP, a dane użytkownika w HTML wstawiaj przez `<%- %>`.
- Webhook niesie pełny wpis łącznie z e-mailem autora, nie ponawia prób i nie loguje błędów; sekret dodaj w `webhooks.defaultHeaders`.
- Cron wymaga `server.cron.enabled: true` i działa w każdej replice.

## Co dalej

Funkcje z tego rozdziału zbudowałeś w `src/` i `config/` jednego projektu. Gdy ten sam mechanizm – na przykład kolejka moderacji komentarzy z powiadomieniami – ma działać w kilku projektach, przenosisz go do pluginu z własnymi trasami, serwisami i stroną w panelu. Tym zajmuje się rozdział 9.

## Źródła

- https://docs.strapi.io/cms/features/draft-and-publish
- https://docs.strapi.io/cms/api/rest/status
- https://docs.strapi.io/cms/api/rest/publication-filter
- https://docs.strapi.io/cms/features/internationalization
- https://docs.strapi.io/cms/api/rest/locale
- https://docs.strapi.io/cms/api/document-service/locale
- https://docs.strapi.io/cms/features/media-library
- https://docs.strapi.io/cms/api/rest/upload
- https://docs.strapi.io/cms/configurations/media-library-providers
- https://docs.strapi.io/cms/configurations/media-library-providers/amazon-s3
- https://docs.strapi.io/cms/features/email
- https://docs.strapi.io/cms/configurations/email-nodemailer
- https://docs.strapi.io/cms/backend-customization/webhooks
- https://docs.strapi.io/cms/configurations/cron
- https://docs.strapi.io/cms/configurations/server
- https://docs.strapi.io/cms/features/preview
