import * as React from 'react';
import { Box, Flex, Typography } from '@strapi/design-system';
import { Widget, useFetchClient } from '@strapi/strapi/admin';

interface PendingComment {
  documentId: string;
  body: string;
  createdAt: string;
}

interface CommentListResponse {
  results: PendingComment[];
  pagination: { total: number };
}

type WidgetState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; comments: PendingComment[]; total: number };

const PendingCommentsWidget = () => {
  const { get } = useFetchClient();
  const [state, setState] = React.useState<WidgetState>({ status: 'loading' });

  React.useEffect(() => {
    // Content Manager admin API: the editor's own RBAC permissions apply.
    get<CommentListResponse>('/content-manager/collection-types/api::comment.comment', {
      params: {
        filters: { moderationStatus: { $eq: 'pending' } },
        sort: 'createdAt:ASC',
        pageSize: 5,
      },
    })
      .then(({ data }) =>
        setState({ status: 'ready', comments: data.results, total: data.pagination.total })
      )
      .catch(() => setState({ status: 'error' }));
  }, [get]);

  if (state.status === 'loading') return <Widget.Loading />;
  if (state.status === 'error') return <Widget.Error />;
  if (state.total === 0) return <Widget.NoData>Brak komentarzy w kolejce</Widget.NoData>;

  return (
    <Flex direction="column" alignItems="stretch" gap={2}>
      <Typography variant="omega" fontWeight="bold">
        Czeka na moderację: {state.total}
      </Typography>
      {state.comments.map((comment) => (
        <Box key={comment.documentId} padding={2} background="neutral100" hasRadius>
          <Typography ellipsis>{comment.body}</Typography>
        </Box>
      ))}
    </Flex>
  );
};

export default PendingCommentsWidget;
