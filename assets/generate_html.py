#!/usr/bin/env python3
"""Generate JupyterHub spawner HTML forms from labs.yaml.

Usage:
    python3 assets/generate_html.py

Requires: pyyaml  (pip install pyyaml)
Output:   assets/html/<lab_id>.html  (one file per lab)

Each lab uses the global `images` list by default.
Add an `images` key to a lab to override with a lab-specific list.
"""

import os
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'labs.yaml')
OUTPUT_DIR  = os.path.join(SCRIPT_DIR, 'html')

DEFAULT_CPU_HELP = "Reserved number of cores.  Choose minimum. Server will use more if needed and available automatically."
DEFAULT_RAM_HELP = "The amount of memory to be allocated."


def options_html(opts, indent='                '):
    lines = []
    for opt in opts:
        sel = ' selected="selected"' if opt.get('default') else ''
        lines.append(f'{indent}<option value="{opt["value"]}"{sel}>{opt["label"]}</option>\n')
    return ''.join(lines)


def render(lab_id, lab, global_images, registry):
    cpu_label   = lab.get('cpu_label', '')
    cpu_bracket = f' [{cpu_label}]' if cpu_label else ''
    cpu_help    = lab.get('cpu_help', DEFAULT_CPU_HELP)
    ram_help    = lab.get('ram_help', DEFAULT_RAM_HELP)

    # Lab-specific images override global list
    images = lab.get('images', global_images)
    img_opts = options_html([
        {'value': f'{registry}:{img["tag"]}', 'label': img['label'], 'default': img.get('default')}
        for img in images
    ])
    cpu_opts = options_html(lab['cpu_options'])
    gpu_opts = options_html(lab['gpu_options'])
    ram_opts = options_html(lab['ram_options'])

    ls_image = f'{lab_id}_image'
    ls_cpu   = f'{lab_id}_cpu'
    ls_gpu   = f'{lab_id}_gpu'
    ls_ram   = f'{lab_id}_ram'

    lines = []
    lines.append('  <script>    \n')
    lines.append(f"    var lab = '{lab_id}';\n")
    lines.append("    var url_status = 'https://' + window.location.hostname + '/allocationstatus/current.json';\n")
    lines.append("    $.getJSON(url_status, function(data){{\n")
    lines.append("    if(data){{\n")
    lines.append("      $('#label-summary').text(data[lab].summary_title);\n")
    lines.append("      $('#label-summary-details').text(data[lab].summary_details);\n")
    lines.append("      $.each(data[lab].usage, function(index, value){{        \n")
    lines.append("        let entry = $('<small>');\n")
    lines.append("        entry.text(value);\n")
    lines.append("        entry.addClass('form-text text-muted');\n")
    lines.append("        $('#label-usage').append(entry);\n")
    lines.append("        $('#label-usage').append($('<br>'));        \n")
    lines.append("      }})\n")
    lines.append("    }}\n")
    lines.append("    }})\n")
    lines.append("\n")
    lines.append("    // Restore last selections from localStorage\n")
    lines.append("    $(document).ready(function() {\n")
    lines.append("      var restoreSelect = function(id, key) {\n")
    lines.append("        var saved = localStorage.getItem(key);\n")
    lines.append("        if (saved) { $(id).val(saved); }\n")
    lines.append("        $(id).on('change', function() { localStorage.setItem(key, $(this).val()); });\n")
    lines.append("      };\n")
    lines.append(f"      restoreSelect('#inputIMG', '{ls_image}');\n")
    lines.append(f"      restoreSelect('#inputCPU', '{ls_cpu}');\n")
    lines.append(f"      restoreSelect('#inputGPU', '{ls_gpu}');\n")
    lines.append(f"      restoreSelect('#inputRAM', '{ls_ram}');\n")
    lines.append("    });\n")
    lines.append("  </script>\n")
    lines.append('  <div class="form-group" id="label-usage">\n')
    lines.append('  <label id="label-summary"></label><br>\n')
    lines.append('  <label id="label-summary-details"></label><br>\n')
    lines.append('  </div>\n')
    lines.append('  <div class="form-group">\n')
    lines.append('              <label for="inputIMG">Base docker image to be deployed</label>\n')
    lines.append('              <select name="image" class="form-control" id="inputIMG" aria-describedby="emailHelp">\n')
    lines.append(img_opts)
    lines.append('              </select>\n')
    lines.append('              <small id="imageHelp" class="form-text text-muted">Included most of the dependencies you would need. For a custom base image, please email help@cs.queensu.ca</small>\n')
    lines.append('  </div>\n')
    lines.append('  <div class="form-group">\n')
    lines.append(f'              <label for="inputCPU">Guaranteed Number of CPU Cores{cpu_bracket}</label>\n')
    lines.append('              <select name="cpu_limit" class="form-control" id="inputCPU" aria-describedby="emailHelp">\n')
    lines.append(cpu_opts)
    lines.append('              </select>\n')
    lines.append(f'              <small id="cpuLimitHelp" class="form-text text-muted">{cpu_help}</small>\n')
    lines.append('            </div>\n')
    lines.append('            <div class="form-group">\n')
    lines.append('              <label for="inputGPU">Number of GPU accelerators</label>\n')
    lines.append('              <select name="gpu_limit" class="form-control" id="inputGPU" aria-describedby="emailHelp">\n')
    lines.append(gpu_opts)
    lines.append('              </select>\n')
    lines.append('              <small id="cpuHelp" class="form-text text-muted">The number of physical GPU devices to be allocated.</small>\n')
    lines.append('            </div>\n')
    lines.append('            <div class="form-group">\n')
    lines.append('              <label for="inputRAM">RAM to be allocated</label>\n')
    lines.append('              <select name="mem_limit" class="form-control" id="inputRAM" aria-describedby="emailHelp">\n')
    lines.append(ram_opts)
    lines.append('              </select>\n')
    lines.append(f'              <small id="memHelp" class="form-text text-muted">{ram_help}</small>\n')
    lines.append('            </div>\n')
    lines.append('            <div class="form-group" style="display:none;">\n')
    lines.append('              <label for="inputPVC">Storage volume claim</label>\n')
    lines.append('              <select name="storage_class" class="form-control" id="inputPVC" aria-describedby="emailHelp">\n')
    lines.append('                <option value="{}" selected="selected">{}</option>\n')
    lines.append('              </select>\n')
    lines.append('              <small id="gpuHelp" class="form-text text-muted">The storage volume will be created for you only once. If you need to upgrade the storage (change PV), please let us know. </small>\n')
    lines.append('              </div>\n')
    lines.append('          <div class="form-check">\n')
    lines.append('          <label class="form-check-label" for="exampleCheck1">Note: your server will be culled after 72 hours of activity, and all the files will be automatically saved. Only your home folder is persisted (your conda environments and vscode extensions are installed under your home folder and persisted by default).</label>\n')
    lines.append('          <a href="https://github.com/Queens-School-of-Computing/Lobot-Cluster-Information/blob/master/instruction_server.md" target="_blank" rel="noopener noreferrer">Click here to read all about using Lobot.</a>\n')
    lines.append('  </div>\n')

    return ''.join(lines)


def main():
    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)

    global_images = config['images']
    registry      = config['image_registry']

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for lab_id, lab in config['labs'].items():
        html     = render(lab_id, lab, global_images, registry)
        out_path = os.path.join(OUTPUT_DIR, f'{lab_id}.html')
        with open(out_path, 'w') as f:
            f.write(html)
        print(f'Generated: {lab_id}.html')


if __name__ == '__main__':
    main()
