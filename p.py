src = open('frontend/app/admin/page.tsx', encoding='utf-8').read()

old = '    return counts;\n  }, [applications]);'
new = '    counts["paid"] = applications.filter((a) => a.is_paid).length;\n    return counts;\n  }, [applications]);'

if old not in src:
    print('ERROR'); exit(1)
src = src.replace(old, new, 1)
open('frontend/app/admin/page.tsx', 'w', encoding='utf-8').write(src)
print('OK')