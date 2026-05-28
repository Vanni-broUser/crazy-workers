import logging
import os
import sys
import warnings

# Suppress logging during tests to avoid confusing output
logging.getLogger('crazy_workers').setLevel(logging.CRITICAL)

# Suppress ResourceWarnings for orphaned subprocesses (intended behavior)
warnings.filterwarnings('ignore', category=ResourceWarning)

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
