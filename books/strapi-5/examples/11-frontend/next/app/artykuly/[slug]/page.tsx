import Image from 'next/image';
import { notFound } from 'next/navigation';
import { getArticle, mediaUrl, type ArticleBlock } from '@/lib/strapi';
import { Comments } from './comments';

function Block({ block }: { block: ArticleBlock }) {
  switch (block.__component) {
    case 'shared.rich-text':
      return block.body.map((node, index) => (
        <p key={index}>{node.children.map((child) => child.text ?? '').join('')}</p>
      ));
    case 'shared.quote':
      return <blockquote>{block.body}</blockquote>;
    case 'shared.media':
      return block.file ? (
        <Image
          src={mediaUrl(block.file)}
          alt={block.file.alternativeText ?? ''}
          width={block.file.width}
          height={block.file.height}
        />
      ) : null;
  }
}

export default async function ArticlePage({ params }: PageProps<'/artykuly/[slug]'>) {
  const { slug } = await params;
  const article = await getArticle(slug);
  if (!article) notFound();

  return (
    <article>
      <h1>{article.title}</h1>
      <p>{article.excerpt}</p>
      {article.content.map((block) => (
        <Block key={`${block.__component}-${block.id}`} block={block} />
      ))}
      <Comments articleId={article.documentId} />
    </article>
  );
}
