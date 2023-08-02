import streamlit as st
import PyPDF2
import base64
from io import BytesIO

# Function to compress the PDF
def compress_pdf(input_file, compression_factor):
    output_file = BytesIO()

    with input_file as file:
        reader = PyPDF2.PdfFileReader(file)
        writer = PyPDF2.PdfFileWriter()

        for page_num in range(reader.getNumPages()):
            page = reader.getPage(page_num)
            page.compressContentStreams(compression_factor)
            writer.addPage(page)

        writer.write(output_file)
        output_file.seek(0)

    return output_file

# Streamlit app title
st.title("PDF Compressor")

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    st.write("Original File Size:", round(uploaded_file.size / 1024, 2), "KB")

    # Compression factor slider
    compression_factor = st.slider("Select Compression Factor", min_value=0, max_value=9, value=4)

    # Compress the PDF and get the compressed file
    compressed_file = compress_pdf(uploaded_file, compression_factor)

    st.write("Download Compressed PDF")
    compressed_file_base64 = base64.b64encode(compressed_file.read()).decode("utf-8")
    st.markdown(f'<a href="data:application/pdf;base64,{compressed_file_base64}" download="compressed_pdf.pdf">Click here to download</a>', unsafe_allow_html=True)

    st.write("Compressed File Size:", round(len(compressed_file_base64) / 1024, 2), "KB")
