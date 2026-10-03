import { Typography } from '@strapi/design-system';
import { unstable_useContentManagerContext as useContentManagerContext, useField } from '@strapi/strapi/admin';

// Rendered in the `editView.right-links` injection zone, i.e. for every content type.
export const CoverReminder = () => {
  const { model } = useContentManagerContext();
  const { value: cover } = useField('cover');
  if (model !== 'api::article.article' || cover) {
    return null;
  }
  return (
    <Typography variant="pi" textColor="warning600">
      Artykuł nie ma okładki – na stronie głównej pojawi się bez zdjęcia.
    </Typography>
  );
};
