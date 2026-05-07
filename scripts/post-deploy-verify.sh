#!/bin/bash

# Post-deploy verification: Diameter fix, health check, UPF GTP-U counter test.
# Called automatically after stack deployment (from GUI or manually).
# Runs non-interactively — auto-heals and retries up to 3 times.
#
# Usage: ./scripts/post-deploy-verify.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

echo ""
echo "============================================"
echo "  Post-Deploy Verification"
echo "============================================"
echo ""

# Diagnostic toolbelt audit — gates everything else. If any NF is
# missing a probe-required binary, the Investigator will silently
# degrade later; fail the deploy now so the operator notices.
# See docs/ADR/nf_container_diagnostic_tooling.md.
echo "--- Diagnostic toolbelt audit ---"
if ! "$SCRIPT_DIR/audit-container-tooling.sh" --skip-absent; then
    echo ""
    echo "============================================"
    echo "  POST-DEPLOY VERIFICATION FAILED"
    echo "============================================"
    echo ""
    echo "  Diagnostic toolbelt audit failed — at least one NF is"
    echo "  missing a binary required by Investigator probes. Rebuild"
    echo "  the affected images and redeploy."
    exit 1
fi
echo ""

# Run the Python verification (Diameter fix, health check, UPF counters)
.venv/bin/python -c "
import asyncio, sys, logging
sys.path.insert(0, '.')
sys.path.insert(0, 'gui')
logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')

from common.stack_health import post_deploy_verify

async def main():
    ok = await post_deploy_verify(max_attempts=3)
    if ok:
        print()
        print('============================================')
        print('  All verification passed')
        print('============================================')
        sys.exit(0)
    else:
        print()
        print('============================================')
        print('  VERIFICATION FAILED')
        print('============================================')
        print()
        print('  Check the logs above for details.')
        print('  Common issues:')
        print('    - UPF GTP counters at 0: rebuild docker_open5gs from source')
        print('    - IMS registration failed: check Diameter peer state')
        print('    - PDU sessions missing: restart UEs')
        sys.exit(1)

asyncio.run(main())
"
