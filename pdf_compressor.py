import streamlit as st
import PyPDF2
from io import BytesIO

# Function to compress the PDF
def compress_pdf(input_file, compression_factor):
    pdf_reader = PyPDF2.PdfFileReader(input_file)
    pdf_writer = PyPDF2.PdfFileWriter()

    for page_num in range(pdf_reader.numPages):
        page = pdf_reader.getPage(page_num)
        compressed_page = compress_page(page, compression_factor)
        pdf_writer.addPage(compressed_page)

    output_buffer = BytesIO()
    pdf_writer.write(output_buffer)
    return output_buffer

def compress_page(page, compression_factor):
    xObject = page['/Resources']['/XObject']
    if isinstance(xObject, PyPDF2.generic.IndirectObject):
        xObject = xObject.get_object()
    for obj in xObject:
        if xObject[obj]['/Subtype'] == '/Image':
            if '/Filter' in xObject[obj]:
                del xObject[obj]['/Filter']
            if '/F' in xObject[obj]:
                del xObject[obj]['/F']
            xObject[obj].compress()

    return page

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display original file size
    st.write(f"Original File Size: {uploaded_file.size / 1024:.2f} KB")

    # Compression factor (adjust as needed)
    compression_factor = 0.7

    # Compress the PDF
    compressed_pdf = compress_pdf(uploaded_file, compression_factor)

    # Display compressed file size and provide download link
    compressed_size = len(compressed_pdf.getvalue())
    st.write(f"Compressed File Size: {compressed_size / 1024:.2f} KB")
    st.write(f"Compressed File Size: {compressed_size / 1024:.2f} KB")
    # Provide download link for the compressed PDF
    href = f"data:application/pdf;base64,{base64.b64encode(compressed_pdf.getvalue()).decode()}"
    st.markdown(f'<a href="{href}" download="compressed.pdf">Download Compressed PDF</a>', unsafe_allow_html=True)
