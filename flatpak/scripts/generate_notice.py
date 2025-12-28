import sys
import os
from pathlib import Path

# Add src to path so we can import sharly_chess modules
sys.path.append('src')

from common.sharly_chess_config import SharlyChessConfig
from common import SHARLY_CHESS_VERSION

def generate_notice(output_path):
    content = f"""SHARLY CHESS {SHARLY_CHESS_VERSION}
{SharlyChessConfig.en_copyright}
{SharlyChessConfig.web_url}

This software includes third-party libraries and components.
See THIRD_PARTY_LICENSES.md for detailed license information.

For a summary of all licenses used, see LICENSE_SUMMARY.md.
Individual package licenses are available in the packages/ subdirectory.

IMPORTANT LICENSE NOTICES:

1. GNU LGPL Components:
   Some components are licensed under GNU Lesser General Public License (LGPL).
   Source code for these components is available from their respective PyPI packages.

2. Apache License Components:
   Some components are licensed under Apache License 2.0.
   See THIRD_PARTY_LICENSES.md for required copyright notices.

3. BSD License Components:
   Some components are licensed under various BSD licenses.
   See THIRD_PARTY_LICENSES.md for required copyright notices.

4. Mozilla Public License Components:
   Some components are licensed under Mozilla Public License 2.0.
   See THIRD_PARTY_LICENSES.md for complete license terms.

For complete license terms and copyright notices, please refer to
THIRD_PARTY_LICENSES.md.
"""
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Generated NOTICE.txt at {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_notice.py <output_path>")
        sys.exit(1)
    
    generate_notice(sys.argv[1])
