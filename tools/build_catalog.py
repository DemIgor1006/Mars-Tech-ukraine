"""Build the public MARS TECH UKRAINE catalog data from the Довідник MARS · AYFAR base.
Usage: python3 -I build_catalog.py <dir with data/mars.json, data/ayfar.json, data/img_*.json> <out site dir>
Factory prices are NOT copied into the public data on purpose."""
import json, sys, re, base64, io, os, collections
from PIL import Image

src, out = sys.argv[1], sys.argv[2]
SPECS = sys.argv[3] if len(sys.argv) > 3 else None   # dir from mars_specs.py (specs.json + dw/*.png), optional
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

YR = re.compile(r"\((?:[^()]*?)((?:19|20)\d\d)\s*(?:[–\-]\s*((?:19|20)\d\d)|(→|->|>))?\)")
def years_by_make(full):
    """{make: [from, to|None]} — a range right after the make's models, else the next range in the same name part."""
    out = {}
    for part in re.split(r" / (?=(?:Ліхтар|Фара|Покажчик|Скло|Повторювач|Роз'єм|Патрон|Рамка|Катафот|Оптичний)\b)", full):
        mk_pos = []
        for mk in MAKES + list(MAKE_ALIASES):
            for mm in re.finditer(r'(?<![A-Za-z])' + re.escape(mk) + r'(?![A-Za-z])', part):
                mk_pos.append((mm.start(), MAKE_ALIASES.get(mk, mk)))
        mk_pos.sort()
        rngs = [(mm.start(), int(mm.group(1)), int(mm.group(2)) if mm.group(2) else None, bool(mm.group(3))) for mm in YR.finditer(part)]
        for i, (pos, mk) in enumerate(mk_pos):
            r = next((x for x in rngs if x[0] > pos), None)
            if not r: continue
            y0, y1, open_ = r[1], r[2], r[3]
            y1 = None if open_ or y1 is None and open_ else (y1 if y1 else y0)
            if open_: y1 = None
            if mk not in out: out[mk] = [y0, y1]
    return out

CONN = [('amp', "Роз'єм AMP", r"роз'єм AMP|AMP Soket|Soket AMP|\bAMP\b.*Soket"),
        ('din', "Роз'єм DIN", r"(?!x)x"),
        ('pin', "Роз'єм N-pin", r"(?!x)x"),
        ('plug', "З роз'ємом на корпусі", r"(?!x)x"),
        ('schlemmer', "Роз'єм Schlemmer", r"Schlemmer"),
        ('hdscs', "Роз'єм HDSCS", r"HDSCS"),
        ('daf', "Роз'єм DAF", r"роз'єм DAF"),
        ('wire', 'Проводка / кабель', r"з проводкою|з кабелем|Kablolu"),
        ('socket', 'З патроном', r"з патроном|\bDuylu\b"),
        ('nosocket', 'Без патрона', r"без патрона|\bDuysuz\b")]
def conn_of(full, tr):
    txt = full + ' ' + tr
    return [cid for cid, _, rx in CONN if re.search(rx, txt)]
BULB = re.compile(r"лампа ((?:P|PY|R|RY|H|W|C|T|HB|BA)\d+(?:/\d+)?W?)")
def bulbs_of(full):
    return sorted(set(BULB.findall(full)))

TYPE_HINT = [('fog', r'протитуман'), ('spot', r'дальнього'), ('tail', r'заднього ліхтаря|стоп-сигналу|заднього ходу'),
             ('turn', r'покажчика|повороту'), ('marker', r'габарит'), ('head', r'фар')]
def part_target(n):
    for t, rx in TYPE_HINT:
        if re.search(rx, n): return t
    return None
def descriptor(n):
    m_ = re.search(r"[A-Z][^,]*", n)
    if not m_: return None, None
    d_ = m_.group(0).strip()
    yrs = tuple(re.findall(r'(?:19|20)\d\d', d_))
    d_ = re.sub(r'\s*\([^()]*(?:19|20)\d\d[^()]*\)', '', d_).strip()
    return d_.lower(), yrs

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
              '_img': v.get('img'), 'cn': conn_of(n, ' '.join(v.get('names') or [])), 'lb': bulbs_of(n),
              'yr': years_by_make(n), 'pg': v.get('catalog_page')}
        if len(parts) > 1: it['alt'] = parts[1:]
        items.append(it)

LAMP_T = {'tail', 'head', 'turn', 'marker', 'fog', 'spot', 'work'}
BULB_RX = re.compile(r'(?:(\d+)\s*[xX×]\s*)?\b(P\s?Y|P|R\s?Y|R|W|C|T|HB|H)\s?(\d+(?:/\d+)?)\s?(W)?\b')
def parse_bulbs(txt):
    out = []
    for m_ in BULB_RX.finditer(txt):
        kind, num, w = re.sub(r'\s', '', m_.group(2)), m_.group(3), m_.group(4)
        if kind in ('H', 'HB'):
            if w: continue
            typ = f'{kind}{num}'
        else:
            if not w: continue
            typ = f'{kind}{num}W'
        out.append((int(m_.group(1)) if m_.group(1) else None, typ))
    return out
def volt(txt):
    m_ = re.search(r'\b(12\s?[-–/]\s?(?:24|80)|12|24)\s?V\b', txt)
    if not m_: return None
    v = re.sub(r'\s', '', m_.group(1)).replace('/', '–').replace('-', '–')
    return f'{v} В'
def conn_from_spec(row, title):
    ids, parts = [], []
    m_ = re.search(r'\bAMP\s?(\d[,.]\d)?', row)
    if m_: ids.append('amp'); parts.append("Роз'єм AMP" + (f" {m_.group(1).replace(',', '.')}" if m_.group(1) else ''))
    if re.search(r'\bDIN\b', row): ids.append('din'); parts.append("Роз'єм DIN")
    m_ = re.search(r'(\d+)\s?Pin', row, re.I)
    if m_: ids.append('pin'); parts.append(f"Роз'єм {m_.group(1)}-pin")
    if re.search(r'Schlemmer', row): ids.append('schlemmer'); parts.append("Роз'єм Schlemmer")
    if re.search(r'HDSCS', row): ids.append('hdscs'); parts.append("Роз'єм HDSCS")
    if re.search(r'Tesisatl|W-?\s?Cable|Kablolu', row): ids.append('wire'); parts.append('Проводка (кабель)')
    m_ = re.search(r'Kablo\s?(\d+)\s?cm', row + ' ' + title, re.I)
    if m_:
        if 'wire' not in ids: ids.append('wire')
        parts.append(f'кабель {m_.group(1)} см')
    if re.search(r'\bSoketli\b', row) and not re.search(r'Duy', row): ids.append('plug'); parts.append("Роз'єм на корпусі")
    if re.search(r'\bDuylu\b', row): ids.append('socket'); parts.append('З патроном')
    if re.search(r'Duysuz', row): ids.append('nosocket'); parts.append('Без патрона')
    pos = 'ззаду' if re.search(r'Arka Soketli|Rear Connector', title) else 'збоку' if re.search(r'Yan Soketli|Side Connector', title) else ''
    txt = ', '.join(parts)
    if pos and txt: txt += f' ({pos})'
    elif pos: txt = f"Роз'єм {pos}"
    return ids, txt
DW_CH = []
if SPECS:
    sp = json.load(open(os.path.join(SPECS, 'specs.json')))
    specs, dmeta = sp['specs'], sp['drawings']
    used = {}
    def dw_ref(did):
        if did not in used:
            if not DW_CH or len(DW_CH[-1]) >= 40: DW_CH.append({})
            im = Image.open(os.path.join(SPECS, 'dw', did + '.png')).convert('RGB')
            if im.width > 900: im = im.resize((900, round(im.height * 900 / im.width)), Image.LANCZOS)
            buf = io.BytesIO(); im.save(buf, 'WEBP', quality=72, method=6)
            DW_CH[-1][did] = base64.b64encode(buf.getvalue()).decode(); used[did] = len(DW_CH) - 1
        return [used[did], did]
    nb = nc = nd = 0
    for it in items:
        if it['b'] != 'MARS': continue
        e = specs.get(it['c'][:7])
        if not e: continue
        row = e.get('row', ''); title = ' '.join(e.get('title', []))
        is_lens = bool(re.search(r'\bCam\b|\bLens\b', row))
        if not is_lens and it['t'] in LAMP_T:
            bl = ' / '.join(e.get('bulb_line', []))
            bulbs = list(dict.fromkeys(parse_bulbs(e['bulb_line'][0]) if e.get('bulb_line') else [])) or list(dict.fromkeys(parse_bulbs(row)))
            if bulbs:
                it['lbt'] = ', '.join(f'{n} × {t}' if n else t for n, t in bulbs)
                it['lb'] = sorted(set(t for _, t in bulbs)); nb += 1
            v = volt(row) or volt(bl)
            if v: it['v'] = v
            ids, txt = conn_from_spec(row, title)
            if ids:
                it['cn'] = list(dict.fromkeys(ids + it.get('cn', [])))
                it['cnx'] = txt; nc += 1
            if re.search(r'\bLED\b', row): it['led'] = True
        pg0 = lambda ids: [d for d in ids if d.split('_')[0] == min(x.split('_')[0] for x in ids)] if ids else []
        first = lambda ids: sorted(ids, key=lambda d: int(d.split('_')[0][1:]))
        if e.get('dw'):
            ids = first(e['dw']); p0 = ids[0].split('_')[0]
            it['dw'] = [dw_ref(d) for d in ids if d.split('_')[0] == p0][:3]; nd += 1
        if e.get('pin'): it['pin'] = dw_ref(first(e['pin'])[0])
        if e.get('conn'): it['cv'] = dw_ref(first(e['conn'])[0])
    print('specs applied: bulbs', nb, 'conn', nc, 'drawings', nd, 'drawing files', sum(len(c) for c in DW_CH))
byd = collections.defaultdict(list)
for it in items:
    dsc, yrs = descriptor(it['n']); it['_d'], it['_y'] = dsc, yrs
    if dsc: byd[dsc].append(it)
codes = {it['c']: it for it in items}
def side_ok(a, b): return not a or not b or a == b or 'LR' in (a, b)
for it in items:
    if it['t'] != 'glass': continue
    tgt = part_target(it['n'])
    fits = []
    m_ = re.match(r'^(.*)-PC$', it['c'])
    if m_ and m_.group(1) in codes: fits.append(m_.group(1))
    if tgt and it['_d']:
        for L in byd[it['_d']]:
            if L['t'] != tgt or L['b'] != it['b'] or not side_ok(L.get('sd', ''), it.get('sd', '')): continue
            if it['_y'] and L['_y'] and it['_y'] != L['_y']: continue
            if L['c'] not in fits: fits.append(L['c'])
    if fits:
        it['for'] = fits
        for c in fits: codes[c].setdefault('parts', []).append(it['c'])
for it in items: it.pop('_d', None); it.pop('_y', None)

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
if DW_CH:
    os.makedirs(f'{out}/data/dw', exist_ok=True)
    for i, ch in enumerate(DW_CH):
        json.dump(ch, open(f'{out}/data/dw/d{i:02d}.json', 'w'), separators=(',', ':'))
for it in items:
    if not it['md']: it.pop('md')
    if not it['mk']: it.pop('mk')
    if not it['o']: it.pop('o')
    if not it['sd']: it.pop('sd')
    if not it['led']: it.pop('led')
    for k in ('cn', 'lb', 'yr'):
        if k in it and not it[k]: it.pop(k)
    for k in ():
        if not it[k]: it.pop(k)
    if it.get('pg') is None: it.pop('pg', None)
    it.pop('pg', None)
CAT_PICK = {'tail': 'M611250', 'head': '505800', 'turn': 'M521312', 'marker': 'M720233', 'fog': 'M630960', 'spot': 'M710621',
            'work': 'M720533', 'glass': 'M691710', 'elec': 'M680041', 'acc': 'TK 105'}
byc = {it['c']: it for it in items}
cat_img = {cid: chunks[byc[code]['i']][code] for cid, code in CAT_PICK.items() if code in byc and 'i' in byc[code]}
meta = {'conn': [{'id': c[0], 'title': c[1]} for c in CONN], 'cats': [{'id': c[0], 'title': c[1]} for c in CATS], 'version': 'Прайси 2026-1', 'chunks': len(chunks), 'catImg': cat_img}
json.dump({'meta': meta, 'items': items}, open(f'{out}/data/catalog.json', 'w'), ensure_ascii=False, separators=(',', ':'))

print('items', len(items), 'chunks', len(chunks), 'unclassified', len(unc))
for u in unc[:40]: print('  UNC', u)
print(collections.Counter(i['t'] for i in items))
print(collections.Counter(s for i in items for s in i['s']))
mkc = collections.Counter(mk for i in items for mk in i.get('mk', []))
print(mkc.most_common())
print('conn', collections.Counter(c for i in items for c in i.get('cn', [])), 'bulbs', sum(1 for i in items if 'lb' in i), 'years', sum(1 for i in items if 'yr' in i), 'glass linked', sum(1 for i in items if 'for' in i), 'lamps with parts', sum(1 for i in items if 'parts' in i))
print('with img', sum(1 for i in items if 'i' in i), 'cert', sum(1 for i in items if i['cert']), 'led', sum(1 for i in items if i.get('led')))
