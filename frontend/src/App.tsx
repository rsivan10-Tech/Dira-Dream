import { IntlProvider } from 'react-intl';
import messages_he from './i18n/he.json';
import DebugViewer from './canvas/DebugViewer';

function App() {
  return (
    <IntlProvider locale="he" messages={messages_he}>
      <DebugViewer />
    </IntlProvider>
  );
}

export default App;
