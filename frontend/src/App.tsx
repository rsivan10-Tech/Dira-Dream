import { IntlProvider, FormattedMessage } from 'react-intl';
import messages_he from './i18n/he.json';

function App() {
  return (
    <IntlProvider locale="he" messages={messages_he}>
      <div className="app-layout">
        <main className="canvas-area" aria-label="תצוגת תוכנית">
          <h1><FormattedMessage id="app.title" /></h1>
          <p><FormattedMessage id="app.subtitle" /></p>
        </main>
        <aside className="sidebar" aria-label="כלים">
          <h2><FormattedMessage id="upload.title" /></h2>
          <button aria-label="העלאת קובץ PDF">
            <FormattedMessage id="upload.button" />
          </button>
        </aside>
      </div>
    </IntlProvider>
  );
}

export default App;
