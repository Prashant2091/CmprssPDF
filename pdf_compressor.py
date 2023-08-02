import streamlit as st
import PyPDF2
from io import BytesIO

# Function to compress a single page of the PDF
def compress_page(page, compression_factor):
    xObject = page['/Resources']['/XObject'].get_object()
    for obj in xObject:
        xObject[obj].get_object().compressContentStreams()
    return page

# Function to compress the entire PDF
def compress_pdf(input_file, compression_factor):
    pdf_reader = PyPDF2.PdfFileReader(input_file)
    writer = PyPDF2.PdfFileWriter()

    for page_num in range(pdf_reader.numPages):
        page = pdf_reader.getPage(page_num)
        writer.addPage(compress_page(page, compression_factor))

    output_buffer = BytesIO()
    writer.write(output_buffer)
    return output_buffer

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display original file size
    st.write(f"Original File Size: {uploaded_file.size / 1024:.2f} KB")

    # Compress the PDF
    compression_factor = st.slider("Compression Factor", min_value=0, max_value=9, value=1)
    compressed_pdf = compress_pdf(uploaded_file, compression_factor)

    # Display compressed file size and provide download link
    compressed_size = len(compressed_pdf.getvalue())
    st.write(f"Compressed File Size: {compressed_size / 1024:.2f} KB")
    st.download_as_file(compressed_pdf, "compressed.pdf", "Download Compressed PDF")
