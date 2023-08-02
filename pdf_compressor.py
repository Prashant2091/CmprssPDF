import streamlit as st
import PyPDF2
from io import BytesIO

# Function to compress the PDF
def compress_pdf(input_file):
    reader = PyPDF2.PdfFileReader(input_file)
    writer = PyPDF2.PdfFileWriter()

    for page_num in range(reader.numPages):
        page = reader.getPage(page_num)
        page.compressContentStreams()
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

    # Compress the PDF
    compressed_pdf = compress_pdf(uploaded_file)

    # Display compressed file size
    compressed_size = len(compressed_pdf.getvalue())
    st.write(f"Compressed File Size: {compressed_size / 1024:.2f} KB")

    # Provide download link for the compressed PDF
    st.markdown(f'<a href="data:application/pdf;base64,{compressed_pdf.getvalue().decode("base64")}" download="compressed.pdf">Download Compressed PDF</a>', unsafe_allow_html=True)
