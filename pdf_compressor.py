import streamlit as st
import PyPDF2
import io
from reportlab.pdfgen import canvas

# Function to compress the PDF
def compress_pdf(input_file, compression_factor):
    output_file = io.BytesIO()

    with input_file as file:
        reader = PyPDF2.PdfFileReader(file)
        writer = PyPDF2.PdfFileWriter()

        for page_num in range(reader.getNumPages()):
            page = reader.getPage(page_num)
            compressed_page = io.BytesIO()
            c = canvas.Canvas(compressed_page)
            c.setPageSize((page.mediaBox.getWidth() / compression_factor, page.mediaBox.getHeight() / compression_factor))
            c.doFormXObject(PyPDF2.pdf.ContentStream(page.getContents(), page.pdf))
            c.save()
            compressed_page.seek(0)
            compressed_pdf_page = PyPDF2.PdfFileReader(compressed_page)
            writer.addPage(compressed_pdf_page.getPage(0))

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
    compression_factor = st.slider("Select Compression Factor", min_value=1, max_value=10, value=4)

    # Compress the PDF and get the compressed file
    compressed_file = compress_pdf(uploaded_file, compression_factor)

    st.write("Download Compressed PDF")
    st.download_button("Click here to download", data=compressed_file, file_name="compressed_pdf.pdf")

    st.write("Compressed File Size:", round(len(compressed_file.read()) / 1024, 2), "KB")
