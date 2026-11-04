import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { Link, type LinkProps } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import { cx } from '@/lib/cx';
import { ICON } from '@/lib/icons';

export type ButtonVariant = 'primary' | 'secondary' | 'tertiary' | 'danger';

const base =
  'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded text-sm font-medium select-none ' +
  'focus-ring disabled:cursor-not-allowed disabled:opacity-50';

const variants: Record<ButtonVariant, string> = {
  primary: 'h-ctl px-3 bg-navy text-surface border border-navy hover:bg-ink-700 hover:border-ink-700',
  secondary: 'h-ctl px-3 bg-surface text-ink-900 border border-line hover:bg-paper',
  tertiary: 'h-auto px-0 text-navy border border-transparent hover:underline',
  danger: 'h-ctl px-3 bg-red text-surface border border-red hover:opacity-90',
};

export function buttonClass(variant: ButtonVariant = 'secondary', extra?: string): string {
  return cx(base, variants[variant], extra);
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  icon?: LucideIcon;
  loading?: boolean;
  children?: ReactNode;
}

/** 32px, radius 4. Icon-only buttons must pass aria-label (and wrap in Tooltip). */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', icon: Icon, loading, disabled, className, children, type = 'button', ...rest },
  ref,
) {
  return (
    <button ref={ref} type={type} disabled={disabled || loading} className={buttonClass(variant, className)} {...rest}>
      {Icon && <Icon {...ICON} />}
      {loading ? 'Working…' : children}
    </button>
  );
});

export interface ButtonLinkProps extends LinkProps {
  variant?: ButtonVariant;
  icon?: LucideIcon;
}

/** Router link styled as a button. */
export function ButtonLink({ variant = 'secondary', icon: Icon, className, children, ...rest }: ButtonLinkProps) {
  return (
    <Link className={cx(buttonClass(variant, className), 'hover:no-underline')} {...rest}>
      {Icon && <Icon {...ICON} />}
      {children}
    </Link>
  );
}
