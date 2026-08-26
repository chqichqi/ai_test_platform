"""Fix Phase B debug + disable Phase A merge."""
import ast

filepath = 'app/api/api_v1/endpoints/business_flow.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Disable Phase A by making merged only use Phase B
old_merge = '''seen_names = set()
            merged = []
            # Phase B (DOM) 优先——直接找 a[href]，比 X 聚类精确
            for it in items_b:
                n = it.get('name', '')
                if n and n not in seen_names:
                    seen_names.add(n)
                    merged.append(it)
            # Phase A (X 聚类) 补充
            for it in items_a:
                n = it.get('name', '')
                if n and n not in seen_names:
                    seen_names.add(n)
                    merged.append(it)'''

new_merge = '''seen_names = set()
            merged = []
            # Phase B (DOM) 直接找 a[href]——不合并 Phase A（X 聚类对此 UI 不可靠）
            for it in items_b:
                n = it.get('name', '')
                if n and n not in seen_names:
                    seen_names.add(n)
                    merged.append(it)'''

if old_merge in content:
    content = content.replace(old_merge, new_merge)
    print("Merge updated: Phase B only")
else:
    print("WARNING: old merge not found, checking...")
    # Try without the Chinese comment
    alt_old = '''seen_names = set()
            merged = []
            # Phase B (DOM)'''
    if alt_old in content:
        print("Found partial match, manual fix needed")

# 2. Add debug logging to Phase B result
old_phase_b_end = '""", parent_name) or []'
# Only replace the Phase B occurrence (second one)
idx1 = content.find(old_phase_b_end)
idx2 = content.find(old_phase_b_end, idx1 + 1) if idx1 > 0 else -1
if idx2 > 0:
    new_b_end = '''""", parent_name) or {}
        if isinstance(items_b, dict):
            items_b = items_b.get('items', [])
        else:
            items_b = items_b or []'''
    content = content[:idx2] + new_b_end + content[idx2 + len(old_phase_b_end):]
    print("Phase B extraction updated")
else:
    print(f"WARNING: Phase B end not found, idx1={idx1}, idx2={idx2}")

# 3. Find the Phase B JS code and add debug returns
# Look for "const results = [];" inside Phase B
old_results_push = '''results.push({name: text, href: href, source: 'dom'});'''
new_results_push = '''results.push({name: text, href: href, source: 'dom', _dbg: 'found'});'''
content = content.replace(old_results_push, new_results_push)

# Look for "return results;" in Phase B (second occurrence) and change to return with debug
old_return = '''return results;
                }
            """, parent_name)'''
# Only change the Phase B one
idx_r1 = content.find(old_return)
idx_r2 = content.find(old_return, idx_r1 + 1) if idx_r1 > 0 else -1
if idx_r2 > 0:
    new_return = '''return {items: results, _containerTag: (container ? container.tagName : 'none'), _linkCount: allLinks ? allLinks.length : 0};
                }
            """, parent_name)'''
    content = content[:idx_r2] + new_return + content[idx_r2 + len(old_return):]
    print("Phase B debug return added")

with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

try:
    ast.parse(content)
    print("SYNTAX OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR line {e.lineno}: {e.msg}")
print("Done")
