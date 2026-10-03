import type { Event } from '@strapi/database';

// Experiment from chapter 6: logs every write-level lifecycle event of articles.
// Enable with TRACE_ARTICLE_EVENTS=true; remove once you have seen the numbers.
const trace = (event: Event) => {
  if (process.env.TRACE_ARTICLE_EVENTS !== 'true') return;
  const row = event.result ?? event.params.data ?? {};
  const version = row.publishedAt ? 'published' : row.publishedAt === null ? 'draft' : '?';
  const id = event.result?.id ?? event.params.where?.id ?? '-';
  strapi.log.info(`[lifecycle] ${event.action.padEnd(12)} id=${id} version=${version} trx=${strapi.db.inTransaction()}`);
};

export default {
  beforeCreate: trace,
  afterCreate: trace,
  beforeUpdate: trace,
  afterUpdate: trace,
  beforeDelete: trace,
  afterDelete: trace,
};
