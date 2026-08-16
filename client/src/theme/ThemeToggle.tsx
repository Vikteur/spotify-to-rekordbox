import { Moon, Sun } from '../components/Icons';
import { useTheme } from './useTheme';

/** Light/dark switch. Lives in the sidebar footer; the app defaults to light. */
export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === 'light' ? 'dark' : 'light';
  return (
    <button className="theme-toggle" onClick={toggle} title={`Switch to ${next} theme`} aria-label={`Switch to ${next} theme`}>
      {theme === 'light' ? <Moon /> : <Sun />}
      <span>{theme === 'light' ? 'Booth mode' : 'Light mode'}</span>
    </button>
  );
}
