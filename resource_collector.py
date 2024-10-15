from collections import defaultdict
import datetime
from math import floor
from threading import Timer
from subprocess import check_output
import logging
from logging.handlers import SysLogHandler
from traceback import format_exc
import sys
import os
import pandas as pd
from io import StringIO
import json

output_folder = 'resource_collector_data'
output_file = '/opt/Lobot/resource_collector_data/current.json'
interval = 5

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = SysLogHandler(
    facility=SysLogHandler.LOG_DAEMON,
    address='/dev/log'
)

formatter = logging.Formatter(
    fmt="%(asctime)s - %(filename)s:%(funcName)s:%(lineno)d %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
handler.setFormatter(formatter)
# logger.addHandler(handler)
std_handler = logging.StreamHandler(sys.stdout)
std_handler.setFormatter(formatter)
logger.addHandler(std_handler)


class RepeatTimer(Timer):
    error_counter = 0
    error_threshold = 0

    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)
            try:
                data = {}
                content = check_output(['/opt/Lobot/kubectl-view-allocations', '-o', 'csv']).decode()
                df = pd.read_csv(StringIO(content))
                df = df.fillna(0)
                node_info = check_output(['kubectl', 'get', 'nodes', '--show-labels']).decode().splitlines()[1:]
                labs = {}
                for l in node_info:
                    parts = l.split()
                    node = parts[0]
                    if 'lab=' in parts[5]:
                        lab = parts[5].split('lab=')[1]
                        lab = lab[:lab.index(',')].strip()
                        labs[node] = lab
                df['lab']=df.apply(lambda row: labs.get(row['node'], ''), axis=1)
                for lab in set(labs.values()):
                    mem = df.loc[(df['lab'] == lab) & (df['Kind'] == 'node') & (df['resource'] == 'memory')]
                    mem_total = floor(round(sum(mem['Allocatable'])/1073741824.0,0))
                    mem_free = floor(mem_total -  round(sum(mem['Requested'])/1073741824.0,0))

                    cpus = df.loc[(df['lab'] == lab) & (df['Kind'] == 'node') & (df['resource'] == 'cpu')]
                    cpus_total = sum(cpus['Allocatable'])
                    cpus_free = cpus_total -  sum(cpus['Requested'])
                    gpus = df.loc[(df['lab'] == lab) & (df['Kind'] == 'node') & (df['resource'] == 'nvidia.com/gpu')]
                    gpus_total = sum(gpus['Allocatable'])
                    gpus_free = gpus_total -  sum(gpus['Requested'])
                    pods = set(df.loc[(df['lab'] == lab) & (df['pod'].str.contains('jupyter-'))]['pod'])
                    cpus_total = floor(cpus_total)
                    cpus_free = floor(cpus_free)
                    gpus_total = floor(gpus_total)
                    gpus_free = floor(gpus_free)
                    current_dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
                    summary = f'{lab} available resources CPU Cores: {cpus_free} of {cpus_total}, MEMORY GB: {mem_free} of {mem_total}, GPU: {gpus_free} of {gpus_total} [{current_dt}]'
                    summary_title = f'{lab} available resources as of {current_dt}'
                    summary_details = f'CPU Cores: {cpus_free} of {cpus_total}, MEMORY GB: {mem_free} of {mem_total}, GPU: {gpus_free} of {gpus_total}'
                    #summary = summary.capitalize()
                    pod_usage = []
                    for pod in pods:
                        pod_cpu = list(df.loc[(df['pod'] == pod)  & (df['resource'] == 'cpu')]['Requested'])
                        pod_mem = list(df.loc[(df['pod'] == pod)  & (df['resource'] == 'memory')]['Requested'])
                        pod_gpu = list(df.loc[(df['pod'] == pod)  & (df['resource'] == 'nvidia.com/gpu')]['Requested'])
                        if len(pod_mem) > 0:
                            pod_mem = round(pod_mem[0]/1073741824,0)
                        else:
                            pod_mem = 0
                        pod_mem = floor(pod_mem)
                        if len(pod_cpu) > 0:
                            pod_cpu = pod_cpu[0]
                        else:
                            pod_cpu = 0
                        pod_cpu = floor(pod_cpu)
                        if len(pod_gpu) > 0:
                            pod_gpu = pod_gpu[0]
                        else:
                            pod_gpu = 0
                        pod_gpu = floor(pod_gpu)
                        pod = pod.replace('jupyter-', '')
                        pod = pod.replace('-2d', '-')
                        
                        pod_usage.append(f'{pod} == {pod_cpu} cores, {pod_mem} mem, {pod_gpu} gpu')
                    pod_usage.append(f'NOTICE: If you select more resources than are available, your workload will be pending until resources are available.')
                    data[lab] = {
                            'time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'summary': summary,
                            'summary_title': summary_title,
                            'summary_details': summary_details,
                            'usage': pod_usage
                            }
                json.dump(data, open(output_file, 'w'))
            except:
                _, value, traceback = sys.exc_info()
                print(value, self.error_counter)
                self.error_counter += 1
                if self.error_counter > self.error_threshold:
                    logger.error(
                        f'{value} happened more than {self.error_threshold} times')
                    logger.error(format_exc())
                    break


class run_once():
    logger.info('Starting resource collector...')


if __name__ == '__main__':
    # every 15 seconds
    timer = RepeatTimer(interval, run_once)
    timer.start()

