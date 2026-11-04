import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, errorMessage } from '@/api/client';
import { useAuth } from '@/auth';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { useToast } from '@/components/ui/Toast';
import { DEMO_MODE } from '@/lib/env';

/** 11px neutral strip, DEMO_MODE only. "Reset demo" needs an admin session and an explicit confirm. */
export function EnvBar() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const { toast } = useToast();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!DEMO_MODE) return null;

  const reset = async () => {
    setBusy(true);
    try {
      await api.post('/admin/reset-demo', { confirm: true });
      await qc.invalidateQueries();
      toast('Demo data reset to the seeded state.', 'ok');
      setConfirm(false);
    } catch (e) {
      toast(errorMessage(e), 'red');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-envbar shrink-0 items-center justify-between border-b border-line bg-neutral-bg px-4 text-2xs text-ink-700">
      <span>
        Prototype {'·'} synthetic data modelled on AICTE Permanent ID format
        {user && (
          <>
            {' '}
            {'·'}{' '}
            <button
              type="button"
              onClick={() => setConfirm(true)}
              className="focus-ring text-navy underline"
              style={{ background: 'none', border: 0, padding: 0, font: 'inherit' }}
            >
              Reset demo
            </button>
          </>
        )}
      </span>
      <Modal
        open={confirm}
        onClose={() => setConfirm(false)}
        title="Reset demo data"
        footer={
          <>
            <Button onClick={() => setConfirm(false)}>Cancel</Button>
            <Button variant="danger" onClick={reset} loading={busy}>
              Reset demo data
            </Button>
          </>
        }
      >
        This replaces all cases, links and Passport entries with the deterministic seeded set. Changes made in this session are lost.
      </Modal>
    </div>
  );
}
