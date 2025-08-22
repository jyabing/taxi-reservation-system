import os, re
PATTERNS = [
    (r"db_column\s*=\s*['\"]company['\"]", "db_column='company'"),
    (r"values\([^)]*['\"]company['\"][^)]*\)", "values('company')"),
    (r"order_by\([^)]*['\"]company['\"][^)]*\)", "order_by('company')"),
    (r"staffbook_driver\"?\.\s*\"?company\"?", 'raw SQL "staffbook_driver"."company"'),
    (r"Model\.objects\.raw\([^)]*company(?!_)[^)]*\)", "objects.raw(... company ...)"),
    (r"\.extra\([^)]*company[^_][^)]*\)", "QuerySet.extra(... company ...)"),
]
rx=[(re.compile(p,re.I), label) for p,label in PATTERNS]
hits=[]
for dp,_,files in os.walk(os.getcwd()):
    for fn in files:
        if not fn.endswith((".py",".html",".sql",".txt")): continue
        p=os.path.join(dp,fn)
        try:
            with open(p,"r",encoding="utf-8",errors="ignore") as f:
                for i,line in enumerate(f,1):
                    for r,label in rx:
                        if r.search(line):
                            hits.append((p,i,label,line.rstrip()))
        except: pass
if not hits:
    print("✅ 未发现可疑引用。")
else:
    print("❗疑似错误引用（把 company → company_id / company__name）：\n")
    for p,i,label,line in hits:
        print(f"{p}:{i}: [{label}] {line}")
