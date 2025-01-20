from flask import Flask, render_template, jsonify
import subprocess
import json
from datetime import datetime, timedelta
from collections import Counter
import logging
import sys

app = Flask(__name__)

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def run_command(command):
    try:
        app.logger.debug(f"Executing command: {command}")
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.stderr:
            app.logger.error(f"Command stderr: {result.stderr}")
        app.logger.debug(f"Command output: {result.stdout}")
        return result.stdout
    except Exception as e:
        app.logger.error(f"Error executing command: {str(e)}")
        return str(e)

def get_current_jobs():
    # Get current jobs using squeue with a nice format
    squeue_cmd = "squeue --format='%i|%u|%P|%j|%T|%M|%l|%D|%C' --noheader"
    output = run_command(squeue_cmd)
    
    jobs = []
    job_stats = {'total': 0, 'running': 0, 'pending': 0}
    
    for line in output.strip().split('\n'):
        if line:
            job_id, user, partition, name, state, time, time_limit, nodes, cpus = line.split('|')
            jobs.append({
                'job_id': job_id,
                'user': user,
                'partition': partition,
                'name': name,
                'state': state,
                'time': time,
                'time_limit': time_limit,
                'nodes': nodes,
                'cpus': cpus
            })
            job_stats['total'] += 1
            if state == 'RUNNING':
                job_stats['running'] += 1
            elif state == 'PENDING':
                job_stats['pending'] += 1
    
    return {'jobs': jobs, 'stats': job_stats}

def get_top_users():
    # Get top users using sreport with CPU metrics
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    # Format dates as MMDD
    start_str = start_date.strftime('%m%d')
    end_str = end_date.strftime('%m%d')
    
    sreport_cmd = f"sreport user top start={start_str} end={end_str} TopCount=50 -t hourper --tres=cpu -n"
    output = run_command(sreport_cmd)
    
    users = []
    
    for line in output.strip().split('\n'):
        # Skip empty lines, headers and separators
        if not line or line.startswith('-') or 'Cluster' in line or 'Login' in line:
            continue
            
        # Split line into fixed-width fields based on the format shown in example
        try:
            # Fixed width parsing based on example output format
            cluster = line[0:10].strip()
            login = line[10:20].strip()
            proper_name = line[20:35].strip()
            account = line[35:50].strip() 
            tres_name = line[50:65].strip()
            usage = line[65:].strip()
            
            # Extract usage percentage and hours from the format "1051(16.23%)"
            try:
                if '(' in usage:
                    hours_str, percent_str = usage.split('(')
                    hours = float(hours_str)
                    usage_percent = float(percent_str.rstrip('%)'))
                else:
                    hours = float(usage)
                    usage_percent = 0.0
            except (ValueError, IndexError):
                hours = 0.0
                usage_percent = 0.0
            
            users.append({
                'user': login.rstrip('+'),  # Remove + from truncated names
                'account': account,
                'cpu_percent': usage_percent,
                'cpu_hours': hours
            })
            
        except Exception as e:
            continue  # Skip malformed lines
    
    # Sort users by CPU percentage
    users.sort(key=lambda x: x['cpu_percent'], reverse=True)
    
    return {
        'users': users[:5],  # Top 5 users
        'period': {
            'start': start_date.strftime('%Y-%m-%d'),
            'end': end_date.strftime('%Y-%m-%d')
        }
    }

def get_cluster_usage():
    # Get cluster usage for the last month using sreport
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)  # Default to last 30 days
    
    # Get cluster utilization
    sreport_cmd = f"sreport cluster utilization start={start_date.strftime('%Y-%m-%d')} end={end_date.strftime('%Y-%m-%d')} -t Hours -n"
    output = run_command(sreport_cmd)
    
    try:
        # Parse the text output
        lines = output.strip().split('\n')
        if not lines:
            return {"error": "No data available", "data": []}

        # Get the line with the numbers (should be the last non-empty line)
        data_line = None
        for line in lines:
            if line.strip() and not line.startswith('-') and 'Cluster' not in line:
                data_line = line

        if not data_line:
            return {"error": "No data available", "data": []}

        # Split the line into fields and convert to numbers
        parts = [p for p in data_line.split() if p]
        if len(parts) >= 7:
            cluster = parts[0]
            allocated = float(parts[1])
            down = float(parts[2])
            plnd_down = float(parts[3])
            idle = float(parts[4])
            reserved = float(parts[5])
            reported = float(parts[6])
            
            # Calculate utilization
            if reported > 0:
                utilization = (allocated / reported) * 100
            else:
                utilization = 0

            # Create a single data point
            data_point = {
                'timestamp': datetime.now().strftime('%Y-%m-%d'),
                'utilization': round(utilization, 2),
                'allocated_hours': allocated,
                'total_hours': reported,
                'idle_hours': idle,
                'down_hours': down
            }

            return {
                'data': [data_point],
                'period': {
                    'start': start_date.strftime('%Y-%m-%d'),
                    'end': end_date.strftime('%Y-%m-%d')
                }
            }

    except Exception as e:
        app.logger.error(f"Error parsing cluster usage: {str(e)}")
        return {"error": "Could not parse sreport output", "data": []}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/jobs')
def jobs():
    return jsonify(get_current_jobs())

@app.route('/api/usage')
def usage():
    return jsonify(get_cluster_usage())

@app.route('/api/top_users')
def top_users():
    return jsonify(get_top_users())

if __name__ == '__main__':
    app.run(host='pc059.cern.ch', port=5000)
