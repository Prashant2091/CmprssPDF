import streamlit as st
import PyPDF2
import base64
from io import BytesIO

# Function to compress the PDF
def compress_pdf(uploaded_file, compression_factor):
    input_pdf = PyPDF2.PdfFileReader(uploaded_file)

    # Create a new PDF with compression settings
    output_pdf = PyPDF2.PdfFileWriter()
    for page_number in range(input_pdf.getNumPages()):
        page = input_pdf.getPage(page_number)
        page.compressContentStreams()
        page.scaleBy(compression_factor)
        output_pdf.addPage(page)

    return output_pdf

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

# Compression factor slider
compression_factor = st.slider("Compression Factor", min_value=0.01, max_value=0.1, step=0.01, value=0.05)

if uploaded_file is not None:
    # Display the uploaded file
    original_size_kb = round(uploaded_file.size / 1024, 2)
    st.write(f"Original File Size: {original_size_kb} KB")

    # Compress the PDF
    compressed_pdf = compress_pdf(uploaded_file, compression_factor)

    # Save the compressed PDF to a buffer
    output_buffer = BytesIO()
    compressed_pdf.write(output_buffer)

    # Convert buffer to base64
    encoded_pdf = base64.b64encode(output_buffer.getvalue()).decode()

    # Download link to download the compressed PDF
    st.markdown(f'<a href="data:application/pdf;base64,{encoded_pdf}" download="compressed_pdf.pdf">Download Compressed PDF</a>', unsafe_allow_html=True)

    # Display the compressed file size
    compressed_size_kb = round(len(output_buffer.getvalue()) / 1024, 2)
    st.write(f"Compressed File Size: {compressed_size_kb} KB")
