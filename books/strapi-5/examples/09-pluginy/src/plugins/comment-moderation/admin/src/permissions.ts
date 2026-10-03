// Action UIDs registered by the server in bootstrap(): plugin::<plugin-name>.<uid>.
export const PERMISSIONS = {
  read: [{ action: 'plugin::comment-moderation.read', subject: null }],
  moderate: [{ action: 'plugin::comment-moderation.moderate', subject: null }],
};
