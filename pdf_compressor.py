import streamlit as st
import PyPDF2
from io import BytesIO

# Function to compress the PDF
def compress_pdf(input_file):
    pdf_reader = PyPDF2.PdfFileReader(input_file)
    pdf_writer = PyPDF2.PdfFileWriter()

    for page_number in range(pdf_reader.getNumPages()):
        page = pdf_reader.getPage(page_number)
        pdf_writer.addPage(page)

    compressed_pdf = BytesIO()
    pdf_writer.write(compressed_pdf)
    return compressed_pdf

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display original file size
    st.write(f"Original File Size: {uploaded_file.size / 1024:.2f} KB")

    # Compress the PDF
    compressed_pdf = compress_pdf(uploaded_file)

    # Display compressed file size and provide download link
    compressed_size = len(compressed_pdf.getvalue())
    st.write(f"Compressed File Size: {compressed_size / 1024:.2f} KB")
    href = f"data:application/pdf;base64,{base64.b64encode(compressed_pdf.getvalue()).decode()}"
    st.markdown(f'<a href="{href}" download="compressed.pdf">Download Compressed PDF</a>', unsafe_allow_html=True)
