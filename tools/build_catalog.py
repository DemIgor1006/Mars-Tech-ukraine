"""Build the public MARS TECH UKRAINE catalog data from the Довідник MARS · AYFAR base.
Usage: python3 -I build_catalog.py <dir with data/mars.json, data/ayfar.json, data/img_*.json> <out site dir>
Factory prices are NOT copied into the public data on purpose."""
import json, sys, re, base64, io, os, collections
from PIL import Image

src, out = sys.argv[1], sys.argv[2]
m = json.load(open(f'{src}/data/mars.json')); a = json.load(open(f'{src}/data/ayfar.json'))
imgs = {}
for f in ('img_mars.json', 'img_ayfar.json'):
    imgs.update(json.load(open(f'{src}/data/{f}')))

CATS = [  # id, title, rule (prefixes of name_ua)
 ('tail', 'Задні ліхтарі', ('Ліхтар задній', 'Ліхтар комбінований', 'Ліхтар стоп-сигналу', 'Ліхтар заднього ходу', 'Ліхтар для причепа')),
 ('head', 'Фари головного світла', ('Фара права', 'Фара ліва', 'Фара (', 'Фара Ford', 'Фара Renault', 'Фара Magirus', 'Фара Otokar', 'Фара Lada', 'Фара Fiat', 'Фара Massey', 'Фара Berliand', 'Фара Sanakom', 'Фара універсальна')),
 ('turn', 'Покажчики повороту', ('Покажчик повороту', 'Повторювач повороту')),
 ('marker', 'Габаритні та контурні ліхтарі', ('Ліхтар габаритний', 'Ліхтар денних', 'Ліхтар освітлення')),
 ('fog', 'Протитуманні фари', ('Фара протитуманна', 'Ліхтар протитуманний')),
 ('spot', 'Фари дальнього світла', ('Фара дальнього', 'Оптичний елемент')),
 ('work', 'Фари робочого світла', ('Фара робоча',)),
 ('beacon', 'Проблискові маячки', ('Маячок', 'Ковпак')),
 ('glass', 'Скло та деталі оптики', ('Скло', 'Рамка', 'Відбивач', 'Кришка', 'Кронштейн', 'Накладка', 'Катафот')),
 ('elec', "Роз'єми, патрони, проводка", ("Роз'єм", 'Ремкомплект', 'Комплект проводів', 'Джгут', 'Кабель', 'Патрон')),
 ('acc', 'Аксесуари', ('Зумер', 'Ящик', 'Упор')),
]
def cat_of(n):
    for cid, _, pref in CATS:
        if n.startswith(pref): return cid
    return None

MAKES = ['Mercedes-Benz', 'Volvo', 'Scania', 'DAF', 'MAN', 'Renault', 'Iveco', 'Ford', 'Isuzu', 'BMC', 'Mitsubishi', 'Magirus',
         'Volkswagen', 'Fiat', 'Peugeot', 'Citroen', 'Opel', 'Dacia', 'Hyundai', 'Toyota', 'Nissan', 'Lada', 'Daewoo', 'Audi',
         'Dodge', 'Otokar', 'Temsa', 'Karsan', 'Tofaş', 'Kia', 'Skoda', 'Seat', 'Honda', 'Chevrolet', 'Massey Ferguson', 'Setra', 'Neoplan']
MAKE_ALIASES = {'Tofa': 'Tofaş', 'Massey/Ferguson': 'Massey Ferguson', 'Doğan': 'Tofaş'}
TRUCK_MODELS = r'Actros|Axor|Atego|Arocs|Antos|Unimog|Mercedes-Benz (?:1[0-9]{3}|2[5-9][0-9]{2})\b|\bFH|\bFM\b|\bFL\b|\bFE\b|\bNL\b|\bF ?1[0-6]\b|P-G-R|L-G-P|Premium|Magnum|Kerax|Midliner|Midlum|Stralis|Eurocargo|Eurotech|Eurostar|Trakker|TGA|TGL|TGX|TGM|TGS|F2000|L2000|M2000|Ford Cargo|F-MAX|NPR|NQR|Turkuaz|Fatih|Canter'
BUS_MODELS = r'автобус|Travego|Tourismo|Intouro|Conecto|Citaro|Otokar|Temsa|Karsan|Sultan|Setra|Neoplan|Safir|Prestij|Navigo'
LCV_MODELS = r'Sprinter|Vito|Viano|Citan|Transit|Connect|Courier|Daily|Ducato|Jumper|Boxer|Master|Trafic|Kangoo|Crafter|Transporter|\bLT\b|Caddy|Doblo|Fiorino|Berlingo|Partner|Bipper|Nemo|Jumpy|Expert|Scudo|Combo|Movano|Vivaro|H-?100|H-?1|Proace|Dokker|мікроавтобус|Pick-up'

def makes_models(n):
    found = []
    for mk in MAKES + list(MAKE_ALIASES):
        for mm in re.finditer(r'(?<![A-Za-z])' + re.escape(mk) + r'(?![A-Za-z])', n):
            found.append((mm.start(), mm.end(), MAKE_ALIASES.get(mk, mk)))
    found.sort()
    res = collections.OrderedDict()
    for i, (s, e, mk) in enumerate(found):
        if mk == 'MAN' and re.search(r'MAN\s?\d', n[s:s+5]) is None and False: pass
        res.setdefault(mk, [])
        end = found[i+1][0] if i + 1 < len(found) else len(n)
        seg = n[e:end]
        seg = re.split(r'[(,]', seg)[0]
        for part in seg.split('/'):
            part = part.strip()
            w = re.match(r"([A-Za-z0-9][A-Za-z0-9'\-]*)", part)
            if w:
                tok = w.group(1)
                if tok.lower() in ('серії', 'серія') or re.fullmatch(r'[IVX]+|[A-Za-z]|\d', tok): continue
                if tok not in res[mk]: res[mk].append(tok)
    return res

def segment(v, n, mk):
    g = v['group']
    if re.search(r'трактор|комбайн|Massey|Ferguson|Uzel', n): return 'agro'
    if g == 'DORSE GRUBU' or re.search(r'причеп|напівпричеп', n): return 'trailer'
    if re.search(LCV_MODELS, n): return 'lcv'
    if g == 'OTOBÜS GRUBU' or re.search(BUS_MODELS, n): return 'bus'
    if g in ('AĞIR TİCARİ ARAÇLAR',) or g.startswith('Ağır'):
        return 'truck'
    truck_makes = {'Scania', 'DAF', 'MAN', 'Isuzu', 'BMC', 'Magirus'}
    if (set(mk) & truck_makes) or (re.search(TRUCK_MODELS, n) and set(mk) & {'Mercedes-Benz', 'Volvo', 'Renault', 'Iveco', 'Ford', 'Mitsubishi'}):
        return 'truck'
    if not mk: return 'univ'
    return 'car'

def side(n):
    s = re.sub(r'праве кермо', '', n)
    l = re.search(r'\bлів(ий|а|е)\b', s); r = re.search(r'\bправ(ий|а|е)\b', s)
    if 'ліва/права' in s or 'лівий/правий' in s: return 'LR'
    if l and not r: return 'L'
    if r and not l: return 'R'
    if l and r: return 'LR'
    return ''

def to_webp_b64(b64):
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert('RGB')
    buf = io.BytesIO(); img.save(buf, 'WEBP', quality=80, method=6)
    return base64.b64encode(buf.getvalue()).decode()

items = []; unc = []
for db in (m, a):
    for code, v in db.items():
        n = v['name_ua'].strip()
        cid = cat_of(n)
        if not cid: unc.append((code, n)); cid = 'acc'
        mm = makes_models(n)
        sg = segment(v, n, mm); sg = [sg]
        if sg == ['bus'] and re.search(TRUCK_MODELS, n): sg.append('truck')
        if sg == ['truck'] and re.search(BUS_MODELS, n): sg.append('bus')
        parts = re.split(r" / (?=(?:Ліхтар|Фара|Покажчик|Скло|Повторювач|Роз'єм|Патрон|Рамка|Катафот|Оптичний)\b)", n)
        it = {'c': v['code'], 'b': v['brand'], 'n': parts[0], 't': cid, 's': sg,
              'mk': list(mm.keys()), 'md': {k: vv for k, vv in mm.items() if vv},
              'o': v.get('oem') or [], 'cert': v.get('cert'), 'box': v.get('box'),
              'sd': side(n), 'led': bool(re.search(r'LED|діод', n + ' ' + (v.get('cert_name_ua') or ''))),
              '_img': v.get('img')}
        if len(parts) > 1: it['alt'] = parts[1:]
        items.append(it)

cat_order = {c[0]: i for i, c in enumerate(CATS)}
seg_order = {k: i for i, k in enumerate(['truck', 'trailer', 'bus', 'lcv', 'car', 'agro', 'univ'])}
items.sort(key=lambda x: (cat_order[x['t']], seg_order[x['s'][0]], 0 if x['b'] == 'MARS' else 1, (x['mk'] or ['~'])[0], x['c']))

os.makedirs(f'{out}/data/img', exist_ok=True)
chunk, chunks, CH = {}, [], 80
for it in items:
    k = it.pop('_img')
    if k and k in imgs:
        if len(chunk) >= CH: chunks.append(chunk); chunk = {}
        chunk[it['c']] = to_webp_b64(imgs[k]); it['i'] = len(chunks)
if chunk: chunks.append(chunk)
for i, ch in enumerate(chunks):
    json.dump(ch, open(f'{out}/data/img/i{i:02d}.json', 'w'), separators=(',', ':'))
for it in items:
    if not it['md']: it.pop('md')
    if not it['mk']: it.pop('mk')
    if not it['o']: it.pop('o')
    if not it['sd']: it.pop('sd')
    if not it['led']: it.pop('led')
CAT_PICK = {'tail': 'M611250', 'head': '505800', 'turn': 'M521312', 'marker': 'M720233', 'fog': 'M630960', 'spot': 'M710621',
            'work': 'M720533', 'glass': 'M691710', 'elec': 'M680041', 'acc': 'TK 105'}
byc = {it['c']: it for it in items}
cat_img = {cid: chunks[byc[code]['i']][code] for cid, code in CAT_PICK.items() if code in byc and 'i' in byc[code]}
meta = {'cats': [{'id': c[0], 'title': c[1]} for c in CATS], 'version': 'Прайси 2026-1', 'chunks': len(chunks), 'catImg': cat_img}
json.dump({'meta': meta, 'items': items}, open(f'{out}/data/catalog.json', 'w'), ensure_ascii=False, separators=(',', ':'))

print('items', len(items), 'chunks', len(chunks), 'unclassified', len(unc))
for u in unc[:40]: print('  UNC', u)
print(collections.Counter(i['t'] for i in items))
print(collections.Counter(s for i in items for s in i['s']))
mkc = collections.Counter(mk for i in items for mk in i.get('mk', []))
print(mkc.most_common())
print('with img', sum(1 for i in items if 'i' in i), 'cert', sum(1 for i in items if i['cert']), 'led', sum(1 for i in items if i.get('led')))
