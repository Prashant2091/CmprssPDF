import streamlit as st
import base64
import tempfile
import subprocess
import fitz

# Function to compress the PDF
def compress_pdf(uploaded_file, compression_factor):
    input_pdf = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    output_pdf = fitz.open()

    for page_number in range(input_pdf.page_count):
        page = input_pdf[page_number]
        page.set_dct_filter(compression_factor)
        output_pdf.insert_pdf(input_pdf, from_page=page_number, to_page=page_number)

    return output_pdf

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display the original file size
    st.write(f"Original File Size: {round(len(uploaded_file.read()) / 1024, 2)} KB")

    # Compression factor
    compression_factor = st.slider("Select Compression Factor:", min_value=1, max_value=10, step=1, value=2)

    if st.button("Compress PDF"):
        # Compress the PDF
        compressed_pdf = compress_pdf(uploaded_file, compression_factor)

        # Save the compressed PDF to a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        with open(temp_file.name, 'wb') as f:
            compressed_pdf.save(f)

        # Display the compressed file size
        st.write(f"Compressed File Size: {round(temp_file.stat().st_size / 1024, 2)} KB")

        # Download the compressed PDF
        with open(temp_file.name, "rb") as f:
            data = f.read()
        st.download_button(label="Download Compressed PDF", data=data, file_name="compressed_pdf.pdf")





