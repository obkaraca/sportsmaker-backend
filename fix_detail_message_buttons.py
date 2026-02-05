# Script to fix message buttons in detail pages
import re

# Files to fix
files = [
    '/app/frontend/app/reservations/coach-detail.tsx',
    '/app/frontend/app/reservations/venue-detail.tsx',
    '/app/frontend/app/reservations/referee-detail.tsx',
    '/app/frontend/app/reservations/player-detail.tsx'
]

for file_path in files:
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Find the old pattern and replace with new
        old_pattern = r"router\.push\(\{\s*pathname: '\(tabs\)/messages' as any,\s*params: \{ recipientId: (\w+)\.id \}\s*\}\);"
        new_pattern = r"router.push({ pathname: '/chat' as any, params: { userId: \1.id, userName: \1.full_name || \1.venue_name || 'User' } });"
        
        content = re.sub(old_pattern, new_pattern, content)
        
        # Also fix any variation without recipientId
        old_pattern2 = r"router\.push\(\{\s*pathname: '\(tabs\)/messages' as any\s*\}\);"
        # Skip this one for now, need user context
        
        with open(file_path, 'w') as f:
            f.write(content)
        
        print(f'Fixed {file_path}')
    except Exception as e:
        print(f'Error fixing {file_path}: {e}')

print('Done!')
