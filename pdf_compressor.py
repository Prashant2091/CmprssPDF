import streamlit as st
import PyPDF2
from io import BytesIO

def compress_pdf(input_file):
    # Create a BytesIO buffer to hold the compressed PDF
    output_buffer = BytesIO()

    # Read the input PDF using PyPDF2
    reader = PyPDF2.PdfFileReader(input_file)

    # Create a new PDF writer without compression
    writer = PyPDF2.PdfFileWriter()

    # Copy the pages from the original PDF to the new writer
    for page_num in range(reader.numPages):
        page = reader.getPage(page_num)
        writer.addPage(page)

    # Write the new PDF to the buffer
    writer.write(output_buffer)
    output_buffer.seek(0)

    return output_buffer

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display original file size
    st.write(f"Original File Size: {uploaded_file.size / 1024:.2f} KB")

    # Compress the PDF
    compressed_pdf = compress_pdf(uploaded_file)

    # Display compressed file size and provide download link
    compressed_size = len(compressed_pdf.getvalue())
    st.write(f"Compressed File Size: {compressed_size / 1024:.2f} KB")
    st.download_button(label="Download Compressed PDF", data=compressed_pdf.getvalue(), file_name="compressed.pdf")
