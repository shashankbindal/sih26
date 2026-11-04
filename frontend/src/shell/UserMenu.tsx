import { useNavigate } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { useAuth } from '@/auth';
import { BUREAU_LABEL, ROLE_LABEL } from '@/lib/constants';
import { ICON } from '@/lib/icons';
import { DropdownMenu } from '@/components/ui/DropdownMenu';

/** name · designation · bureau; menu with Sign out. */
export function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  const designation = user.designation ?? ROLE_LABEL[user.role];
  const bureau = user.bureau === 'RO' && user.ro_code ? `RO (${user.ro_code})` : BUREAU_LABEL[user.bureau];
  return (
    <DropdownMenu
      align="right"
      width={260}
      header={
        <div className="text-sm">
          <div className="font-semibold text-ink-900">{user.name}</div>
          <div className="text-xs text-ink-500">{user.email}</div>
        </div>
      }
      items={[
        {
          key: 'out',
          label: 'Sign out',
          onSelect: () => {
            logout();
            navigate('/login', { replace: true });
          },
        },
      ]}
      trigger={({ open, toggle }) => (
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={toggle}
          className="focus-ring flex h-ctl items-center gap-2 rounded border border-transparent px-2 text-left hover:bg-paper"
        >
          <span className="text-sm leading-tight">
            <span className="block font-medium text-ink-900">{user.name}</span>
            <span className="block text-2xs text-ink-500">
              {designation} {'·'} {bureau}
            </span>
          </span>
          <ChevronDown {...ICON} className="text-ink-500" />
        </button>
      )}
    />
  );
}
