import streamlit as st
import base64
import tempfile
import PyPDF2

# Function to compress the PDF
def compress_pdf(uploaded_file, compression_factor):
    pdf_reader = PyPDF2.PdfFileReader(uploaded_file)
    pdf_writer = PyPDF2.PdfFileWriter()

    for page_number in range(pdf_reader.getNumPages()):
        page = pdf_reader.getPage(page_number)
        page.compressContentStreams(compression_factor)
        pdf_writer.addPage(page)

    return pdf_writer

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
            compressed_pdf.write(f)

        # Display the compressed file size
        st.write(f"Compressed File Size: {round(temp_file.stat().st_size / 1024, 2)} KB")

        # Download the compressed PDF
        with open(temp_file.name, "rb") as f:
            data = f.read()
        st.download_button(label="Download Compressed PDF", data=data, file_name="compressed_pdf.pdf")
