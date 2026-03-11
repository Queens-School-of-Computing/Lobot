#!/usr/bin/env python3
"""Generate a JupyterHub spawn form HTML by reading hardware info directly
from the local machine.

Run this on the node itself, then commit the output to assets/html/.

Usage:
    python3 generate-resource-page.py --lab <labname>
    python3 generate-resource-page.py --lab <labname> --output /tmp/mylab.html

The script reads:
  - CPU count and model  from /proc/cpuinfo
  - RAM                  from /proc/meminfo
  - GPU count, model,    from nvidia-smi (skipped gracefully if no GPU)
    and memory
  - Image tag            from /opt/Lobot/config-env.yaml (if present)
"""

import argparse
import subprocess
import sys
import re
from pathlib import Path

CONFIG_ENV  = Path('/opt/Lobot/config-env.yaml')
ASSETS_HTML = Path('.')
IMAGE_REPO  = 'queensschoolofcomputingdocker/gpu-jupyter-latest'

CPU_STEPS    = [2, 4, 8, 10, 16, 24, 32, 48, 64, 96, 128]
RAM_STEPS_GB = [8, 16, 32, 64, 96, 128, 192, 256, 384, 512, 768, 1024]


def main():
    parser = argparse.ArgumentParser(
        description='Generate a JupyterHub spawn form HTML from local hardware info.'
    )
    parser.add_argument('--lab', '-l', required=True,
                        help='Lab name (used as the filename and JupyterHub resource key)')
    parser.add_argument('--output', '-o',
                        help='Output path (default: /opt/Lobot/assets/html/<lab>.html)')
    args = parser.parse_args()

    info = get_hardware_info()
    image_tag, image_label = get_current_image()
    html = render_html(args.lab, info, image_tag, image_label)

    out_path = Path(args.output) if args.output else ASSETS_HTML / f'{args.lab}.html'
    if out_path.exists():
        print(f"WARNING: {out_path} already exists.")
        print("Overwrite? [y/N] ", end='', flush=True)
        if input().strip().lower() != 'y':
            print("Aborted.")
            sys.exit(0)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)

    gpu_mem = f" ({info['gpu_mem_gb']}G)" if info['gpu_mem_gb'] else ''
    gpu_str = f"{info['gpu_count']}x {info['gpu_model']}{gpu_mem}" \
              if info['gpu_count'] else 'none'

    print(f"\nWritten: {out_path}")
    print(f"  Lab:  {args.lab}")
    print(f"  CPU:  {info['cpu_count']} cores ({info['cpu_model']})  →  options: {info['cpu_options']}")
    print(f"  RAM:  {info['ram_gb']} GB   →  options: {info['ram_options']} GB")
    print(f"  GPU:  {gpu_str}")


def _round_gpu_mem(mib):
    """Round raw MiB to the nearest standard GPU VRAM size in GB.
    e.g. 15356 MiB → 16G, 81920 MiB → 80G, 49152 MiB → 48G."""
    common = [4, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96]
    gb = mib / 1024
    return min(common, key=lambda x: abs(x - gb))


def get_hardware_info():
    # --- CPU ---
    cpuinfo = Path('/proc/cpuinfo').read_text()
    cpu_count = cpuinfo.count('processor\t:')
    model_match = re.search(r'^model name\s+:\s+(.+)$', cpuinfo, re.MULTILINE)
    cpu_model = model_match.group(1).strip() if model_match else 'Unknown CPU'

    # --- RAM ---
    meminfo = Path('/proc/meminfo').read_text()
    mem_match = re.search(r'^MemTotal:\s+(\d+)\s+kB', meminfo, re.MULTILINE)
    ram_gb = int(mem_match.group(1)) // (1024 * 1024) if mem_match else 0

    # --- GPU (optional) ---
    gpu_count, gpu_model, gpu_mem_gb = 0, '', None
    try:
        smi = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'],
            capture_output=True, text=True, check=True
        ).stdout.strip().splitlines()
        gpu_count = len(smi)
        if smi:
            name, mem = smi[0].split(',', 1)
            gpu_model = name.strip().removeprefix('NVIDIA ').strip()
            mem_mib   = int(re.search(r'\d+', mem).group())
            gpu_mem_gb = _round_gpu_mem(mem_mib)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass  # No GPU or nvidia-smi not available

    # --- Option lists ---
    cpu_options = [c for c in CPU_STEPS if c <= cpu_count]
    if not cpu_options or cpu_options[-1] != cpu_count:
        cpu_options.append(cpu_count)

    ram_options = [r for r in RAM_STEPS_GB if r <= ram_gb]
    if not ram_options or ram_options[-1] != ram_gb:
        ram_options.append(ram_gb)

    return {
        'cpu_count':   cpu_count,
        'cpu_model':   cpu_model,
        'cpu_options': cpu_options,
        'ram_gb':      ram_gb,
        'ram_options': ram_options,
        'gpu_count':   gpu_count,
        'gpu_model':   gpu_model,
        'gpu_mem_gb':  gpu_mem_gb,
    }


def get_current_image():
    try:
        import yaml
        cfg = yaml.safe_load(CONFIG_ENV.read_text())
        tag = cfg['singleuser']['image']['tag']
        return tag, tag
    except Exception:
        return 'latest', 'latest'


def render_html(lab, info, image_tag, image_label):
    image_full   = f'{IMAGE_REPO}:{image_tag}'
    cpu_hw_label = info['cpu_model']

    cpu_options_html = '\n'.join(
        '                <option value="{v}" select="selected">{n} cores</option>'.format(
            v=f'{c}.0', n=c) if i == 0 else
        '                <option value="{v}">{n} cores</option>'.format(v=f'{c}.0', n=c)
        for i, c in enumerate(info['cpu_options'])
    )

    if info['gpu_count'] > 0:
        mem_label = f" ({info['gpu_mem_gb']}G)" if info['gpu_mem_gb'] else ''
        model_str = info['gpu_model'] + mem_label
        gpu_options_html = (
            "                <option value=\"0\" selected=\"selected\">"
            "I don't need a GPU for now.</option>\n" +
            '\n'.join(
                '                <option value="{g}">{g}x {m}</option>'.format(
                    g=g, m=model_str)
                for g in range(1, info['gpu_count'] + 1)
            )
        )
    else:
        gpu_options_html = (
            '                <option value="0" selected="selected">'
            'No GPU available on this node.</option>'
        )

    ram_options_html = '\n'.join(
        '                <option value="{v}" select="selected">{v} RAM</option>'.format(
            v=f'{r}G') if i == 0 else
        '                <option value="{v}">{v} RAM</option>'.format(v=f'{r}G')
        for i, r in enumerate(info['ram_options'])
    )

    # {{ and }} are literal braces in the output — required by JupyterHub's Jinja2 templating.
    template = (
        "  <script>    \n"
        "    var lab = '__LAB__';\n"
        "    var url_status = 'https://' + window.location.hostname + '/allocationstatus/current.json';\n"
        "    $.getJSON(url_status, function(data){{\n"
        "    if(data){{\n"
        "      $('#label-summary').text(data[lab].summary_title);\n"
        "      $('#label-summary-details').text(data[lab].summary_details);\n"
        "      $.each(data[lab].usage, function(index, value){{\n"
        "        let entry = $('<small>');\n"
        "        entry.text(value);\n"
        "        entry.addClass('form-text text-muted');\n"
        "        $('#label-usage').append(entry);\n"
        "        $('#label-usage').append($('<br>'));        \n"
        "      }})\n"
        "    }}\n"
        "    }})\n"
        "  </script>\n"
        "  <div class=\"form-group\" id=\"label-usage\">\n"
        "  <label id=\"label-summary\"></label><br>\n"
        "  <label id=\"label-summary-details\"></label><br>\n"
        "  </div>\n"
        "  <div class=\"form-group\">\n"
        "              <label for=\"inputIMG\">Base docker image to be deployed</label>\n"
        "              <select name=\"image\" class=\"form-control\" id=\"inputIMG\" aria-describedby=\"emailHelp\">\n"
        "              <option value=\"__IMAGE_FULL__\" select=\"selected\">__IMAGE_LABEL__</option>\n"
        "              </select>\n"
        "              <small id=\"imageHelp\" class=\"form-text text-muted\">Included most of the dependencies you would need. For a custom base image, please email help@cs.queensu.ca</small>\n"
        "  </div>\n"
        "  <div class=\"form-group\">\n"
        "              <label for=\"inputCPU\">Guaranteed Number of CPU Cores [__CPU_HW_LABEL__]</label>\n"
        "              <select name=\"cpu_limit\" class=\"form-control\" id=\"inputCPU\" aria-describedby=\"emailHelp\">\n"
        "__CPU_OPTIONS__\n"
        "              </select>\n"
        "              <small id=\"cpuLimitHelp\" class=\"form-text text-muted\">Reserved number of cores. Choose minimum. Server will use more if needed and available automatically.</small>\n"
        "            </div>\n"
        "            <div class=\"form-group\">\n"
        "              <label for=\"inputGPU\">Number of GPU accelerators</label>\n"
        "              <select name=\"gpu_limit\" class=\"form-control\" id=\"inputGPU\" aria-describedby=\"emailHelp\">\n"
        "__GPU_OPTIONS__\n"
        "              </select>\n"
        "              <small id=\"cpuHelp\" class=\"form-text text-muted\">The number of physical GPU devices to be allocated.</small>\n"
        "            </div>\n"
        "            <div class=\"form-group\">\n"
        "              <label for=\"inputRAM\">RAM to be allocated</label>\n"
        "              <select name=\"mem_limit\" class=\"form-control\" id=\"inputRAM\" aria-describedby=\"emailHelp\">\n"
        "__RAM_OPTIONS__\n"
        "              </select>\n"
        "              <small id=\"memHelp\" class=\"form-text text-muted\">The amount of memory to be allocated.</small>\n"
        "            </div>\n"
        "            <div class=\"form-group\" style=\"display:none;\">\n"
        "              <label for=\"inputPVC\">Storage volume claim</label>\n"
        "              <select name=\"storage_class\" class=\"form-control\" id=\"inputPVC\" aria-describedby=\"emailHelp\">\n"
        "                <option value=\"{}\" selected=\"selected\">{}</option>\n"
        "              </select>\n"
        "              <small id=\"gpuHelp\" class=\"form-text text-muted\">The storage volume will be created for you only once. If you need to upgrade the storage (change PV), please let us know. </small>\n"
        "              </div>\n"
        "          <div class=\"form-check\">\n"
        "          <label class=\"form-check-label\" for=\"exampleCheck1\">Note: your server will be culled after 72 hours of activity, and all the files will be automatically saved. Only your home folder is persisted (your conda environments and vscode extensions are installed under your home folder and persisted by default).</label>\n"
        "          <a href=\"https://github.com/Queens-School-of-Computing/Lobot-Cluster-Information/blob/master/instruction_server.md\" target=\"_blank\" rel=\"noopener noreferrer\">Click here to read all about using Lobot.</a>\n"
        "  </div>\n"
    )

    return (template
            .replace('__LAB__',          lab)
            .replace('__IMAGE_FULL__',   image_full)
            .replace('__IMAGE_LABEL__',  image_label)
            .replace('__CPU_HW_LABEL__', cpu_hw_label)
            .replace('__CPU_OPTIONS__',  cpu_options_html)
            .replace('__GPU_OPTIONS__',  gpu_options_html)
            .replace('__RAM_OPTIONS__',  ram_options_html))


if __name__ == '__main__':
    main()
