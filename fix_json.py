import json
import codecs

with codecs.open('grafana/dashboard-hospital.json', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('namespace=\\"hospital\\"', 'namespace=\\"grupo-5\\"')
content = content.replace('datname=\\"hospital\\"', 'datname=\\"grupo-5\\"')

with codecs.open('grafana/dashboard-hospital.json', 'w', encoding='utf-8') as f:
    f.write(content)
