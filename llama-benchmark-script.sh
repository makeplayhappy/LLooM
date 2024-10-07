#!/bin/bash

# Configuration variables
MODEL_DIR=/home/david/Documents/models
LLAMA_SERVER_PATH="/home/david/Documents/llama.cpp/llama-server"
LOOM_RUNALL_PATH="/home/david/Documents/LLooM/loom_runall.py"

# Timeout for server startup (in seconds)
STARTUP_TIMEOUT=40

# Function to check if the server is ready
check_server_ready() {
    local start_time=$(date +%s)
    while true; do
        if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/health | grep -q "200"; then
            echo "Server is ready"
            return 0
        fi
        
        # Check if we've exceeded the timeout
        local current_time=$(date +%s)
        if (( current_time - start_time > STARTUP_TIMEOUT )); then
            echo "Server startup timed out after $STARTUP_TIMEOUT seconds"
            return 1
        fi
        
        sleep 1
    done
}

# Function to check for common error messages in the log
check_for_errors() {
    if grep -q "CUDA out of memory" "$1" || grep -q "failed to load model" "$1"; then
        echo "Error detected: GPU memory issue or model loading failure"
        return 1
    fi
    return 0
}

# Check if the specified paths exist
if [ ! -d "$MODEL_DIR" ]; then
    echo "Error: Model directory does not exist: $MODEL_DIR"
    exit 1
fi

if [ ! -f "$LLAMA_SERVER_PATH" ]; then
    echo "Error: llama-server not found at: $LLAMA_SERVER_PATH"
    exit 1
fi

if [ ! -f "$LOOM_RUNALL_PATH" ]; then
    echo "Error: loom_runall.py not found at: $LOOM_RUNALL_PATH"
    exit 1
fi

# Loop through all GGUF files in the specified directory
for model in "$MODEL_DIR"/*.gguf; do
    if [ -f "$model" ]; then
        model_filename=$(basename "$model")
        echo "Processing model: $model_filename"
        
        # Start the llama-server in the background, redirecting output to a log file
        "$LLAMA_SERVER_PATH" --no-display-prompt --model "$model" --host 127.0.0.1 --port 5000 -ngl 99 --ctx-size 1024 > "server_${model_filename}.log" 2>&1 &
        
        # Capture the process ID
        server_pid=$!
        echo "Server started with PID: $server_pid"
        
        # Wait for the server to be ready or timeout
        if check_server_ready; then
            # Check for errors in the log
            if check_for_errors "server_${model_filename}.log"; then
                # Run the benchmarking script
                echo "Running benchmarking script..."
                LLAMA_API_URL=http://127.0.0.1:5000 python "$LOOM_RUNALL_PATH"
            else
                echo "Error detected in server log. Skipping benchmark for this model."
            fi
        else
            echo "Server failed to start properly. Skipping benchmark for this model."
        fi
        
        # Kill the llama-server process
        echo "Killing server process..."
        kill $server_pid 2>/dev/null
        
        echo "Finished processing $model_filename"
        echo "----------------------------------------"
    fi
done

echo "All models have been processed."
