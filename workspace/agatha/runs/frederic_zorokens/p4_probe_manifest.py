import sys; sys.path.insert(0,"/workspace/agatha")
import importlib.util, re, agatha_cache as ac
spec = importlib.util.spec_from_file_location('e','/workspace/agatha/enum_antwerp_baptism.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for bp in ['6186','6364','6257','6084','6320','6138']:
    url = f"https://agatha.arch.be/en/search/genealogie/{bp}"
    try:
        html = m.fetch(url, 'https://agatha.arch.be/', ac.get_cookie())
    except Exception as e:
        print("====",bp,"FETCH ERR",e); continue
    print("====",bp,"bytes",len(html))
    print("  data/json manifests:", sorted(set(re.findall(r'/data/json/[^<>\s"\']+\.json', html))))
    print("  iiif 511 ids:", sorted(set(re.findall(r'511_9000_000_0(\d+)_000', html))))
