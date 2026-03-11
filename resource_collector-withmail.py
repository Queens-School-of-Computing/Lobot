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
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import signal
import atexit
import socket

output_folder = 'resource_collector_data'
output_file = '/opt/Lobot/resource_collector_data/current.json'
interval = 5

# Email configuration - update these with your SMTP settings
EMAIL_ENABLED = True  # Set to False to disable email notifications
SMTP_SERVER = 'innovate.cs.queensu.ca'  # e.g., 'smtp.gmail.com' or 'localhost'
SMTP_PORT = 25  # 587 for TLS, 465 for SSL, 25 for local
SMTP_USE_TLS = False  # Set to True if using port 587
SMTP_USERNAME = None  # Set if authentication is required
SMTP_PASSWORD = None  # Set if authentication is required
FROM_EMAIL = f"{socket.getfqdn().split('.')[0]}@cs.queensu.ca"
TO_EMAIL = 'aaron@cs.queensu.ca'  # Change this to your email address

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


def send_notification_email(subject, body):
    """Send a general notification email."""
    if not EMAIL_ENABLED:
        return
    
    try:
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL
        msg['Subject'] = f'Resource Collector: {subject}'
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        if SMTP_USE_TLS:
            server.starttls()
        if SMTP_USERNAME and SMTP_PASSWORD:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
        
        server.send_message(msg)
        server.quit()
        logger.info(f"Notification email sent to {TO_EMAIL}: {subject}")
    except Exception as e:
        logger.error(f"Failed to send notification email: {e}")


def send_error_email(subject, error_message, traceback_info=None):
    """Send an email notification when an error occurs."""
    if not EMAIL_ENABLED:
        return
    
    try:
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL
        msg['Subject'] = f'Resource Collector Error: {subject}'
        
        body = f"""
Resource Collector encountered an error:

Time: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Error: {error_message}

"""
        if traceback_info:
            body += f"\nFull Traceback:\n{traceback_info}\n"
        
        body += "\nThe resource collector is still running and will retry on the next interval.\n"
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        if SMTP_USE_TLS:
            server.starttls()
        if SMTP_USERNAME and SMTP_PASSWORD:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
        
        server.send_message(msg)
        server.quit()
        logger.info(f"Error notification email sent to {TO_EMAIL}")
    except Exception as e:
        logger.error(f"Failed to send error email: {e}")


class RepeatTimer(Timer):
    error_counter = 0
    error_threshold = 10  # Increased threshold before sending repeated emails
    last_error_email_time = None
    email_cooldown_minutes = 30  # Only send error emails once per 30 minutes

    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)
            try:
                data = {}
                content = check_output(['/opt/Lobot/kubectl-view-allocations', '-o', 'csv']).decode()
                
                # Validate the content before parsing
                if not content or 'error' in content.lower() or len(content.strip()) < 10:
                    raise ValueError(f"Invalid kubectl-view-allocations output: {content[:200]}")
                
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
                    if lab == "gandslab":
                        summary = f'GOAL&SWIMS Labs available resources CPU Cores: {cpus_free} of {cpus_total}, MEMORY GB: {mem_free} of {mem_total}, GPU: {gpus_free} of {gpus_total} [{current_dt}]'
                        summary_title = f'GOAL&SWIMS Labs available resources as of {current_dt}'
                    elif lab == "lobot_a5000":
                        summary = f'Lobot [A5000] available resources CPU Cores: {cpus_free} of {cpus_total}, MEMORY GB: {mem_free} of {mem_total}, GPU: {gpus_free} of {gpus_total} [{current_dt}]'
                        summary_title = f'Lobot [A5000] available resources as of {current_dt}'
                    elif lab == "lobot_a16":
                        summary = f'Lobot [A16] available resources CPU Cores: {cpus_free} of {cpus_total}, MEMORY GB: {mem_free} of {mem_total}, GPU: {gpus_free} of {gpus_total} [{current_dt}]'
                        summary_title = f'Lobot [A16] available resources as of {current_dt}'
                    elif lab == "lobot_a40":
                        summary = f'Lobot [A40] available resources CPU Cores: {cpus_free} of {cpus_total}, MEMORY GB: {mem_free} of {mem_total}, GPU: {gpus_free} of {gpus_total} [{current_dt}]'
                        summary_title = f'Lobot [A40] available resources as of {current_dt}'
                    elif lab == "lobot_problackwell":
                        summary = f'Lobot [Blackwell] available resources CPU Cores: {cpus_free} of {cpus_total}, MEMORY GB: {mem_free} of {mem_total}, GPU: {gpus_free} of {gpus_total} [{current_dt}]'
                        summary_title = f'Lobot [Blackwell] available resources as of {current_dt}'
                    elif lab == "edemsmithbusiness":
                        summary = f'Smith School of Business (Edem) available resources CPU Cores: {cpus_free} of {cpus_total}, MEMORY GB: {mem_free} of {mem_total}, GPU: {gpus_free} of {gpus_total} [{current_dt}]'
                        summary_title = f'Smith School of Business (Edem) available resources as of {current_dt}'
                    else: 
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
                        #pod_usage.append(f'{pod} == {pod_cpu} cores, {pod_mem}GB mem, {pod_gpu} gpu <a href="http://github.com/{pod}">{pod}</a>') 
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
                # Reset error counter on success
                self.error_counter = 0
            except Exception as e:
                error_type = type(e).__name__
                error_message = str(e)
                traceback_str = format_exc()
                
                self.error_counter += 1
                logger.error(f'{error_type}: {error_message} (error #{self.error_counter})')
                logger.error(traceback_str)
                
                # Send email notification with cooldown to avoid spam
                current_time = datetime.datetime.now()
                should_send_email = False
                
                if self.last_error_email_time is None:
                    should_send_email = True
                else:
                    time_since_last_email = (current_time - self.last_error_email_time).total_seconds() / 60
                    if time_since_last_email >= self.email_cooldown_minutes:
                        should_send_email = True
                
                if should_send_email:
                    send_error_email(
                        subject=f"{error_type} (error #{self.error_counter})",
                        error_message=error_message,
                        traceback_info=traceback_str
                    )
                    self.last_error_email_time = current_time
                
                # NEVER break - just continue to the next iteration
                logger.info(f"Continuing execution despite error. Will retry in {self.interval} seconds.")


class run_once():
    logger.info('Starting resource collector...')


def send_startup_email():
    """Send email notification when the script starts."""
    body = f"""
Resource Collector has started successfully.

Start Time: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Host: {os.uname().nodename}
Interval: {interval} seconds
Output File: {output_file}

The collector is now monitoring Kubernetes resources and will send notifications if errors occur.
"""
    send_notification_email("Started", body)


def send_shutdown_email(reason="Normal shutdown"):
    """Send email notification when the script stops."""
    body = f"""
Resource Collector has stopped.

Stop Time: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Host: {os.uname().nodename}
Reason: {reason}

The resource collector is no longer running.
"""
    send_notification_email("Stopped", body)


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    signal_name = signal.Signals(signum).name
    logger.info(f"Received signal {signal_name}, shutting down gracefully...")
    send_shutdown_email(f"Received signal {signal_name}")
    sys.exit(0)


if __name__ == '__main__':
    # Register shutdown handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(lambda: send_shutdown_email("Process exit"))
    
    # Send startup notification
    logger.info('Starting resource collector...')
    send_startup_email()
    
    # every 15 seconds
    timer = RepeatTimer(interval, run_once)
    timer.start()
