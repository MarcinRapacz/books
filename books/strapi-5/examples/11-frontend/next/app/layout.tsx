import type { Metadata } from 'next';
import { draftMode } from 'next/headers';

export const metadata: Metadata = {
  title: 'Redakcja',
  description: 'Magazyn technologiczny',
};

export default async function RootLayout({ children }: LayoutProps<'/'>) {
  const { isEnabled: isDraft } = await draftMode();
  return (
    <html lang="pl">
      <body>
        {isDraft && (
          <form action="/api/preview/exit" method="post" role="status">
            Podgląd szkiców <button type="submit">Wyłącz</button>
          </form>
        )}
        {children}
      </body>
    </html>
  );
}
