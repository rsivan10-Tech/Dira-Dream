import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import App from './App';

describe('App', () => {
  it('renders Hebrew title', () => {
    render(<App />);
    expect(screen.getByText('דירה דרים')).toBeInTheDocument();
  });

  it('renders upload button', () => {
    render(<App />);
    expect(screen.getByText('בחר קובץ PDF')).toBeInTheDocument();
  });

  it('has RTL document direction', () => {
    render(<App />);
    const main = screen.getByRole('main');
    expect(main).toHaveAttribute('aria-label', 'תצוגת תוכנית');
  });
});
