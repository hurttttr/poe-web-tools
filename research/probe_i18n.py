import re, glob, os, collections

for p in glob.glob('ninja_chunks/*.mjs'):
    s = open(p, encoding='utf-8', errors='replace').read()
    if 'Q2lUR2' in s:
        i = s.find('Q2lUR2')
        print('FILE', os.path.basename(p))
        print(repr(s[max(0, i - 100):i + 160]))

tot = collections.Counter()
for p in glob.glob('ninja_chunks/*.mjs'):
    s = open(p, encoding='utf-8', errors='replace').read()
    tot['id_backtick'] += len(re.findall(r'id:\s*`', s))
    tot['message_backtick'] += len(re.findall(r'message:\s*`', s))
    tot['id_quote'] += len(re.findall(r'id:\s*"', s))
    tot['message_word'] += s.count('message')
    tot['id_word'] += s.count('id:')
print(tot)

# 尝试宽松匹配
pairs = {}
for p in glob.glob('ninja_chunks/*.mjs'):
    s = open(p, encoding='utf-8', errors='replace').read()
    for m in re.finditer(r'id:\s*[`"\']([A-Za-z0-9_\-]{4,12})[`"\']\s*,\s*message:\s*[`"\']([^`"\']{0,200})[`"\']', s):
        pairs.setdefault(m.group(1), m.group(2))
print('pairs', len(pairs))
for k, v in list(pairs.items())[:15]:
    print(' ', k, '=>', v[:80])
