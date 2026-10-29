"""Turn the artifact page (index.html without <html>/<head>) into a standalone page for GitHub Pages.
Usage: python3 make_standalone.py <artifact index.html> <out index.html>"""
import sys
s = open(sys.argv[1]).read().replace('<meta name="claude:viewport-fit-sides" content="cover">\n', '')
head_end = s.index('</style>') + len('</style>')
reset = ('<style>\n:root { box-sizing: border-box; padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }\n'
         'body { margin: 0; padding: 0; }\nimg { max-width: 100%; }\n[hidden]:not([hidden=until-found i]) { display: none !important; }\n</style>\n')
doc = ('<!doctype html>\n<html lang="uk">\n<head>\n<meta charset="utf-8">\n'
       '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
       + reset + s[:head_end] + '\n</head>\n<body>' + s[head_end:].rstrip() + '\n</body>\n</html>\n')
open(sys.argv[2], 'w').write(doc)
