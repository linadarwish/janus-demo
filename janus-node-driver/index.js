import Janode from "janode";
const { Logger } = Janode;
import { WebSocketServer } from "ws";
import EchoTestPlugin from "janode/plugins/echotest";
import fs from "fs";
import path from "path";
import { execSync } from "child_process";

// Connect to Janus Gateway
const connection = await Janode.connect({
  is_admin: false,
  address: {
    url: "ws://127.0.0.1:8188",
    apisecret: "DOES_NOT_MATTER",
  },
});

const session = await connection.create();
let echoHandle; // A handle for the EchoTestPlugin
let currentRecordingFilename = null; // Track current recording

// Start WebSocket server
const WSSPORT = 8090;

const websockerServer = new WebSocketServer({
  port: WSSPORT,
});

// Utility to send stringified messages to the WebSocket server.
const sendWsMessage = (ws, type, body) => {
  ws.send(
    JSON.stringify({
      type,
      body,
    }),
    { binary: false }
  );
};

// Main logic of the server.
// Basically, it listens to 4 types of messages:
// - start: to start a session
// - offer: to receive the offer from the client
// - trickle: to receive the ICE candidate from the client
// - trickle-complete: to signal the end of ICE candidates
// The server talks with the `EchoTestPlugin` of the Janus Gateway, which is a plugin that simply 
// echoes back the audio and video streams.
const onMessage = async (ws, request, message) => {
  const remoteAddress = request.socket.address();
  const remote = `[${remoteAddress.address}:${remoteAddress.port}]`;
  try {
    const parsedMessage = JSON.parse(message);
    const { type, body } = parsedMessage;

    switch (type) {
      case "start":
        Logger.info(remote, "Starting session");
        echoHandle = await session.attach(EchoTestPlugin);
        sendWsMessage(ws, "ready");
        break;
      case "offer":
        Logger.info(remote, "Offer received");
        const { audio, video, offer, bitrate, record, filename } = body;

        // Generate a unique filename for recording if recording is enabled
        const recordFilename = record ? `janus-rec-${Date.now()}-${Math.random().toString(36).substr(2, 9)}` : filename;

        const { jsep: answer } = await echoHandle.start({
          audio,
          video,
          jsep: offer,
          bitrate,
          record: record || false, // Enable recording based on client request
          filename: recordFilename,
        });

        if (record) {
          currentRecordingFilename = recordFilename;
          Logger.info(remote, `Recording started with filename: ${recordFilename}`);
        }

        sendWsMessage(ws, "answer", answer);
        break;
      case "trickle":
        Logger.info(remote, "trickle received");
        await echoHandle.trickle(body.candidate);
        break;
      case "trickle-complete":
        Logger.info(remote, "trickle-complete received");
        echoHandle.trickleComplete();
        break;
      case "record-control":
        Logger.info(remote, "record-control received", body);
        const { action, recordFilename: controlFilename } = body;

        if (action === "start") {
          // EchoTest plugin requires recording to be enabled at connection time
          // Tell client to reconnect with recording enabled
          sendWsMessage(ws, "record-error", {
            error: "Please disconnect and reconnect with Janus recording enabled",
            reconnectRequired: true
          });
        } else if (action === "stop" && echoHandle && currentRecordingFilename) {
          // Stop recording and get the file
          try {
            Logger.info(remote, "Recording will stop when connection ends");
            console.log("Processing record-control stop, currentRecordingFilename:", currentRecordingFilename);

            const recordingFilename = currentRecordingFilename;
            currentRecordingFilename = null;

            // First, stop the recording by destroying the handle
            await echoHandle.detach();
            echoHandle = null;

            console.log("Handle detached, waiting for recording file...");

            // Give Janus more time to finish writing the file
            setTimeout(() => {
              try {
                console.log("Looking for the newest .mjr file in container...");

                const containerName = 'janus-demo';
                // Find the most recently modified .mjr file (excluding sample files)
                const findCommand = `docker exec ${containerName} find /janus-gateway -name "*.mjr" -not -name "rec-sample-*" -type f -exec ls -t {} + | head -1`;
                console.log("Running command:", findCommand);

                let mjrFile = null;
                try {
                  const dockerOutput = execSync(findCommand, { encoding: 'utf8', timeout: 5000 }).trim();
                  console.log("Newest file found:", dockerOutput);

                  if (dockerOutput) {
                    mjrFile = dockerOutput;
                  }
                } catch (dockerError) {
                  console.error("Docker command failed:", dockerError.message);
                }

                if (mjrFile) {
                  try {
                    const fileName = path.basename(mjrFile);
                    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                    console.log(`Processing newest file: ${fileName}`);

                    // Copy file from container to temp directory
                    const tempDir = path.join(process.cwd(), 'temp-recordings');
                    if (!fs.existsSync(tempDir)) {
                      fs.mkdirSync(tempDir, { recursive: true });
                    }

                    const localPath = path.join(tempDir, fileName);
                    const copyCommand = `docker cp ${containerName}:${mjrFile} ${localPath}`;
                    execSync(copyCommand, { timeout: 10000 });
                    console.log(`✓ Copied ${fileName} to local filesystem`);

                    // Read and send the file
                    const fileData = fs.readFileSync(localPath);
                    console.log("File read successfully, size:", fileData.length, "bytes");

                    const base64Data = fileData.toString('base64');
                    const timestampedFilename = `${timestamp}-${fileName}`;

                    Logger.info(remote, `Sending .mjr file: ${fileName} as ${timestampedFilename}`);
                    sendWsMessage(ws, "record-stopped", {
                      filename: timestampedFilename,
                      fileData: base64Data
                    });
                    console.log(`✓ Successfully sent ${fileName} to client`);

                    // Clean up files after successful download
                    fs.unlinkSync(localPath);
                    console.log("✓ Cleaned up local file:", localPath);

                    const rmCommand = `docker exec ${containerName} rm ${mjrFile}`;
                    execSync(rmCommand, { timeout: 5000 });
                    console.log("✓ Cleaned up container file:", mjrFile);

                  } catch (fileError) {
                    console.error(`✗ Error processing file:`, fileError.message);
                    Logger.error(remote, `Error processing .mjr file`, fileError);

                    sendWsMessage(ws, "record-stopped", {
                      error: `Failed to process recording file`,
                      details: fileError.message
                    });
                  }
                } else {
                  Logger.warn(remote, "No .mjr file found after recording");
                  sendWsMessage(ws, "record-stopped", {
                    error: "No recording file found"
                  });
                }

              } catch (error) {
                Logger.error(remote, "Error processing recording file", error);
                console.error("Error details:", error);
                sendWsMessage(ws, "record-stopped", {
                  error: "Could not process recording file",
                  details: error.message
                });
              }
            }, 5000); // Wait 5 seconds for file to be written (increased from 2s)

          } catch (error) {
            Logger.error(remote, "Failed to stop recording", error);
            sendWsMessage(ws, "record-stopped", {
              error: "Failed to stop recording",
              details: error.message
            });
          }
        } else {
          console.log("record-control stop conditions not met:");
          console.log("- action:", action);
          console.log("- echoHandle exists:", !!echoHandle);
          console.log("- currentRecordingFilename:", currentRecordingFilename);
        }
        break;
      default:
        Logger.error(remote, "Unknown message type", type);
    }
  } catch (error) {
    Logger.error(remote, "Error parsing message", error);
  }
};

websockerServer.on("connection", (ws, request) => {
  ws.on("message", (message) => onMessage(ws, request, message));
  ws.on("error", console.error);
  ws.on("disconnect", async () => {
    if (echoHandle) await echoHandle.detach();
  });
});

websockerServer.on("listening", function () {
  Logger.info(`Websocket server is running on port: ${WSSPORT}`);
});
