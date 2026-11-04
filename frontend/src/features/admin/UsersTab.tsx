import { Badge, DataTable, type Column } from '@/components/ui';
import { BureauTag } from '@/components/domain';
import { useApiQuery } from '@/api/hooks';
import { ROLE_LABEL, type Bureau, type Role } from '@/lib/constants';

interface AdminUser {
  id: string;
  email: string;
  name: string;
  designation?: string | null;
  role: Role;
  bureau: Bureau;
  ro_code?: string | null;
  is_active: boolean;
}

export function UsersTab() {
  const q = useApiQuery<AdminUser[]>(['admin', 'users'], '/admin/users');
  const columns: Column<AdminUser>[] = [
    { key: 'name', header: 'Name', sortable: true, sortValue: (u) => u.name, render: (u) => <span className="font-medium">{u.name}</span> },
    { key: 'designation', header: 'Designation', render: (u) => u.designation ?? '–' },
    { key: 'email', header: 'Email', mono: true, render: (u) => u.email },
    { key: 'role', header: 'Role', sortable: true, sortValue: (u) => u.role, render: (u) => ROLE_LABEL[u.role] ?? u.role },
    { key: 'bureau', header: 'Bureau', render: (u) => <BureauTag bureau={u.bureau} roCode={u.ro_code} /> },
    { key: 'active', header: 'Status', render: (u) => <Badge tone={u.is_active ? 'ok' : 'neutral'}>{u.is_active ? 'Active' : 'Inactive'}</Badge> },
  ];
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-ink-700">Demo accounts for this prototype. Passwords are not shown or editable here.</p>
      <DataTable
        compact
        caption="Users"
        columns={columns}
        rows={q.data}
        rowKey={(u) => u.id}
        loading={q.isLoading}
        errorMessage={q.error ? `Could not load users. ${q.error.message}` : undefined}
        emptyMessage="No users found."
      />
    </div>
  );
}
