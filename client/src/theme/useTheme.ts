import { useCallback, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'rekord-theme';

/** The theme applied by the no-flash bootstrap in index.html, or light. */
function currentTheme(): Theme {
  const attr = document.documentElement.dataset.theme;
  return attr === 'dark' ? 'dark' : 'light';
}

/**
 * Light/dark theme, persisted to localStorage and reflected onto
 * `<html data-theme>`. Defaults to light (the user's choice); the inline
 * bootstrap in index.html sets the attribute before first paint so there is
 * no flash, and this hook keeps it in sync after the toggle is used.
 */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(currentTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // private mode / storage disabled: the toggle still works this session
    }
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((previous) => (previous === 'light' ? 'dark' : 'light'));
  }, []);

  return { theme, toggle };
}
