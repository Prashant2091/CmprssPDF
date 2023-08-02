import streamlit as st
import PyPDF2
import base64
from io import BytesIO

# Function to compress the PDF
def compress_pdf(input_file, compression_factor):
    output_buffer = BytesIO()

    reader = PyPDF2.PdfFileReader(input_file)
    writer = PyPDF2.PdfFileWriter()

    for page_num in range(reader.numPages):
        page = reader.getPage(page_num)

        # Reduce image resolution by a factor to achieve higher compression
        page.scaleBy(compression_factor)
        writer.addPage(page)

    writer.write(output_buffer)
    return output_buffer

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display original file size
    st.write(f"Original File Size: {uploaded_file.size / 1024:.2f} KB")

    # Define the compression factor (adjust as needed, smaller values result in higher compression)
    compression_factor = 0.7

    # Compress the PDF
    compressed_pdf = compress_pdf(uploaded_file, compression_factor)

    # Display compressed file size
    compressed_size = len(compressed_pdf.getvalue())
    st.write(f"Compressed File Size: {compressed_size / 1024:.2f} KB")

    # Encode the compressed PDF bytes to base64
    encoded_pdf = base64.b64encode(compressed_pdf.getvalue()).decode()

    # Provide download link for the compressed PDF
    st.markdown(f'<a href="data:application/pdf;base64,{encoded_pdf}" download="compressed.pdf">Download Compressed PDF</a>', unsafe_allow_html=True)
