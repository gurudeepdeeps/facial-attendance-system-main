import subprocess
import time
import os
import gradio as gr

# Start the Flask app in a background process
print("Starting Flask application...")
port = os.environ.get("PORT", "7860")

# Run Flask on port 8000 internally
subprocess.Popen(["python", "flask_app.py"], env=dict(os.environ, PORT="8000"))

# Give Flask 3 seconds to start up
time.sleep(3)

# Define a simple Gradio interface that acts as an iframe viewer to your Flask app
def load_app():
    # Gradio will load our Flask app running on port 8000 inside the frame
    return '<iframe src="http://127.0.0.1:8000" style="width:100%; height:800px; border:none;"></iframe>'

with gr.Blocks() as demo:
    gr.HTML(value=load_app())

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(port))
