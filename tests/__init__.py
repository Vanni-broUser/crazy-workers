import logging
import os
import sys
import warnings


# Suppress logging during tests to avoid confusing output
logging.getLogger('crazy_workers').setLevel(logging.CRITICAL)

# Never touch the host's init system during the suite. Boot-restore tests clear
# this explicitly to exercise the real install/inspection logic with fakes.
os.environ.setdefault('CRAZY_WORKERS_NO_BOOT', '1')

# Suppress ResourceWarnings for orphaned subprocesses (intended behavior)
warnings.filterwarnings('ignore', category=ResourceWarning)

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
