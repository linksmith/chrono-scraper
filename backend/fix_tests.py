#!/usr/bin/env python3
"""Script to fix test_performance_bulk_operations.py by wrapping test bodies in AsyncSessionLocal context"""

import re

def fix_test_file():
    with open('tests/test_performance_bulk_operations.py', 'r') as f:
        content = f.read()

    # Remove session from fixture return
    content = content.replace(
        '"session": session\n            }',
        '}'
    )

    # Pattern to find test methods that use session = test_data["session"]
    # We need to:
    # 1. Remove the session = test_data["session"] line
    # 2. Add async with AsyncSessionLocal() as session: after test_data = await...
    # 3. Indent the rest of the test body

    #Pattern: test method starting, getting test_data, then session
    pattern = r'(    async def test_\w+\(self, setup_performance_test_data\):\n        """[^"]*"""\n        test_data = await setup_performance_test_data\n)        session = test_data\["session"\]\n((?:\n|.)*?)(?=\n    async def test_|$|\n\n\n@pytest\.mark\.asyncio)'

    def replace_test(match):
        header = match.group(1)
        body = match.group(2)

        # Skip if already has AsyncSessionLocal
        if 'async with AsyncSessionLocal() as session:' in body:
            return match.group(0)

        # Indent the body by 4 more spaces
        indented_body = '\n'.join('    ' + line if line.strip() else line for line in body.split('\n'))

        return f"{header}\n        async with AsyncSessionLocal() as session:{indented_body}"

    content = re.sub(pattern, replace_test, content, flags=re.MULTILINE)

    with open('tests/test_performance_bulk_operations.py', 'w') as f:
        f.write(content)

    print("Fixed test file")

if __name__ == '__main__':
    fix_test_file()
