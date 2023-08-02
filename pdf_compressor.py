import streamlit as st
from PyPDF2 import PdfReader, PdfWriter
import base64
from io import BytesIO

# Function to compress the PDF
def compress_pdf(uploaded_file, compression_factor):
    pdf_reader = PdfReader(uploaded_file)
    output_buffer = BytesIO()

    pdf_writer = PdfWriter()
    for page in pdf_reader.pages:
        pdf_writer.add_page(page)
        if "/XObject" in page:
            for obj in page["/XObject"]:
                if page["/XObject"][obj]["/Subtype"] == "/Image":
                    img = page["/XObject"][obj]
                    img._data = img._data.encode('zip')
                    img._data = img._data.decode()
                    page["/XObject"][obj] = img

    pdf_writer.write(output_buffer)

    return output_buffer

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

# Compression factor slider
compression_factor = st.slider("Compression Factor", min_value=10, max_value=100, step=10, value=50)

if uploaded_file is not None:
    # Display the original file size
    original_size_kb = round(uploaded_file.size / 1024, 2)
    st.write(f"Original File Size: {original_size_kb} KB")

    # Compress the PDF
    compressed_buffer = compress_pdf(uploaded_file, compression_factor)

    # Convert buffer to base64
    encoded_pdf = base64.b64encode(compressed_buffer.getvalue()).decode()

    # Download link to download the compressed PDF
    st.markdown(f'<a href="data:application/pdf;base64,{encoded_pdf}" download="compressed_pdf.pdf">Download Compressed PDF</a>', unsafe_allow_html=True)

    # Display the compressed file size
    compressed_size_kb = round(len(compressed_buffer.getvalue()) / 1024, 2)
    st.write(f"Compressed File Size: {compressed_size_kb} KB")
