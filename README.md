# Slurm Dashboard

A Flask-based web application that provides a real-time dashboard for monitoring Slurm cluster status, jobs, and user statistics.

## Features

- Real-time job monitoring
- Cluster utilization statistics
- Top users statistics
- Clean and modern Bootstrap-based UI
- Auto-refresh functionality

## Requirements

- Python 3.x
- Slurm workload manager
- Access to Slurm commands (`squeue`, `sreport`)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd slurmdashboard
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

### Port and URL Settings

The application can be configured to run on different ports and URLs in two ways:

1. **Development Mode**
   - Open `slurmdashboard.py`
   - Modify the following line at the bottom of the file:
     ```python
     app.run(host='your.hostname.here', port=5000)
     ```

2. **Production Mode (Gunicorn)**
   - When running with gunicorn, modify the `--bind` parameter in the service file
   - Open `slurmdashboard.service`
   - Modify the ExecStart line:
     ```ini
     ExecStart=/path/to/venv/bin/gunicorn --workers 3 --bind hostname:port slurmdashboard:app
     ```

## Running as a System Service

1. **Configure the Service**
   - Copy the service file to systemd directory:
     ```bash
     sudo cp slurmdashboard.service /etc/systemd/system/
     ```
   - Edit the service file to match your environment:
     - Update `User` and `Group`
     - Modify `WorkingDirectory` to match your installation path
     - Adjust `Environment` variables if needed
     - Update the `ExecStart` path and bind address

2. **Enable and Start the Service**
   ```bash
   # Reload systemd to recognize the new service
   sudo systemctl daemon-reload

   # Enable the service to start on boot
   sudo systemctl enable slurmdashboard

   # Start the service
   sudo systemctl start slurmdashboard

   # Check status
   sudo systemctl status slurmdashboard
   ```

3. **Service Management Commands**
   ```bash
   # Stop the service
   sudo systemctl stop slurmdashboard

   # Restart the service
   sudo systemctl restart slurmdashboard

   # View logs
   sudo journalctl -u slurmdashboard
   ```

## Development

To run the application in development mode:

```bash
python slurmdashboard.py
```

The development server will start on http://localhost:5000 by default.

