import streamlit as st
import PyPDF2
from io import BytesIO
import base64

# Function to compress the PDF
def compress_pdf(input_file, compression_factor=1):
    reader = PyPDF2.PdfFileReader(input_file)
    writer = PyPDF2.PdfFileWriter()

    for page_num in range(reader.numPages):
        page = reader.getPage(page_num)
        page.compressContentStreams()  # Compress using default compression algorithm
        writer.addPage(page)

    # Increase compression by reducing image quality
    for page_num in range(writer.getNumPages()):
        page = writer.getPage(page_num)
        for obj in page['/Resources']['/XObject'].values():
            if obj['/Subtype'] == '/Image':
                obj.getObject().update({
                    PyPDF2.generic.createStringObject('/Filter'): PyPDF2.generic.createStringObject('/DCTDecode'),
                    PyPDF2.generic.createStringObject('/Q'): PyPDF2.generic.createStringObject(str(compression_factor))
                })

    output_buffer = BytesIO()
    writer.write(output_buffer)
    return output_buffer

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display original file size
    st.write(f"Original File Size: {uploaded_file.size / 1024:.2f} KB")

    # Compress the PDF with higher compression factor (e.g., 0 for maximum compression, 1 for default)
    compression_factor = 0.2  # Adjust this value for higher compression
    compressed_pdf = compress_pdf(uploaded_file, compression_factor)

    # Display compressed file size
    compressed_size = len(compressed_pdf.getvalue())
    st.write(f"Compressed File Size: {compressed_size / 1024:.2f} KB")

    # Provide a download link for the compressed PDF
    st.markdown(f'<a href="data:application/pdf;base64,{base64.b64encode(compressed_pdf.getvalue()).decode()}" download="compressed.pdf">Download Compressed PDF</a>', unsafe_allow_html=True)
