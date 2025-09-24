import React, { useEffect, useCallback } from "react";
import { Button, Typography, Checkbox } from "antd";
import "./App.css";

// WebRTC Configuration matching peer-to-peer code
const BITRATE = 15_000_000; // 15 Mbps

const config = {
  video: {
    width: 1920,
    height: 1080,
    frameRate: 30,
    bitrate: BITRATE,
    scaleResolutionDownBy: 1.0,
  },
  rtc: {
    iceServers: [],
    iceTransportPolicy: 'all',
    iceCandidatePoolSize: 0,
    bundlePolicy: 'max-bundle',
    rtcpMuxPolicy: 'require',
  },
  stream: { captureFrameRate: 30 },
  preferredCodec: 'VP8',
};

// LD: A good web SWE would be able to integrate these variables into the React lifecycle.
// I am not a good web SWE.
let localStream = undefined; // The local video stream from the user's camera.
let localPeerConnection = undefined; // The WebRTC peer connection with the other client.

// Recording variables
let mediaRecorder;
let recordedChunks = [];

// Logging utility that adds the current timestamp to the log message.
const log = (message) => {
  console.log(`${new Date().toISOString()} - ${message}`);
};

function App() {
  const [connectButtonDisabled, setConnectButtonDisabled] =
    React.useState(false);
  const [recordButtonText, setRecordButtonText] = React.useState("Start Recording");
  const [isRecording, setIsRecording] = React.useState(false);
  const [enableJanusRecording, setEnableJanusRecording] = React.useState(false);
  const [isJanusRecordingActive, setIsJanusRecordingActive] = React.useState(false);

  // This function sets up a local video file stream instead of webcam
  const setupLocalStream = async () => {
    return new Promise((resolve, reject) => {
      try {
        const localPlayer = document.getElementById("localPlayer");

        // Set up video file source
        localPlayer.src = "/sample-video.mp4";
        localPlayer.muted = true;
        localPlayer.loop = true;
        localPlayer.controls = true;
        localPlayer.playsInline = true;

        const onVideoReady = () => {
          // Ensure video is playing before capturing stream
          if (localPlayer.paused) {
            localPlayer.play();
          }

          // Capture stream from video element
          const frameRate = config.stream.captureFrameRate;
          if (localPlayer.captureStream) {
            localStream = localPlayer.captureStream(frameRate);
          } else if (localPlayer.mozCaptureStream) {
            localStream = localPlayer.mozCaptureStream(frameRate);
          } else {
            console.error("captureStream() not supported");
            reject(new Error("captureStream() not supported"));
            return;
          }

          log("Local video file stream set up");
          resolve();
        };

        // Add event listeners
        localPlayer.addEventListener('loadedmetadata', () => {
          log("Video metadata loaded");
        });

        localPlayer.addEventListener('canplay', () => {
          log("Video can play");
        });

        localPlayer.addEventListener('playing', onVideoReady, { once: true });

        // Handle load errors
        localPlayer.addEventListener('error', (e) => {
          console.error("Video load error:", e);
          reject(new Error("Failed to load video file"));
        });

        // Start loading the video
        localPlayer.load();

      } catch (error) {
        console.error("Error setting up local video stream:", error);
        reject(error);
      }
    });
  };

  const ws = React.useRef(null);

  // Utility to send stringified messages to the WebSocket server.
  const sendWsMessage = (type, body) => {
    log(`Sending ${type} event to signalling server`);
    ws.current.send(JSON.stringify({ type, body }));
  };

  // This function is called when the "Connect" button is clicked.
  const startConnection = async () => {
    console.log("startConnection() called, enableJanusRecording:", enableJanusRecording);
    await setupLocalStream();
    sendWsMessage("start");
  };

  // State to track if we're waiting to disconnect after recording
  const [pendingDisconnect, setPendingDisconnect] = React.useState(false);
  const [disconnectTimeout, setDisconnectTimeout] = React.useState(null);

  // Disconnect function
  const disconnect = () => {
    console.log("disconnect() called, isJanusRecordingActive:", isJanusRecordingActive);
    console.log("WebSocket state:", ws.current?.readyState);

    // Always stop Janus recording if it was enabled, regardless of state
    if (enableJanusRecording && ws.current && ws.current.readyState === WebSocket.OPEN) {
      console.log("Setting pendingDisconnect to true");
      setPendingDisconnect(true);
      sendWsMessage("record-control", { action: "stop" });
      log("Stopping Janus recording before disconnect...");

      // Set a timeout to force disconnect if no response within 10 seconds
      const timeoutId = setTimeout(() => {
        console.log("Timeout waiting for recording stop, forcing disconnect");
        log("Recording stop timeout - forcing disconnect");
        performDisconnect();
      }, 10000);
      setDisconnectTimeout(timeoutId);
      return;
    }

    console.log("No recording to stop, disconnecting immediately");
    // No recording to stop, disconnect immediately
    performDisconnect();
  };

  const performDisconnect = () => {
    // Clear any pending disconnect timeout
    if (disconnectTimeout) {
      clearTimeout(disconnectTimeout);
      setDisconnectTimeout(null);
    }

    // Close WebRTC connection
    if (localPeerConnection) {
      localPeerConnection.close();
      localPeerConnection = null;
    }

    // Reset UI state (but keep enableJanusRecording and isJanusRecordingActive state)
    setConnectButtonDisabled(false);
    setPendingDisconnect(false);
    setIsJanusRecordingActive(false);

    // Clear video streams
    const remotePlayer = document.getElementById("peerPlayer");
    if (remotePlayer) {
      remotePlayer.srcObject = null;
    }

    log("Disconnected from Janus");
  };

  const trickle = useCallback((candidate) => {
    const trickleData = candidate ? { candidate } : {};
    const trickleEvent = candidate ? "trickle" : "trickle-complete";

    sendWsMessage(trickleEvent, trickleData);
  }, []);

  // Function to set codec preferences (from peer-to-peer code)
  const setCodecPreferences = (peerConnection, preferredCodec) => {
    if (!preferredCodec || !RTCRtpSender.getCapabilities) {
      console.log('No codec preference set or getCapabilities not supported');
      return;
    }

    try {
      const capabilities = RTCRtpSender.getCapabilities('video');
      if (!capabilities || !capabilities.codecs) {
        console.log('No video capabilities available');
        return;
      }

      // Filter out non-video codecs
      const videoCodecs = capabilities.codecs.filter((codec) => {
        return !['video/red', 'video/ulpfec', 'video/rtx'].includes(codec.mimeType);
      });

      // Find the preferred codec
      const preferredCodecIndex = videoCodecs.findIndex((codec) =>
        codec.mimeType.toLowerCase().includes(preferredCodec.toLowerCase())
      );

      if (preferredCodecIndex !== -1) {
        // Move preferred codec to the front
        const selectedCodec = videoCodecs[preferredCodecIndex];
        videoCodecs.splice(preferredCodecIndex, 1);
        videoCodecs.unshift(selectedCodec);

        // Apply codec preferences to all video transceivers
        const transceivers = peerConnection.getTransceivers();
        transceivers.forEach((transceiver) => {
          if (
            transceiver.receiver &&
            transceiver.receiver.track &&
            transceiver.receiver.track.kind === 'video'
          ) {
            transceiver.setCodecPreferences(videoCodecs);
          }
        });

        console.log('Codec preferences set, preferred:', selectedCodec.mimeType);
      } else {
        console.log('Preferred codec not found:', preferredCodec);
      }
    } catch (error) {
      console.error('Error setting codec preferences:', error);
    }
  };

  // This sets up the peer connection and sends the offer message to the server.
  const sendOffer = useCallback(async () => {
    // If we already have an active peer connection, don't create a new one
    if (localPeerConnection && localPeerConnection.connectionState !== 'closed' && localPeerConnection.connectionState !== 'failed') {
      console.log("Peer connection already exists and is active, reusing existing connection");
      return;
    }

    // Use the WebRTC API to setup a new peer connection with high-quality settings
    localPeerConnection = new RTCPeerConnection(config.rtc);

    // As soon as a track is added to the peer connection, we show it as a video in the DOM.
    localPeerConnection.ontrack = addRemoteStreamToDom;

    // When the peer connection generates an ICE candidate, we immediately send it to the server using ICE trickling.
    localPeerConnection.onicecandidate = (event) => trickle(event.candidate);

    // Add tracks with high-quality encoding parameters
    const videoTracks = localStream.getVideoTracks();
    if (videoTracks.length > 0) {
      videoTracks[0].contentHint = 'detail';
      const sender = localPeerConnection.addTrack(videoTracks[0], localStream);

      // Set encoding parameters for maximum quality
      const params = sender.getParameters();
      if (!params.encodings) params.encodings = [{}];

      params.encodings[0].maxBitrate = config.video.bitrate;
      params.encodings[0].maxFramerate = config.video.frameRate;
      params.encodings[0].scaleResolutionDownBy = config.video.scaleResolutionDownBy;
      params.encodings[0].priority = 'high';
      params.encodings[0].networkPriority = 'high';
      params.degradationPreference = 'maintain-framerate';

      await sender.setParameters(params);
      console.log('High-quality encoder parameters set:', params.encodings[0]);
    }

    // Set codec preferences before creating offer
    if (config.preferredCodec) {
      setCodecPreferences(localPeerConnection, config.preferredCodec);
    }

    // Generate the offer to send to the signalling server.
    const offer = await localPeerConnection.createOffer();
    await localPeerConnection.setLocalDescription(offer);

    console.log("Sending offer with record:", enableJanusRecording);
    sendWsMessage("offer", {
      audio: false,
      video: true,
      record: enableJanusRecording, // Enable recording based on checkbox
      bitrate: config.video.bitrate, // Use configured bitrate (15 Mbps)
      offer,
    });

    setConnectButtonDisabled(true);
  }, [trickle, enableJanusRecording]);

  const addRemoteStreamToDom = (event) => {
    log(`My peer has added a track. Adding to DOM.`);
    const remotePlayer = document.getElementById("peerPlayer");
    remotePlayer.srcObject = event.streams[0];
  };

  // Recording functions from peer-to-peer code
  const startRecording = () => {
    const remotePlayer = document.getElementById("peerPlayer");
    const localPlayer = document.getElementById("localPlayer");

    if (!remotePlayer.srcObject) {
      alert('No video stream available. Please connect first.');
      return;
    }

    console.log('Starting recording at current video position...');

    recordedChunks = [];

    try {
      const stream = remotePlayer.captureStream();
      const extension = 'webm';

      // Try to find the best quality codec - VP8 to match WebRTC
      let mimeType = 'video/webm; codecs=vp8';

      console.log(`MediaRecorder codec: ${mimeType}`);

      mediaRecorder = new MediaRecorder(stream, {
        mimeType,
        videoBitsPerSecond: BITRATE, // Use same bitrate as WebRTC
      });
      mediaRecorder._extension = extension;

      mediaRecorder.ondataavailable = function (event) {
        if (event.data.size > 0) {
          recordedChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = function () {
        const mimeType = mediaRecorder.mimeType || 'video/webm';
        const extension = mediaRecorder._extension || 'webm';
        const blob = new Blob(recordedChunks, { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'media-rec-' + new Date().getTime() + '.' + extension;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        console.log('Recording saved as .' + extension);
      };

      mediaRecorder.start();
      setRecordButtonText("Stop Recording");
      setIsRecording(true);
      console.log('Recording started');

      // Add event listener to stop recording when video ends
      localPlayer.addEventListener('ended', stopRecording, {
        once: true,
      });
    } catch (error) {
      console.error('Error starting recording:', error);
      alert('Failed to start recording: ' + error.message);
    }
  };

  const stopRecording = () => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
      setRecordButtonText("Start Recording");
      setIsRecording(false);

      // Remove the 'ended' event listener in case recording was stopped manually
      const localPlayer = document.getElementById("localPlayer");
      localPlayer.removeEventListener('ended', stopRecording);

      console.log('Recording stopped');
    }
  };

  const handleRecordClick = () => {
    if (recordButtonText === "Start Recording") {
      startRecording();
    } else {
      stopRecording();
    }
  };


  // Set up the WebSocket connection with the signalling server.
  // This is only used to send and receive SDP messages, which are
  // the offers and answers that are used to establish the WebRTC connection.
  useEffect(() => {
    log("Setting up WebSocket connection");
    const url = "ws://localhost:8090";
    const wsClient = new WebSocket(url);
    ws.current = wsClient;

    wsClient.onopen = () => {
      log(`WebSocket connected to signalling server at ${url}`);
    };
  }, []);

  useEffect(() => {
    ws.current.onmessage = (event) => {
      const { type, body } = JSON.parse(event.data);
      switch (type) {
        case "ready":
          log("ready event received from signalling server");
          sendOffer();
          break;
        case "answer":
          log("answer event received from signalling server");
          localPeerConnection?.setRemoteDescription(body);

          // Update recording status if Janus recording was enabled
          if (enableJanusRecording) {
            console.log("Setting isJanusRecordingActive to true");
            setIsJanusRecordingActive(true);
            log("Janus recording active in session");
          }
          break;
        case "record-started":
          log(`Janus recording started: ${body.filename}`);
          break;
        case "record-stopped":
          console.log("record-stopped received, body:", body);

          // Reset recording state
          setIsJanusRecordingActive(false);

          if (body.error) {
            console.error("Recording stop error:", body.error, body.details || "");
            log(`Recording stop failed: ${body.error}`);

            // Show error details if available
            if (body.details) {
              console.error("Error details:", body.details);
            }
            if (body.searchedFor) {
              console.error("Searched for file:", body.searchedFor);
            }
          } else {
            log("Janus recording stopped successfully");
          }

          console.log("Checking for fileData:", !!body.fileData, "filename:", body.filename);
          if (body.fileData && body.filename) {
            console.log("Starting .mjr file download process");
            // Automatically download the .mjr file
            try {
              const binaryString = atob(body.fileData);
              console.log("Base64 decoded, binary length:", binaryString.length);
              const bytes = new Uint8Array(binaryString.length);
              for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
              }
              const blob = new Blob([bytes], { type: 'application/octet-stream' });
              console.log("Blob created, size:", blob.size);
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = body.filename;
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
              console.log("Download initiated for:", body.filename);
              log(`Downloaded Janus recording: ${body.filename}`);
            } catch (error) {
              console.error('Error downloading .mjr file:', error);
              log(`Download failed: ${error.message}`);
            }
          } else if (!body.error) {
            console.log("No fileData or filename in response, but no error reported");
            log("Recording stopped but no file available");
          }

          // If we were waiting to disconnect after recording, do it now
          console.log("Checking pendingDisconnect:", pendingDisconnect);
          if (pendingDisconnect) {
            // Clear the timeout since we got a response
            if (disconnectTimeout) {
              clearTimeout(disconnectTimeout);
              setDisconnectTimeout(null);
            }

            console.log("Will disconnect in 1 second");
            setTimeout(() => {
              console.log("Performing delayed disconnect");
              performDisconnect();
            }, 1000); // Small delay to ensure download starts
          }
          break;
        default:
          console.error("Unknown message type", type, body);
      }
    };
  }, [sendOffer, enableJanusRecording, pendingDisconnect]);

  return (
    <div className="App">
      <div className="App-header">
        <Typography.Title>WebRTC</Typography.Title>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
          <Checkbox
            checked={enableJanusRecording}
            onChange={(e) => {
              console.log("Janus recording checkbox changed:", e.target.checked);
              setEnableJanusRecording(e.target.checked);
            }}
            disabled={connectButtonDisabled}
            style={{ fontSize: 16 }}
          >
            Enable Janus Recording (server-side)
          </Checkbox>

          <div className="wrapper-row">
            {!connectButtonDisabled ? (
              <Button
                style={{ width: 200, marginRight: 8 }}
                type="primary"
                onClick={startConnection}
              >
                Connect
              </Button>
            ) : (
              <Button
                style={{ width: 200, marginRight: 8 }}
                type="default"
                onClick={disconnect}
              >
                Disconnect
              </Button>
            )}
            <Button
              style={{
                width: 200,
                marginLeft: 4,
                marginRight: 4,
                backgroundColor: isRecording ? '#ff4d4f' : undefined,
                borderColor: isRecording ? '#ff4d4f' : undefined,
                color: isRecording ? 'white' : undefined
              }}
              type="primary"
              onClick={handleRecordClick}
            >
              {recordButtonText}
            </Button>
          </div>
        </div>
        <div className="playerContainer" id="playerContainer">
          <div>
            <h1 style={{ color: "#003eb3", marginBottom: 10 }}>You</h1>
            <video
              id="localPlayer"
              autoPlay
              muted
              loop
              controls
              playsInline
              preload="auto"
              style={{
                width: 1920,
                height: 1080,
                border: "5px solid #003eb3",
                borderRadius: 5,
                backgroundColor: "#003eb3",
                marginBottom: 20,
              }}
            />
          </div>

          <div>
            <h1 style={{ color: "#ad2102", marginBottom: 10 }}>Them</h1>
            <video
              id="peerPlayer"
              autoPlay
              style={{
                width: 1920,
                height: 1080,
                border: "5px solid #ad2102",
                borderRadius: 5,
                backgroundColor: "#ad2102",
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
export default App;
