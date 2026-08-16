import type { ReactNode } from 'react';

/** Small inline-SVG icon set. All inherit `currentColor` and take an optional size. */

interface IconProps {
  size?: number;
  className?: string;
}

function svg(path: ReactNode, size: number, className?: string) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {path}
    </svg>
  );
}

export function ChevronDown({ size = 14, className }: IconProps) {
  return svg(<polyline points="6 9 12 15 18 9" />, size, className);
}

export function ChevronUp({ size = 14, className }: IconProps) {
  return svg(<polyline points="6 15 12 9 18 15" />, size, className);
}

export function Plus({ size = 14, className }: IconProps) {
  return svg(
    <>
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </>,
    size,
    className,
  );
}

export function Close({ size = 16, className }: IconProps) {
  return svg(
    <>
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </>,
    size,
    className,
  );
}

export function Search({ size = 14, className }: IconProps) {
  return svg(
    <>
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </>,
    size,
    className,
  );
}

export function ArrowRight({ size = 14, className }: IconProps) {
  return svg(
    <>
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </>,
    size,
    className,
  );
}

export function Sun({ size = 15, className }: IconProps) {
  return svg(
    <>
      <circle cx="12" cy="12" r="4" />
      <line x1="12" y1="2" x2="12" y2="4" />
      <line x1="12" y1="20" x2="12" y2="22" />
      <line x1="4.9" y1="4.9" x2="6.3" y2="6.3" />
      <line x1="17.7" y1="17.7" x2="19.1" y2="19.1" />
      <line x1="2" y1="12" x2="4" y2="12" />
      <line x1="20" y1="12" x2="22" y2="12" />
      <line x1="4.9" y1="19.1" x2="6.3" y2="17.7" />
      <line x1="17.7" y1="6.3" x2="19.1" y2="4.9" />
    </>,
    size,
    className,
  );
}

export function Moon({ size = 15, className }: IconProps) {
  return svg(<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />, size, className);
}

export function Folder({ size = 14, className }: IconProps) {
  return svg(
    <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
    size,
    className,
  );
}

export function Doc({ size = 14, className }: IconProps) {
  return svg(
    <>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <polyline points="14 3 14 8 19 8" />
    </>,
    size,
    className,
  );
}

export function Star({ size = 12, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      aria-hidden
    >
      <path d="M12 2l2.9 6.3 6.9.7-5.2 4.6 1.5 6.8L12 17.8 5.9 20.4l1.5-6.8L2.2 9l6.9-.7z" />
    </svg>
  );
}
