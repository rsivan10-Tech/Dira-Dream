# Hebrew RTL Implementation Guide

## HTML Setup

```html
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;700&display=swap"
        rel="stylesheet" />
  <title>DiraDream — דירה דרים</title>
</head>
```

## CSS Logical Properties

ALWAYS use logical properties instead of physical directional properties:

| Physical (DON'T) | Logical (DO) |
|-------------------|--------------|
| `margin-left` | `margin-inline-start` |
| `margin-right` | `margin-inline-end` |
| `padding-left` | `padding-inline-start` |
| `padding-right` | `padding-inline-end` |
| `text-align: left` | `text-align: start` |
| `text-align: right` | `text-align: end` |
| `float: left` | `float: inline-start` |
| `float: right` | `float: inline-end` |
| `border-left` | `border-inline-start` |
| `border-right` | `border-inline-end` |
| `left: 10px` | `inset-inline-start: 10px` |
| `right: 10px` | `inset-inline-end: 10px` |

### Block vs Inline
- **Inline** = reading direction (RTL in Hebrew)
- **Block** = perpendicular (top-to-bottom, same as LTR)
- `inline-start` = right side in RTL
- `inline-end` = left side in RTL

## Heebo Font Setup

```css
:root {
  --font-family: 'Heebo', sans-serif;
  --font-weight-light: 300;
  --font-weight-regular: 400;
  --font-weight-medium: 500;
  --font-weight-bold: 700;
}

body {
  font-family: var(--font-family);
  font-weight: var(--font-weight-regular);
  direction: rtl;
  text-align: start;
}

h1, h2, h3, h4, h5, h6 {
  font-weight: var(--font-weight-bold);
}
```

## React-Intl Configuration

### Setup (main.tsx)
```tsx
import { IntlProvider } from 'react-intl';
import messages_he from './i18n/he.json';

const App = () => (
  <IntlProvider locale="he" messages={messages_he}>
    <AppContent />
  </IntlProvider>
);
```

### Message file (i18n/he.json)
```json
{
  "app.title": "דירה דרים",
  "app.subtitle": "תכנון דירה חכם",
  "upload.title": "העלאת תוכנית",
  "upload.button": "בחר קובץ PDF",
  "upload.dragDrop": "גרור קובץ לכאן",
  "upload.processing": "מעבד תוכנית...",
  "upload.error.notPdf": "יש להעלות קובץ PDF בלבד",
  "upload.error.noPaths": "הקובץ אינו מכיל שרטוט וקטורי",
  "rooms.salon": "סלון",
  "rooms.bedroom": "חדר שינה",
  "rooms.masterBedroom": "חדר שינה הורים",
  "rooms.kitchen": "מטבח",
  "rooms.bathroom": "חדר רחצה",
  "rooms.mamad": "ממ\"ד",
  "rooms.balcony": "מרפסת",
  "rooms.storage": "מחסן",
  "rooms.hallway": "מסדרון",
  "rooms.entrance": "כניסה",
  "common.area": "שטח",
  "common.sqm": "מ\"ר",
  "common.confidence": "רמת ודאות",
  "common.save": "שמור",
  "common.cancel": "ביטול",
  "common.close": "סגור",
  "common.loading": "טוען...",
  "common.error": "שגיאה"
}
```

### Usage in Components
```tsx
import { useIntl, FormattedMessage } from 'react-intl';

const RoomLabel = ({ room }) => {
  const intl = useIntl();

  return (
    <div>
      <FormattedMessage id={`rooms.${room.type}`} />
      <span>{formatArea(room.area_sqm)} {intl.formatMessage({ id: 'common.sqm' })}</span>
    </div>
  );
};
```

## Number Formatting

### Rules
- Use **Western (Arabic) digits**: 0-9 (not Hebrew numerals)
- Decimal separator: **period** (.)
- Thousands separator: **comma** (,)
- Currency: **ILS (₪)** — symbol AFTER number in Hebrew (e.g., `150,000 ₪`)
- Area: **sqm (מ"ר)** — unit AFTER number (e.g., `12.5 מ"ר`)
- Dimensions: **cm** — unit AFTER number (e.g., `320 ס"מ`)
- Date: **DD/MM/YYYY** (e.g., `09/04/2026`)

### Formatting Functions
```typescript
export function formatArea(sqm: number): string {
  return sqm.toFixed(1);  // "12.5"
}

export function formatDimension(cm: number): string {
  return Math.round(cm).toString();  // "320"
}

export function formatCurrency(ils: number): string {
  return ils.toLocaleString('he-IL');  // "150,000"
}

export function formatCurrencyRange(min: number, max: number): string {
  return `${formatCurrency(min)} - ${formatCurrency(max)} ₪`;
}

export function formatDate(date: Date): string {
  return date.toLocaleDateString('he-IL');  // "09/04/2026"
}

export function formatConfidence(score: number): string {
  // Display confidence as percentage
  return `${score}%`;
}
```

## Layout Rules for DiraDream

### RTL Layout
- **Sidebar**: LEFT side (end in RTL)
- **Main canvas**: RIGHT side (start in RTL)
- **Properties panel**: LEFT side below sidebar
- **Toolbar**: Top, items flow RIGHT-to-LEFT

```css
.app-layout {
  display: flex;
  flex-direction: row-reverse; /* RTL: canvas on right, sidebar on left */
}

.sidebar {
  width: 320px;
  order: 1; /* Appears on left in RTL */
}

.canvas-area {
  flex: 1;
  order: 0; /* Appears on right in RTL */
}
```

### Canvas Coordinates
- **Canvas (Konva.js) remains LTR** — coordinate system is mathematical, not linguistic
- (0,0) at top-left of canvas, X increases right, Y increases down
- Only UI chrome (buttons, labels, panels) follows RTL
- Room labels on canvas render Hebrew text but position using LTR coordinates

### Icons
- **DO mirror**: Back arrow, forward arrow, navigation chevrons
- **DO NOT mirror**: Play/pause, media controls, clock, checkmarks, search magnifier
- **DO NOT mirror**: Mathematical symbols, chart axes

## Accessibility (Hebrew-specific)

```tsx
// Hebrew ARIA labels
<button aria-label="העלאת קובץ PDF">
  <UploadIcon />
</button>

<nav aria-label="ניווט ראשי">
  {/* Navigation items */}
</nav>

<div role="status" aria-live="polite">
  <FormattedMessage id="upload.processing" />
</div>
```

- All ARIA labels in Hebrew
- `aria-live` regions for dynamic content updates
- Keyboard navigation: Tab order follows visual RTL flow
- Focus indicators visible on all interactive elements
- Screen reader announces Hebrew text naturally
