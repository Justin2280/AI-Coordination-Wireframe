#!/usr/bin/env python3
"""
Deployment script for Spaceship Coordination Experiment
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def run_command(command, check=True):
    """Run a shell command"""
    print(f"Running: {command}")
    try:
        result = subprocess.run(command, shell=True, check=check, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        if e.stderr:
            print(f"Stderr: {e.stderr}")
        return False


def check_prerequisites():
    """Check if required software is installed"""
    print("Checking prerequisites...")
    
    # Check Python version
    if sys.version_info < (3, 11):
        print("ERROR: Python 3.11+ is required")
        return False
    
    # Check if virtual environment exists
    if not Path("venv").exists():
        print("Virtual environment not found. Creating...")
        if not run_command("python -m venv venv"):
            return False
    
    return True


def setup_environment():
    """Set up the Python environment"""
    print("Setting up environment...")
    
    # Activate virtual environment and install requirements
    if os.name == 'nt':  # Windows
        pip_cmd = "venv\\Scripts\\pip"
        python_cmd = "venv\\Scripts\\python"
    else:  # Unix/Linux/Mac
        pip_cmd = "venv/bin/pip"
        python_cmd = "venv/bin/python"
    
    # Upgrade pip
    if not run_command(f"{pip_cmd} install --upgrade pip"):
        return False
    
    # Install requirements
    if not run_command(f"{pip_cmd} install -r requirements.txt"):
        return False
    
    return True


def setup_database():
    """Set up the database"""
    print("Setting up database...")
    
    # Check if .env file exists
    if not Path(".env").exists():
        print("Creating .env file...")
        env_content = """DEBUG=True
SECRET_KEY=your-secret-key-here-change-in-production
DB_NAME=spaceship_coordination
DB_USER=postgres
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=5432
REDIS_URL=redis://localhost:6379
ALLOWED_HOSTS=localhost,127.0.0.1
"""
        with open(".env", "w") as f:
            f.write(env_content)
        print("Please edit .env file with your actual database credentials")
    
    # Run migrations
    if os.name == 'nt':  # Windows
        python_cmd = "venv\\Scripts\\python"
    else:  # Unix/Linux/Mac
        python_cmd = "venv/bin/python"
    
    if not run_command(f"{python_cmd} manage.py migrate"):
        return False
    
    return True


def create_superuser():
    """Create a superuser account"""
    print("Creating superuser account...")
    
    if os.name == 'nt':  # Windows
        python_cmd = "venv\\Scripts\\python"
    else:  # Unix/Linux/Mac
        python_cmd = "venv/bin/python"
    
    # Check if superuser already exists
    result = subprocess.run(
        f"{python_cmd} manage.py shell -c \"from django.contrib.auth.models import User; print(User.objects.filter(is_superuser=True).count())\"",
        shell=True, capture_output=True, text=True
    )
    
    if result.stdout.strip() == "0":
        print("No superuser found. Creating one...")
        if not run_command(f"{python_cmd} manage.py createsuperuser"):
            return False
    else:
        print("Superuser already exists")
    
    return True


def start_services():
    """Start required services"""
    print("Starting services...")
    
    # Check if Redis is running
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("Redis is already running")
    except:
        print("Redis is not running. Please start Redis in a separate terminal:")
        print("  redis-server")
    
    # Start Django development server
    if os.name == 'nt':  # Windows
        python_cmd = "venv\\Scripts\\python"
    else:  # Unix/Linux/Mac
        python_cmd = "venv/bin/python"
    
    print("Starting Django development server...")
    print("The application will be available at http://localhost:8000")
    print("Admin interface: http://localhost:8000/admin")
    print("Press Ctrl+C to stop the server")
    
    run_command(f"{python_cmd} manage.py runserver", check=False)


def run_tests():
    """Run the test suite"""
    print("Running tests...")
    
    if os.name == 'nt':  # Windows
        python_cmd = "venv\\Scripts\\python"
    else:  # Unix/Linux/Mac
        python_cmd = "venv/bin/python"
    
    if not run_command(f"{python_cmd} manage.py test spaceship_coordination"):
        return False
    
    return True


def main():
    parser = argparse.ArgumentParser(description="Deploy Spaceship Coordination Experiment")
    parser.add_argument("--setup", action="store_true", help="Set up the environment")
    parser.add_argument("--test", action="store_true", help="Run tests")
    parser.add_argument("--start", action="store_true", help="Start the application")
    parser.add_argument("--full", action="store_true", help="Full setup and start")
    
    args = parser.parse_args()
    
    if args.full or args.setup:
        if not check_prerequisites():
            sys.exit(1)
        
        if not setup_environment():
            sys.exit(1)
        
        if not setup_database():
            sys.exit(1)
        
        if not create_superuser():
            sys.exit(1)
    
    if args.test:
        if not run_tests():
            sys.exit(1)
    
    if args.full or args.start:
        start_services()
    
    if not any([args.setup, args.test, args.start, args.full]):
        parser.print_help()


if __name__ == "__main__":
    main()




