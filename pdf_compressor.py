import streamlit as st
import PyPDF2
from io import BytesIO
import base64

# Function to compress the PDF
def compress_pdf(input_file, compression_factor):
    pdf_reader = PyPDF2.PdfFileReader(input_file)
    writer = PyPDF2.PdfFileWriter()
    writer.cloneDocumentFromReader(pdf_reader)

    # Set compression factor for all pages
    for page_num in range(pdf_reader.getNumPages()):
        page = writer.getPage(page_num)
        page.compressContentStreams()

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

    # Display compressed file size
    compressed_size = len(compressed_pdf.getvalue())
    st.write(f"Compressed File Size: {compressed_size / 1024:.2f} KB")

    # Provide download link for the compressed PDF
    href = f"data:application/pdf;base64,{base64.b64encode(compressed_pdf.getvalue()).decode()}"
    st.markdown(f'<a href="{href}" download="compressed.pdf">Download Compressed PDF</a>', unsafe_allow_html=True)
