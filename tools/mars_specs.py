"""Extract per-code technical drawings, connector pinouts, bulbs, connection and voltage from the MARS catalog PDF.
Usage: python3 -I mars_specs.py <catalog.pdf> <out_dir>   -> out_dir/specs.json + out_dir/dw/*.png"""
import pymupdf as fitz, re, json, sys, os, colorsys
PDF, OUT = sys.argv[1], sys.argv[2]
os.makedirs(os.path.join(OUT, 'dw'), exist_ok=True)
doc = fitz.open(PDF)

def find_codes(words):
    res = []
    for i, w in enumerate(words):
        t = w[4]
        m = re.fullmatch(r'[MМ](\d{6})', t)
        if m: res.append(('M' + m.group(1), fitz.Rect(w[:4]))); continue
        if re.fullmatch(r'\d{6}', t) and i > 0 and words[i-1][4] in ('M', 'М') and abs(words[i-1][1]-w[1]) < 3:
            res.append(('M' + t, fitz.Rect(words[i-1][:4]) | fitz.Rect(w[:4])))
    return res

def sat(c):
    if not c: return 0
    r, g, b = c[:3]; return colorsys.rgb_to_hsv(r, g, b)[1]

class UF:
    def __init__(s, n): s.p = list(range(n))
    def f(s, a):
        while s.p[a] != a: s.p[a] = s.p[s.p[a]]; a = s.p[a]
        return a
    def u(s, a, b): s.p[s.f(a)] = s.f(b)

def cluster(rects, pad):
    n = len(rects); uf = UF(n)
    infl = [r + (-pad, -pad, pad, pad) for r in rects]
    # sweep on x for speed
    order = sorted(range(n), key=lambda i: infl[i].x0)
    active = []
    for i in order:
        ri = infl[i]
        active = [j for j in active if infl[j].x1 >= ri.x0]
        for j in active:
            if infl[j].intersects(ri): uf.u(i, j)
        active.append(i)
    groups = {}
    for i in range(n): groups.setdefault(uf.f(i), []).append(i)
    out = []
    for g in groups.values():
        u = fitz.Rect(rects[g[0]])
        for i in g[1:]: u |= rects[i]
        out.append((u, len(g)))
    return out

BULB_RX = re.compile(r'(?:(\d+)\s*[xX×]\s*)?\b(PY|P|RY|R|W|C|T|HB|H)\s?(\d+(?:/\d+)?)\s?(W)?\b')
def bulbs_in(txt):
    res = []
    for m in BULB_RX.finditer(txt):
        kind, num, w = m.group(2), m.group(3), m.group(4)
        if kind in ('H', 'HB'):
            if w: continue  # e.g. 'H 21W' unlikely; skip odd
            typ = f'{kind}{num}'
        else:
            if not w: continue
            typ = f'{kind}{num}W'
        res.append((int(m.group(1)) if m.group(1) else None, typ))
    return res

specs = {}
dw_meta = {}
def add(code, key, val):
    e = specs.setdefault(code, {'pages': []})
    if key == 'page':
        if val not in e['pages']: e['pages'].append(val)
        return
    lst = e.setdefault(key, [])
    if val not in lst: lst.append(val)

for pno in range(16, doc.page_count):
    page = doc[pno]; W, H = page.rect.width, page.rect.height
    words = page.get_text('words')
    codes = find_codes(words)
    if not codes: continue
    drs = page.get_drawings()
    bars = sorted([d['rect'] for d in drs if d.get('fill') and d['rect'].width > 150 and 7 < d['rect'].height < 24 and sat(d['fill']) > 0.35 and d['rect'].y0 > 50], key=lambda r: r.y0)
    # de-dup bars on the same line
    bl = []
    for b in bars:
        if not bl or b.y0 - bl[-1].y0 > 12: bl.append(b)
    edges = [0] + [b.y0 - 4 for b in bl] + [H]
    blocks = [(edges[i], edges[i+1]) for i in range(len(edges)-1)]
    imgs = [fitz.Rect(im['bbox']) for im in page.get_image_info() if fitz.Rect(im['bbox']).width * fitz.Rect(im['bbox']).height > 1500]
    hdrs = [fitz.Rect(w[:4]) for w in words if w[4] == 'Marstech']
    code_rects = [r for _, r in codes]
    # vector paths -> clusters
    paths = []
    for d in drs:
        r = d['rect']
        if r.y1 < 62 or r.x1 < 34 or r.x0 > W - 34: continue
        if r.width > W * 0.8: continue
        if any(abs(r.y0 - b.y0) < 3 and r.height < 26 and r.width > 100 for b in bl): continue
        if r.width < 0.1 and r.height < 0.1: continue
        paths.append(r)
    cl = cluster(paths, 3) if paths else []
    table_like, cand = [], []
    for r, n in cl:
        if any(r.contains(fitz.Point((c.x0+c.x1)/2, (c.y0+c.y1)/2)) for c in code_rects) or any(r.contains(fitz.Point((h.x0+h.x1)/2, (h.y0+h.y1)/2)) for h in hdrs):
            table_like.append(r); continue
        if r.width < 40 or r.height < 22: continue
        area = r.width * r.height
        if any((r & im).get_area() > 0.5 * area for im in imgs if r.intersects(im)): continue
        cand.append(r)
    cand = [r for r in cand if not any((r + (-2, -2, 2, 2)).intersects(t) for t in table_like)]
    specw = [fitz.Rect(w[:4]) for w in words if w[4] in ('Özellikler', 'Lumen', 'Watt', 'Volt')]
    # merge nearby drawing pieces (views + dimension lines)
    merged = cluster(cand, 14) if cand else []
    fwords = [fitz.Rect(w[:4]) for w in words if w[4].startswith('Fonksiyon') or w[4].startswith('nksiyonlar')]
    if not fwords: fwords = [fitz.Rect(w[:4]) for w in words if w[4] == 'Functions']
    for b0, b1 in blocks:
        bcodes = [(c, r) for c, r in codes if b0 <= r.y0 < b1]
        if not bcodes: continue
        for c, r in bcodes: add(c, 'page', pno + 1)
        # tables in block: group codes by nearest Marstech header above in same column
        tables = {}
        for c, r in bcodes:
            hs = [h for h in hdrs if h.y1 <= r.y0 + 2 and abs((h.x0+h.x1)/2 - (r.x0+r.x1)/2) < 70 and h.y0 >= b0 - 2]
            h = max(hs, key=lambda h: h.y0) if hs else None
            key = (round(h.x0), round(h.y0)) if h else ('x', round(r.x0))
            tables.setdefault(key, {'hdr': h, 'codes': []})['codes'].append((c, r))
        tlist = list(tables.values())
        for t in tlist:
            rs = [r for _, r in t['codes']]
            top = (t['hdr'].y0 if t['hdr'] else min(r.y0 for r in rs)) - 30
            t['box'] = fitz.Rect(min(r.x0 for r in rs) - 260, top, max(r.x1 for r in rs) + 130, max(r.y1 for r in rs) + 8)
            tb = [tl for tl in table_like if tl.intersects(fitz.Rect(min(r.x0 for r in rs), min(r.y0 for r in rs), max(r.x1 for r in rs), max(r.y1 for r in rs)))]
            if tb:
                u = tb[0]
                for x in tb[1:]: u |= x
                t['box'] = u
        # row specs
        for t in tlist:
            box = t['box']; hdr = t['hdr']
            hdr_bottom = hdr.y1 + 1 if hdr else box.y0
            rows = t['codes']
            cx0 = min(r.x0 for _, r in rows)
            title_txt = ' '.join(w[4] for w in words if box.y0 - 2 <= w[1] <= (hdr.y0 - 2 if hdr else box.y0 + 20) and box.x0 - 2 <= w[0] <= box.x1)
            for w in words:
                wr = fitz.Rect(w[:4])
                if not (hdr_bottom <= wr.y0 <= box.y1 + 2 and box.x0 - 2 <= wr.x0 and wr.x1 <= cx0 - 1): continue
                yc = (wr.y0 + wr.y1) / 2
                ds = [(abs(yc - (r.y0 + r.y1) / 2), c) for c, r in rows]
                mn = min(d for d, _ in ds)
                if mn > 16: continue
                for d, c in ds:
                    if d <= mn + 3: add(c, 'row_w', (round(wr.y0, 1), round(wr.x0, 1), w[4]))
            for c, _ in rows:
                if title_txt: add(c, 'title', title_txt)
        # bulb lines in block
        lines = {}
        for w in words:
            if b0 <= w[1] < b1:
                k = round((w[1] + w[3]) / 2 / 3)
                lines.setdefault(k, []).append(w)
        for k, ws in lines.items():
            ws = sorted(ws, key=lambda w: w[0]); txt = ' '.join(w[4] for w in ws)
            if not re.search(r'Ampül\s*/\s*Bulb|Bulb\s*:|^-?\s*(?:H\d{1,2}|HB\d)\s*,\s*(?:12|24)', txt): continue
            y = ws[0][1]
            above = [t for t in tlist if t['box'].y1 <= y + 4]
            tgt = [max(above, key=lambda t: t['box'].y1)] if above else tlist
            val = re.split(r':', txt, 1)[-1].strip() if ':' in txt else txt
            for t in tgt:
                for c, _ in t['codes']: add(c, 'bulb_line', val)
        # drawings in block
        for r, _ in merged:
            if not (b0 - 4 <= (r.y0 + r.y1) / 2 < b1): continue
            if any(r.contains(fitz.Point((w.x0+w.x1)/2, (w.y0+w.y1)/2)) for w in specw): continue
            if any(r.contains(fitz.Point((c.x0+c.x1)/2, (c.y0+c.y1)/2)) for c in code_rects): continue
            kind = 'pin' if any(abs(f.y0 - r.y1) < 30 and f.x0 < r.x1 + 60 and f.x1 > r.x0 - 60 for f in fwords) else 'dw'
            if kind == 'dw':
                cov = sum((r & im).get_area() for im in imgs if r.intersects(im))
                if cov > 0.35 * r.width * r.height: kind = 'conn'
            clip = fitz.Rect(r) + (-6, -6, 6, 6)
            if kind == 'pin':
                fw = [f for f in fwords if abs(f.y0 - r.y1) < 30][0]
                below = [fitz.Rect(w[:4]) for w in words if fw.y0 - 2 <= w[1] <= fw.y0 + 110 and fw.x0 - 10 <= w[0] <= fw.x0 + 150]
                u = clip
                for x in below: u |= x
                clip = u + (-3, -3, 3, 3)
            if clip.width < 60 or clip.height < 40: continue
            # pick table(s)
            if len(tlist) == 1: tgt = tlist
            else:
                def dist(t):
                    b = t['box']; dy = max(0, b.y0 - r.y1, r.y0 - b.y1); dx = max(0, b.x0 - r.x1, r.x0 - b.x1)
                    return dy * 2 + dx * 0.3
                tgt = [min(tlist, key=dist)]
            did = f'p{pno+1}_{round(clip.x0)}_{round(clip.y0)}'
            if did not in dw_meta:
                pix = page.get_pixmap(clip=clip & page.rect, dpi=170)
                if pix.alpha: pix = fitz.Pixmap(pix, 0)
                pix.save(os.path.join(OUT, 'dw', did + '.png'))
                dw_meta[did] = {'page': pno + 1, 'kind': kind, 'bbox': [round(v, 1) for v in clip]}
            for t in tgt:
                for c, _ in t['codes']: add(c, kind, did)

# row text -> parsed fields
for c, e in specs.items():
    rw = sorted(e.pop('row_w', []))
    e['row'] = ' '.join(w for _, _, w in rw)
json.dump({'specs': specs, 'drawings': dw_meta}, open(os.path.join(OUT, 'specs.json'), 'w'), ensure_ascii=False, indent=1)
print('codes', len(specs), 'drawings', sum(1 for v in dw_meta.values() if v['kind'] == 'dw'), 'pins', sum(1 for v in dw_meta.values() if v['kind'] == 'pin'), 'conn', sum(1 for v in dw_meta.values() if v['kind'] == 'conn'),
      'codes w/ dw', sum(1 for e in specs.values() if 'dw' in e), 'w/ pin', sum(1 for e in specs.values() if 'pin' in e), 'w/ bulb line', sum(1 for e in specs.values() if 'bulb_line' in e))
