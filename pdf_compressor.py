import streamlit as st
import PyPDF2
from io import BytesIO

def compress_pdf(input_file, compression_factor):
    pdf_reader = PyPDF2.PdfReader(input_file)

    output_buffer = BytesIO()
    pdf_writer = PyPDF2.PdfWriter()

    for page in pdf_reader.pages:
        page.compressContentStreams()
        pdf_writer.add_page(page)

    pdf_writer.write(output_buffer)
    return output_buffer

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display original file size
    st.write(f"Original File Size: {uploaded_file.size / 1024:.2f} KB")

    # Compression factor slider
    compression_factor = st.slider("Select Compression Factor", 0, 9, 3)

    if st.button("Compress PDF"):
        # Compress the PDF
        compressed_pdf = compress_pdf(uploaded_file, compression_factor)

        # Display compressed file size and provide download link
        compressed_size = len(compressed_pdf.getvalue())
        st.write(f"Compressed File Size: {compressed_size / 1024:.2f} KB")
        st.download_button(label="Download Compressed PDF",
                           data=compressed_pdf.getvalue(),
                           file_name="compressed.pdf")
