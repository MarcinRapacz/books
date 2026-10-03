import Image from 'next/image';
import Link from 'next/link';
import { getArticles, mediaUrl } from '@/lib/strapi';

export default async function HomePage() {
  const articles = await getArticles();
  return (
    <main>
      <h1>Redakcja</h1>
      <ul>
        {articles.map((article) => (
          <li key={article.documentId}>
            {article.cover && (
              <Image
                src={mediaUrl(article.cover)}
                alt={article.cover.alternativeText ?? ''}
                width={article.cover.width}
                height={article.cover.height}
              />
            )}
            <Link href={`/artykuly/${article.slug}`}>{article.title}</Link>
            {article.category && <small> [{article.category.name}]</small>}
            <p>{article.excerpt}</p>
          </li>
        ))}
      </ul>
    </main>
  );
}
