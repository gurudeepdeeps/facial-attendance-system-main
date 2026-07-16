FROM python:3.11-slim

# Install system dependencies needed for compilation (CMake, compilers, and X11)
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set up work directory
WORKDIR /code

# Copy requirements and install
COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy all project files
COPY . .

# Expose the default Hugging Face port (7860)
EXPOSE 7860

# Run Flask application on port 7860
CMD ["python", "app.py"]
