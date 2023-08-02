# Use the official Python base image
FROM python:3.9

# Set working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your Streamlit app code into the container
COPY pdf_compressor.py.

# Expose the Streamlit port
EXPOSE 8501

# Set the entry point to run your Streamlit app
CMD ["streamlit", "run", "pdf_compressor.py"]
