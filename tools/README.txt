MARS TECH UKRAINE — catalog site (artifact) — how to rebuild

Source of truth for products: artifact "Довідник MARS · AYFAR" https://claude.ai/artifact/6G2jZhLyMEeXd519veJiDA
(data/mars.json, data/ayfar.json, data/img_mars.json, data/img_ayfar.json).

Rebuild public data after the base changes (new price list, photos, translations):
  1. Artifact read of the Довідник paths above into a folder <src>/data/
  2. python3 -I build_catalog.py <src> <site dir>
     -> <site>/data/catalog.json (no factory prices on purpose) + <site>/data/img/iNN.json (WebP base64, 80 photos per chunk)
  3. Republish this artifact with index.html + data/catalog.json + data/img/*.json (+ tools/*).

Data fields in catalog.json items: c code, b brand (MARS|AYFAR), n Ukrainian name, alt other price-list names,
t category id, s vehicle segments [truck|trailer|bus|lcv|car|agro|univ], mk makes, md {make: [models]},
o OEM codes, cert (true = MARS certificate list), box (factory box norm), sd side (L|R|LR), led, i photo chunk index.

Contacts, company name and hours are in the CONFIG object at the top of the <script> in index.html.
Orders: the page cannot send data anywhere from an artifact; it builds the order text (with box-norm rounding for
container pre-orders) for the client to copy / send to Telegram. A real domain + form backend is the production step.
