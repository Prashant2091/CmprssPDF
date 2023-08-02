import streamlit as st
import PyPDF2
from io import BytesIO

def compress_pdf(input_file, compression_factor):
    reader = PyPDF2.PdfFileReader(input_file)
    writer = PyPDF2.PdfFileWriter()

    for page_num in range(reader.numPages):
        page = reader.getPage(page_num)
        page.compressContentStreams(compression_factor)
        writer.addPage(page)

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

    # Set the desired compression factor (between 0 and 1)
    compression_factor = 0.3  # Adjust this value to achieve higher compression

    # Compress the PDF
    compressed_pdf = compress_pdf(uploaded_file, compression_factor)

    # Display compressed file size and provide download link
    compressed_size = len(compressed_pdf.getvalue())
    st.write(f"Compressed File Size: {compressed_size / 1024:.2f} KB")
    st.download_button(label="Download Compressed PDF", data=compressed_pdf.getvalue(), file_name="compressed.pdf")
