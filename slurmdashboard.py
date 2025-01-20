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
    squeue_cmd = "squeue --format='%i|%u|%P|%j|%T|%M|%l|%D|%C|%N' --noheader"
    output = run_command(squeue_cmd)
    
    jobs = []
    job_stats = {'total': 0, 'running': 0, 'pending': 0}
    
    for line in output.strip().split('\n'):
        if line:
            job_id, user, partition, name, state, time, time_limit, nodes, cpus, nodelist = line.split('|')
            jobs.append({
                'job_id': job_id,
                'user': user,
                'partition': partition,
                'name': name,
                'state': state,
                'time': time,
                'time_limit': time_limit,
                'nodes': nodes,
                'cpus': cpus,
                'nodelist': nodelist
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
    
    # Format dates as Month/Day-Hour:Minute
    start_str = start_date.strftime('%m/%d-%H:%M')
    end_str = end_date.strftime('%m/%d-%H:%M')
    
    # Get CPU usage
    sreport_cmd = f"sreport user top start={start_str} end={end_str} TopCount=50 -t hourper --tres=cpu -n"
    app.logger.debug(f"Executing command: {sreport_cmd}")
    output = run_command(sreport_cmd)
    app.logger.debug(f"Raw sreport output:\n{output}")
    
    users = []
    
    for line in output.strip().split('\n'):
        if not line or line.startswith('-') or 'Cluster' in line or 'Login' in line:
            continue
            
        try:
            # Split by whitespace and get fields
            # Expected format: cluster login proper_name account tres_name usage
            fields = [f for f in line.split() if f]  # Remove empty strings
            if len(fields) < 6:  # Need at least all required fields
                app.logger.debug(f"Skipping line with insufficient fields: {line}")
                continue
                
            # Find the account field by looking for the TRES field (cpu) and taking the field before it
            try:
                tres_index = fields.index('cpu')
                account = fields[tres_index - 1]
                login = fields[1]
                usage = fields[-1]  # Last field contains the usage data
            except ValueError:
                app.logger.debug(f"Could not find 'cpu' field in line: {line}")
                continue
            
            app.logger.debug(f"Processing line for user {login}:")
            app.logger.debug(f"  Raw usage field: {usage}")
            app.logger.debug(f"  Account: {account}")
            
            # Extract usage percentage and hours from the format "1051(16.23%)"
            try:
                if '(' in usage:
                    hours_str, percent_str = usage.split('(')
                    hours = float(hours_str)
                    usage_percent = float(percent_str.rstrip('%)'))
                    app.logger.debug(f"  Parsed hours: {hours}, percent: {usage_percent}")
                else:
                    hours = float(usage)
                    usage_percent = 0.0
                    app.logger.debug(f"  Parsed hours (no percent): {hours}")
            except (ValueError, IndexError) as e:
                app.logger.error(f"  Error parsing usage values: {str(e)}")
                hours = 0.0
                usage_percent = 0.0
            
            user_data = {
                'user': login.rstrip('+'),  # Remove + from truncated names
                'account': account,
                'cpu_percent': usage_percent,
                'cpu_hours': hours
            }
            app.logger.debug(f"  Adding user data: {user_data}")
            users.append(user_data)
            
        except Exception as e:
            app.logger.error(f"Error processing line: {str(e)}")
            continue  # Skip malformed lines
    
    # Sort users by CPU percentage
    users.sort(key=lambda x: x['cpu_percent'], reverse=True)
    app.logger.debug("Final sorted users data:")
    for user in users[:5]:
        app.logger.debug(f"  {user}")
    
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
    
    # Format dates with hours, minutes, seconds
    start_str = start_date.strftime('%Y-%m-%dT%H:%M:%S')
    end_str = end_date.strftime('%Y-%m-%dT%H:%M:%S')
    
    # Get cluster utilization
    sreport_cmd = f"sreport cluster utilization start={start_str} end={end_str} -t Hours -n"
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
                'timestamp': end_date.strftime('%Y-%m-%dT%H:%M:%S'),
                'utilization': round(utilization, 2),
                'allocated_hours': allocated,
                'total_hours': reported,
                'idle_hours': idle,
                'down_hours': down
            }

            return {
                'data': [data_point],
                'period': {
                    'start': start_str,
                    'end': end_str
                }
            }

    except Exception as e:
        app.logger.error(f"Error parsing cluster usage: {str(e)}")
        return {"error": "Could not parse sreport output", "data": []}

def get_node_status():
    # Get node status using sinfo with a detailed format
    sinfo_cmd = "sinfo --format='%n|%P|%t|%C|%m|%e|%d' --noheader"
    output = run_command(sinfo_cmd)
    
    nodes = {}
    node_stats = {'total': 0, 'allocated': 0, 'idle': 0, 'down': 0, 'reserved': 0}
    
    for line in output.strip().split('\n'):
        if line:
            nodename, partition, state, cpus, memory, free_mem, disk = line.split('|')
            
            # Parse CPU info (format: alloc/idle/other/total)
            cpu_parts = cpus.split('/')
            
            # If node already exists, just add the partition
            if nodename in nodes:
                if partition not in nodes[nodename]['partitions']:
                    nodes[nodename]['partitions'].append(partition)
                continue
            
            # Create new node entry
            nodes[nodename] = {
                'name': nodename,
                'partitions': [partition],
                'state': state,
                'cpus': {
                    'allocated': cpu_parts[0],
                    'idle': cpu_parts[1],
                    'other': cpu_parts[2],
                    'total': cpu_parts[3]
                },
                'memory': memory,
                'free_memory': free_mem,
                'disk': disk
            }
            
            # Update statistics only once per node
            node_stats['total'] += 1
            if 'alloc' in state.lower():
                node_stats['allocated'] += 1
            elif 'idle' in state.lower():
                node_stats['idle'] += 1
            elif 'down' in state.lower():
                node_stats['down'] += 1
            elif 'resv' in state.lower():
                node_stats['reserved'] += 1
    
    return {'nodes': list(nodes.values()), 'stats': node_stats}

def get_hourly_usage():
    # Get CPU usage for the last 24 hours in 30-minute intervals
    end_date = datetime.now()
    start_date = end_date - timedelta(hours=24)
    
    data_points = []
    current = end_date
    
    # Collect data for each 30-minute interval
    while current >= start_date:
        interval_end = current
        interval_start = current - timedelta(minutes=30)
        
        # Format dates
        start_str = interval_start.strftime('%Y-%m-%dT%H:%M:%S')
        end_str = interval_end.strftime('%Y-%m-%dT%H:%M:%S')
        
        # Get cluster utilization for this interval
        sreport_cmd = f"sreport cluster utilization start={start_str} end={end_str} -t Hours -p -n"
        output = run_command(sreport_cmd)
        
        try:
            # Parse pipe-separated values
            for line in output.strip().split('\n'):
                if not line or line.startswith('-') or 'Cluster' in line:
                    continue
                    
                parts = line.strip().split('|')
                if len(parts) >= 7:
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
                        
                    # Create data point
                    data_point = {
                        'timestamp': interval_end.strftime('%Y-%m-%dT%H:%M:%S'),
                        'utilization': round(utilization, 2),
                        'allocated': allocated,
                        'total': reported,
                        'idle': idle,
                        'down': down
                    }
                    data_points.append(data_point)
                    break  # Take only the first valid line for this interval
        except Exception as e:
            app.logger.error(f"Error parsing interval {start_str} to {end_str}: {str(e)}")
        
        current = interval_start
    
    # Sort data points by timestamp
    data_points.sort(key=lambda x: x['timestamp'])
    
    return {
        'data': data_points,
        'period': {
            'start': start_date.strftime('%Y-%m-%dT%H:%M:%S'),
            'end': end_date.strftime('%Y-%m-%dT%H:%M:%S')
        }
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/nodes')
def nodes_page():
    return render_template('nodes.html')

@app.route('/api/jobs')
def jobs():
    return jsonify(get_current_jobs())

@app.route('/api/usage')
def usage():
    return jsonify(get_cluster_usage())

@app.route('/api/top_users')
def top_users():
    return jsonify(get_top_users())

@app.route('/api/nodes')
def nodes():
    return jsonify(get_node_status())

@app.route('/api/hourly_usage')
def hourly_usage():
    return jsonify(get_hourly_usage())

if __name__ == '__main__':
    app.run(host='pc059.cern.ch', port=5000)
