'use client';

import { useEffect, useState } from 'react';
import qs from 'qs';

type Comment = { documentId: string; body: string; createdAt: string };

// Runs in the browser: no API token here, only what the Public role may read.
export function Comments({ articleId }: { articleId: string }) {
  const [comments, setComments] = useState<Comment[] | 'error' | null>(null);

  useEffect(() => {
    const query = qs.stringify(
      {
        fields: ['body', 'createdAt'],
        filters: { article: { documentId: { $eq: articleId } }, moderationStatus: { $eq: 'approved' } },
        sort: ['createdAt:asc'],
      },
      { encodeValuesOnly: true },
    );
    fetch(`${process.env.NEXT_PUBLIC_STRAPI_URL}/api/comments?${query}`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`))))
      .then((json: { data: Comment[] }) => setComments(json.data))
      .catch((error: unknown) => {
        console.error('Loading comments failed', error);
        setComments('error');
      });
  }, [articleId]);

  if (comments === null) return <p>Ładowanie komentarzy…</p>;
  if (comments === 'error') return <p>Nie udało się wczytać komentarzy.</p>;
  return (
    <ul>
      {comments.map((comment) => (
        <li key={comment.documentId}>{comment.body}</li>
      ))}
    </ul>
  );
}
