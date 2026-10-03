'use strict';

// Runs before the schema sync, so it still sees the old `excerpt` column.
async function up(knex) {
  const hasOld = await knex.schema.hasColumn('articles', 'excerpt');
  const hasNew = await knex.schema.hasColumn('articles', 'lead');
  if (hasOld && !hasNew) {
    await knex.schema.alterTable('articles', (table) => {
      table.renameColumn('excerpt', 'lead');
    });
  }
}

module.exports = { up };
