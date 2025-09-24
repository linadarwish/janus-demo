#!/bin/bash

# Janus WebRTC Demo Automation Script
# This script automates the setup and running of the entire Janus WebRTC demo

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to wait for service to be ready
wait_for_service() {
    local host=$1
    local port=$2
    local service_name=$3
    local max_attempts=3000
    local attempt=1

    print_status "Waiting for $service_name to be ready at $host:$port..."

    while [ $attempt -le $max_attempts ]; do
        if nc -z $host $port 2>/dev/null; then
            print_success "$service_name is ready!"
            return 0
        fi

        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done

    print_error "$service_name failed to start within expected time"
    return 1
}

# Function to check if port is in use
check_port() {
    local port=$1
    local service_name=$2

    if lsof -i :$port >/dev/null 2>&1; then
        print_warning "Port $port is already in use (needed for $service_name)"
        return 1
    fi
    return 0
}

# Function to free up ports used by demo
free_demo_ports() {
    print_status "Checking for conflicting processes on demo ports..."

    local ports_to_check=(8088 8188 8090 3000)
    local conflicts_found=false

    for port in "${ports_to_check[@]}"; do
        if lsof -i :$port >/dev/null 2>&1; then
            conflicts_found=true
            print_warning "Port $port is in use"

            # Find and display process using the port
            local process_info=$(lsof -i :$port | tail -n +2)
            echo "$process_info"

            # Kill processes using the port
            local pids=$(lsof -t -i :$port)
            if [ ! -z "$pids" ]; then
                print_status "Killing processes using port $port: $pids"
                echo "$pids" | xargs kill -9 2>/dev/null || true
                sleep 2
            fi
        fi
    done

    # Clean up any existing janus containers
    local existing_containers=$(docker ps -aq --filter "name=janus-demo")
    if [ ! -z "$existing_containers" ]; then
        print_status "Removing existing janus-demo containers..."
        docker rm -f $existing_containers >/dev/null 2>&1 || true
    fi

    # Clean up any janus containers by image
    local janus_containers=$(docker ps -q --filter "ancestor=janus")
    if [ ! -z "$janus_containers" ]; then
        print_status "Removing existing janus containers..."
        echo "$janus_containers" | xargs docker kill >/dev/null 2>&1 || true
    fi

    if [ "$conflicts_found" = true ]; then
        print_success "Port conflicts resolved"
        sleep 2  # Give processes time to fully terminate
    fi
}

# Function to cleanup processes on exit
cleanup() {
    print_warning "Cleaning up processes..."

    # Kill background processes
    if [ ! -z "$JANUS_PID" ]; then
        kill $JANUS_PID 2>/dev/null || true
    fi

    if [ ! -z "$NODE_DRIVER_PID" ]; then
        kill $NODE_DRIVER_PID 2>/dev/null || true
    fi

    if [ ! -z "$CLIENT_PID" ]; then
        kill $CLIENT_PID 2>/dev/null || true
    fi

    # Kill any Docker containers
    docker ps -q --filter "ancestor=janus" | xargs -r docker kill >/dev/null 2>&1 || true
    docker ps -q --filter "name=janus-demo" | xargs -r docker kill >/dev/null 2>&1 || true

    print_success "Cleanup completed"
}

# Set trap to cleanup on exit
trap cleanup EXIT INT TERM

# Check prerequisites
print_status "Checking prerequisites..."

if ! command_exists docker; then
    print_error "Docker is not installed. Please install Docker and try again."
    exit 1
fi

# Check if Docker daemon is running
print_status "Checking Docker daemon..."
if ! docker info >/dev/null 2>&1; then
    print_error "Docker daemon is not running or not accessible."
    print_error "Please ensure Docker Desktop is started and try again."
    echo ""
    echo -e "${BLUE}Troubleshooting steps:${NC}"
    echo -e "  1. Make sure Docker Desktop is running"
    echo -e "  2. Check if you can run: docker ps"
    echo -e "  3. Restart Docker Desktop if needed"
    echo -e "  4. On macOS, you might need to wait a moment after starting Docker Desktop"
    echo ""
    exit 1
fi

print_success "Docker daemon is running"

if ! command_exists node; then
    print_error "Node.js is not installed. Please install Node.js and try again."
    exit 1
fi

if ! command_exists npm; then
    print_error "npm is not installed. Please install npm and try again."
    exit 1
fi

if ! command_exists nc; then
    print_warning "netcat (nc) is not available. Service readiness checks may not work properly."
fi

print_success "Prerequisites check passed"

# Check for port conflicts and offer to clean them up
print_status "Checking for port conflicts..."
ports_to_check=(8088 8188 8090 3000)
conflicts_found=false

for port in "${ports_to_check[@]}"; do
    if lsof -i :$port >/dev/null 2>&1; then
        conflicts_found=true
        print_warning "Port $port is already in use"
    fi
done

if [ "$conflicts_found" = true ]; then
    echo ""
    print_warning "Some ports required by the demo are already in use."
    echo -e "${BLUE}The following ports are needed:${NC}"
    echo -e "  • 8088 - Janus HTTP API"
    echo -e "  • 8188 - Janus WebSocket API"
    echo -e "  • 8090 - Janus Node Driver"
    echo -e "  • 3000 - React Client"
    echo ""

    # Show which processes are using the ports
    for port in "${ports_to_check[@]}"; do
        if lsof -i :$port >/dev/null 2>&1; then
            print_warning "Port $port is being used by:"
            lsof -i :$port | tail -n +2 | awk '{print "  " $1 " (PID: " $2 ")"}'
        fi
    done

    echo ""
    read -p "$(echo -e ${YELLOW}Would you like to automatically free these ports? [y/N]: ${NC})" -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        free_demo_ports

        # Verify ports are now free
        conflicts_still_exist=false
        for port in "${ports_to_check[@]}"; do
            if lsof -i :$port >/dev/null 2>&1; then
                conflicts_still_exist=true
                print_warning "Port $port is still in use after cleanup attempt"
            fi
        done

        if [ "$conflicts_still_exist" = true ]; then
            print_error "Some ports are still in use. Please free them manually and try again."
            exit 1
        else
            print_success "All ports have been freed successfully"
        fi
    else
        print_error "Cannot proceed with port conflicts. Please free the ports manually and try again."
        exit 1
    fi
else
    print_success "No port conflicts detected"
fi

# Build Janus Docker image
print_status "Building Janus Docker image (this may take several minutes)..."
cd janus

# Check if image already exists
if docker images janus -q | grep -q .; then
    print_warning "Janus Docker image already exists"
    read -p "$(echo -e ${YELLOW}Would you like to rebuild it? [y/N]: ${NC})" -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_success "Using existing Janus Docker image"
        cd ..
    else
        print_status "Rebuilding Janus Docker image..."
        print_status "This may take several minutes - showing build output..."
        echo ""
        if docker build -t janus . 2>&1 | tee build.log; then
            print_success "Janus Docker image rebuilt successfully"
        else
            print_error "Failed to rebuild Janus Docker image."
            echo ""
            echo -e "${YELLOW}Last few lines of build log:${NC}"
            tail -20 build.log
            echo ""
            print_error "Full build log available in: $(pwd)/build.log"
            exit 1
        fi
        cd ..
    fi
else
    print_status "This may take several minutes - showing build output..."
    echo ""
    if docker build -t janus . 2>&1 | tee build.log; then
        print_success "Janus Docker image built successfully"
    else
        print_error "Failed to build Janus Docker image."
        echo ""
        echo -e "${YELLOW}Last few lines of build log:${NC}"
        tail -20 build.log
        echo ""
        print_error "Full build log available in: $(pwd)/build.log"
        exit 1
    fi
    cd ..
fi

# Install dependencies for janus-node-driver
print_status "Installing Janus Node Driver dependencies..."
cd janus-node-driver
if [ ! -d node_modules ]; then
    if npm install > install.log 2>&1; then
        print_success "Janus Node Driver dependencies installed"
    else
        print_error "Failed to install Janus Node Driver dependencies. Check install.log for details."
        exit 1
    fi
else
    print_success "Janus Node Driver dependencies already installed"
fi
cd ..

# Install dependencies for client
print_status "Installing React client dependencies..."
cd client
if [ ! -d node_modules ]; then
    if npm install > install.log 2>&1; then
        print_success "React client dependencies installed"
    else
        print_error "Failed to install React client dependencies. Check install.log for details."
        exit 1
    fi
else
    print_success "React client dependencies already installed"
fi
cd ..

# Start Janus server
print_status "Starting Janus server..."
docker run -d --rm -p 8088:8088 -p 8188:8188 --name janus-demo janus > /dev/null
JANUS_CONTAINER_ID=$(docker ps -q --filter "name=janus-demo")

if [ -z "$JANUS_CONTAINER_ID" ]; then
    print_error "Failed to start Janus server"
    exit 1
fi

print_success "Janus server started (Container ID: $JANUS_CONTAINER_ID)"

# Wait for Janus to be ready
if command_exists nc; then
    wait_for_service localhost 8088 "Janus HTTP API"
    wait_for_service localhost 8188 "Janus WebSocket API"
else
    print_warning "Waiting 10 seconds for Janus to start (nc not available for proper check)..."
    sleep 10
fi

# Start Janus Node Driver
print_status "Starting Janus Node Driver..."
cd janus-node-driver
npm start > ../node-driver.log 2>&1 &
NODE_DRIVER_PID=$!
cd ..

print_success "Janus Node Driver started (PID: $NODE_DRIVER_PID)"

# Wait for Node Driver to be ready
if command_exists nc; then
    wait_for_service localhost 8090 "Janus Node Driver"
else
    print_warning "Waiting 5 seconds for Node Driver to start (nc not available for proper check)..."
    sleep 5
fi

# Start React client
print_status "Starting React client..."
cd client
npm start > ../client.log 2>&1 &
CLIENT_PID=$!
cd ..

print_success "React client started (PID: $CLIENT_PID)"

# Wait for React client to be ready
if command_exists nc; then
    wait_for_service localhost 3000 "React client"
else
    print_warning "Waiting 15 seconds for React client to start (nc not available for proper check)..."
    sleep 15
fi

# Display status
print_success "🎉 Janus WebRTC Demo is now running!"
echo ""
echo -e "${GREEN}Components:${NC}"
echo -e "  • Janus Server:      http://localhost:8088 (HTTP API) / ws://localhost:8188 (WebSocket)"
echo -e "  • Node Driver:       ws://localhost:8090"
echo -e "  • React Client:      http://localhost:3000"
echo ""
echo -e "${BLUE}The demo should automatically open in your browser.${NC}"
echo -e "${BLUE}If not, navigate to: http://localhost:3000${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Keep script running and monitor processes
while true; do
    # Check if Janus container is still running
    if ! docker ps -q --filter "name=janus-demo" | grep -q .; then
        print_error "Janus container stopped unexpectedly"
        exit 1
    fi

    # Check if Node Driver is still running
    if ! ps -p $NODE_DRIVER_PID > /dev/null 2>&1; then
        print_error "Janus Node Driver stopped unexpectedly"
        exit 1
    fi

    # Check if React client is still running
    if ! ps -p $CLIENT_PID > /dev/null 2>&1; then
        print_error "React client stopped unexpectedly"
        exit 1
    fi

    sleep 5
done