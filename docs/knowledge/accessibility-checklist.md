# Accessibility Checklist — WCAG AA + Israeli Teken 5568

## Hebrew-Specific Accessibility

### ARIA Labels
All interactive elements must have Hebrew ARIA labels:

```tsx
// Buttons
<button aria-label="העלאת קובץ PDF">
<button aria-label="שמירת שינויים">
<button aria-label="ביטול">

// Navigation
<nav aria-label="ניווט ראשי">
<nav aria-label="ניווט משני">

// Regions
<main aria-label="תצוגת תוכנית">
<aside aria-label="פרטי חדר">
<section aria-label="רשימת חדרים">

// Status updates
<div role="status" aria-live="polite" aria-label="סטטוס עיבוד">
<div role="alert" aria-label="הודעת שגיאה">

// Canvas
<div role="img" aria-label="תוכנית דירה אינטראקטיבית">
```

### Screen Reader Support
- Announce room type and area when room is focused
- Announce wall type and confidence when wall is selected
- Announce modification cost range when viewing modifications
- Progress indicators for long operations (extraction, healing)
- Hebrew number reading: screen readers handle Western digits in Hebrew context

### Keyboard Navigation
- `Tab`: Navigate between interactive elements (follows visual RTL flow)
- `Shift+Tab`: Navigate backward
- `Enter`/`Space`: Activate buttons, toggle selections
- `Arrow keys`: Navigate within canvas (pan), move furniture
- `Escape`: Close dialogs, deselect
- `+`/`-`: Zoom in/out on canvas
- `Delete`: Remove selected furniture item
- `Ctrl+Z`/`Ctrl+Y`: Undo/Redo

```tsx
const handleKeyDown = (e: KeyboardEvent) => {
  switch (e.key) {
    case 'Tab':
      // Ensure focus ring is visible
      document.body.classList.add('keyboard-nav');
      break;
    case 'Escape':
      setSelectedItem(null);
      closeDialog();
      break;
    case '+':
    case '=':
      zoomIn();
      break;
    case '-':
      zoomOut();
      break;
  }
};
```

## Color & Contrast

### WCAG AA Requirements
- **Text contrast**: Minimum 4.5:1 ratio for normal text
- **Large text**: Minimum 3:1 ratio (18px+ or 14px+ bold)
- **UI components**: Minimum 3:1 ratio against background
- **Focus indicators**: Visible, high-contrast focus ring

### Color-Blind Safe Palette
NEVER rely on color alone to convey information. Always pair with:
- Icons, patterns, or labels
- Different shapes for different wall types
- Text labels alongside color indicators

```css
/* Wall type indicators - accessible palette */
:root {
  --wall-exterior: #1a1a1a;      /* Dark - visible to all */
  --wall-mamad: #cc0000;         /* Red + hatching pattern */
  --wall-structural: #ff8800;    /* Orange + dashed line */
  --wall-partition: #4a90d9;     /* Blue + solid line */
  --wall-unknown: #999999;       /* Gray + dotted line */

  /* Confidence indicators */
  --confidence-high: #2e7d32;    /* Green + checkmark icon */
  --confidence-medium: #f57f17;  /* Amber + question icon */
  --confidence-low: #c62828;     /* Red + warning icon */
}
```

**Pattern alternatives for color-blind users**:
- Structural walls: dashed border pattern
- Partition walls: solid line
- Mamad walls: cross-hatch pattern
- Unknown walls: dotted pattern

### Confidence Display
Must be understandable without color:
```tsx
const ConfidenceIndicator = ({ score }: { score: number }) => {
  const level = score >= 85 ? 'high' : score >= 50 ? 'medium' : 'low';
  const icon = { high: '✓', medium: '?', low: '!' }[level];
  const label = {
    high: 'ודאות גבוהה',
    medium: 'ודאות בינונית',
    low: 'ודאות נמוכה'
  }[level];

  return (
    <span
      className={`confidence confidence--${level}`}
      aria-label={`${label}: ${score}%`}
      role="status"
    >
      <span className="confidence__icon">{icon}</span>
      <span className="confidence__score">{score}%</span>
      <span className="confidence__label">{label}</span>
    </span>
  );
};
```

## Touch Targets

### Minimum Sizes
- All interactive elements: **44x44px minimum** touch target
- Spacing between targets: **8px minimum**
- Canvas interaction handles: **44x44px minimum** hit area

```css
button, a, [role="button"] {
  min-width: 44px;
  min-height: 44px;
  padding: 8px 16px;
}

/* Even if visually smaller, maintain touch target */
.icon-button {
  position: relative;
  width: 24px;
  height: 24px;
}
.icon-button::after {
  content: '';
  position: absolute;
  inset: -10px;  /* Expand touch target to 44px */
}
```

## Focus Management

```css
/* Focus ring - visible on all backgrounds */
:focus-visible {
  outline: 3px solid #2196F3;
  outline-offset: 2px;
}

/* Remove default outline only when using mouse */
:focus:not(:focus-visible) {
  outline: none;
}

/* High visibility focus for dark backgrounds */
.dark-bg :focus-visible {
  outline: 3px solid #ffffff;
  box-shadow: 0 0 0 6px rgba(0, 0, 0, 0.5);
}
```

## Form Accessibility

```tsx
// Input with Hebrew label
<div className="form-field">
  <label htmlFor="apartment-name" id="apartment-name-label">
    שם הדירה
  </label>
  <input
    id="apartment-name"
    type="text"
    aria-labelledby="apartment-name-label"
    aria-describedby="apartment-name-help"
    aria-required="true"
  />
  <span id="apartment-name-help" className="help-text">
    לדוגמה: דירת 4 חדרים, רמת גן
  </span>
</div>

// Error state
<input
  aria-invalid="true"
  aria-errormessage="email-error"
/>
<span id="email-error" role="alert">
  כתובת דוא"ל לא תקינה
</span>
```

## Motion & Animation

```css
/* Respect user preference for reduced motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

## Testing Checklist

- [ ] All images have alt text (Hebrew)
- [ ] All form inputs have labels
- [ ] All buttons have accessible names
- [ ] Color contrast passes WCAG AA (4.5:1)
- [ ] Keyboard navigation works for all features
- [ ] Focus order follows visual layout (RTL)
- [ ] Screen reader announces dynamic content changes
- [ ] Touch targets are 44x44px minimum
- [ ] Information not conveyed by color alone
- [ ] Error messages are descriptive in Hebrew
- [ ] Modals trap focus and return it on close
- [ ] Page title updates with context
- [ ] `lang="he"` set on html element
- [ ] `dir="rtl"` set on html element
- [ ] Skip navigation link available
- [ ] Heading hierarchy is logical (h1→h2→h3)
- [ ] Zoom to 200% doesn't break layout
