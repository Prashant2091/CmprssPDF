import streamlit as st
import PyPDF2
import tempfile
import os

def compress_pdf(input_file, output_file, compression_factor):
    with open(input_file, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        writer = PyPDF2.PdfWriter()

        for page in reader.pages:
            # Reduce the resolution to reduce file size
            page.scaleBy(compression_factor)
            writer.add_page(page)

    with open(output_file, "wb") as file:
        writer.write(file)

st.title("PDF Compressor")

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display the original file size
    original_size = round(len(uploaded_file.read()) / 1024, 2)  # Convert to KB
    st.write(f"Original File Size: {original_size} KB")

    # Slider for compression factor
    compression_factor = st.slider("Select Compression Factor", min_value=0.1, max_value=1.0, step=0.1, value=0.5)

    # Save the uploaded PDF to a temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.write(uploaded_file.read())
    temp_file.close()

    # Compress the PDF file
    compressed_file = f"compressed_{uploaded_file.name}"
    compress_pdf(temp_file.name, compressed_file, compression_factor)

    # Display the compressed file size
    compressed_size = round(os.path.getsize(compressed_file) / 1024, 2)  # Convert to KB
    st.write(f"Download Compressed PDF (Compression Factor: {compression_factor:.1f})")
    st.download_button(
        label=f"Compressed File Size: {compressed_size} KB",
        data=open(compressed_file, "rb").read(),
        file_name=compressed_file,
    )

    # Remove the temporary file
    os.remove(temp_file.name)
