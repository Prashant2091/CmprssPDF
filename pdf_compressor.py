import streamlit as st
from PyPDF2 import PdfReader, PdfWriter

# Function to compress the PDF
def compress_pdf(uploaded_file, compression_factor):
    pdf_reader = PdfReader(uploaded_file)
    pdf_writer = PdfWriter()

    for page in pdf_reader.pages:
        page.compressContentStreams(compression_factor)
        pdf_writer.add_page(page)

    output_buffer = st._upload_file_manager._get_encoded_file_contents(pdf_writer)
    return output_buffer

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display the original file size
    st.write(f"Original File Size: {round(len(uploaded_file.read()) / 1024, 2)} KB")

    # Compression factor (this will affect image quality)
    compression_factor = st.slider("Select Compression Factor:", min_value=1, max_value=10, step=1, value=2)

    if st.button("Compress PDF"):
        # Compress the PDF
        compressed_pdf = compress_pdf(uploaded_file, compression_factor)

        # Display the compressed file size
        st.write(f"Compressed File Size: {round(len(compressed_pdf) / 1024, 2)} KB")

        # Download the compressed PDF
        st.download_button(label="Download Compressed PDF", data=compressed_pdf, file_name="compressed_pdf.pdf")
