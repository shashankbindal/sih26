import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  cloneElement,
} from 'react';
import { cx } from '@/lib/cx';

const control =
  'w-full rounded border border-line bg-surface px-2.5 text-sm text-ink-900 placeholder:text-ink-300 ' +
  'hover:border-ink-300 focus-ring disabled:bg-paper disabled:text-ink-500';
const invalid = 'border-red';

export interface FieldProps {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  children: ReactElement<{ id?: string; 'aria-describedby'?: string; 'aria-invalid'?: boolean }>;
  className?: string;
}

/** Label above control, optional hint and error below. Injects id / aria into the single child control. */
export function Field({ label, hint, error, required, children, className }: FieldProps) {
  const id = useId();
  const descId = `${id}-d`;
  return (
    <div className={cx('flex flex-col gap-1', className)}>
      <label htmlFor={id} className="text-xs font-medium text-ink-700">
        {label}
        {required && (
          <span className="text-red" aria-hidden>
            {' '}
            *
          </span>
        )}
      </label>
      {cloneElement(children, { id, 'aria-describedby': hint || error ? descId : undefined, 'aria-invalid': error ? true : undefined })}
      {(hint || error) && (
        <div id={descId} className={cx('text-xs', error ? 'text-red' : 'text-ink-500')}>
          {error ?? hint}
        </div>
      )}
    </div>
  );
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  mono?: boolean;
}
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input({ className, mono, ...rest }, ref) {
  return (
    <input
      ref={ref}
      className={cx(control, 'h-ctl', mono && 'font-mono tnum', rest['aria-invalid'] && invalid, className)}
      {...rest}
    />
  );
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...rest }, ref) {
  return (
    <select ref={ref} className={cx(control, 'h-ctl pr-7', rest['aria-invalid'] && invalid, className)} {...rest}>
      {children}
    </select>
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, rows = 4, ...rest }, ref) {
  return <textarea ref={ref} rows={rows} className={cx(control, 'py-1.5 leading-snug', rest['aria-invalid'] && invalid, className)} {...rest} />;
});

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: ReactNode;
}
export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox({ label, className, id, ...rest }, ref) {
  const auto = useId();
  const cid = id ?? auto;
  return (
    <label htmlFor={cid} className={cx('inline-flex min-h-ctl cursor-pointer items-center gap-2 text-sm text-ink-900', className)}>
      <input ref={ref} id={cid} type="checkbox" className="focus-ring h-4 w-4 accent-navy" {...rest} />
      <span>{label}</span>
    </label>
  );
});
