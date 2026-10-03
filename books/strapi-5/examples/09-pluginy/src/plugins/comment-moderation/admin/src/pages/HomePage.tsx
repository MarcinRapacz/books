import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  EmptyStateLayout,
  Flex,
  Table,
  Tbody,
  Td,
  Th,
  Thead,
  Tr,
  Typography,
} from '@strapi/design-system';
import { Layouts, Page, useFetchClient, useNotification, useRBAC } from '@strapi/strapi/admin';

import { PERMISSIONS } from '../permissions';

type PendingComment = {
  documentId: string;
  body: string;
  createdAt?: string;
  article: string | null;
  author: string | null;
};

type PendingResponse = {
  results: PendingComment[];
  pagination: { page: number; pageSize: number; total: number };
};

type Decision = 'approve' | 'reject';

const HomePage = () => {
  const { get, put } = useFetchClient();
  const { toggleNotification } = useNotification();
  const {
    isLoading: isLoadingPermissions,
    allowedActions: { canModerate },
  } = useRBAC({ moderate: PERMISSIONS.moderate });
  const [data, setData] = useState<PendingResponse | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      // Admin routes of a plugin live under /<plugin-name>, without the /api prefix.
      const response = await get<PendingResponse>('/comment-moderation/comments/pending');
      setData(response.data);
    } catch {
      setError(true);
    }
  }, [get]);

  useEffect(() => {
    load();
  }, [load]);

  const decide = async (documentId: string, decision: Decision) => {
    try {
      await put(`/comment-moderation/comments/${documentId}/${decision}`);
      toggleNotification({ type: 'success', message: decision === 'approve' ? 'Comment approved' : 'Comment rejected' });
    } catch {
      toggleNotification({ type: 'danger', message: 'The comment could not be updated' });
    }
    await load();
  };

  if (error) {
    return <Page.Error />;
  }
  if (!data || isLoadingPermissions) {
    return <Page.Loading />;
  }

  return (
    <Page.Main>
      <Page.Title>Comment moderation</Page.Title>
      <Layouts.Header
        title="Comment moderation"
        subtitle={`${data.pagination.total} comments waiting for review`}
      />
      <Layouts.Content>
        {data.results.length === 0 ? (
          <EmptyStateLayout content="No comments waiting for moderation" />
        ) : (
          <Table colCount={5} rowCount={data.results.length + 1}>
            <Thead>
              <Tr>
                <Th><Typography variant="sigma">Comment</Typography></Th>
                <Th><Typography variant="sigma">Article</Typography></Th>
                <Th><Typography variant="sigma">Author</Typography></Th>
                <Th><Typography variant="sigma">Created</Typography></Th>
                <Th><Typography variant="sigma">Decision</Typography></Th>
              </Tr>
            </Thead>
            <Tbody>
              {data.results.map((comment) => (
                <Tr key={comment.documentId}>
                  <Td><Typography>{comment.body}</Typography></Td>
                  <Td><Typography>{comment.article ?? '–'}</Typography></Td>
                  <Td><Typography>{comment.author ?? '–'}</Typography></Td>
                  <Td>
                    <Typography>
                      {comment.createdAt ? new Date(comment.createdAt).toLocaleString() : '–'}
                    </Typography>
                  </Td>
                  <Td>
                    <Flex gap={2}>
                      <Button
                        size="S"
                        disabled={!canModerate}
                        onClick={() => decide(comment.documentId, 'approve')}
                      >
                        Approve
                      </Button>
                      <Button
                        size="S"
                        variant="danger-light"
                        disabled={!canModerate}
                        onClick={() => decide(comment.documentId, 'reject')}
                      >
                        Reject
                      </Button>
                    </Flex>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </Layouts.Content>
    </Page.Main>
  );
};

export { HomePage };
