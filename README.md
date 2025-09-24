# 🎭 Janus demo

This repo contains a simple WebRTC demo that uses a [Janus](https://github.com/meetecho/janus-gateway) server to play back a video stream to a connected client.

## 🏛️ Architecture

There are three main components in this demo:

- The [Janus server](janus/), which is the actual Janus server. It implements the WebRTC stack (including the signalling server).
- The [Janus Node driver](janus-node-driver/), which is a NodeJS server that implements application-level logic on top of the Janus server, acting as a middleware between a client and the Janus server.
- The [WebRTC client](client/), which is a simple WebRTC client written in React.

## 📁 Directory Structure

```
janus-demo/
├── client/                 # React WebRTC client application
│   ├── src/               # React source code
│   └── package.json       # Client dependencies
├── janus/                 # Janus Gateway server configuration
│   ├── Dockerfile         # Docker container for Janus server
│   └── janus.jcfg         # Janus configuration files
├── janus-node-driver/     # Node.js middleware server
│   ├── index.js          # Main server logic and WebSocket handling
│   └── package.json      # Server dependencies
├── scripts/              # Utility and analysis scripts
│   ├── mjr-to-webm.sh   # Convert Janus .mjr recordings to .webm
│   └── vmaf/            # Video quality analysis tools
│       ├── README.md            # VMAF tools documentation
│       ├── generate_frame_video.py  # Generate test videos with frame numbers
│       ├── plot_vmaf.py         # Visualize VMAF analysis results
│       ├── video_sync_vmaf.py   # Synchronize videos and run VMAF analysis
│       └── pyproject.toml       # Python dependencies
└── run-demo.sh          # Main script to start the entire demo
```

## 🚀 Quick Start

### Running the Full Stack

The easiest way to run the entire demo is using the automated script:

```bash
./run-demo.sh
```

This script will:
- Check prerequisites (Docker, Node.js, npm)
- Build the Janus Docker image
- Install all dependencies
- Start all services in the correct order
- Monitor the services and provide status updates

The demo will be available at: **http://localhost:3000**

### Manual Setup

If you prefer to run components individually:

1. **Build and start Janus server**:
   ```bash
   cd janus
   docker build -t janus .
   docker run -d --rm -p 8088:8088 -p 8188:8188 --name janus-demo janus
   ```

2. **Start the Node.js middleware**:
   ```bash
   cd janus-node-driver
   npm install
   npm start
   ```

3. **Start the React client**:
   ```bash
   cd client
   npm install
   npm start
   ```

### Prerequisites

- **Docker** - For running the Janus server
- **Node.js** (v16+) and **npm** - For the middleware and client
- **netcat (nc)** - Optional, for service readiness checks

## 🧪 Video Quality Testing & Recording

This demo includes comprehensive video quality analysis tools and recording capabilities:

### Recording Options

- **Client-side recording**: Uses the browser's MediaRecorder API to record the video element directly
- **Server-side recording**: Janus Gateway can record WebRTC streams to .mjr format on the server

### Quality Testing Tools

- **Convert recordings**: Use `scripts/mjr-to-webm.sh` to convert Janus .mjr files to video format
- **Quality analysis**: Full VMAF-based video quality testing suite in `scripts/vmaf/`

For complete setup instructions and usage examples, see [`scripts/vmaf/README.md`](scripts/vmaf/README.md).

## 🤔 How it works

The way it works is:

- The Janode server connects to the Janus server using a WebSocket.
- The client connects to the Janode server using another WebSocket.
- The client sends a `start` message, to which the Janode server responds with a `ready` message.
- The client sends an `offer` message that contains an SDP offer. The Janode server forwards this message to the Janus server, which returns an SDP answer, that is then sent back to the client as an `answer` message.
- The client sends one `trickle` message for each ICE candidate, and the Janode server forwards them to the Janus server.
- Once all ICE candidates have been sent, the client sends a `trickle-complete` message.
- At that point, the client and the Janus server are connected and exchanging video streams through WebRTC.

