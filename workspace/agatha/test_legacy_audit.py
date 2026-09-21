#!/usr/bin/env python3
"""One-shot test of the legacy dual-convention audit (verify-only, no Kraken)."""
import sweep_audit

unres = sweep_audit.phase_legacy()
print('TOTAL UNRESOLVED:', len(unres))
print('audit_legacy_done =', open(sweep_audit.AUDIT_LEGACY).read().strip())
for u in unres[:20]:
    print(' ', u.get('volume'), u.get('leaf'), u.get('side'), u.get('issue'))
