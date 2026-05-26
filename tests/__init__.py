import logging
import os
import sys

# Suppress logging during tests to avoid confusing output
logging.getLogger('crazy_workers').setLevel(logging.CRITICAL)

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
