import importlib.util
s=importlib.util.spec_from_file_location('sf','/workspace/agatha/runs/frederic_zorokens/scan_frederic.py')
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
print("=== surname_score (None for Zoron/Zooren/van Zoron/Theodorus; match for Zorok* & Borrokens) ===")
for t in ['Zorokens','Zorrokens','Zoorekens','Zorockens','Zovrekens','Zorickens','Zorokensx','Borrokens','Zorog','Zoron','Zooren','van Zoron','Theodorus','Doncker']:
    print("  %14s -> %s" % (t, m.surname_score(t)))
print("=== firstname_score (match Frederic variants; None for Joannes/Johan) ===")
for t in ['Frederic','Friederic','Frideric','Phrederic','Frederick','Frederickus','Fredericius','Joannes','Johan']:
    print("  %14s -> %s" % (t, m.firstname_score(t)))
