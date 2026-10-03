# Rozdział 10. Panel admina i custom fields

> **Cel rozdziału:** dopasować panel Redakcji do zespołu (język, marka, strona startowa), dodać akcję i wskazówkę w edycji artykułu oraz zbudować własne pole z licznikiem znaków, zarejestrowane po stronie serwera i panelu.
>
> **Kod:** `examples/10-panel-admina/`. **Pakiety poza fundamentem:** brak.

Redaktorki Redakcji pracują po polsku i każdego ranka robią to samo: sprawdzają, ile komentarzy czeka na moderację, poprawiają tytuły SEO i otwierają opublikowany artykuł na stronie, żeby zobaczyć go oczami czytelnika. Panel wita je angielskim interfejsem z logo Strapi, a pole `metaTitle` przyjmie 70 znaków, choć wyszukiwarka utnie tytuł wcześniej.

W rozdziale 9 panel dostał stronę z pluginu. Tym razem zmieniasz go z poziomu projektu: konfiguracją, API Content Managera, strefą wstrzykiwania, widgetem i custom fieldem – polem z własnym komponentem React, które dla bazy pozostaje zwykłym tekstem. Poza custom fieldem wszystko trafia do paczki JavaScript panelu przy `npm run build` (albo `strapi develop`), nie do serwera.

## Konfiguracja w `src/admin/app.tsx`

Strapi ignoruje `src/admin/app.example.tsx` z fundamentu, dopóki nie zmienisz nazwy na `app.tsx`. Obiekt `config` opisuje to, co da się zmienić bez pisania komponentów:

```tsx
// src/admin/app.tsx (fragment)
import logo from './extensions/logo.svg';

export default {
  config: {
    locales: ['pl'],
    translations: {
      pl: { 'Auth.form.welcome.title': 'Witaj w Redakcji', 'app.components.LeftMenu.navbrand.title': 'Redakcja' },
    },
    auth: { logo },
    menu: { logo },
    theme: {
      light: { colors: { primary100: '#fdf0ef', primary200: '#f6cfcc', primary500: '#d9534c', primary600: '#b4231f', primary700: '#8f1a17' } },
      dark: { colors: { primary100: '#3a1514', primary200: '#6b2523', primary500: '#e0726c', primary600: '#e88a85', primary700: '#f2b3af' } },
    },
    tutorials: false,
    notifications: { releases: false },
  },
};
```

`locales` dodaje języki do wyboru w profilu. Angielskiego nie usuniesz, bo jest domyślny i zapasowy dla brakujących kluczy – a te są: w Strapi 5.56 (październik 2026) polski plik rdzenia panelu ma około 850 z 915 kluczy, Media Library około 245 z 392. `translations` nadpisuje pojedyncze klucze; klucze pluginów mają przedrostek, np. `content-type-builder.plugin.name`. `theme` jest głęboko scalany z motywem Design Systemu, więc podajesz tylko zmienione kolory. Logo z `src/admin/extensions/` Vite wstawił do paczki jako `data:image/svg+xml`; `tsc` potrzebuje do tego importu pliku `src/admin/vite-env.d.ts` z `/// <reference types="vite/client" />`. Logo wgrane w Settings → Global settings → Overview ma pierwszeństwo przed konfiguracją.

Bundler konfigurujesz w `src/admin/vite.config.ts` przez `mergeConfig` z Vite (rozdział 9).

Plik eksportuje też `register(app)` i `bootstrap(app)`. `register` wywołuje się po rejestracji pluginów i dostaje pełny `StrapiApp` – tu dodajesz custom fields i widgety. `bootstrap` działa, gdy pluginy są gotowe, więc tu sięgasz po Content Managera. Dokumentacja radzi zaczynać od `app.tsx` i przenosić kod do pluginu, gdy powtarza się w kilku projektach.

> **Pułapka:** `bootstrap` nie dostaje `StrapiApp`, tylko wycinek: `addComponents`, `addFields`, `addMenuLink`, `addReducers`, `addSettingsLink(s)`, `getPlugin` i `registerHook` (`StrapiApp.bootstrap` w `@strapi/admin`). `app.widgets.register()` w `bootstrap` kończy się „Cannot read properties of undefined”. Dlatego w przykładzie parametr ma typ `Pick<StrapiApp, 'getPlugin'>`.

## Akcja „Otwórz na stronie”: API Content Managera

Preview (rozdziały 8 i 11) pokazuje szkic w ramce panelu, a redaktorka chce zwykłego linku do opublikowanej wersji na stronie magazynu. Content Manager ma na to punkty rozszerzeń: `addEditViewSidePanel` (panel w bocznej kolumnie edycji), `addDocumentAction` (akcja w panelu, w menu „More actions” albo w wierszu listy), `addDocumentHeaderAction` (przycisk w nagłówku), `addBulkAction` (akcja na zaznaczonych wpisach) i `addRichTextBlocks` (bloki edytora Blocks). Każde przyjmuje „komponenty opisu” – funkcje, które dostają kontekst dokumentu i zwracają obiekt z etykietą i akcją albo `null`:

```tsx
// src/admin/extensions/open-on-site-action.tsx (bez importów)
const FRONTEND_URL = process.env.STRAPI_ADMIN_FRONTEND_URL ?? 'http://localhost:3000';

export const OpenOnSiteAction: HeaderActionComponent = ({ model, document }) => {
  // Header actions are rendered for every content type, so the action filters itself out.
  if (model !== 'api::article.article') {
    return null;
  }
  const slug: unknown = document?.slug;
  const hasPublishedVersion = document !== undefined && document.status !== 'draft';
  return {
    label: 'Otwórz na stronie',
    icon: <ExternalLink />,
    disabled: typeof slug !== 'string' || !hasPublishedVersion,
    onClick: () => {
      window.open(`${FRONTEND_URL}/articles/${String(slug)}`, '_blank', 'noopener');
    },
  };
};
```

W `bootstrap` rzutujesz `app.getPlugin('content-manager').apis` (w typach `unknown`) na `ContentManagerPlugin['config']['apis']` z `@strapi/content-manager/strapi-admin` i wywołujesz `addDocumentHeaderAction([OpenOnSiteAction])`. Content Manager renderuje opis jak komponent React, więc wolno w nim używać hooków. Przycisk trafia do nagłówka edycji każdego typu treści, stąd `null` dla wszystkiego poza artykułem. Pole `document.status` przyjmuje `draft`, `published` albo `modified`; curl na `/content-manager/collection-types/api::article.article` pokazał dla artykułów z seeda trzy razy `published` i raz `draft` – ten ostatni ma przycisk wyszarzony. Przykłady w dokumentacji piszą `onClick: ({ documentId }) => ...`, ale w 5.56 `onClick` dostaje zdarzenie (`React.SyntheticEvent`); kontekst przekazujesz przez domknięcie.

Adres frontendu daje zmienna `STRAPI_ADMIN_FRONTEND_URL`. Build wstawia do paczki obiekt `process.env` złożony tylko ze zmiennych z przedrostkiem `STRAPI_ADMIN_` (i kilku własnych Strapi). Po `STRAPI_ADMIN_FRONTEND_URL=https://redakcja.example npm run build` adres był w `dist/build/strapi-*.js`. Zmiana wymaga nowego buildu, a wszystko z tym przedrostkiem jest publiczne – żadnych sekretów.

### Strefa wstrzykiwania

API Content Managera zastąpiło w v5 większość stref wstrzykiwania (injection zones), w które plugin dokłada dowolny komponent. Zostały tam, gdzie API nie sięga, np. `editView.right-links`. Redakcja wstawia tam przypomnienie o okładce:

```tsx
// src/admin/extensions/cover-reminder.tsx (rdzeń)
export const CoverReminder = () => {
  const { model } = useContentManagerContext(); // unstable_useContentManagerContext
  const { value: cover } = useField('cover');
  if (model !== 'api::article.article' || cover) return null;
  return <Typography variant="pi" textColor="warning600">Artykuł nie ma okładki...</Typography>;
};
```

W `bootstrap` podpinasz go przez `contentManager.injectComponent('editView', 'right-links', { name: 'redakcja-cover-reminder', Component: CoverReminder })`. Komponent strefy dostaje tylko prop `slug`, a dane bierze z hooków: `useField` czyta bieżącą, niezapisaną wartość pola, więc komunikat znika po wybraniu okładki. Kolumny listy wpisów i układ formularza zmieniają z kolei predefiniowane hooki panelu (`registerHook`).

> **Pułapka:** dokumentacja umieszcza `editView.right-links` „między przyciskami Configure the view i Edit”, co pasuje do układu ze Strapi 4. W 5.56 `Panels.mjs` Content Managera renderuje strefę w panelu „Entry”, pod przyciskami akcji dokumentu, a `editView.informations` nie renderuje nigdzie, choć jest na liście stref. Zanim zaplanujesz ekran pod strefę, sprawdź w `node_modules/@strapi/content-manager`, gdzie pada `InjectionZone area=`.

## Widget na stronie głównej

Domyślnych widgetów strony głównej (ostatnie wpisy, profil, statystyki) nie usuniesz, ale możesz dodać własne. Redakcja dokłada kolejkę moderacji:

```tsx
// src/admin/app.tsx, register() (fragment)
app.widgets.register({
  id: 'pending-comments',
  icon: Discuss,
  title: { id: 'redakcja.widget.pending-comments', defaultMessage: 'Komentarze do moderacji' },
  component: async () => (await import('./extensions/pending-comments-widget')).default,
  link: { label: { id: 'redakcja.widget.link', defaultMessage: 'Wszystkie komentarze' },
    href: '/content-manager/collection-types/api::comment.comment' },
  permissions: [{ action: 'plugin::content-manager.explorer.read', subject: 'api::comment.comment' }],
});
```

Strapi rysuje ramkę, ikonę, tytuł i link, a twój komponent wypełnia środek. `icon` jest obowiązkowa (bez niej: `An icon must be provided`). Komponent ładuje się leniwie, `permissions` ukrywa widget przed rolą bez odczytu komentarzy, a bez `pluginId` widget dostaje UID `global::pending-comments`. Dane pobiera przez `useFetchClient` (rozdział 9) z API Content Managera, czyli z uprawnieniami zalogowanej osoby, a stany ładowania, błędu i pustej kolejki rysują `Widget.Loading`, `Widget.Error` i `Widget.NoData` z `@strapi/strapi/admin`. Zapytanie widgetu (`filters[moderationStatus][$eq]=pending`, `sort=createdAt:ASC`) wysłane curl-em z tokenem administratora po dodaniu dwóch komentarzy zwróciło `"total": 2` i oba komentarze, od najstarszego.

## Custom field: tytuł SEO z licznikiem

Redaktorka chce widzieć przy `metaTitle` licznik znaków i ostrzeżenie po przekroczeniu zalecanych 60, bez blokowania zapisu. To zadanie dla custom fielda: pola, które w Content-Type Builderze i formularzu wygląda jak nowy typ, a w bazie jest jednym z istniejących. Nowego typu danych nie doda, nie oprze się też na relacji, mediach, komponencie ani dynamic zone.

Pole rejestrujesz dwa razy. Serwer musi je znać, zanim wczyta schematy, więc rejestracja trafia do `register` w `src/index.ts`:

```ts
// src/index.ts
register({ strapi }: { strapi: Core.Strapi }) {
  strapi.customFields.register([
    { name: 'seo-title', type: 'string', inputSize: { default: 12, isResizable: true } },
    { name: 'seo-description', type: 'text', inputSize: { default: 12, isResizable: true } },
  ]);
},
```

Pola bez pluginu dostają UID-y `global::seo-title` i `global::seo-description`. Typ bazowy jest stały dla rejestracji, dlatego tytuł (`string`) i opis (`text`) to dwa pola z jednym komponentem. W `shared.seo` atrybut dostaje `type: "customField"` i UID pola, a walidacje zostają:

```json
"metaTitle": { "type": "customField", "customField": "global::seo-title",
  "required": true, "maxLength": 70, "options": { "recommendedLength": 60 } }
```

Przy starcie Strapi zamienia `customField` na typ bazowy (`convertCustomFieldType` w `@strapi/core`), więc kolumna się nie zmienia i tytuły z seeda przetrwały bez migracji. W panelu rejestracja idzie w `register` z `app.tsx`, z leniwie ładowanym komponentem:

```tsx
// src/admin/app.tsx, register(), for each of the two fields (fragment)
app.customFields.register({
  name: field.name,
  type: field.type,
  icon: Search,
  intlLabel: { id: `redakcja.${field.name}.label`, defaultMessage: field.label },
  intlDescription: { id: `redakcja.${field.name}.description`, defaultMessage: 'Pole z licznikiem znaków' },
  components: {
    Input: async () => {
      const { default: SeoLengthInput } = await import('./extensions/seo-length-input');
      // The registry types Input without props; the Content Manager passes them at runtime.
      return { default: SeoLengthInput as ComponentType };
    },
  },
});
```

`components.Input` jest otypowany jako komponent bez propsów, więc `tsc` odrzucił komponent z wymaganymi propsami – stąd rzutowanie. Pełny plik ma jeszcze `options.base` z ustawieniem „Zalecana długość” (`name: 'options.recommendedLength'`, `type: 'number'`) w Content-Type Builderze. Rejestr wymaga nazw opcji z przedrostkiem `options.`, ale typ `CustomFieldOptionName` w 5.56 zna tylko nazwy wbudowane, jak `maxLength`, więc linia ma `@ts-expect-error`, który sam zgłosi się do usunięcia po poprawce typu.

Komponent czyta i zmienia wartość przez formularz Content Managera:

```tsx
// src/admin/extensions/seo-length-input.tsx (rdzeń)
const { value, error, onChange } = useField<string>(name);
const fieldRef = useFocusInputField<HTMLInputElement & HTMLTextAreaElement>(name);
const text = value ?? '';
const recommended = attribute.options?.recommendedLength ?? DEFAULT_RECOMMENDED_LENGTH;
const inputProps = { ref: fieldRef, name, value: text, disabled, onChange: handleChange };
return (
  <Field.Root name={name} hint={hint} error={error} required={required}>
    <Flex justifyContent="space-between">
      <Field.Label>{label}</Field.Label>
      <Typography variant="pi" textColor={text.length > recommended ? 'danger600' : 'neutral600'}>
        {text.length} / {recommended}
      </Typography>
    </Flex>
    {attribute.type === 'text' ? <Textarea {...inputProps} /> : <TextInput {...inputProps} />}
    <Field.Hint />
    <Field.Error />
  </Field.Root>
);
```

`handleChange` wywołuje `onChange(name, event.target.value)`. Dokumentacja opisuje propsy `value`, `onChange` i `intlLabel` oraz radzi `forwardRef` dla fokusu, ale `InputRenderer` w 5.56 podaje etykietę jako tekst `label` i nie przekazuje `ref`. Hooki `useField` i `useFocusInputField` z `@strapi/strapi/admin` dają wartość i fokus jawnie, z typami. `attribute` zawiera typ bazowy i opcje: `/content-manager/init` zwrócił dla `metaTitle` `{"type":"string","customField":"global::seo-title","required":true,"maxLength":70,"options":{"recommendedLength":60}}`.

Walidację robi serwer na podstawie typu bazowego; licznik to tylko wskazówka, a `recommendedLength` serwer pomija. Zapis przez REST z pełnym tokenem API:

```text
PUT /api/articles/i7cdjb2elborwn2s23dr4e7h  {"data":{"seo":{"metaTitle":"Policies in Strapi 5: who may edit what", ...}}}
200 "seo": {"id": 10, "metaTitle": "Policies in Strapi 5: who may edit what", "metaDescription": "How route policies ..."}
PUT ... {"data":{"seo":{"metaTitle":"<71 znaków>"}}}  → 400 "seo.metaTitle must be at most 70 characters"
PUT ... {"data":{"seo":{"metaDescription":"no title"}}}  → 400 "seo.metaTitle must be a `string` type, but the final value was: `null`."
```

> **Pułapka:** obie rejestracje muszą się zgadzać. Bez serwerowej Strapi nie wstaje: `Error: Could not find Custom Field: global::seo-title`. Bez rejestracji w panelu serwer działa, a formularz pokazuje zablokowane pole z tekstem `Unsupported field type: global::seo-title` (`NotSupportedField` w `@strapi/admin`). Pole z pluginu ma UID `plugin::<plugin>.<nazwa>`, a `plugin` na serwerze i `pluginId` w panelu muszą mieć tę samą wartość.

Build (około 20 s) wydzielił chunki `seo-length-input-*.js` i `pending-comments-widget-*.js`. Opis zachowania panelu pochodzi z kodu, typów i buildu, nie z klikania.

## Własny edytor treści

Edytor WYSIWYG pola `richtext` (Markdown) wymienisz pluginem z Marketplace (np. z CKEditorem) albo custom fieldem na typie `richtext`, zbudowanym jak licznik SEO. Pole `blocks` z `shared.rich-text` rozszerzasz przez `addRichTextBlocks` w `register`: dodajesz bloki albo usuwasz wbudowane, jak `code` – a frontend musi umieć je wyrenderować.

## Panel pod innym adresem

Inną ścieżkę ustawiasz w `config/admin.ts` przez `url: '/dashboard'`. Od Strapi 5.51 ciasteczko sesji panelu ma domyślnie ścieżkę `/admin`, więc dodaj `auth.cookie.path: '/dashboard'` i przebuduj panel – inaczej, według dokumentacji, każde żądanie po zalogowaniu wraca do ekranu logowania.

Panel na osobnym hoście to statyczne pliki z `dist/build`, np. na CDN, i Strapi jako samo API: absolutne `url` w `config/server.ts` oraz `url: '/'` i `serveAdminPanel: false` w `config/admin.ts`. Z `serveAdminPanel: false` adres `/admin` i pliki panelu zwracały 404, a API panelu działało (`/admin/users/me` z tokenem administratora – 200). Wdrożenia na dwóch domenach nie uruchamiałem; sprawdź przy nim `auth.cookie` (`domain`, `sameSite`), bo sesja panelu żyje w ciasteczkach httpOnly. Reverse proxy i HTTPS – rozdział 13.

## Podsumowanie

- `config` w `src/admin/app.tsx` ustawia języki, tłumaczenia, motyw, logo i powiadomienia; polskie braki spadają do angielskiego.
- `register` panelu dostaje pełny `StrapiApp` (custom fields, widgety), `bootstrap` – wycinek z `getPlugin` dla Content Managera.
- Akcje Content Managera to komponenty zwracające opis, renderowane dla każdego typu treści – filtruj po `model`. Położenie stref wstrzykiwania w 5.56 różni się od dokumentacji.
- Widget to leniwy komponent z ikoną i uprawnieniami; dane bierze z API Content Managera przez `useFetchClient`.
- Custom field to istniejący typ danych z własnym komponentem, rejestrowany na serwerze i w panelu; walidację robi serwer według typu bazowego.
- Zmienne `STRAPI_ADMIN_*` są wpisywane w paczkę przy buildzie i publiczne. `serveAdminPanel: false` wyłącza serwowanie plików panelu, nie jego API.

## Co dalej

Przycisk „Otwórz na stronie” prowadzi na stronę magazynu, której jeszcze nie ma. W rozdziale 11 zbudujesz ją w Next.js, z odświeżaniem cache po publikacji i podglądem szkiców.

## Źródła

- https://docs.strapi.io/cms/admin-panel-customization
- https://docs.strapi.io/cms/admin-panel-customization/locales-translations
- https://docs.strapi.io/cms/admin-panel-customization/theme-extension
- https://docs.strapi.io/cms/admin-panel-customization/logos
- https://docs.strapi.io/cms/admin-panel-customization/bundlers
- https://docs.strapi.io/cms/admin-panel-customization/extension
- https://docs.strapi.io/cms/admin-panel-customization/homepage
- https://docs.strapi.io/cms/admin-panel-customization/wysiwyg-editor
- https://docs.strapi.io/cms/admin-panel-customization/host-port-path
- https://docs.strapi.io/cms/configurations/admin-panel
- https://docs.strapi.io/cms/features/admin-panel
- https://docs.strapi.io/cms/features/custom-fields
- https://docs.strapi.io/cms/plugins-development/admin-panel-api
- https://docs.strapi.io/cms/plugins-development/content-manager-apis
- https://docs.strapi.io/cms/plugins-development/admin-injection-zones
- https://docs.strapi.io/cms/plugins-development/admin-hooks
