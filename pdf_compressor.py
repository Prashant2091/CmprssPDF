import streamlit as st
import PyPDF2

# Function to compress the PDF
def compress_pdf(input_file, output_file, compression_factor):
    reader = PyPDF2.PdfFileReader(input_file)
    writer = PyPDF2.PdfFileWriter()

    for page_num in range(reader.numPages):
        page = reader.getPage(page_num)
        page.compressContentStreams(compression_factor)
        writer.addPage(page)

    with open(output_file, "wb") as f:
        writer.write(f)

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display original file size
    st.write(f"Original File Size: {uploaded_file.size / 1024:.2f} KB")

    # Set the compression factor (you can adjust this value as needed)
    compression_factor = 0.5

    # Compress the PDF
    compressed_file = f"{uploaded_file.name.split('.')[0]}_compressed.pdf"
    compress_pdf(uploaded_file, compressed_file, compression_factor)

    # Display compressed file size and provide download link
    st.write(f"Compressed File Size: {st.file_uploader(compressed_file).size / 1024:.2f} KB")
    st.download_button(label="Download Compressed PDF", data=open(compressed_file, 'rb').read(), file_name=compressed_file)
