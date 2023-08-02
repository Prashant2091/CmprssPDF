import streamlit as st
import fitz  # PyMuPDF
from io import BytesIO

def compress_pdf(input_file):
    # Create a BytesIO buffer to hold the compressed PDF
    output_buffer = BytesIO()

    # Read the input PDF using PyMuPDF
    pdf_document = fitz.open(stream=input_file.read(), filetype="pdf")

    # Create a new PDF document without compression
    pdf_writer = fitz.open()

    # Copy the pages from the original PDF to the new writer
    for page_number in range(pdf_document.page_count):
        page = pdf_document.load_page(page_number)
        pdf_writer.insert_pdf(pdf_document, from_page=page_number, to_page=page_number)

    # Save the compressed PDF to the buffer
    pdf_writer.save(output_buffer)
    pdf_writer.close()
    pdf_document.close()

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
