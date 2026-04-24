import yaml

from jinja2 import Environment, FileSystemLoader
from pathlib import Path

env = Environment(loader=FileSystemLoader('templates'))

template = env.get_template('spawner_options_form.html')

labs_config = yaml.safe_load(Path('./lab-spawn-page-resources.yaml').read_text())

# TODO Loop this
lab = labs_config['labs'][0]
output = template.render(lab=lab)

print(output)
print(lab)
