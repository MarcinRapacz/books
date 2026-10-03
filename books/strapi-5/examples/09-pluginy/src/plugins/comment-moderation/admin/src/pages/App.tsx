import { Page } from '@strapi/strapi/admin';
import { Routes, Route } from 'react-router-dom';

import { PERMISSIONS } from '../permissions';
import { HomePage } from './HomePage';

const App = () => {
  return (
    <Page.Protect permissions={PERMISSIONS.read}>
      <Routes>
        <Route index element={<HomePage />} />
        <Route path="*" element={<Page.Error />} />
      </Routes>
    </Page.Protect>
  );
};

export default App;
