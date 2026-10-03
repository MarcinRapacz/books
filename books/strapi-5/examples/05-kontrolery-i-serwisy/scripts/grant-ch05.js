'use strict';

// Grants the permissions used in chapter 5: the public "related" action and an Editor role
// (user "ewa", password Passw0rd!) that may approve comments. Run with the server stopped.
const { createStrapi, compileStrapi } = require('@strapi/strapi');

const RELATED = 'api::article.article.related';
const APPROVE = 'api::comment.comment.approve';

async function grant(strapi, roleId, actions) {
  const permissions = strapi.db.query('plugin::users-permissions.permission');
  for (const action of actions) {
    if (!(await permissions.findOne({ where: { action, role: roleId } }))) {
      await permissions.create({ data: { action, role: roleId } });
    }
  }
}

async function run(strapi) {
  const roles = strapi.db.query('plugin::users-permissions.role');
  for (const type of ['public', 'authenticated']) {
    const role = await roles.findOne({ where: { type } });
    await grant(strapi, role.id, [RELATED]);
  }
  const editor =
    (await roles.findOne({ where: { type: 'editor' } })) ??
    (await roles.create({ data: { name: 'Editor', type: 'editor', description: 'Moderates comments' } }));
  await grant(strapi, editor.id, ['api::comment.comment.find', APPROVE]);

  const users = strapi.db.query('plugin::users-permissions.user');
  if (!(await users.findOne({ where: { username: 'ewa' } }))) {
    await strapi.plugin('users-permissions').service('user').add({
      username: 'ewa',
      email: 'ewa@example.com',
      password: 'Passw0rd!',
      provider: 'local',
      confirmed: true,
      blocked: false,
      role: editor.id,
    });
  }
}

async function main() {
  const app = await createStrapi(await compileStrapi()).load();
  app.log.level = 'error';
  try {
    await run(app);
    console.log('grant-ch05: ok');
  } finally {
    await app.destroy();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
