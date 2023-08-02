import streamlit as st
import PyPDF2
from io import BytesIO

# Function to compress the PDF
def compress_pdf(input_file, compression_factor):
    reader = PyPDF2.PdfFileReader(input_file)
    writer = PyPDF2.PdfFileWriter()

    for page_num in range(reader.numPages):
        page = reader.getPage(page_num)
        writer.addPage(compress_page(page, compression_factor))

    output_buffer = BytesIO()
    writer.write(output_buffer)
    return output_buffer

# Function to compress a single page
def compress_page(page, compression_factor):
    xObject = page['/Resources']['/XObject'].get_object()
    for obj in xObject:
        if xObject[obj]['/Subtype'] == '/Image':
            size = (xObject[obj]['/Width'], xObject[obj]['/Height'])
            data = xObject[obj].get_object()['/Filter']
            if data == '/FlateDecode':
                image = xObject[obj].get_object()
                image_data = image.get_data()
                image_stream = BytesIO(image_data)
                img = PyPDF2.PdfImageXObject(image_stream)
                img.compress(compression_factor)
                xObject[obj] = img
    return page

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display original file size
    st.write(f"Original File Size: {uploaded_file.size / 1024:.2f} KB")

    # Compress the PDF
    compression_factor = st.slider("Select Compression Factor", min_value=0.0, max_value=1.0, value=0.5, step=0.1)
    compressed_pdf = compress_pdf(uploaded_file, compression_factor)

    # Display compressed file size and provide download link
    compressed_size = len(compressed_pdf.getvalue())
    st.write(f"Compressed File Size: {compressed_size / 1024:.2f} KB")
    st.download_as_file(compressed_pdf, "compressed.pdf", "Download Compressed PDF")
